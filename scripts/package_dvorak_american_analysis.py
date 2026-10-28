"""Package the Op.96 score essay and verify its source links and coverage."""
from collections import Counter
from fractions import Fraction as F
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.build_dvorak_american_research import OUT, BASE, record, write


def build():
    document = OUT / 'full-analysis.md'
    text = document.read_text(encoding='utf8')
    index = json.loads((OUT / 'measure-index.json').read_text(encoding='utf8'))
    rows = index['measures']
    lookup = {(r['movement'], r['local_number']): r for r in rows}
    event_data = json.loads((OUT / 'musicxml/events.json').read_text(encoding='utf8'))
    actual_source = record(next(BASE.glob('*.mxl')))
    if actual_source != index['source'] or actual_source != event_data['source']:
        raise ValueError('Source fingerprint changed; rebuild and reassess the edition before packaging')
    pdf_inventory = json.loads((OUT / 'pdf-inventory.json').read_text(encoding='utf8'))
    if pdf_inventory['source'] != record(next(BASE.glob('*.pdf'))):
        raise ValueError('PDF fingerprint changed; reassess page associations before packaging')
    events = event_data['events']
    event_lookup = {e['id']: e for e in events}
    chapters = {'第一乐章': 1, '第二乐章': 2, '第三乐章': 3, '第四乐章': 4}
    movement = None
    sections = []
    revised = []
    fields = {'和声': 'harmony', '配器与织体': 'orchestration',
              '声部关系与复调': 'voices', '曲式与主题发展': 'form', '聆听线索': 'listening'}
    for block in re.split(r'(?=^## |^### )', text, flags=re.M):
        heading = block.splitlines()[0] if block else ''
        if heading.startswith('## '):
            movement = next((v for k, v in chapters.items() if heading.startswith('## ' + k)), None)
        if heading.startswith('### '):
            match = re.match(r'### (\d+)至(\d+)小节 (.+)', heading)
            if movement is None or match is None:
                raise ValueError('Unexpected section heading: ' + heading)
            first, last = map(int, match.groups()[:2])
            start, end = lookup[movement, str(first)], lookup[movement, str(last)]
            members = rows[start['sequence']-1:end['sequence']]
            locator = f'定位：X第{movement}乐章{first}–{last}小节，序列{start["sequence"]}–{end["sequence"]}；S物理{start["xml_layout_page"]}–{end["xml_layout_page"]}页（X布局对应，非逐音头几何）。'
            block = re.sub(r'^定位：.*$', locator, block, flags=re.M)
            payload = {}
            for label, key in fields.items():
                found = re.search(r'\*\*' + label + r'。\*\* (.*?)(?=\n\n|\Z)', block, flags=re.S)
                if not found:
                    raise ValueError('Missing dimension: ' + heading + label)
                payload[key] = found.group(1)
            sections.append({'id': f'dvorak-american-{movement}-{first:03d}-{last:03d}',
                             'movement': movement, 'title': heading[4:],
                             'first_sequence': start['sequence'], 'last_sequence': end['sequence'],
                             'local_measure_range': [first, last],
                             'measure_ids': [r['measure_id'] for r in members],
                             'xml_layout_page_range': [start['xml_layout_page'], end['xml_layout_page']],
                             **payload, 'source_locator': locator,
                             'scope': 'continuous_editorial_reading_range_not_necessarily_formal_boundary',
                             'review_status': 'agent_score_analysis_draft_with_selected_visual_and_note_checks',
                             'audio_projection': None, 'human_signoff': None, 'expert_review': None})
        revised.append(block)
    text = ''.join(revised)
    if '待索引' in text:
        raise ValueError('Unfilled locator')
    coverage = [mid for s in sections for mid in s['measure_ids']]
    if coverage != [r['measure_id'] for r in rows]:
        raise ValueError('Prose coverage has an omission, overlap or ordering error')
    document.write_text(text, encoding='utf8')
    write(OUT / 'sections.json', {'format_version': 1, 'work_id': 'dvorak-american',
                                 'sections': sections, 'alignment': None, 'audio': None})

    def compare(identity, pid_a, seq_a, pid_b, seq_b, delta, description):
        def extract(pid, seqs):
            notes = [e for e in events if e['part_id'] == pid and e['sequence'] in seqs and e['eligible']]
            notes.sort(key=lambda e: (e['sequence'], F(e['onset_q']), F(e['concert_ps'])))
            signature = [(seqs.index(e['sequence']), F(e['onset_q']), F(e['duration_q']), F(e['concert_ps'])) for e in notes]
            return notes, signature
        a, sa = extract(pid_a, seq_a)
        b, sb = extract(pid_b, seq_b)
        good = [(s, o, d, p + delta) for s, o, d, p in sa] == sb
        if not good:
            raise ValueError('Proposed material relation not supported: ' + identity)
        return {'id': identity, 'description': description,
                'source_event_ids': [e['id'] for e in a], 'target_event_ids': [e['id'] for e in b],
                'source_sequences': seq_a, 'target_sequences': seq_b,
                'source_part': pid_a, 'target_part': pid_b,
                'semitone_shift': delta, 'exact_local_rhythm_and_shifted_pitch_match': good,
                'matched_encoded_events_per_side': len(a),
                'scope': 'specified_two_measure_melody_only_not_full_texture_identity',
                'human_signoff': None, 'expert_review': None}
    relations = [compare('I-viola-to-violin', 'P3', [3, 4], 'P1', [7, 8], 24,
                         '第一乐章3–4小节中提琴向7–8小节第一小提琴提高两个八度交接。'),
                 compare('II-violin-to-cello', 'P1', [181, 182], 'P4', [189, 190], -12,
                         '第二乐章3–4小节第一小提琴向11–12小节大提琴低八度交接。'),
                 compare('I-viola-return', 'P3', [3, 4], 'P3', [112, 113], 0,
                         '第一乐章112–113小节中提琴重现3–4小节旋律；不认定伴奏逐音相同。')]
    write(OUT / 'material-relations.json', {'relations': relations,
          'cross_movement_literal_identity': 'not_established', 'human_signoff': None})

    selected_pages = [1, 3, 4, 7, 8, 12, 14, 15, 16, 18, 19, 21, 22, 25, 28, 29, 31, 34]
    sources = [
        {'id': 'S', 'kind': 'user_supplied_score', **record(next(BASE.glob('*.pdf'))),
         'physical_pages': 34, 'reading': 'All page contact sheets; selected individual page images.',
         'individual_pages_examined': selected_pages,
         'cautions': ['PDF and XML may share one transcription lineage.',
                      'No independent all-note proofreading or notehead geometry certification.']},
        {'id': 'X', 'kind': 'user_supplied_musicxml', **record(next(BASE.glob('*.mxl'))),
         'declared_source': 'http://musescore.com/user/37221589/scores/8885439',
         'reading': 'Complete source-event inventory and local measure structure; selected pitches, articulations and material matches.',
         'transcription_review': 'not_a_critical_edition',
         'cautions': ['Written tie segments retained.', 'Tremolo intervals are encoding, not independently timed repeated attacks.',
                      'Octave-line and optional octave performance choices require visual and listening review.']},
        {'id': 'MIDI', 'kind': 'user_supplied_reference', **record(next(BASE.glob('*.mid'))),
         'reading': 'File identity only; no note-to-XML validation or performance timing.'},
        {'id': 'R01', 'author': 'Hartmut Schick', 'year': 1994,
         'title': "What's American About Dvorák's 'American' Quartet and Quintet?",
         'publication': 'Czech Music 18(2), 72–83', 'doi': '10.5282/ubm/epub.5755',
         'url': 'https://epub.ub.uni-muenchen.de/5755/1/5755.pdf',
         'read_scope': 'Selected text passages about compositional treatment and accompaniment; not all examples.',
         'access': 'online_pdf_text', 'use': 'limits on stylistic-origin attribution'},
        {'id': 'R02', 'author': 'Mark F. Rockwood', 'year': 2017,
         'title': 'Form, Style, and Influence in the Chamber Music of Antonin Dvořák',
         'publication': 'PhD dissertation, University of Oregon',
         'url': 'https://scholarsbank.uoregon.edu/bitstreams/d0d2b785-cf05-4264-b834-1f069d88e308/download',
         'read_scope': 'Title, table of contents; Op.96 passages around table 3.4 and printed pages 93–96, PDF physical105–108; extracted text, not full125 pages.',
         'use': 'contrasting first-movement formal readings and declining transition energy'},
        {'id': 'R03', 'author': 'Xieyi (Abby) Zhang', 'year': 2023,
         'title': 'Between Half and Perfect Cadences: The Modulating Antecedent in Dvořák’s Parallel Periods',
         'publication': 'Music Theory Online 29(1)', 'doi': '10.30535/mto.29.1.5',
         'url': 'https://www.mtosmt.org/issues/mto.23.29.1/mto.23.29.1.zhang.html',
         'read_scope': 'Abstract, paragraphs4.9–4.12, note34; example-caption inconsistency retained.',
         'use': 'finale phrase modulations and retrospective material hierarchy',
         'issue': 'Body says finale, example31–35 web captions say first movement; local finale69 Ab and123 return support body. Article example images not visually verified.'},
        {'id': 'R04', 'author': 'Mark J. McKone; David A. Beccue', 'year': 2021,
         'title': 'The Iowa Bird That Inspired Antonín Dvořák’s American String Quartet in 1893: Controversy over the Species’ Identity and Why It Matters',
         'publication': 'Nineteenth-Century Music Review 18, 521–537', 'doi': '10.1017/S1479409820000282',
         'url': 'https://doi.org/10.1017/S1479409820000282',
         'read_scope': 'Abstract; relevant species-comparison passages; sectionsF–G via PDF text. Not all article score images.',
         'use': 'attributed and conditional birdsong interpretation'},
        {'id': 'R05', 'author': 'Benedict Taylor', 'year': 2010,
         'title': "Modal Four-Note Pitch Collections in the Music of Dvořák's American Period",
         'publication': 'Music Theory Spectrum 32(1), 44–59', 'doi': '10.1525/mts.2010.32.1.44',
         'url': 'https://academic.oup.com/mts/article-abstract/32/1/44/1147057',
         'read_scope': 'Abstract and bibliographic record only', 'use': 'method lead, no bar-specific claims'},
        {'id': 'R06', 'author': 'Hartmut Schick', 'year': 1990,
         'title': 'Studien zu Dvořáks Streichquartetten',
         'url': 'https://epub.ub.uni-muenchen.de/5753/',
         'read_scope': 'Institutional catalogue only; no relevant monograph text read', 'use': 'future reading'},
        {'id': 'R07', 'author': 'Peter Jost', 'date': '2015-11-09',
         'title': 'Ein Böhme in Amerika: Hat Dvořáks F-dur-Streichquartett falsche Akzente?',
         'url': 'https://www.henle.de/blog/de/2015/11/09/ein-bohme-in-amerika-hat-dvoraks-f-dur-streichquartett-falsche-akzente/',
         'read_scope': 'Publisher full text returned by prior search, especially57–62; autograph illustration not inspected.',
         'kind': 'editorial_source_commentary_not_peer_reviewed_article', 'use': 'specific accent variant issue'},
        {'id': 'R08', 'author': 'Kelly Marie Fallon', 'year': 2014,
         'title': 'An “Alien Foundation”: The Eclectism of Antonin Dvorak’s American Period',
         'url': 'https://mds.marshall.edu/etd/858/',
         'read_scope': 'Abstract only', 'use': 'historical research lead, no musical conclusion'},
        {'id': 'R09', 'kind': 'composer_work_information',
         'url': 'https://www.antonin-dvorak.cz/en/work/string-quartet-no-12-in-f-major/',
         'read_scope': 'Work metadata and opening historical paragraphs', 'use': 'work identity only'}]
    write(OUT / 'sources.json', {'accessed_on': '2026-10-28', 'sources': sources,
          'external_pdf_local_downloads': [],
          'access_note': 'Shell downloads failed; research used accessible browser-tool text. No failed HTML saved as PDF.'})

    studies = json.loads((OUT / 'score-studies.json').read_text(encoding='utf8'))['windows']
    for w in studies:
        selected = w['selected_events']
        if any(e['id'] not in event_lookup for e in selected):
            raise ValueError('Unknown source event')
        q = F(w['offset_q'])
        if any(not (F(e['onset_q']) <= q < F(e['onset_q']) + F(e['duration_q'])) for e in selected):
            raise ValueError('Incorrect interval slice')
    # Verify local labels across parts and meter extents, keeping diagnostics rather than defaulting.
    from backend.musicxml_analysis.ingest import xml_root
    root, _ = xml_root(next(BASE.glob('*.mxl')))
    label_sequences = [[m.get('number') for m in p.findall('measure')] for p in root.findall('part')]
    if any(labels != label_sequences[0] for labels in label_sequences):
        raise ValueError('Part label sequence disagreement')
    mismatch = [r['sequence'] for r in rows if F(next(iter(r['part_extents_q'].values()))) !=
                F(r['meter']['beats']) * 4 / F(r['meter']['beat-type'])]
    signoff = {'human_signoff': None, 'expert_review': None}
    write(OUT / 'score-review.json', {'contact_sheets_examined_physical_pages': list(range(1, 35)),
          'individual_page_images_examined': selected_pages,
          'method': 'agent visual sampling plus source structural and specified local-note checks',
          'page_mapping': 'XML layout candidate supported by overview and selected page images; no notehead geometry',
          'meter_extent_diagnostics': mismatch,
          'octave_policy': 'MusicXML pitch values retained; source octave-shift directions remain in input, performance octave choices not certified.',
          'accent_case': {'movement': 3, 'measures': [57, 62],
                         'local_pdf_examined': 19, 'original_manuscript_not_examined': True,
                         'decision': 'retain user edition, record Jost variant without altering source'}, **signoff})
    summary = json.loads((OUT / 'symbolic-source-summary.json').read_text(encoding='utf8'))
    write(OUT.parent / 'project.json', {'id': 'dvorak-american',
          'title': '德沃夏克 第十二弦乐四重奏 美国', 'stage': 'full_score_editorial_analysis_draft',
          'source_directory': 'resource/American', 'movements': summary['movements'],
          'analysis_document': 'works/dvorak-american/analysis/full-analysis.md',
          'sources': 'works/dvorak-american/analysis/sources.json',
          'video_identity': 'filename says Stradivari Quartet; exact date and personnel unverified',
          'alignment': None, 'recording_projection': None, 'player_registration': False, **signoff})
    manifest = {'schema_version': 1, 'date': '2026-10-28', 'status': 'agent_full_score_analysis_draft',
                'sections': len(sections), 'sections_by_movement': dict(Counter(s['movement'] for s in sections)),
                'characters': len(text), 'xml_measures': len(rows), 'local_studies': len(studies),
                'exact_two_bar_material_checks': len(relations),
                'verification': {'ordered_exactly_once_editorial_coverage': True,
                                 'five_fields_per_section': True, 'all_window_note_ids_resolve': True,
                                 'half_open_local_windows_checked': True, 'part_label_sequences_equal': True,
                                 'meter_extent_diagnostics': mismatch},
                'recording_listening': 'not_performed', 'browser_playback': 'not_performed',
                'player_activation': False, 'recording_projection': None, **signoff,
                'code': [record(Path(__file__)), record(ROOT / 'scripts/build_dvorak_american_research.py')],
                'files': [record(p) for p in sorted(OUT.rglob('*')) if p.is_file() and p.name != 'manifest.json']}
    write(OUT / 'manifest.json', manifest)
    print(json.dumps({k: manifest[k] for k in ['sections', 'sections_by_movement', 'characters',
                                              'xml_measures', 'local_studies', 'verification']}, ensure_ascii=False))


if __name__ == '__main__':
    build()
