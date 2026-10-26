"""Standard-library access to fingerprint-bound precomputed MusicXML evidence."""
from collections import defaultdict
from pathlib import Path
from functools import lru_cache
from backend.structure_analysis.common import read,digest,bounded_path


@lru_cache(maxsize=1)
def _load(root_string,directory_string,pointer_text,manifest_mtime):
    import json
    root=Path(root_string);directory=Path(directory_string);pointer=json.loads(pointer_text)
    run=bounded_path(root,pointer['path'])
    if not run.is_relative_to(directory/'analysis/musicxml'):raise ValueError('MusicXML run outside work')
    if digest(run/'manifest.json')!=pointer['manifest_sha256']:raise ValueError('MusicXML manifest fingerprint mismatch')
    manifest=read(run/'manifest.json')
    for source in [manifest['source'],manifest['pdf']]:
        if digest(bounded_path(root,source['path']))!=source['sha256']:raise ValueError('MusicXML/PDF input fingerprint mismatch')
    if digest(directory/'measure-map.json')!=manifest['geometry_sha256']:raise ValueError('MusicXML geometry fingerprint mismatch')
    tables={}
    for name,binding in manifest['files'].items():
        path=bounded_path(run,name)
        if digest(path)!=binding['sha256']:raise ValueError('MusicXML evidence fingerprint mismatch: '+name)
        tables[name.removesuffix('.json')]=read(path)
    indices={}
    def group(name,values,field='measure_id'):
        index=defaultdict(list)
        for value in values:index[value[field]].append(value)
        indices[name]=dict(index)
    group('events',tables['events']['events'])
    group('harmony',tables['harmony']['windows'])
    group('layers',tables['harmony']['layer_reductions'])
    group('key_context',tables['harmony']['key_contexts'])
    group('orchestration',tables['orchestration']['measures'])
    group('intervals',tables['counterpoint']['intervals'])
    group('motions',tables['counterpoint']['motions'])
    group('chordal_intervals',tables['counterpoint']['chordal_intervals'])
    group('notation',tables['notation']['notation'])
    group('landmarks',tables['form']['landmarks'])
    group('cadences',tables['form']['cadence_candidates'])
    group('pdf',tables['pdf-map']['measures'])
    return {'manifest':manifest,'tables':tables,'indices':indices,'run_path':pointer['path']}


def load_bundle(root,directory,mapping=None):
    root=Path(root).resolve();directory=Path(directory).resolve()
    pointer_path=directory/'analysis/musicxml/current.json'
    if not pointer_path.exists():return None
    text=pointer_path.read_text(encoding='utf-8');pointer=read(pointer_path)
    run=bounded_path(root,pointer['path'])
    # Include source/evidence stats so changing a file cannot keep a cached
    # validated run alive. Hash checking is performed whenever this token changes.
    manifest=read(run/'manifest.json')
    paths=[run/'manifest.json',directory/'measure-map.json',
        bounded_path(root,manifest['source']['path']),bounded_path(root,manifest['pdf']['path']),
        *[bounded_path(run,name) for name in manifest['files']]]
    token=tuple((p.stat().st_size,p.stat().st_mtime_ns) for p in paths)
    bundle=_load(str(root),str(directory),text,token)
    if mapping and bundle['manifest']['pdf']['sha256']!=mapping['pdf_sha256']:raise ValueError('MusicXML navigation PDF differs')
    return bundle


def measure_evidence(bundle,measure_id):
    m=next((m for m in bundle['tables']['measures']['measures'] if m['measure_id']==measure_id),None)
    if m is None:raise ValueError('Unknown XML measure')
    return {'measure':m,'source':bundle['manifest']['source'],'review_status':bundle['manifest']['review_status'],
        **{name:index.get(measure_id,[]) for name,index in bundle['indices'].items()},
        'part_registry':bundle['tables']['parts']['parts'],
        'motif_comparisons':[f for f in bundle['tables']['form']['motif_comparisons'] if any(o['measure_id']==measure_id for o in f['occurrences'])],
        'hierarchy':[u for u in bundle['tables']['form']['hierarchy'] if measure_id in u['xml_measure_ids']]}


