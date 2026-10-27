"""Small local caption editor backend; reuse exported media, PDF cache and JS."""
import copy
import json
import math
import os
from pathlib import Path
import shutil
import subprocess

from .content import FORBIDDEN, normalized, read, write
from .media import ffmpeg
from .subtitles import analysis_ass, score_ass
from .paths import configured_path
from .presentation import presentation_config,display_events

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = configured_path('sample_package')
DOCUMENT = configured_path('sample_document')
SLOTS = {'和弦': 'harmony', '配器': 'orchestration', '对位': 'counterpoint',
         '曲式': 'form', '导聆': 'guide', '诠释': 'interpretation', '片头': 'intro'}
DEFAULT_SIZES = {'和弦': 44, '配器': 40, '对位': 43, '曲式': 41,
                 '导聆': 43, '诠释': 51, '片头': 63}
COLUMN_NAMES = {'对位':'声部关系与复调', '曲式':'曲式与主题发展'}
CREATE_NO_WINDOW = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
STYLE_FIELDS={'横坐标':'x','纵坐标':'y','宽度':'w','高度':'h','字体':'font','字号':'font_size','滚动倍速':'scroll_speed'}


def package_config(package):
    legacy=package/'export-config-kaiti.json'
    config=read(legacy if legacy.exists() else package/'export-config.json')
    if config.get('visualization'):
        from .visual_full import refreshed_config
        config=refreshed_config(package,config)
    return config


def validate_style(style,base,config):
    result={}
    for key,value in style.items():
        if key not in STYLE_FIELDS or value in ('',None):continue
        field=STYLE_FIELDS[key]
        if field=='font':
            if not isinstance(value,str) or not value.strip() or any(c in value for c in ',{}\\\r\n'):raise ValueError('字体名称无效。')
            result[field]=value.strip();continue
        if isinstance(value,bool):raise ValueError(f'{key}须为数字。')
        try:number=float(value)
        except (ValueError,TypeError):raise ValueError(f'{key}须为数字。') from None
        if not math.isfinite(number):raise ValueError(f'{key}须为有限数字。')
        if field=='font_size' and (not number.is_integer() or not 12<=number<=120):raise ValueError('字号须为12至120的整数。')
        if field=='scroll_speed' and not .25<=number<=4:raise ValueError('滚动倍速须为0.25至4；数值越大越快。')
        result[field]=int(number) if number.is_integer() else number
    merged={**base,**result}
    if min(merged['x'],merged['y'])<0 or min(merged['w'],merged['h'])<=0 or merged['x']+merged['w']>config['width'] or merged['y']+merged['h']>config['height']:raise ValueError('字幕坐标或尺寸超出画面。')
    if merged['h']<=merged.get('font_size',config['font_size'])*1.12+8:raise ValueError('字幕区域太矮，标题下须留出正文空间。')
    return result


def column_key(label):
    return next((key for key,value in COLUMN_NAMES.items() if value==label),label)


def normalized_sizes(values):
    result = {}
    for label,size in values.items():
        key=column_key(label)
        if key in result and result[key]!=size:
            raise ValueError(f'{label}的新旧字号设置不一致。')
        result[key]=size
    return result


def document_names(document):
    names={column_key(k):v for k,v in document.get('栏目名称',{}).items()}
    for label in document.get('字号',{}):
        if label in COLUMN_NAMES.values():names.setdefault(column_key(label),label)
    for row in document.get('字幕',[]):
        if isinstance(row,dict) and row.get('栏目') in COLUMN_NAMES.values():
            names.setdefault(column_key(row['栏目']),row['栏目'])
    return names


def stored_column(label,names):
    key=column_key(label)
    return COLUMN_NAMES[key] if key in COLUMN_NAMES and names.get(key)==COLUMN_NAMES[key] else key


def stored_sizes(values,names):
    return {stored_column(key,names):value for key,value in normalized_sizes(values).items()}


def initial_document(package=PACKAGE):
    """Import the captions used by the sample once, without touching analysis."""
    sizes = dict(DEFAULT_SIZES)
    settings = configured_path('font_settings')
    if settings.exists():
        values = normalized_sizes(json.loads(settings.read_text(encoding='utf-8-sig')))
        sizes.update({k: values[k] for k in sizes if k in values})
    source = read(package / 'annotations-kaiti.json')['events']
    reverse = {v: k for k, v in SLOTS.items()}
    rows = []
    for e in sorted(source, key=lambda e: (e['output_start'], e['slot'])):
        rows.append({'编号': e['id'], '栏目': '片头' if e.get('phase') == 'intro' else reverse[e['slot']],
                     '开始秒': e['output_start'], '结束秒': e['output_end'],
                     '标题': e.get('display_title', ''), '文字': e['text'], '显示': True})
    return {'说明': '时间为当前95秒成片的秒数。修改后保存并生成新视频；显示=false表示隐藏。原视频、乐谱同步和旧成片不覆盖。',
            '字号': sizes, '字幕': rows}


