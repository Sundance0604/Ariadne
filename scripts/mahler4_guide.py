"""Short reading windows keyed to the scanned score, independent of MIDI bar IDs."""
from bisect import bisect_right
import hashlib
import json


def score_key(point):
    return tuple(point)


def reference_at(mapping, point):
    page, system, x = point
    parent = next((r for r in mapping['score_regions']
                   if r['page_number'] == page and r['system_index'] == system), None)
    if parent is None:
        raise ValueError(f'导聆缺少谱面系统：{point}')
    if not x:
        return parent['midi_start_seconds']
    left, _, width, _ = parent['rect_pt']
    if not left <= x <= left + width:
        raise ValueError(f'导聆边界超出谱面系统：{point}')
    children = [r for r in mapping.get('bar_regions', [])
                if r.get('parent_region_id') == parent['region_id']
                and r['rect_pt'][0] <= x < r['rect_pt'][0] + r['rect_pt'][2]]
    region = children[0] if children else parent
    fraction = (x - region['rect_pt'][0]) / region['rect_pt'][2]
    return region['midi_start_seconds'] + fraction * (
        region['midi_end_seconds'] - region['midi_start_seconds'])


def recording_at(time_map, reference):
    times = [p['midi_seconds'] for p in time_map]
    index = bisect_right(times, reference)
    if not index:
        return time_map[0]['audio_seconds']
    if index == len(times):
        return time_map[-1]['audio_seconds']
    a, b = time_map[index - 1], time_map[index]
    return a['audio_seconds'] + (reference-a['midi_seconds']) / (
        b['midi_seconds']-a['midi_seconds']) * (b['audio_seconds']-a['audio_seconds'])


def build_score_guide(path, mapping, alignment, essays, render):
    raw = path.read_bytes()
    guide = json.loads(raw)
    if guide['pdf_sha256'] != mapping['pdf_sha256']:
        raise ValueError('分段导聆绑定的 PDF 与当前谱面不一致')
    segments = guide['segments']
    if any(score_key(a['start']) >= score_key(b['start']) for a, b in zip(segments, segments[1:])):
        raise ValueError('分段导聆必须按谱面顺序排列')
    essays = {n['movement']: n for n in essays}
    movements = {m['movement']: m for m in mapping['movements']}
    annotations = []
    for i, segment in enumerate(segments):
        movement = segment['movement']
        bounds = movements[movement]
        start = segment['start']
        if not bounds['first_pdf_page'] <= start[0] <= bounds['last_pdf_page']:
            raise ValueError('分段导聆越过乐章边界')
        next_segment = segments[i+1] if i+1 < len(segments) else None
        end = next_segment['start'] if next_segment else [mapping['page_count']+1, 0, 0]
        same_movement = next_segment and next_segment['movement'] == movement
        start_ref = reference_at(mapping, start)
        end_ref = reference_at(mapping, end) if same_movement else max(
            r['midi_end_seconds'] for r in mapping['score_regions'] if r['movement'] == movement)
        start_time = recording_at(alignment['time_map'], start_ref)
        end_time = recording_at(alignment['time_map'], end_ref)
        candidates = [m for m in alignment['measures'] if m.get('movement') == movement]
        first = min(candidates, key=lambda m: abs(m['start_seconds']-start_time))
        last = min(candidates, key=lambda m: abs(m['end_seconds']-end_time))
        markdown = segment['markdown']
        annotations.append({
            'annotation_id': f'mahler4-segment-{i+1:02d}', 'movement': movement,
            'title': segment['title'], 'markdown': markdown, 'html': render(markdown),
            'start_pdf_page': start[0],
            'end_pdf_page': end[0]-1 if end[1:] == [0, 0] else end[0],
            'score_start': start, 'score_end': end,
            'start_measure_id': first['measure_id'], 'end_measure_id': last['measure_id'],
            'start_seconds': start_time, 'end_seconds': end_time,
            'category': 'score_segment_listening_guide', 'locator_precision': 'score_segment',
            'review_status': 'score_located_timing_unreviewed',
            'boundary_kind': segment['boundary_kind'], 'score_cue': segment['cue'],
            'source_section': segment['source_section'],
            'source_ids': essays[movement]['source_ids'],
            'evidence': '依据本次扫描谱的速度、歌词或织体阅读窗口分段；'+segment['cue'],
        })
    return annotations, {'sha256': hashlib.sha256(raw).hexdigest(), 'note': guide['editorial_note']}