def research_events(bundle):
    result=[];indices=bundle['indices'];form=bundle['tables']['form']
    names={p['id']:p['name'] for p in bundle['tables']['parts']['parts']}
    for m in bundle['tables']['measures']['measures']:
        mid=m['measure_id'];pdf=indices['pdf'][mid][0]
        if pdf['status']=='unresolved':continue
        h=indices['harmony'].get(mid,[]);o=indices['orchestration'][mid][0]
        intervals=indices['intervals'].get(mid,[]);chordal=indices['chordal_intervals'].get(mid,[])
        header=f'MusicXML第{m["number"]}小节 · PDF物理第{m["page"]}页。按小节区域激活，未校准为当前逐音和弦。\n\n'
        harmony_rows=['| 小节内起点（四分音符） | 记谱实音和声 | 转位 | 条件性级数 |','|---|---|---|---|']
        for w in h:
            c=w['sonority']['chord'];inv=str(c['inversion']) if c else '不作单一转位'
            romans='；'.join(k['context']+'：'+k['roman'] for k in w['roman_hypotheses']) or '不强加级数'
            harmony_rows.append(f'| {w["onset_q"]} | {w["sonority"]["label"]} | {inv} | {romans} |')
        bodies={'harmony':header+'\n'.join(harmony_rows)+'\n\n转位0/1/2/3分别为原位/第一/第二/第三转位。级数以未核验的局部调性候选为条件；音集识别不等于终止或功能认定。踏板余响及震音实际交替不由记谱时值假造。',
            'orchestration':header+'\n'.join(['| 分部 | 实音音域 | 谱面活动／职责依据 |','|---|---|---|']+[
                '| '+row['name']+' | '+('–'.join(row['range']) if row['range'] else '非定音')+' | '+
                '; '.join(row['role_observations']+row['written_techniques'])+' |' for row in o['parts']])+
                '\n\n最高音不自动等于旋律。休止分部：'+', '.join(names[id] for id in o['resting_part_ids']),
            'counterpoint':header+f'本小节保留{len(intervals)}条独立单音声部对的音程见证，及{len(chordal)}组同一XML声部内的和弦／分部音程。\n\n'+
                '\n'.join('- '+' / '.join(r['voices'])+'：'+'/'.join(r['pitches'])+'，'+r['interval']+'；事件 '+', '.join(r['event_ids']) for r in intervals[:10])+
                '\n\n和弦与divisi攻击不伪装为独立旋律；反向、斜向及平行运动另存逐事件证据，平行五八度不自动判作作曲错误。',
            'form':header+'\n'.join('- '+u['level']+' · '+u['title']+'：'+u['argument'] for u in form['hierarchy'] if mid in u['xml_measure_ids'])+
                '\n\n动机的音程＋节奏比例比较、排练号、速度文字、终止候选和配器变化均保留独立证据，不将其中一项自动当作正式曲式边界。'}
        span={'precision':'score_segment_candidate','pdf_page_start':m['page'],'pdf_page_end':m['page'],
                    'region_ids':[pdf['legacy_geometry_id']]} if pdf['legacy_geometry_id'] else {
                    'precision':'page_range','pdf_page_start':m['page'],'pdf_page_end':m['page'],'region_ids':[]}
        # New XML cadenza geometry is available through the independent API.
        # Do not falsely activate three different systems as one page background.
        if not pdf['legacy_geometry_id']:continue
        for dimension in ['harmony','orchestration','counterpoint','form']:
            result.append({'id':f'musicxml-{dimension}-{mid}','dimension':dimension,'claim_level':'theoretical_analysis',
                'short_label':f'MusicXML m.{m["number"]} · '+{'harmony':'和声与转位','orchestration':'乐器活动与职责','counterpoint':'声部关系','form':'结构证据'}[dimension],
                'detail_markdown':bodies[dimension],'analysis_origin':'musicxml_analysis','xml_measure_id':mid,
                'score_spans':[span],
                'verification':{'score':'pending','location':'score_segment_candidate','literature':'not_applicable','timing':'candidate_alignment'},
                'sources':[{'source_id':'ravel-musicxml-score','locator':f'MusicXML measure {m["number"]}; '+mid,'claim_attribution':'score'}],
                'related_essay_ids':[],'analysis_framework':'MusicXML-first; source note IDs and separate XML→PDF measure containment',
                'evidence_url':'/api/musicxml-evidence?track=ravel-left-hand&measure_id='+mid})
    return result
