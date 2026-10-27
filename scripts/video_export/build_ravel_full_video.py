"""Expand the approved Ravel excerpt to the source video, using existing assets."""
import argparse
import collections
import copy
import json
import math
from pathlib import Path
import re
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from backend.video_export.content import FORBIDDEN, normalized, read, write
from backend.video_export.editor import SLOTS, export, prepare, stored_sizes
from backend.video_export.paths import configured_path,remember_full
from backend.video_export.media import ffmpeg, inspect_frames
from backend.video_export.subtitles import analysis_ass
from scripts.pdf_render import render_page

DEMO = ROOT / 'output/video-export/ravel-demo'


def node(script, source, output):
    result = subprocess.run(['node', str(script), str(source), str(output)],
                            capture_output=True, encoding='utf-8', errors='replace')
    if result.returncode:
        raise RuntimeError(result.stderr[-3000:])


def fresh_package():
    index = 1
    while True:
        path = ROOT / f'output/video-export/ravel-full-{index:03d}'
        try:
            path.mkdir()
            return path
        except FileExistsError:
            index += 1


def audit_events(events, config):
    """Exclude complete incomplete claims; retain music facts and finished prose."""
    accepted, excluded, seen_guides = [], [], set()
    generic = re.compile(r'先辨织体|再谈对位|点击查看|当前重要声部关系|当前结构功能|非严格对位认定|仅页级定位|本页／本段背景')
    uncertain = re.compile(r'待核|未定位|候选|未经|尚未|待审查')
    for original in events:
        e = dict(original)
        text = e['text']
        reason = None
        if FORBIDDEN.search(normalized(text)) or uncertain.search(text):
            reason = '包含未完成、候选或未经确认的分析表述，整条排除'
        elif generic.search(text):
            reason = '研究操作提示或通用方法文字，缺少当前音乐的有效信息'
        elif e['slot'] == 'guide':
            if e['source'] in seen_guides:
                reason = '同一导聆已经呈现过一次'
            seen_guides.add(e['source'])
        if reason:
            excluded.append({'id': e['id'], 'slot': e['slot'], 'text': text, 'reason': reason})
            continue
        e.update(output_start=e['video_start'], output_end=e['video_end'])
        accepted.append(e)
    return accepted, excluded


def full_interpretations(payload, page_plan, sample):
    # Use existing finished paragraphs only, at observed page ranges. No new
    # recording positions are inferred from prose length or assumed tempo.
    times = {}
    for e in page_plan['events']:
        if e['visible']:
            times.setdefault(e['page'], e['start'])
    extras = [copy.deepcopy(e) for e in sample if e['slot'] == 'interpretation']
    choices = [
        (10, 14, 'ravel-tonal-emergence', 1, '诠释：钢琴如何改变调性的前景'),
        (15, 23, 'ravel-tonal-emergence', 2, '诠释：和声、低音与音色的分时到达'),
        (91, 94, 'ravel-timbre-perspectives', 2, '诠释：一架钢琴内部的多重声音'),
        (95, 99, 'ravel-timbre-perspectives', 4, '诠释：华彩如何重新连接乐队'),
    ]
    for page, last, essay, paragraph, title in choices:
        if page not in times:
            continue
        path = ROOT / f'analysis/essays/{essay}.md'
        paragraphs = [p.strip() for p in path.read_text(encoding='utf-8').split('\n\n') if p.strip() and not p.startswith('#')]
        text = paragraphs[paragraph]
        # Give the page's guide enough time to be read once before the larger
        # interpretation replaces it. A two-second lead would flash a paragraph.
        start = times[page] + 22
        limit = times.get(last + 1, payload['project']['alignment']['score_time_coverage']['end_seconds'])
        end = min(start + max(16, len(text) / 6 + 2), limit)
        if end - start < 10 or FORBIDDEN.search(normalized(text)):
            continue
        extras.append({'id': f'full-interpretation-p{page}', 'slot': 'interpretation', 'phase': 'performance',
                       'video_start': start, 'video_end': end, 'output_start': start, 'output_end': end,
                       'display_title': title, 'text': text, 'source': f'{path.relative_to(ROOT).as_posix()} paragraph {paragraph + 1}'})
    return extras


