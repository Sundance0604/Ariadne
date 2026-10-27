"""Export a reviewable, non-active table of model candidates and raw support."""
from pathlib import Path
import csv
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from backend.chordgnn_experiment import EXPERIMENT,read,write


def summarize(folder=EXPERIMENT):
    manifest=read(folder/'manifest.json')
    rows=[];summaries=[]
    for case in manifest['cases']:
        path=folder/'analysisgnn'/f"{case['id']}.json"
        if not path.exists():raise FileNotFoundError('Actual model result missing: '+str(path))
        result=read(path)
        for onset in result['onsets']:
            preds=onset['candidates']
            rows.append({'case':case['id'],'movement':case['movement'],'bar':onset['bar'],
                'score_q':onset['score_q'],'recording_seconds':onset['recording_seconds'],
                'raw_pitch_classes':' '.join(map(str,onset['sounding_pitch_classes'])),
                'existing_chord':str(onset['existing_chord'] or ''),
                'model_pcset':str(preds.get('pcset',{}).get('value','')),
                'model_root':preds.get('root',{}).get('value',''),
                'model_localkey':preds.get('localkey',{}).get('value',''),
                'model_quality_index_undecoded':preds.get('quality',{}).get('class_index',''),
                'model_roman_index_undecoded':preds.get('romanNumeral',{}).get('class_index',''),
                'model_chord_tone_attacks':onset['model_chord_tone_attacks'],
                'attacked_notes':onset['attacked_note_count'],
                'pcset_supported_now':onset['predicted_pcset_supported_now'],
                'missing_predicted_pcs':str(onset['missing_predicted_pitch_classes']),
                'other_sounding_pcs':str(onset['extra_raw_pitch_classes'])})
        ons=result['onsets'];ns=result['notes']
        summaries.append({'id':case['id'],'onsets':len(ons),
            'raw_pc_count_min':min(len(o['sounding_pitch_classes']) for o in ons),
            'raw_pc_count_max':max(len(o['sounding_pitch_classes']) for o in ons),
            'over_three_raw_pcs':sum(len(o['sounding_pitch_classes'])>3 for o in ons),
            'no_candidate':sum(not o['candidates'] for o in ons),
            'supported_candidate':sum(o['predicted_pcset_supported_now'] is True for o in ons),
            'unsupported_candidate':sum(o['predicted_pcset_supported_now'] is False for o in ons),
            'baseline_unnamed':sum(not o['existing_chord'] for o in ons),
            'attacked_notes':len(ns),'model_excluded_attacks':sum(not n['model_chord_tone'] for n in ns)})
    with (folder/'comparison.csv').open('w',encoding='utf-8-sig',newline='') as handle:
        writer=csv.DictWriter(handle,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    write(folder/'comparison-summary.json',{'cases':summaries,
        'scope':'Model candidates and raw pitch support; no accuracy claim or player activation.'})
    print(summaries)


if __name__=='__main__':summarize()
