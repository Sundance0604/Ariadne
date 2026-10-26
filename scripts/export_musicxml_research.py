"""Export readable ledgers and selected musical witnesses from the current XML run."""
import csv
from collections import Counter
from fractions import Fraction as F
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from backend.musicxml_analysis.store import load_bundle,measure_evidence
from backend.structure_analysis.common import write,digest


def export(root=ROOT):
    bundle=load_bundle(root,root)
    if not bundle:raise ValueError('No MusicXML run')
    folder=root/'output/research/ravel-musicxml';folder.mkdir(parents=True,exist_ok=True)
    def csv_file(name,headers,rows):
        with (folder/name).open('w',encoding='utf-8-sig',newline='') as f:
            writer=csv.writer(f);writer.writerow(headers);writer.writerows(rows)
    notes=bundle['tables']['events']['events'];names={p['id']:p['name'] for p in bundle['tables']['parts']['parts']}
    instruments={i['id']:i['name'] for p in bundle['tables']['parts']['parts'] for i in p['score_instruments']}
    csv_file('note-events.csv',['event_id','part_id','instrument','xml_measure_id','source_note_index','voice','staff','kind',
        'onset_quarters','duration_quarters','written_pitch','encoded_pitch','concert_pitch','transpose_semitones','tie',
        'analysis_eligible','exclusion_reason','articulations','technique_context','instrument_ref','source_instrument_name','stem','beams'],[
        [e['id'],e['part_id'],names[e['part_id']],e['measure_id'],e['source_note_index'],e['voice'],e['staff'],e['kind'],
        e['onset_q'],e['duration_q'],(e['written_pitch'] or {}).get('name'),(e['encoded_pitch'] or {}).get('name'),
        (e['concert_pitch'] or {}).get('name'),e['transpose']['semitones'],'+'.join(e['tie']),e['analysis_eligible'],
        e['exclusion_reason'],'+'.join(e['articulations']),e['technique_context'],e.get('instrument_ref'),instruments.get(e.get('instrument_ref')),e.get('stem'),
        ';'.join((b.get('number') or '')+':'+(b['value'] or '') for b in e.get('beams',[]))] for e in notes])
    csv_file('harmonic-ledger.csv',['window_id','xml_measure_id','onset_quarters','end_score_quarters','label','bass','root',
        'inversion_0_to_3','pitch_classes','conditional_roman','event_ids'],[
        [w['id'],w['measure_id'],w['onset_q'],w['end_q'],w['sonority']['label'],w['sonority']['bass']['name'],
        (w['sonority']['chord'] or {}).get('root'),(w['sonority']['chord'] or {}).get('inversion'),
        ' '.join(map(str,w['sonority']['pitch_classes'])),'; '.join(k['context']+':'+k['roman'] for k in w['roman_hypotheses']),
        ' '.join(w['event_ids'])] for w in bundle['tables']['harmony']['windows']])
    rows=[]
    for m in bundle['tables']['orchestration']['measures']:
        active={p['part_id']:p for p in m['parts']}
        for pid,name in names.items():
            p=active.get(pid)
            rows.append([m['measure_id'],pid,name,bool(p),'–'.join(p['range']) if p and p['range'] else '',
                p['attack_count'] if p else 0,'; '.join(p['role_observations']) if p else 'rest',
                '; '.join(p['written_techniques']) if p else '', ' '.join(p['event_ids']) if p else ''])
    csv_file('instrument-activity.csv',['xml_measure_id','part_id','instrument','active','concert_range','attacks',
        'role_observations','last_written_technique_context','event_ids'],rows)
    csv_file('voice-intervals.csv',['relation_id','xml_measure_id','voice_a','voice_b','pitch_a','pitch_b','interval',
        'semitones','start_score_quarters','end_score_quarters','event_ids'],[
        [r['id'],r['measure_id'],*r['voices'],*r['pitches'],r['interval'],r['semitones'],r['start_q'],r['end_q'],' '.join(r['event_ids'])]
        for r in bundle['tables']['counterpoint']['intervals']])
    selected={mid:measure_evidence(bundle,mid) for mid in ['xml-m0001','xml-m0011','xml-m0063','xml-m0064','xml-m0126','xml-m0251','xml-m0520','xml-m0535']}
    # A compact case packet retains the actual complete event membership, not just prose.
    packet={'run_path':bundle['run_path'],'source':bundle['manifest']['source'],'cases':[]}
    for mid,at in [('xml-m0001','0'),('xml-m0011','0'),('xml-m0063','7/4'),('xml-m0064','0'),
        ('xml-m0126','0'),('xml-m0251','0'),('xml-m0520','2'),('xml-m0520','11/4'),('xml-m0535','2')]:
        d=selected[mid];m=d['measure'];ns=[e for e in d['events'] if e['analysis_eligible'] and F(e['onset_q'])<=F(at)<F(e['onset_q'])+F(e['duration_q'])]
        h=next(w for w in d['harmony'] if F(w['onset_q'])<=F(at)<F(w['end_q'])-F(m['start_q']))
        packet['cases'].append({'measure_id':mid,'onset_q':at,'window_id':h['id'],'sonority':h['sonority'],
            'roman_hypotheses':h['roman_hypotheses'],'events':ns,'human_signoff':'pending',
            'basis':'full eligible pitched XML events at the specified half-open notated time; no pedal acoustic model'})
    write(folder/'selected-case-evidence.json',packet)
    write(folder/'export-manifest.json',{'run_path':bundle['run_path'],'source':bundle['manifest']['source'],
        'files':{p.name:{'sha256':digest(p),'bytes':p.stat().st_size} for p in folder.iterdir() if p.name!='export-manifest.json'},
        'status':'computed evidence exports; not independent human review'})
    print('Exported note, harmony, orchestration, voice ledgers and full-event case evidence to',folder)


if __name__=='__main__':export()