def narrative_timing(events, excluded):
    interpretations = [(e['video_start'], e['video_end']) for e in events if e['slot'] == 'interpretation' and e.get('phase') != 'intro']
    for slot in ('guide', 'counterpoint', 'form'):
        rows = sorted((e for e in events if e['slot'] == slot), key=lambda e: e['video_start'])
        for e in rows:
            start, end = e['video_start'], e['video_end']
            # Leave a quiet interval before the following narrative. One pass,
            # with short paragraphs held in place by the existing ASS formatter.
            if end - start >= 5:
                end = max(start + 3, math.floor(start + (end - start) * .75))
            for a, b in interpretations:
                if start < a < end:
                    end = a  # Never restart this same paragraph after a break.
                elif a <= start < b:
                    start = b
            if end - start < 3:
                e['exclude_after_timing'] = True
                excluded.append({'id': e['id'], 'slot': slot, 'text': e['text'], 'reason': '实际阅读时段不足3秒，整条隐藏，避免闪现或再次起滚'})
                continue
            if slot == 'form' and len(e['text']) / (end - start) > 9:
                summary = e['text'].splitlines()[0]
                excluded.append({'id': e['id'], 'slot': slot, 'text': e['text'],
                                 'reason': '短曲式时段仅呈现已有完整段落名称，避免长篇模型闪现', 'replacement': summary})
                e['text'] = summary
            if slot == 'guide' and len(e['text']) / (end - start) > 9:
                title, _, body = e['text'].partition('\n')
                sentence = re.split(r'(?<=。)', body)[0]
                summary = title + '\n' + sentence
                if len(summary) < len(e['text']):
                    excluded.append({'id': e['id'], 'slot': slot, 'text': e['text'],
                                     'reason': '短时段使用原文首个完整句，全文保留在网页及web-captions.json', 'replacement': summary})
                    e['text'] = summary
            e.update(video_start=start, video_end=end, output_start=start, output_end=end)
    return [e for e in events if not e.pop('exclude_after_timing', False)]