def load_document(path=DOCUMENT, package=PACKAGE):
    if path.exists():
        return json.loads(path.read_text(encoding='utf-8-sig'))
    data = initial_document(package)
    write(path, data)
    return data


def prepare(document, package=PACKAGE):
    config = presentation_config(package_config(package),document.get('呈现规则',{}))
    segment = config['segments'][0]
    duration = segment['video_end'] - segment['video_start']
    events, excluded, identifiers = [], [], set()
    sizes=normalized_sizes(document['字号'])
    for label, slot in SLOTS.items():
        size = sizes[label]
        if isinstance(size, bool) or not isinstance(size, int) or not 12 <= size <= 120:
            raise ValueError(f'{label}字号须为12至120的整数。')
        config['layout'][slot]['font_size'] = size
        settings=document.get('字幕样式',{}).get(stored_column(label,document_names(document)),{})
        config['layout'][slot].update(validate_style(settings,config['layout'][slot],config))
    config['font_size'] = sizes['和弦']
    for n, row in enumerate(document['字幕'], 1):
        name = str(row.get('编号', ''))
        context = f'第{n}条（{row.get("栏目", "")}，{name}）'
        if not isinstance(row.get('显示', True), bool):
            raise ValueError(f'{context}：“显示”须为true或false。')
        if not row.get('显示', True):
            excluded.append({'id': name, 'text': row.get('文字'), 'reason': '用户在编辑器中隐藏'})
            continue
        if not name or name in identifiers:
            raise ValueError(f'{context}：编号为空或重复。')
        identifiers.add(name)
        label=column_key(row.get('栏目'))
        if label not in SLOTS:
            raise ValueError(f'{context}：栏目名称无效。')
        text, title = row.get('文字', ''), row.get('标题', '')
        if not isinstance(text, str) or not text.strip() or not isinstance(title, str):
            raise ValueError(f'{context}：请填写正文；不显示时请取消“显示此条”。')
        if FORBIDDEN.search(normalized(text + '\n' + title)):
            raise ValueError(f'{context}：含研究提示或占位文字，请整条隐藏或改为可发布的完整表述。')
        try:
            if any(isinstance(row[k], bool) for k in ('开始秒', '结束秒')):
                raise ValueError()
            start, end = float(row['开始秒']), float(row['结束秒'])
        except (ValueError, TypeError):
            raise ValueError(f'{context}：起止时间请输入秒数，例如12.5。') from None
        if not all(math.isfinite(t) for t in (start, end)) or not 0 <= start < end <= duration:
            raise ValueError(f'{context}：须满足0 ≤ 开始 < 结束 ≤ {duration:g}秒。')
        intro = label == '片头'
        if intro and end + segment['video_start'] > config.get('intro_clear_video', config['music_start_video'] - 3) + 1e-7:
            raise ValueError(f'{context}：片头最迟须在{config["intro_clear_video"] - segment["video_start"]:g}秒消失。')
        if not intro and start + segment['video_start'] < config['music_start_video'] - 1e-7:
            raise ValueError(f'{context}：正式演奏字幕请从{config["music_start_video"] - segment["video_start"]:g}秒以后开始。')
        event = {'id': name, 'slot': 'interpretation' if intro else SLOTS[label],
                 'phase': 'intro' if intro else 'performance', 'text': text.strip(),
                 'video_start': start + segment['video_start'], 'video_end': end + segment['video_start'],
                 'output_start': start, 'output_end': end, 'source': 'local editable caption document'}
        if row.get('样式'):
            event['render_style']=validate_style(row['样式'],config['layout'][SLOTS[label]],config)
        if title.strip():
            event['display_title'] = title.strip()
        if row.get('研究条目'):
            event['research_reading_id'] = row['研究条目']
            event['relation_ids'] = list(row.get('关系依据', []))
        events.append(event)
    # Source ranges may span a whole musical section after its short card has
    # faded. Check actual on-screen lifetimes so a later card can use that slot.
    visible_events=display_events(events,config)
    for slot in SLOTS.values():
        rows = sorted((e for e in visible_events if ('intro' if e['phase'] == 'intro' else e['slot']) == slot),
                      key=lambda e: e['output_start'])
        for a, b in zip(rows, rows[1:]):
            if a['output_end'] > b['output_start'] + 1e-7:
                label = next(k for k, v in SLOTS.items() if v == slot)
                raise ValueError(f'{label}的时间重叠：{a["id"]} 与 {b["id"]}。请调整结束或开始时间。')
    return config, events, excluded


