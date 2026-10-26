"""Update only two Ravel subtitle slots; never encode video or touch score sync."""
import argparse
import copy
from datetime import datetime
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from backend.video_export.content import FORBIDDEN, normalized, read, write
from backend.video_export.editor import prepare,column_key,document_names,stored_sizes,stored_column
from backend.video_export.subtitles import analysis_ass
from backend.video_export.paths import full_paths,configured_path

NAMES = {'对位': '声部关系与复调', '曲式': '曲式与主题发展'}
SLOTS = {'counterpoint': '对位', 'form': '曲式'}


def replacement_events(raw, document, profile, duration):
    readings = {e['id']: e for e in profile['readings']}
    interpretations = [(float(e['开始秒']), float(e['结束秒'])) for e in document['字幕']
                       if e['栏目'] == '诠释' and e.get('显示', True)]
    rows, omitted, seen = [], [], set()
    for e in raw['events']:
        if e['slot'] not in SLOTS:
            raise ValueError('Caption update tried to change another slot')
        start, end = max(0, e['video_start']), min(duration, e['video_end'])
        if end - start >= 5:
            end = max(start + 3, int(start + (end - start) * .75))
        for a, b in interpretations:
            if a <= start < b:
                start = b
            elif start < a < end:
                # Very short leads wait until after the interpretation. Longer
                # paragraphs show once and never restart after interruption.
                if a - start < 3:
                    start = b
                else:
                    end = a
        entry = readings[e['source']]
        text = entry.get('video_text') or e['text']
        if entry['id'] in seen:
            omitted.append({'id':e['id'], 'reading_id':entry['id'], 'reason':'同一研究文字已呈现，不在子片段结束后重新起滚'})
            continue
        if end - start < 3:
            omitted.append({'id': e['id'], 'reading_id': entry['id'], 'reason': '有效阅读时段不足3秒，整条隐藏'})
            continue
        if FORBIDDEN.search(normalized(text)):
            raise ValueError('Research status text in revised caption: ' + entry['id'])
        seen.add(entry['id'])
        label = SLOTS[e['slot']]
        from scripts.video_export.polish_ravel_caption_text import POLISHED
        text=POLISHED.get(entry['id'],text)
        rows.append({'编号': 'ravel-modules-' + entry['id'] + f'-{len(rows)+1}', '栏目': NAMES[label],
                     '开始秒': start, '结束秒': end, '标题': NAMES[label], '文字': text, '显示': True,
                     '研究条目': entry['id'], '关系依据': entry['relation_ids']})
    return rows, omitted


def sync(package, document_path, profile, raw):
    old = json.loads(document_path.read_text(encoding='utf-8-sig'))
    config = read(package / 'export-config-kaiti.json')
    duration = config['segments'][0]['video_end'] - config['segments'][0]['video_start']
    config.setdefault('slot_labels', {}).update({slot: NAMES[label] for slot, label in SLOTS.items()})
    before = [e for e in old['字幕'] if column_key(e['栏目']) not in NAMES]
    updates, omitted = replacement_events(raw, old, profile, duration)
    data = copy.deepcopy(old)
    names={**document_names(data),**NAMES}
    data['栏目名称'] = {stored_column(k,names):v for k,v in names.items()}
    data['字号']=stored_sizes(data['字号'],names)
    data['字幕'] = sorted(before + updates, key=lambda e: float(e['开始秒']))
    # This guard covers text, times, visibility, custom titles and user edits.
    if before != [e for e in data['字幕'] if column_key(e['栏目']) not in NAMES]:
        raise ValueError('Unrelated captions changed')
    backup = package / 'caption-backups' / datetime.now().strftime('%Y%m%d-%H%M%S-%f')
    backup.mkdir(parents=True)
    write(backup / document_path.name, old)
    write(backup / 'export-config-kaiti.json', read(package / 'export-config-kaiti.json'))
    write(package / 'export-config-kaiti.json', config)
    # Validate all saved timings, while keeping old render snapshots untouched.
    verified_config, events, excluded = prepare(data, package)
    ass = analysis_ass(events, verified_config)
    write(document_path, data)
    if package.name.startswith('ravel-full-'):
        write(package / 'module-profile.json', profile)
        write(package / '字幕编辑.json', data)
        write(package / 'annotations.json', {'events': events})
        (package / 'analysis.ass').write_text(ass, encoding='utf-8-sig')
        manifest_path = package / 'export-manifest.json'
        if manifest_path.exists():
            manifest = read(manifest_path)
            manifest['caption_update'] = {'status': 'updated_video_regeneration_needed',
                'changed_slots': list(NAMES.values()), 'editing_document': document_path.relative_to(package).as_posix(),
                'unchanged_slots': ['和弦', '配器', '导聆', '诠释', '片头']}
            manifest['module_profile'] = 'module-profile.json'
            write(manifest_path, manifest)
    report = {'status': 'subtitles_updated_no_video_encoded', 'changed_slots': list(NAMES.values()),
        'caption_count': len(updates), 'unrelated_rows_preserved': len(before), 'sizes_preserved': stored_sizes(data['字号'],names) == stored_sizes(old['字号'],names),
        'excluded': omitted + excluded, 'backup': str(backup), 'note': 'Motif局部对应不等于完整主题身份。'}
    write(package / 'module-caption-update-report.json', report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--package', type=Path)
    args = parser.parse_args()
    package = args.package
    if package is None:
        package,_=full_paths()
    package = package.resolve()
    profile = read(ROOT / 'analysis/ravel-module-development.json')
    payload = read(package / 'web-text-source.json')
    payload['research']['module_profile'] = profile
    payload['dimensions'] = ['counterpoint', 'form']
    source, output = package / 'two-module-caption-input.json', package / 'two-module-caption-events.json'
    write(source, payload)
    result = subprocess.run(['node', str(ROOT / 'scripts/video_export/export_web_captions.mjs'), str(source), str(output)],
                            capture_output=True, encoding='utf-8', errors='replace')
    if result.returncode:
        raise RuntimeError(result.stderr)
    raw = read(output)
    full = sync(package, package / 'captions-editable.json', profile, raw)
    # The old 95-second editor stays usable and gets the same two revisions.
    sample = sync(configured_path('sample_package'), configured_path('sample_document'), profile, raw)
    print(json.dumps({'full': full, 'sample': sample}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
