"""Edition-bound research, kept separate from recording time and legacy guides."""
import hashlib
import json
import re
from pathlib import Path, PureWindowsPath
from urllib.parse import urlparse

from analysis_data import RENDER, load_analysis
from review_library import page_count

DIMENSIONS = {'harmony', 'counterpoint', 'form', 'orchestration', 'motif'}
HARMONIC_SYSTEMS = {'functional_tonal', 'modal_pentatonic', 'quartal', 'layered_pedal'}
CLAIMS = {'score_observation', 'theoretical_analysis', 'hermeneutic_interpretation'}
PRECISIONS = {'page_range', 'score_segment', 'score_segment_candidate', 'reference_interval_candidate', 'unlocated'}
ROOT = Path(__file__).resolve().parents[1]


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def require(condition, message):
    if not condition:
        raise ValueError(message)


def integer(value):
    return isinstance(value, int) and not isinstance(value, bool)


def harmonic_fields(item):
    """Validate evidence structure, never certify the musical interpretation."""
    harmonic = item.get('harmonic_analysis')
    if harmonic is None:
        return
    require(item.get('dimension') == 'harmony' and isinstance(harmonic, dict), '和声记录须属于和声事件')
    require(harmonic.get('system') in HARMONIC_SYSTEMS, '和声体系无效')
    require(harmonic.get('pitch_basis') == 'concert', '和声合计须使用实音')
    for field in ['key_context', 'bass', 'temporal_scope', 'voice_leading', 'nonchord_tones']:
        require(isinstance(harmonic.get(field), str) and harmonic[field].strip(), '和声缺少语境、低音或声部证据')
    pitch = re.compile(r'^[A-G](?:#|b)?$')
    for field in ['pitch_collection', 'chord_tones', 'omitted_tones']:
        values = harmonic.get(field)
        require(isinstance(values, list) and all(isinstance(p, str) and pitch.fullmatch(p) for p in values)
                and len(set(values)) == len(values), '和声音名格式无效')
    require(harmonic['pitch_collection'], '和声缺少结构音集合')
    require(set(harmonic['omitted_tones']) <= set(harmonic['chord_tones'])
            and not set(harmonic['omitted_tones']) & set(harmonic['pitch_collection']), '省略音与当前音集合矛盾')
    root, roman, inversion = (harmonic.get(k) for k in ['root', 'roman_numeral', 'inversion'])
    require(root is None or isinstance(root, str) and pitch.fullmatch(root), '和声根音无效')
    require(roman is None or isinstance(roman, str) and roman.strip(), '和声级数无效')
    require(inversion in {'root','first','second','third','not_applicable','undetermined'}, '和弦转位无效')
    if harmonic['system'] == 'functional_tonal':
        tones = harmonic['chord_tones']
        index = {'root': 0, 'first': 1, 'second': 2, 'third': 3}.get(inversion)
        require(root and roman and len(tones) in {3,4} and tones[0] == root and
                index is not None and index < len(tones), '功能和声缺少根音、级数或转位依据')
        bass = re.fullmatch(r'([A-G](?:#|b)?)-?\d+', harmonic['bass'])
        require(bass and bass[1] == tones[index], '实际低音与和弦转位矛盾')
        require(set(harmonic['pitch_collection']) <= set(tones), '功能和声结构音未与和弦音区分')
    voices = harmonic.get('voices')
    require(isinstance(voices, list) and voices, '缺少乐器实音分工')
    for voice in voices:
        require(isinstance(voice, dict) and all(isinstance(voice.get(k), str) and voice[k].strip()
                for k in ['instrument','role']), '声部身份或职责无效')
        require(isinstance(voice.get('pitches'), list) and voice['pitches'] and all(
                isinstance(p, str) and re.fullmatch(r'[A-G](?:#|b)?(?:-?\d+)?', p)
                for p in voice['pitches']), '乐器实音格式无效')


def local_path(root, value):
    require(isinstance(value, str) and value, '研究文件路径无效')
    require(not Path(value).is_absolute() and not PureWindowsPath(value).drive, '研究文件须使用项目相对路径')
    path = (root / value).resolve()
    require(path.is_relative_to(root.resolve()), '研究文件路径越界')
    return path