def reserve_revision(package):
    number = 1
    while True:
        folder = package / f'edits-{number:03d}'
        try:
            folder.mkdir()
            return folder
        except FileExistsError:
            number += 1


def score_resources(package, folder, config, events):
    """Re-evaluate existing JS at new interpretation times; no alignment/PDF OMR."""
    from PIL import Image
    source = read(package / 'score/render-input.json')
    source.update(config=config, annotations=events)
    write(folder / 'score-input.json', source)
    node = shutil.which('node')
    if not node:
        raise ValueError('未找到Node.js，无法调用现有乐谱同步。请安装或恢复本机Node.js后重试。')
    command = [node, str(package / 'score/renderer/render-plan.mjs'),
               str(folder / 'score-input.json'), str(folder / 'score-plan.json')]
    result = subprocess.run(command, capture_output=True, encoding='utf-8', errors='replace',
                            creationflags=CREATE_NO_WINDOW)
    if result.returncode:
        raise RuntimeError('原有乐谱同步调用失败：' + result.stderr[-1800:])
    plan = read(folder / 'score-plan.json')
    # Index existing fixed-viewport images by original JS geometry.
    old = read(package / 'score/plan.json')
    page_events = read(package / 'score/page-events.json')
    cached = {}
    def key(e):
        return json.dumps([e['page'], e['pageGeometry']], sort_keys=True)
    j = 0
    for e in old['events']:
        while j + 1 < len(page_events) and page_events[j]['end'] <= e['start'] + 1e-7:
            j += 1
        image = package / 'score' / page_events[j]['file']
        if e['visible'] and e.get('pageGeometry') and image.name != 'blank.png':
            cached[key(e)] = image
    v = config['layout']['score']
    pages = []
    for e in plan['events']:
        path = package / 'score/blank.png'
        if e['visible'] and e.get('pageGeometry'):
            identity = key(e)
            if identity not in cached:
                # A moved interpretation may reveal a previously hidden page.
                # Use already cached full-page pixels and the original JS transform.
                g = e['pageGeometry']
                raster = package / f'score/page-{e["page"]:03d}.png'
                if not raster.exists():
                    raise ValueError(f'缺少第{e["page"]}页的乐谱图片缓存。原缓存和成片已保留。')
                canvas = Image.new('RGBA', (v['w'], v['h']), (0, 0, 0, 0))
                with Image.open(raster) as image:
                    scaled = image.convert('RGBA').resize((round(g['width']), round(g['height'])), Image.Resampling.LANCZOS)
                canvas.alpha_composite(scaled, (round(g['x'] - g['scroll']['left']), round(g['y'] - g['scroll']['top'])))
                path = folder / f'score-view-{len(cached):04d}.png'
                canvas.save(path)
                cached[identity] = path
            path = cached[identity]
        if pages and pages[-1]['path'] == path:
            pages[-1]['end'] = e['end']
        else:
            pages.append({'path': path, 'start': e['start'], 'end': e['end']})
    lines = ['ffconcat version 1.0']
    def entry(path):
        relative = os.path.relpath(path, folder).replace('\\', '/')
        return "file '" + relative.replace("'", "'\\''") + "'"
    for e in pages:
        lines.extend([entry(e['path']), 'option framerate 1000000', f'duration {e["end"] - e["start"]:.6f}'])
    lines.extend([entry(pages[-1]['path']), 'option framerate 1000000'])
    (folder / 'pages.ffconcat').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    (folder / 'score.ass').write_text(score_ass(plan, config), encoding='utf-8-sig')


