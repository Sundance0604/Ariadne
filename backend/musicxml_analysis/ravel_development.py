"""Only Ravel's two revised modules; frozen analysis and other works stay intact."""
from fractions import Fraction as F
from pathlib import Path
from backend.structure_analysis.common import read


def load_profile(root, shared, bundle):
    root, shared = Path(root).resolve(), Path(shared).resolve()
    path = shared / 'analysis/ravel-module-development.json'
    if shared != root or not path.exists() or bundle is None:
        return None
    profile = read(path)
    if profile['work_id'] != bundle['manifest']['work_id'] or profile['base_snapshot'] != bundle['run_path']:
        raise ValueError('Ravel module readings need updating for this XML snapshot')
    if set(profile['labels']) != {'counterpoint', 'form'}:
        raise ValueError('Ravel development may change only two modules')
    sources = {}
    for name in ['analysis/structural-events.json', 'analysis/score-studies/ravel-study-20261026.json']:
        sources[name] = {e['id']: e for e in read(root / name)['events']}
    ids = set()
    for entry in profile['readings']:
        if entry['id'] in ids or entry['dimension'] not in profile['labels']:
            raise ValueError('Invalid Ravel module reading')
        ids.add(entry['id'])
        if not entry['summary'].strip() or not entry['score_spans']:
            raise ValueError('Ravel reading lacks text or score scope')
        if 'start_q' in entry and not 0 <= F(entry['start_q']) < F(entry['end_q']):
            raise ValueError('Invalid XML interval')
        for ref in entry['source_events']:
            e = sources[ref['path']][ref['id']]
            text = e.get('detail_markdown') or '\n'.join(e['observations'] + e['reasoning'])
            if text != ref['text']:
                raise ValueError('Source prose changed; rebuild Ravel module readings')
    notes = {e['id']: e for e in bundle['tables']['events']['events']}
    motifs = {m['id']: m for m in bundle['tables']['form']['motif_comparisons']}
    relation_ids = set()
    for r in profile['relations']:
        motif = motifs[r['motif_comparison_id']]
        sequences = []
        for occurrence in [r['from'], r['to'], *r.get('simultaneous_doublings', [])]:
            if not any(o['event_ids'] == occurrence['event_ids'] for o in motif['occurrences']):
                raise ValueError('Unknown Motif occurrence')
            ns = [notes[id] for id in occurrence['event_ids']]
            intervals = [b['concert_pitch']['ps'] - a['concert_pitch']['ps'] for a, b in zip(ns, ns[1:])]
            ratios = [str(F(n['duration_q']) / F(ns[0]['duration_q'])) for n in ns]
            if intervals != r['intervals'] or ratios != r['duration_ratios']:
                raise ValueError('Motif note evidence differs from reading')
            if any(F(a['score_end_q']) != F(b['score_start_q']) for a, b in zip(ns, ns[1:])):
                raise ValueError('Motif occurrence is not a continuous strand')
            sequences.append(ns)
        if {b['concert_pitch']['ps'] - a['concert_pitch']['ps'] for a, b in zip(*sequences[:2])} != {r['transposition_semitones']}:
            raise ValueError('Motif transposition differs')
        if r['theme_identity'] != 'unassigned' or r.get('human_signoff') is not None:
            raise ValueError('Literal note comparison cannot certify a theme or human review')
        relation_ids.add(r['id'])
    if any(set(e['relation_ids']) - relation_ids for e in profile['readings']):
        raise ValueError('Unknown development relation')
    return profile