def build(package=None):
    package = package or fresh_package()
    payload = read(DEMO / 'web-text-source.json')
    profile_path=ROOT/'analysis/ravel-module-development.json'
    if profile_path.exists():
        payload['research']['module_profile']=read(profile_path)
    source_doc = json.loads(configured_path('sample_document').read_text(encoding='utf-8-sig'))
    config, sample, _ = prepare(source_doc, DEMO)
    duration = payload['project']['media']['video']['duration_seconds']
    config['segments'] = [{'video_start': 0, 'video_end': duration}]
    config['caption_lifecycle'] = 'single_pass'
    payload['config'] = config
    print(f'完整版目录：{package}', flush=True)
    print(f'保留原片0—{duration:g}秒；复用你保存的字号与全部乐谱同步。', flush=True)
    package.mkdir(exist_ok=True)
    (package / 'score').mkdir(exist_ok=True)
    for name in ('performance.mp4', 'alignment.json', 'project.json'):
        if not (package / name).exists():
            shutil.copy2(DEMO / name, package / name)
    for path in (DEMO / 'score').iterdir():
        if path.is_file() and (path.suffix == '.png' or path.name in ('source.pdf', 'render-input.json', 'plan.json', 'page-events.json')):
            shutil.copy2(path, package / 'score' / path.name)
    shutil.copytree(DEMO / 'score/renderer', package / 'score/renderer', dirs_exist_ok=True)
    write(package / 'export-config-kaiti.json', config)
    write(package / 'web-text-source.json', payload)
    print('正在按原网页的整曲时间轴整理字幕……', flush=True)
    node(ROOT / 'scripts/video_export/export_web_captions.mjs', package / 'web-text-source.json', package / 'web-captions.json')
    raw = read(package / 'web-captions.json')
    accepted, excluded = audit_events(raw['events'], config)
    excluded.extend({'slot': e['slot'], 'text': e['text'], 'reason': e['reason']} for e in raw['omitted'])
    # Preserve genuine user edits from the approved sample by applying changed
    # fields only; unchanged events can naturally extend beyond second 95.
    original = {e['id']: e for e in read(DEMO / 'annotations-kaiti.json')['events']}
    edited = {e['编号']: e for e in source_doc['字幕']}
    reverse = {v: k for k, v in SLOTS.items()}
    for e in accepted:
        old, update = original.get(e['id']), edited.get(e['id'])
        if not old or not update:
            continue
        fields = [('text', '文字', 'text'), ('video_start', '开始秒', 'video_start'),
                  ('video_end', '结束秒', 'video_end'), ('display_title', '标题', 'display_title')]
        for target, source, compare in fields:
            value = update.get(source, '')
            previous = old.get(compare, '')
            if target in ('video_start', 'video_end'):
                value = float(value)
            if value != previous:
                e[target] = value
        if not update.get('显示', True):
            e['hidden_by_user'] = True
        e.update(output_start=e['video_start'], output_end=e['video_end'])
    accepted = [e for e in accepted if not e.pop('hidden_by_user', False)]
    baseline = read(package / 'score/render-input.json')
    baseline.update(config=config, annotations=[])
    write(package / 'score/full-page-input.json', baseline)
    node(package / 'score/renderer/render-plan.mjs', package / 'score/full-page-input.json', package / 'score/full-page-plan.json')
    plan = read(package / 'score/full-page-plan.json')
    # Pre-render each full page once. The score viewport and its transforms are
    # still calculated exclusively by the saved original JS renderer.
    pages = sorted({e['page'] for e in plan['events'] if e['visible'] and e.get('pageGeometry')})
    print(f'正在缓存完整乐谱，共{len(pages)}页……', flush=True)
    for i, page in enumerate(pages, 1):
        target = package / f'score/page-{page:03d}.png'
        if not target.exists():
            render_page(package / 'score/source.pdf', page, target, dpi=config.get('score_dpi', 144))
        if i % 10 == 0 or i == len(pages):
            print(f'乐谱缓存：{i}/{len(pages)}', flush=True)
    accepted.extend(full_interpretations(payload, plan, sample))
    accepted = narrative_timing(accepted, excluded)
    rows = []
    for e in sorted(accepted, key=lambda e: (e['output_start'], e['slot'])):
        rows.append({'编号': e['id'], '栏目': '片头' if e.get('phase') == 'intro' else config.get('slot_labels',{}).get(e['slot'],reverse[e['slot']]),
                     '开始秒': e['output_start'], '结束秒': e['output_end'], '标题': e.get('display_title', ''),
                     '文字': e['text'], '显示': True})
    names={reverse[slot]:name for slot,name in config.get('slot_labels',{}).items() if slot in reverse}
    document = {'说明': f'拉威尔完整版0—{duration:g}秒，所有时间均为成片秒数。修改后另存新视频。',
                '字号': stored_sizes(source_doc['字号'],names), '字幕': rows,
                '栏目名称': {name:name for name in names.values()}}
    docpath = package / '字幕编辑.json'
    write(docpath, document)
    prepare(document, package)
    analysis_ass(accepted, config)  # Final actual text scan, before encoding.
    issues, previous_page = [], None
    for e in plan['events']:
        if e.get('issue'):
            issues.append({'time': e['videoTime'], 'measure_id': e['measureId'], 'reason': e['issue'], 'action': '保留谱页、隐藏不可靠高亮与播放线'})
        if e['visible']:
            if previous_page is not None and e['page'] < previous_page:
                raise ValueError(f'原乐谱算法在{e["start"]:.3f}秒出现页码回退，请先修正对应位置。')
            previous_page = e['page']
    write(package / 'review-report.json', {'excluded': excluded,
          'score_issues': list({json.dumps(e, sort_keys=True): e for e in issues}.values()),
          'scope': '整曲字幕发布检查；沿用原网页已存的乐谱/XML与成稿。未重新分析录音，未代填人类或专家签核。',
          'accepted_counts': dict(collections.Counter(e['slot'] for e in accepted)),
          'music_start_video': config['music_start_video'], 'score_time_coverage': payload['project']['alignment']['score_time_coverage']})
    if (package / 'source-frame-timestamps.json').exists():
        probes = read(package / 'source-frame-timestamps.json')[0]
    else:
        print('正在读取源视频实际时间戳，不运行指纹或分析测试……', flush=True)
        probes = inspect_frames(ffmpeg(ROOT), package / 'performance.mp4', 0, duration, package / 'source-timestamps.log')
        write(package / 'source-frame-timestamps.json', [probes])
    print(f'原片时间戳：{probes["frame_count"]}帧；字幕数量：{len(rows)}。开始合成完整版。', flush=True)
    output = export(document, package)
    folder = output.parent
    # Make the final version an ordinary editable export package as requested.
    shutil.copy2(folder / 'analysis.ass', package / 'analysis.ass')
    shutil.copy2(folder / 'annotations.json', package / 'annotations.json')
    report = read(package / 'review-report.json')
    report.update(render=read(folder / 'review-report.json'))
    write(package / 'review-report.json', report)
    write(package / 'export-manifest.json', {'format_version': '1.0', 'track': 'ravel-left-hand-video',
          'performance': 'performance.mp4', 'output': output.relative_to(package).as_posix(),
          'subtitles': 'analysis.ass', 'annotations': 'annotations.json', 'alignment': 'alignment.json',
          'editing_document': 'captions-editable.json', 'config': 'export-config-kaiti.json', 'review_report': 'review-report.json',
          'duration_seconds': duration, 'font': config['font'], 'sizes': document['字号'],
          'score': {'pages': 'score/', 'plan': f'{folder.name}/score-plan.json', 'graphics': f'{folder.name}/score.ass'},
          'audio': '原演奏AAC音轨复制', 'time_axes': {'outputTime': '成片秒数', 'videoTime': '原演奏录像秒数', 'musicTime': 'videoTime - 27.5'},
          'reuse': ['既有alignment', 'playhead.mjs', 'score-follow.mjs', 'score-display.mjs', 'web HUD formatter']})
    # ASCII batch arguments: the editable document has an ASCII alias for cmd.
    shutil.copy2(docpath, package / 'captions-editable.json')
    remember_full(package,package/'captions-editable.json')
    print(f'完整版完成：{output}', flush=True)
    print(f'以后编辑：{ROOT / "编辑视频字幕.bat"}，选择拉威尔左手钢协完整版。', flush=True)
    return output


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    build(args.output.resolve() if args.output else None)