def spans_for(item, pages, regions):
    spans = item.get('score_spans')
    require(isinstance(spans, list) and spans, '研究条目缺少谱面定位')
    for span in spans:
        require(isinstance(span, dict), '谱面定位格式无效')
        precision = span.get('precision')
        require(precision in PRECISIONS, '未知定位精度')
        require(not any(k in span for k in ['start_seconds', 'end_seconds', 'audio_seconds',
                    'audio_start_seconds', 'audio_end_seconds', 'video_seconds']),
                '作品级谱面定位不能永久绑定录音秒数')
        if precision == 'unlocated':
            require(not span.get('region_ids') and span.get('pdf_page_start') is None
                    and span.get('pdf_page_end') is None, '未定位不能携带可激活的页码或区域')
            continue
        first, last = span.get('pdf_page_start'), span.get('pdf_page_end')
        require(integer(first) and integer(last) and 1 <= first <= last <= pages, '谱页范围无效')
        ids = span.get('region_ids', [])
        require(isinstance(ids, list) and all(isinstance(i, str) and i in regions for i in ids),
                '研究条目引用未知谱面区域')
        require(all(first <= regions[i]['page_number'] <= last for i in ids), '谱面区域与页码不匹配')
        if precision == 'reference_interval_candidate':
            start,end=span.get('reference_start_tick'),span.get('reference_end_tick')
            require(all(isinstance(v,(int,float)) and not isinstance(v,bool) for v in [start,end])
                    and 0<=start<end, '参考音符窗口无效')
            require(isinstance(span.get('reference_sha256'),str) and
                    re.fullmatch(r'[a-f0-9]{64}',span['reference_sha256']), '参考音符窗口缺少源指纹')
        if precision == 'score_segment_candidate':
            require(ids, '候选区域定位必须引用实际区域')
        if precision == 'score_segment':
            start, end = span.get('score_start'), span.get('score_end')
            for point in [start, end]:
                require(isinstance(point, list) and len(point) == 3 and
                        integer(point[0]) and first <= point[0] <= last and
                        integer(point[1]) and point[1] >= 0 and
                        isinstance(point[2], (float, int)) and not isinstance(point[2], bool)
                        and 0 <= point[2] <= 10000, '谱面段落坐标无效')
            require(start < end, '谱面段落必须前闭后开且正向')


