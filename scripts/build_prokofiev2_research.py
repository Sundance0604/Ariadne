"""Score-only Prokofiev II evidence; local bars, existing harmony identity method.

No common full-score clock, recording projection or player activation is made.
"""
from collections import Counter,defaultdict
from fractions import Fraction as F
import hashlib,json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'scripts')]
from backend.musicxml_analysis.ingest import xml_root,pitch_record
from backend.musicxml_analysis.analyze import chord_description
from compare_mother_goose_sources import xml_events,file_record

BASE=ROOT/'resource/PROKOFIEV PIANO CONCERTO 2'
WORK=ROOT/'works/prokofiev-piano-concerto-2'
OUT=WORK/'analysis'
SOURCE=BASE/'piano-concerto-no2-op16-s-prokofiev.mxl'
MOVEMENTS=[(1,1,200,'Andantino',1,37),(2,201,387,'Scherzo Vivace',38,69),
           (3,388,546,'Intermezzo Allegro moderato',70,108),(4,547,864,'Finale Allegro tempestoso',109,168)]


def write(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf8')


def build():
    import music21 as m21
    from music21.musicxml.xmlToM21 import MeasureParser
    OUT.mkdir(parents=True,exist_ok=True)
    source_record=file_record(SOURCE)
    protected=[ROOT/'library.json',ROOT/'alignment.json',ROOT/'measure-map.json',
        ROOT/'works/ravel-mother-goose-video/playback/current.json',
        ROOT/'works/ravel-mother-goose-video/alignment.json',
        ROOT/'works/ravel-mother-goose-video/video-export/captions-optimized.json']
    before=[file_record(p) for p in protected]
    data=xml_events(SOURCE);root,_=xml_root(SOURCE);parser=MeasureParser()
    parts={p['id']:p['name'] for p in data['parts']}
    elements={};transpositions={};directions=defaultdict(list)
    for part in root.findall('part'):
        current={};pid=part.get('id')
        for seq,measure in enumerate(part.findall('measure'),1):
            for attr in measure.findall('attributes'):
                for t in attr.findall('transpose'):current[t.get('number','all')]=parser.xmlTransposeToInterval(t)
            transpositions[(pid,seq)]=dict(current)
            for n,note in enumerate(measure.findall('note'),1):elements[f'{pid}-xml-m{seq:04d}-n{n:04d}']=note
            for direction in measure.findall('direction'):
                words=[e.text for e in direction.findall('direction-type/words') if e.text]
                words=[w for w in words if any(ch.isalpha() for ch in w)]
                if words:directions[seq].append({'part_id':pid,'words':words})
    eligible=[e for e in data['events'] if e['eligible'] and e['part_id']!='P14']
    by_measure=defaultdict(list)
    for e in eligible:by_measure[e['sequence']].append(e)
    audit=json.loads((WORK/'reports/source-audit-20261027.json').read_text(encoding='utf8'))
    if source_record['sha256']!=audit['mxl']['sha256']:
        raise ValueError('Source differs from the audited edition; reassess before rebuilding')
    if parts.get('P14')!='Ossia' or parts.get('P15')!='Piano':
        raise ValueError('Audited source part identities changed')
    large=set(audit['timing_review_classification']['large_extent_difference_sequences'])
    small=set(audit['timing_review_classification']['small_extent_difference_sequences'])
    indices=[];page=1
    for seq,measure in enumerate(root.find('part').findall('measure'),1):
        printing=measure.find('print')
        if printing is not None and printing.get('new-page')=='yes':page+=1
        mv=next(x for x in MOVEMENTS if x[1]<=seq<=x[2])
        indices.append({'measure_id':f'xml-m{seq:04d}','sequence':seq,'movement':mv[0],
            'local_number':measure.get('number'),'implicit':measure.get('implicit')=='yes',
            'xml_layout_page':page,'pdf_page_status':'layout_reference_not_independent_measure_geometry',
            'rehearsals':[x.text for x in measure.findall('.//rehearsal')],
            'directions':directions[seq],
            'pitched_note_counts_by_part':dict(Counter(e['part_id'] for e in by_measure[seq])),
            'timing_review':'large_disagreement_no_vertical_inference' if seq in large else
                'small_rounding_disagreement_review_required' if seq in small else 'not_flagged_by_existing_structure_audit'})
    write(OUT/'measure-index.json',{'source':source_record,'parts':parts,'measures':indices,
        'limitations':['Eligible note presence is not an independent-voice count or acoustic activity.',
            'P14 Ossia, hidden notes, grace notes without duration, rests and unpitched events excluded from pitch counts.',
            'All clocks remain local to individual XML measures; no cumulative global or recording clock.']})

    def enrich(e):
        note=elements[e['id']];p=note.find('pitch');encoded=m21.pitch.Pitch()
        encoded.step=p.findtext('step');encoded.octave=int(p.findtext('octave'));encoded.accidental=float(p.findtext('alter','0'))
        ts=transpositions[(e['part_id'],e['sequence'])]
        t=ts.get(e['staff'],ts.get('all'))
        concert=encoded.transpose(t) if t else encoded
        if F(str(concert.ps))!=F(e['concert_ps']):raise ValueError('Pitch transposition audit failed: '+e['id'])
        return {**e,'part_name':parts[e['part_id']],'encoded_pitch':pitch_record(encoded),
            'concert_pitch':pitch_record(concert),'tie':[x.get('type') for x in note.findall('tie')],
            'notations_xml': [__import__('xml.etree.ElementTree',fromlist=['tostring']).tostring(x,encoding='unicode') for x in note.findall('notations')]}

    def window(identity,seq,offset,selected_parts=None):
        if seq in large:raise ValueError('Known faulty local timing cannot enter a vertical study')
        q=F(offset)
        active=[enrich(e) for e in by_measure[seq] if F(e['onset_q'])<=q<F(e['onset_q'])+F(e['duration_q'])]
        chosen=[e for e in active if selected_parts is None or e['part_id'] in selected_parts]
        other=[e for e in active if e not in chosen]
        return {'id':identity,'sequence':seq,'measure_id':f'xml-m{seq:04d}',
            'movement':indices[seq-1]['movement'],'local_number':indices[seq-1]['local_number'],
            'offset_q':str(q),'xml_layout_page':indices[seq-1]['xml_layout_page'],
            'selected_parts':selected_parts,'selected_events':chosen,'other_active_events':other,
            'sonority':chord_description(chosen),'all_active_event_ids':[e['id'] for e in active],
            'source_timing_review':indices[seq-1]['timing_review'],
            'status':'local_xml_candidate_with_source_witnesses_not_final_functional_harmony',
            'human_signoff':None,'expert_review':None}
    windows=[window('I-initial-rest',1,0),window('I-first-sounding-attack',1,'3/2'),window('I-second-intro-bar',2,0),
        window('I-piano-accompaniment-entry',3,0,['P15']),window('I-narrante-bar-start',4,0,['P15']),
        window('I-narrante-right-hand-entry',4,3,['P15']),
        window('II-opening-attack',201,0),window('II-opening-second-attack',201,'1/4'),
        window('II-trio-entry',280,0),window('II-inner-section',304,0),
        window('III-march-onset',388,0),window('III-central-melody',477,0),
        window('IV-opening-attack',547,0),window('IV-lullaby-solo-entry',629,0,['P15']),
        window('IV-R116-start',734,0),window('IV-low-pulse',735,0),
        window('IV-flat-side-low-note',737,1),window('IV-flat-side-chord',737,2),window('IV-unison-after-flat-side',738,0),
        window('IV-penultimate-page-chord',862,0),window('IV-last-full-ensemble-bar',863,0),
        window('IV-last-bar',864,0)]
    write(OUT/'score-studies.json',{'method':'Existing backend.musicxml_analysis.analyze.chord_description, unchanged.',
        'policy':'Half-open local written intervals; full octave spelling; explicit XML transpose once; no GNN.',
        'windows':windows,'limitations':['Local pitch identities are not chord functions or cadences.',
            'Only stated offsets are computed; whole-bar arpeggio unions are never labelled simultaneous.',
            'Pedal, tremolo, ornaments and acoustic resonance are not reconstructed.']})
    write(OUT/'symbolic-source-summary.json',{'source':source_record,'parts':data['parts'],
        'pitched_events':len(data['events']),'eligible_non_ossia_events':len(eligible),
        'excluded_pitched_events':len(data['events'])-len(eligible),'parser_anomalies':data['anomalies'],
        'large_timing_quarantine_sequences':sorted(large),'small_rounding_review_sequences':sorted(small),
        'existing_audit':file_record(WORK/'reports/source-audit-20261027.json'),
        'global_score_time':None,'audio_projection':None})
    if [file_record(p) for p in protected]!=before or file_record(SOURCE)!=source_record:
        raise ValueError('Protected source/playback input changed')
    write(OUT/'build-audit.json',{'source':source_record,'protected_files':before,
        'code':[file_record(ROOT/p) for p in ['scripts/build_prokofiev2_research.py',
            'scripts/compare_mother_goose_sources.py','backend/musicxml_analysis/ingest.py','backend/musicxml_analysis/analyze.py']],
        'music21_version':m21.__version__,'harmony_method':'existing chord_description unchanged',
        'clock':'measure-local only','player_activation':False,'human_signoff':None,'expert_review':None})
    print('Source local evidence:',len(indices),'measures;',len(eligible),'eligible notes;',len(windows),'local windows')
    for w in windows:print(w['id'],w['sonority']['label'],w['sonority'].get('spelled_pitches',[]))


if __name__=='__main__':build()
