"""Classify existing diagnostics; never change matches, audio clocks or scores."""
import argparse
from collections import Counter
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from backend.structure_analysis.common import read,digest,write,bounded_path
from backend.structure_analysis.store import validate_run

CATEGORIES={'percussion':'打击乐','tremolo':'震音记谱／展开','octave':'八度','transposition':'移调疑点',
    'rhythm':'节奏、延续或装饰展开','pedal':'踏板／发声延续疑点','confirmed_error':'已证实错误','unresolved':'证据不足，保留未分类'}


def classify(run):
    run=Path(run);notes=read(run/'notes.json')['notes'];pdf=read(run/'pdf-observations.json');heads={h['id']:h for h in pdf['notes']}
    correspondence=read(run/'correspondence.json');records=[]
    def add(id,kind,category,basis,**extra):
        records.append({'id':id,'record_kind':kind,'category':category,'basis':basis,
            'status':'diagnostic_classification_not_verified_error','automatic_action':'none',**extra})
    for n in notes:
        if n['score_locations'] and n['correspondence']['octave_agrees']:continue
        if n['score_locations']:
            add(n['id'],'midi_note','octave','Decoded/source-reference octave differs; may still be a pairing error.',part_id=n['part_id']);continue
        peers=[h for h in heads.values() if h['part_id']==n['part_id'] and n['midi_measure_candidate'] in h['midi_measure_candidates']]
        if n['is_drum'] or n['part_id']=='timpani':
            category,basis='percussion','Percussion: preserve pitched timpani and unpitched-channel references separately.'
        elif any(m['part_id']==n['part_id'] and m['kind']=='written_text' and 'gliss' in m['value'].lower()
            and any(h['page']==m['page'] and h['physical_system_index']==m['physical_system_index'] for h in peers) for m in pdf['marks']):
            category,basis='rhythm','Explicit glissando and expanded reference attacks; not classified as tremolo.'
        elif any(h['written_pitch_candidate']==n['pitch'] and h['concert_pitch_candidate']!=n['pitch'] for h in peers):
            category,basis='transposition','Written-pitch candidate equals reference while concert pitch differs; hypothesis only.'
        elif n['sounding_end_tick']>n['key_end_tick']:
            category,basis='pedal','Reference sustain extends key interval; not proof that pedal caused the missing correspondence.'
        else:category,basis='unresolved','No sufficient notation evidence to assign a cause.'
        add(n['id'],'midi_note',category,basis,part_id=n['part_id'],pitched=not n['is_drum'])
    tremolo_ids={id for m in pdf['marks'] if m['kind'] in {'single_chord_tremolo_candidate','two_note_tremolo_candidate'}
        for id in m.get('head_ids',[])+m.get('left_head_ids',[])+m.get('right_head_ids',[])}
    for id in correspondence['unmatched_pdf_head_ids']:
        h=heads[id];peers=[n for n in notes if n['part_id']==h['part_id'] and n['midi_measure_candidate'] in h['midi_measure_candidates']]
        if id in tremolo_ids:category,basis='tremolo','Native tremolo head; many-to-one realization or continuation needs review.'
        elif any(n['pitch']==h['concert_pitch_candidate'] for n in peers):category,basis='rhythm','Same local pitch exists; tied/repeated notation or event order is a hypothesis, not a confirmed error.'
        else:category,basis='unresolved','No sufficient duration, transposition or voice evidence; leave unassigned.'
        add(id,'pdf_head',category,basis,part_id=h['part_id'],page=h['page'])
    counts=Counter(r['category'] for r in records)
    return {'categories':CATEGORIES,'counts':{k:counts[k] for k in CATEGORIES},'records':records,
        'scope':'MIDI missing/contested records and unmatched PDF heads; categories are diagnostic hypotheses, not new correspondences.',
        'automatic_corrections':0,'research_gate':'none; meaningful score studies do not require these counts to reach zero',
        'closed_implementation_errors':[{'id':'stem-as-barline','category':'confirmed_error','status':'fixed_previous_round','evidence':'tests/test_notation_rules.py'},
            {'id':'bassa-staff-assignment','category':'confirmed_error','status':'fixed_previous_round','evidence':'tests/test_notation_rules.py'}],
        'error_note':'Closed implementation defects are distinct from current unclassified score/reference records. No unreviewed input error is certified.'}


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--run',required=True);parser.add_argument('--output',required=True);args=parser.parse_args()
    run=bounded_path(ROOT,args.run);output=bounded_path(ROOT,args.output)
    if output.is_relative_to(run):raise ValueError('Do not write diagnostics into frozen run')
    if output.exists():raise ValueError('Preserve old diagnostic classification; choose a new output')
    validate_run(run,ROOT);result=classify(run);result['run_path']=args.run;result['manifest_sha256']=digest(run/'manifest.json');write(output,result)
    print('Diagnostic records classified; no matching or transcription changed.')


if __name__=='__main__':main()