def load_research(root=ROOT, data_root=None, track_id='ravel-left-hand'):
    root = root.resolve()
    directory = (data_root or root).resolve()
    require(directory.is_relative_to(root), '研究目录越界')
    from review_library import score_directory
    shared = score_directory(root,directory)
    files = [shared / 'analysis/structural-events.json', shared / 'analysis/hermeneutic-essays.json']
    empty = {'schema_version': '1.0.0', 'available': False, 'events': [], 'essays': [], 'sources': [], 'edition': None}
    if not any(path.exists() for path in files):
        return empty
    mapping = read(directory / 'measure-map.json')
    metadata = read(directory / 'metadata/recording.json')
    pdf = local_path(root, mapping['pdf_path'])
    with pdf.open('rb') as stream:
        require(hashlib.file_digest(stream, 'sha256').hexdigest() == mapping['pdf_sha256'], '当前 PDF 内容与研究版次不匹配')
    guide = load_analysis(root, directory)
    sources = {s['source_id']: dict(s) for s in guide.get('references', [])}
    registry = shared / 'analysis/sources.json'
    if registry.exists():
        for source in read(registry)['sources']:
            require(source.get('source_id') not in sources, '研究来源标识重复')
            if source.get('path'):
                source_path = local_path(root, source['path'])
                if source.get('sha256'):
                    with source_path.open('rb') as stream:
                        require(hashlib.file_digest(stream, 'sha256').hexdigest() == source['sha256'],
                                '研究参考谱内容与指纹不匹配')
            require(all(urlparse(url).scheme in {'http', 'https'} and urlparse(url).netloc
                        for url in source.get('urls', [])), '研究来源链接无效')
            sources[source['source_id']] = source
    # Optional precomputed engine: playback does not import PDF or MIDI libraries.
    from backend.structure_analysis.store import load_bundle
    engine=None;engine_error=None
    try:
        engine = load_bundle(root,shared,mapping)
        if engine:
            require(engine['manifest']['work_id']==metadata['work']['work_id'], '分析引擎作品不匹配')
            symbolic=read(directory/'alignment.json')['symbolic_reference']
            require(engine['manifest']['sources']['midi']['sha256']==symbolic['sha256'], '分析引擎参考MIDI与播放时间轴不匹配')
    except (OSError,ValueError,KeyError,TypeError) as error:
        # Reject the invalid generated run while retaining independent essays
        # and previously curated research. Never relax fingerprint validation.
        engine=None;engine_error=str(error)
    if engine:
        sources['engine-methods-v1']={'source_id':'engine-methods-v1','title':'Ariadne 独立结构分析引擎：规则与证据',
            'kind':'project_method','reading_status':'not_applicable','urls':[],
            'reading_note':'原始PDF观测、辅助MIDI时值与候选对应分别保存；算法结果不能自行升级成人工核查。'}
    regions = {r.get('region_id', r.get('measure_id')): r for key in ['measures', 'score_regions', 'bar_regions']
               for r in mapping.get(key, [])}
    edition = None
    documents = []
    for path in files:
        if not path.exists():
            documents.append({})
            continue
        document = read(path)
        require(isinstance(document, dict), '研究文档必须为对象')
        require(document.get('schema_version') == '1.0.0', '研究数据版本不支持')
        require(document.get('work_id') == metadata['work']['work_id'], '研究作品与当前曲目不匹配')
        bound = document.get('edition', {})
        require(isinstance(bound, dict), '研究版次格式无效')
        require(bound.get('edition_id') and bound.get('pdf_sha256') == mapping['pdf_sha256'], '研究 PDF 指纹不匹配')
        require(edition is None or edition == bound, '技术事件与诠释文章版次不同')
        edition = bound
        documents.append(document)
    result = {**empty, 'available': True, 'work_id': metadata['work']['work_id'], 'edition': edition,
              'sources': list(sources.values())}
    # Score studies are independent of the automatic candidate engine and its
    # unmatched-note count. A damaged study must not hide existing essays.
    from backend.score_studies import load_studies
    try:
        study=load_studies(root,shared,mapping)
        if study:
            require(study['document']['work_id']==metadata['work']['work_id'],'谱面研究作品不匹配')
            documents[0]={**documents[0],'events':documents[0].get('events',[])+study['events']}
            result['score_study']={'path':study['path'],'policy':study['document']['research_policy'],
                'window_ids':[w['id'] for w in study['document']['windows']],
                'form':study['document']['form']}
    except (OSError,ValueError,KeyError,TypeError) as error:result['score_study_error']=str(error)
    # MusicXML is the primary full-score symbolic source. The optional older
    # MIDI/PDF candidate engine is not a prerequisite for this loader.
    from backend.musicxml_analysis.store import load_bundle as load_xml, research_events as xml_events
    try:
        xml=load_xml(root,shared,mapping)
        if xml:
            require(xml['manifest']['work_id']==metadata['work']['work_id'],'MusicXML作品不匹配')
            sources['ravel-musicxml-score']={'source_id':'ravel-musicxml-score','title':'用户提供的拉威尔完整管弦乐MusicXML',
                'kind':'score','reading_status':'key_pages_checked','urls':[],
                'reading_note':'music21全谱解析；关键谱例与PDF布局核查，逐音人工签核待完成。隐藏记谱事件隔离保留。',
                **xml['manifest']['source']}
            result['sources']=list(sources.values())
            documents[0]={**documents[0],'events':documents[0].get('events',[])+xml_events(xml,track_id)}
            result['musicxml']={'summary':xml['tables']['summary'],'source':xml['manifest']['source'],
                'measures':xml['tables']['measures']['measures'],'review_status':xml['manifest']['review_status']}
            from backend.musicxml_analysis.ravel_development import load_profile
            try:
                profile=load_profile(root,shared,xml)
                if profile:result['module_profile']=profile
            except (OSError,ValueError,KeyError,TypeError) as error:
                result['module_profile_error']=str(error)
    except (OSError,ValueError,KeyError,TypeError) as error:result['musicxml_error']=str(error)
    if engine_error:result['engine_error']=engine_error
    if engine:
        documents[0] = {**documents[0],'events':documents[0].get('events',[])+engine['events']}
        result['engine']={'run_id':engine['manifest']['run_id'],'summary':engine['summary'],
                          'reference_sha256':engine['manifest']['sources']['midi']['sha256']}
        result['reference_clock']=engine['reference_clock']
    for key, document in zip(['events', 'essays'], documents):
        items = document.get(key, [])
        require(isinstance(items, list), '研究条目必须为数组')
        seen = set()
        for item in items:
            require(isinstance(item, dict) and isinstance(item.get('id'), str)
                    and item['id'] and item['id'] not in seen, '研究条目标识无效或重复')
            seen.add(item['id'])
            require(item.get('claim_level') in CLAIMS, '认识层次无效')
            label = item.get('short_label' if key == 'events' else 'title')
            require(isinstance(label, str) and label.strip(), '研究条目缺少标题')
            if key == 'events':
                require(item.get('dimension') in DIMENSIONS, '研究维度无效')
                harmonic_fields(item)
            else:
                require(item.get('reading_mode') == 'persistent', '诠释文章必须支持独立阅读')
            spans_for(item, page_count(mapping), regions)
            verification = item.get('verification', {})
            require(all(isinstance(verification.get(k), str) and verification[k] for k in
                        ['score', 'literature', 'location', 'timing']), '缺少独立核查状态')
            allowed = {
                'score': {'verified','pending','disputed','not_applicable','key_pages_checked','agent_score_checked'},
                'literature': {'verified','pending','disputed','not_applicable','relevant_sections_checked',
                               'full_text_checked','abstract_checked','not_read'},
                'location': {'verified','pending','disputed','not_applicable',*PRECISIONS},
                'timing': {'verified','pending','disputed','not_applicable','candidate_alignment','manual_reviewed'}}
            require(all(verification[k] in allowed[k] for k in allowed), '未知核查状态')
            require(not any(k in item for k in ['confidence', 'start_seconds', 'end_seconds']),
                    '研究条目不接受虚构置信度或永久时间边界')
            if verification['score'] == 'verified' or verification['location'] == 'verified':
                require(item.get('reviewer') and item.get('reviewed_at'), '人工确认须记录审核者和时间')
            refs = item.get('sources', [])
            require(isinstance(refs, list) and refs, '研究条目缺少来源')
            require(all(isinstance(ref, dict) and ref.get('source_id') in sources
                        and ref.get('locator') and ref.get('claim_attribution') for ref in refs), '研究来源或具体出处无效')
            require(all(ref['claim_attribution'] in {'authors','score','project'} for ref in refs), '来源观点归属无效')
            readings = [sources[ref['source_id']].get('reading_status') for ref in refs
                        if ref['claim_attribution'] == 'authors']
            if verification['literature'] in {'verified','full_text_checked'}:
                require(readings and all(s == 'full_text_checked' for s in readings), '摘要或局部阅读不能升级为全文核查')
            if verification['literature'] == 'relevant_sections_checked':
                require(readings and all(s in {'relevant_sections_checked','full_text_checked'} for s in readings),
                        '来源未记录相关章节阅读，不能升级核查范围')
            binding = item.get('recording')
            require(binding is None or isinstance(binding, dict), '演奏绑定格式无效')
            if binding:
                require(binding.get('recording_id') == metadata['recording']['recording_id'] and
                        binding.get('audio_sha256') == guide['audio_sha256'], '演奏专属研究与录音不匹配')
                alignment = read(directory / 'alignment.json')
                with local_path(root, alignment['audio']['path']).open('rb') as stream:
                    require(hashlib.file_digest(stream, 'sha256').hexdigest() == binding['audio_sha256'],
                            '当前录音内容与演奏专属研究不匹配')
            body = item.get('detail_markdown' if key == 'events' else 'markdown', '')
            if item.get('markdown_path'):
                require(not body, '文章正文只能使用一个来源')
                body = local_path(root, item['markdown_path']).read_text(encoding='utf-8')
            require(isinstance(body, str) and body.strip(), '研究正文为空')
            result[key].append({**item, 'html': RENDER(body)})
    event_ids = {e['id'] for e in result['events']}
    essay_ids = {e['id'] for e in result['essays']}
    for essay in result['essays']:
        require(set(essay.get('related_event_ids', [])) <= event_ids, '文章引用未知事件')
    for event in result['events']:
        require(set(event.get('related_essay_ids', [])) <= essay_ids, '事件引用未知文章')
    return result