def export(document, package=PACKAGE, progress=None, ass_only=False):
    """Each export is a snapshot. Progress callback receives (percent, message)."""
    package = package.resolve()
    emit = progress or (lambda percent, message: print(message, flush=True))
    config, events, excluded = prepare(document, package)
    subtitles = analysis_ass(events, config)
    folder = reserve_revision(package)
    write(folder / 'editing.json', copy.deepcopy(document))
    write(folder / 'config.json', config)
    write(folder / 'annotations.json', {'events': events})
    write(folder / 'review-report.json', {'excluded': excluded,
          'scope': '检查当前编辑文稿的时间、占位文字、栏目重叠；不重跑音乐分析或推断人工签核。',
          'human_or_expert_signature_inferred': False})
    (folder / 'analysis.ass').write_text(subtitles, encoding='utf-8-sig')
    if ass_only:
        emit(100, f'字幕已生成：{folder / "analysis.ass"}')
        return folder / 'analysis.ass'
    emit(0, '正在复用乐谱缓存，并按新的诠释时间更新乐谱隐藏与恢复……')
    score_resources(package, folder, config, events)
    if config.get('visualization'):
        from .visual_full import export_visual_revision
        return export_visual_revision(package,folder,config,emit)
    relative = folder.name
    v = config['layout']['score']
    graph = (f'[0:v]settb=AVTB[base];[1:v]format=rgba[paper];'
             f'[base][paper]overlay=x={v["x"]}:y={v["y"]}:eof_action=repeat:repeatlast=1:format=auto,'
             f"ass=filename='{relative}/score.ass',ass=filename='{relative}/analysis.ass',format=yuv420p[out]")
    (folder / 'compose.ffgraph').write_text(graph, encoding='utf-8')
    probes = read(package / 'source-frame-timestamps.json')
    if len(probes) != 1:
        raise ValueError('此编辑器当前用于已有的单个连续视频片段。')
    p, segment = probes[0], config['segments'][0]
    duration = segment['video_end'] - segment['video_start']
    last = min(p['frame_durations'][-1] or p['min_frame_delta'], segment['video_end'] - p['last_pts'])
    bsf = f'setts=duration=if(eq(N\\,{p["frame_count"] - 1})\\,{last:.9f}/TB\\,DURATION)'
    output = folder / '导聆视频.mp4'
    command = [ffmpeg(ROOT), '-hide_banner', '-nostdin', '-n', '-progress', 'pipe:1', '-nostats',
               '-ss', str(segment['video_start']), '-i', 'performance.mp4', '-safe', '0', '-f', 'concat',
               '-i', f'{relative}/pages.ffconcat', '-filter_complex_script', f'{relative}/compose.ffgraph',
               '-map', '[out]', '-map', '0:a:0', '-t', str(duration), '-c:v', 'libx264',
               '-crf', str(config.get('crf', 18)), '-preset', config.get('preset', 'fast'), '-bf', '0',
               '-fps_mode:v', 'passthrough', '-enc_time_base:v', 'demux', '-bsf:v', bsf,
               '-c:a', 'copy', '-map_metadata', '-1', '-movflags', '+faststart', str(output)]
    emit(0, '正在生成新视频……')
    with (folder / 'export.log').open('w', encoding='utf-8') as log:
        process = subprocess.Popen(command, cwd=package, stdout=subprocess.PIPE, stderr=log,
                                   encoding='utf-8', errors='replace', creationflags=CREATE_NO_WINDOW)
        last_percent = -1
        rendered_frames = None
        for line in process.stdout:
            if line.startswith('frame='):
                rendered_frames = int(line.split('=', 1)[1].strip())
            if line.startswith('out_time_us='):
                try:
                    percent = max(0, min(99, int(float(line.split('=', 1)[1]) / 1e6 / duration * 100)))
                except ValueError:
                    continue
                if percent != last_percent:
                    emit(percent, f'正在生成新视频：{percent}%')
                    last_percent = percent
        process.stdout.close()
        code = process.wait()
    if code or not output.exists() or output.stat().st_size == 0:
        raise RuntimeError(f'视频生成失败，错误记录：{folder / "export.log"}')
    if config.get('chapters'):
        # Preserve the complete film's chapter navigation in every edited copy.
        from .media import run
        rows=[';FFMETADATA1']
        for i,c in enumerate(config['chapters']):
            end=config['chapters'][i+1]['start'] if i+1<len(config['chapters']) else duration
            title=str(c['title']).replace('\\','\\\\').replace('\n',' ').replace('=','\\=').replace(';','\\;').replace('#','\\#')
            rows+=['[CHAPTER]','TIMEBASE=1/1000',f"START={round(c['start']*1000)}",f'END={round(end*1000)}','title='+title]
        (folder/'chapters.ffmetadata').write_text('\n'.join(rows)+'\n',encoding='utf-8')
        chaptered=folder/'导聆视频-含章节.mp4'
        run([ffmpeg(ROOT),'-v','error','-n','-i',str(output),'-i',str(folder/'chapters.ffmetadata'),'-map','0','-map_metadata','1','-map_chapters','1','-c','copy','-movflags','+faststart',str(chaptered)],folder/'chapters.log')
        output=chaptered
    report = read(folder / 'review-report.json')
    report.update(output={'video': output.name, 'bytes': output.stat().st_size,
                          'duration_seconds': duration, 'rendered_frames': rendered_frames,
                          'expected_source_frames': p['frame_count']},
                  audio='original AAC stream copied', status='rendered_for_user_viewing')
    write(folder / 'review-report.json', report)
    write(package / 'latest-caption-export.json', {'video': str(output), 'subtitles': str(folder / 'analysis.ass')})
    pointer=configured_path('latest_video')
    pointer.parent.mkdir(parents=True,exist_ok=True)
    pointer.write_text(str(output) + '\n', encoding='utf-8-sig')
    emit(100, f'已完成：{output}')
    return output
