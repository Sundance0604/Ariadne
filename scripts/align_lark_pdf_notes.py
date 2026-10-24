"""Candidate diatonic solo-note correspondence, independent of MIDI bar numbers."""
import json
import sys
from pathlib import Path
import numpy as np
from numba import njit
from midi_score import read_midi

ROOT=Path(__file__).resolve().parents[1]
DATA=ROOT/'works/lark-ascending'


@njit
def match(pdf,midi):
    d=np.zeros((len(pdf)+1,len(midi)+1),np.float32)
    d[:,0]=np.arange(len(pdf)+1)*.7
    d[0,:]=np.arange(len(midi)+1)*.7
    for i in range(1,len(pdf)+1):
        for j in range(1,len(midi)+1):
            diff=abs(pdf[i-1]-midi[j-1])
            cost=0 if diff==0 else .15 if diff%7==0 else 1.2
            d[i,j]=min(d[i-1,j-1]+cost,d[i-1,j]+.7,d[i,j-1]+.7)
    pairs=[]
    i,j=len(pdf),len(midi)
    while i and j:
        diff=abs(pdf[i-1]-midi[j-1])
        cost=0 if diff==0 else .15 if diff%7==0 else 1.2
        vals=np.array([d[i-1,j-1]+cost,d[i-1,j]+.7,d[i,j-1]+.7])
        k=np.argmin(vals)
        if k==0:
            pairs.append((i-1,j-1));i-=1;j-=1
        elif k==1:i-=1
        else:j-=1
    return pairs,d[-1,-1]


def main():
    pdf=json.loads((DATA/'reports/pdf-solo-notes.json').read_text())
    score=read_midi(ROOT/'resource/Lark Ascending/lark-ascending.mid')
    midi=sorted([n for n in score['notes'] if n['track_index']==6],key=lambda n:(n['start_tick'],-n['pitch']))
    natural=[0,0,1,1,2,3,3,4,4,5,5,6]
    diatonic=np.array([(n['pitch']//12-1)*7+natural[n['pitch']%12] for n in midi])
    pairs,cost=match(np.array([n['diatonic'] for n in pdf]),diatonic)
    records=[]
    for i,j in reversed(pairs):
        records.append(dict(**pdf[i],midi_index=j,tick=midi[j]['start_tick'],
                            midi_seconds=midi[j]['start'],pitch=midi[j]['pitch'],
                            exact_diatonic=bool(pdf[i]['diatonic']==diatonic[j]),
                            same_letter=bool(pdf[i]['diatonic']%7==diatonic[j]%7)))
    report=dict(method='global_diatonic_note_sequence_edit_alignment',
                pdf_notes=len(pdf),midi_solo_notes=len(midi),cost=float(cost),
                matched_note_pairs=len(records),
                exact_diatonic_pairs=sum(n['exact_diatonic'] for n in records),
                same_letter_pairs=sum(n['same_letter'] for n in records),
                limitations=['Accidentals ignored; octave signs matched with a small penalty.',
                             'This is candidate note correspondence, not proof of score edition identity.'],notes=records)
    (DATA/'reports/pdf-note-correspondence.json').write_text(json.dumps(report,indent=2),encoding='utf8')
    print({k:v for k,v in report.items() if k!='notes'})
    for key in sorted(set((r['page_number'],r['system_index']) for r in records)):
        notes=[r for r in records if (r['page_number'],r['system_index'])==key]
        print(key,notes[0]['printed_system_start'],notes[0]['tick'],
              next(m['sequence_index'] for m in score['measures'] if m['score_start_tick']<=notes[0]['tick']<m['score_end_tick']),
              round(sum(r['same_letter'] for r in notes)/len(notes),3))


if __name__=='__main__':main()
