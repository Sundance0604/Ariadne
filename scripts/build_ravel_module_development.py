"""Ravel-only readings over existing studies and XML Motif evidence."""
import copy
from fractions import Fraction as F
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.video_export.content import read, write


def build():
    base_path = read(ROOT / 'analysis/musicxml/current.json')['path']
    base = ROOT / base_path
    form = read(base / 'form.json')
    measures = read(base / 'measures.json')['measures']
    geometry = read(base / 'pdf-map.json')['measures']
    notes = {e['id']: e for e in read(base / 'events.json')['events']}
    research = read(ROOT / 'analysis/structural-events.json')
    study = read(ROOT / 'analysis/score-studies/ravel-study-20261026.json')
    events = {e['id']: e for e in research['events']}
    studies = {e['id']: e for e in study['events']}
    sections = read(ROOT / read(ROOT / 'analysis/musicxml/interpretation-current.json')['path'] / 'form-synthesis.json')['sections']
    readings = []

    def add(id, dimension, title, summary, detail, pages=None, source_ids=(), section=None, priority=10, related=()):
        if section:
            s = next(s for s in sections if s['id'] == section)
            scope = {'start_q': s['start_q'], 'end_q': s['end_q']}
            members = [m for m in measures if F(s['start_q']) <= F(m['start_q']) < F(s['end_q'])]
            pages = [min(m['page'] for m in members), max(m['page'] for m in members)]
        else:
            scope = {}
        spans = [{'precision': 'page_range', 'pdf_page_start': pages[0], 'pdf_page_end': pages[1], 'region_ids': []}]
        refs = []
        for source in source_ids:
            e = events.get(source) or studies[source]
            refs.append({'id': source, 'path': 'analysis/structural-events.json' if source in events else 'analysis/score-studies/ravel-study-20261026.json',
                         'text': e.get('detail_markdown') or '\n'.join(e['observations'] + e['reasoning'])})
        entry = {'id': id, 'dimension': dimension, 'title': title, 'summary': summary, 'detail': detail,
                 'score_spans': spans, 'priority': priority, 'source_events': refs, 'relation_ids': list(related),
                 'evidence_level': 'existing_score_study_synthesis', 'human_signoff': None, **scope}
        readings.append(entry)
        return entry

    add('voices-opening', 'counterpoint', '持续层与流动层',
        '大提琴长音与低音提琴六连音分担持续和流动；节奏分层不等于多条独立旋律。',
        '\n'.join(studies['study-arpeggio-layers']['observations'] + studies['study-arpeggio-layers']['reasoning']), [1, 1], ['study-arpeggio-layers'])
    add('voices-bassoon', 'counterpoint', '旋律从背景中显出',
        '低音巴松的长句成为前景，低弦保持持续音与流动背景；先分清旋律和支撑层。',
        '沿低音巴松句子的延续聆听，再与低弦的持续／分解层比较。声部职责不同，不按同时演奏的乐器数计算复调声部。',
        [2, 2], ['study-form-intro'])
    add('voices-horn', 'counterpoint', '加倍合并后的异节奏关系',
        '圆号八度加倍与巴松平行六度各合为一层；两层以不同节奏交错推进。',
        '\n'.join(studies['study-passing']['observations'] + studies['study-passing']['reasoning']), [3, 3], ['study-passing'])
    originals = [
        ('single-hand-layers', '歌唱线、低音与填充', '钢琴分时触及旋律与低音；长音线的句法与和弦填充分开，不能把每颗分解音都算作独立声部。'),
        ('vivo-contrary-lines', '外声的反向运动', 'Vivo的上下层走向不同；分开追踪两条线的方向与节奏，听它们怎样保持独立。'),
        ('lyrical-poly-meter', '不同节奏组织下的主副层', '歌唱旋律与快速伴奏各有节拍组织；旋律句法与伴奏周期不必同时起止。'),
        ('planing-not-counterpoint', '和声化旋律与平行支撑', '上层线条带着和弦块同向下降，内声主要支撑旋律；三颗和弦音不等于三条独立旋律。'),
        ('trombone-ostinato', '长线条与固定背景', '长号持续、连接的线条与中低弦和鼓类的反复节奏并置，两层具有不同时间尺度。'),
        ('contrary-return', '交替音区中的声部区分', '钢琴与低弦形成不同节奏的线条；高低音区交替时，仍分别追踪外声的走向。'),
        ('cadenza-melody-layer', '旋律与流动伴奏并存', '较长旋律音在密集音型上延续；旋律句法与伴奏周期不等长，先保持两层的连续性。'),
        ('cadenza-countermelody', '独立低声部的加入', '较慢低声部另有三连组织、入口与方向，与上方旋律和密集音型形成更明确的多层声部关系。'),
    ]
    for id, title, summary in originals:
        old = events[id]
        spans = old['score_spans']
        entry = add('voices-' + id, 'counterpoint', title, summary, old['detail_markdown'],
                    [spans[0]['pdf_page_start'], spans[-1]['pdf_page_end']], [id], priority=20)
        entry['score_spans'] = copy.deepcopy(spans)
        # Existing PDF rectangles only supply bar containment for the original
        # hand-located span. Do not invent within-bar note timestamps.
        if spans[0]['precision'] == 'score_segment':
            span = spans[0]
            contained = []
            for g in geometry:
                x, y, w, h = g['rect_pt']
                a = [g['page_number'], g['system_index'], x]
                b = [g['page_number'], g['system_index'], x + w]
                if a < span['score_end'] and b > span['score_start']:
                    contained.append(next(m for m in measures if m['measure_id'] == g['measure_id']))
            if contained:
                entry.update(start_q=str(min(F(m['start_q']) for m in contained)),
                             end_q=str(max(F(m['start_q']) + F(m['duration_q']) for m in contained)),
                             activation_precision='existing_pdf_span_measure_containment')
    form_specs = [
        ('intro', '引子：材料的预呈示与积累', '低弦背景先建立，低音巴松与圆号材料随后进入；这些陈述为独奏接管前景积累条件。', 'study-form-intro'),
        ('cadenza-1', '首次华彩：独奏陈述与展开', '独奏接管此前的管弦乐空间，经歌唱性陈述、强化运动与结束姿态，准备后续乐队的到达。', 'opening-cadenza'),
        ('orchestral-return', '乐队重入：到达与主题确认', '首次华彩之后，乐队重新承担主题陈述；和声、低音与音色的到达分阶段完成。', 'return-formal-arrival'),
        ('lyric', '抒情对比与连接', '长旋律音与流动伴奏改变前一段厚重陈述的组织方式；对比与连接共同推进慢段。', 'lyrical-formal-region'),
        ('allegro', '快段：对比与内部发展', '6/8、下降和弦型与反复节奏建立快板对比；内部通过交替、叠合和层次变化继续展开。', 'allegro-region'),
        ('cadenza-2', '后段华彩：重组独奏空间', '与首次华彩对照：独奏再次组织低音、歌唱线和连续运动；组织方式的呼应不等于整段主题相同。', 'closing-cadenza'),
        ('reconstruction', '独奏与乐队的重叠连接', '钢琴尚未结束，乐队已逐层加入；华彩与合奏以重叠连接，逐渐加强返回和收束功能。', 'overlapping-return'),
        ('coda', '短Allegro：压缩收束', '短促的6/8集体动作回收快段动力，把此前的回忆与聚合压缩为最后的收束。', 'final-allegro'),
    ]
    for section, title, summary, source in form_specs:
        add('development-' + section, 'form', title, summary,
            (events.get(source) or studies[source]).get('detail_markdown') or '\n'.join(studies[source]['reasoning']),
            source_ids=[source], section=section)
    for id, title, summary in [
        ('scene-transition', '展开内部的织体转折', '快段继续展开，高音短句与连续分解形成新的组织；这是内部转折，不因换配器就另立完整主题。'),
        ('development-continuation', '材料的交替与叠合', '长线、早先材料与反复背景交替或重叠；通过不同时间尺度的组合延续展开。'),
        ('retransition', '返回前的聚合过程', '低层材料、钢琴跳跃与乐队逐渐聚合，为后段回收准备条件；返回是一段过程。'),
    ]:
        old = events[id]
        add('development-' + id, 'form', title, summary, old['detail_markdown'],
            [old['score_spans'][0]['pdf_page_start'], old['score_spans'][-1]['pdf_page_end']], [id], priority=20)

    # Reuse an existing comparison. Verify the actual XML notes, not a motif
    # label, MIDI projection, or visual resemblance, before promoting a literal
    # correspondence. Theme identity deliberately remains unassigned.
    motif = next(m for m in form['motif_comparisons'] if m['id'] == 'xml-motif-f8f68a3c49e6')
    first = next(o for o in motif['occurrences'] if o['voice_id'] == 'P23:v1' and o['measure_id'] == 'xml-m0042')
    answer = next(o for o in motif['occurrences'] if o['voice_id'] == 'P1:v1' and o['measure_id'] == 'xml-m0067')
    def sequence(o):
        ns = [notes[id] for id in o['event_ids']]
        if any(F(a['score_end_q']) != F(b['score_start_q']) for a, b in zip(ns, ns[1:])):
            raise ValueError('Compared attacks are not contiguous')
        return ns, [b['concert_pitch']['ps'] - a['concert_pitch']['ps'] for a, b in zip(ns, ns[1:])], [str(F(e['duration_q']) / F(ns[0]['duration_q'])) for e in ns]
    a, ai, ar = sequence(first)
    b, bi, br = sequence(answer)
    if ai != bi or ar != br or {y['concert_pitch']['ps'] - x['concert_pitch']['ps'] for x, y in zip(a, b)} != {24}:
        raise ValueError('Ravel literal correspondence no longer agrees with XML')
    rid = 'ravel-five-attack-cadenza-return'
    relation = {'id': rid, 'motif_comparison_id': motif['id'], 'type': 'literal_transposed_correspondence',
        'from': first, 'to': answer, 'intervals': ai, 'duration_ratios': ar, 'transposition_semitones': 24,
        'status': 'agent_xml_note_comparison_checked', 'theme_identity': 'unassigned', 'human_signoff': None,
        'scope': '五个连续攻击的上层取音；不是完整旋律或整段主题的同一性认定',
        'counterevidence': ['同度及八度加倍不能计作多次独立主题陈述。', '五音相同也可能是局部公式；未据此合并整段主题。']}
    doubles = []
    for o in motif['occurrences']:
        if o['start_q'] == answer['start_q']:
            ns, intervals, ratios = sequence(o)
            if intervals != bi or ratios != br or len({x['concert_pitch']['ps'] - y['concert_pitch']['ps'] for x, y in zip(ns, b)}) != 1:
                raise ValueError('Doubling evidence no longer agrees')
            if any(F(x['score_start_q']) != F(y['score_start_q']) for x, y in zip(ns, b)):
                raise ValueError('Doubling attacks are not simultaneous')
            doubles.append(o)
    relation['simultaneous_doublings'] = doubles
    for id, dimension, title, summary, occurrence in [
        ('development-five-origin', 'form', '华彩中的五音上层片段', '记住上层D—D—A—C♯—B的重复起音、跳进与回折；后续乐队陈述会出现相同的音程及节奏配置。', first),
        ('development-five-return', 'form', '独奏与乐队之间的局部对应', '此处上层五音与此前华彩片段相隔两个八度，音程及节奏比例保持；局部对应连接独奏与乐队陈述。', answer),
        ('voices-five-doubling', 'counterpoint', '同度与八度加倍的一条线', '长笛、短笛、双簧管等以同度或八度加倍相同上层片段；共同强化一条线，不按分部数计算复调声部。', answer),
    ]:
        ns = [notes[n] for n in occurrence['event_ids']]
        m = next(m for m in measures if m['measure_id'] == occurrence['measure_id'])
        end_index = max(int(n['measure_id'].split('m')[-1]) for n in ns)
        end_measure = next(m for m in measures if m['sequence'] == end_index)
        e = add(id, dimension, title, summary, relation['scope'] + '。原型与对应片段的音符、音程、时值比例及反证分别保留。',
                [m['page'], end_measure['page']], priority=100, related=[rid])
        e.update(start_q=occurrence['start_q'], end_q=str(F(end_measure['start_q']) + F(end_measure['duration_q'])),
                 note_ids=occurrence['event_ids'], evidence_level='xml_literal_note_comparison')
        e['video_text'] = {'development-five-origin':'华彩上层：D—D—A—C♯—B。留意重复起音、跳进和回折。',
                           'development-five-return':'华彩的五音上层片段在此上移两八度，音程与节奏比例保持。',
                           'voices-five-doubling':'多件乐器同度或八度加倍这一上层片段，共同强化一条线。'}[id]
    profile = {'schema_version': '1.0', 'work_id': research['work_id'], 'base_snapshot': base_path,
        'labels': {'counterpoint': '声部关系与复调', 'form': '曲式与主题发展'},
        'materials': form['materials'], 'material_links': form['material_links'],
        'motif_interface': 'reuse MusicXML form.motif_comparisons; legacy MotifAnalyzer remains auxiliary',
        'relations': [relation], 'readings': readings,
        'review': {'scope': '既有谱面研究的职责重组；另逐音复算一组XML局部对应。', 'human_signoffs': 0, 'expert_signoffs': 0}}
    write(ROOT / 'analysis/ravel-module-development.json', profile)
    print(f'Ravel profile: {len(readings)} readings, one note-checked correspondence; theme identity unassigned.')


if __name__ == '__main__':
    build()
