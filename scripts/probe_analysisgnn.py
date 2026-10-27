"""Successor-model comparison, using official weights and a separate Linux env."""
from pathlib import Path
import argparse
import sys
from fractions import Fraction as F

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'scripts')]
from backend.chordgnn_experiment import DATA,EXPERIMENT,read,write,fingerprint,verify_protected
from probe_chordgnn import make_score


def run(args):
    import numpy as np
    import torch
    torch.set_num_threads(4)
    sys.path.insert(0,str(args.upstream))
    if args.graphmuse_source:sys.path.insert(0,str(args.graphmuse_source))
    from analysisgnn.models.analysis import ContinualAnalysisGNN
    from analysisgnn.descriptors import select_features
    from analysisgnn.utils.music import PitchEncoder,KeySignatureEncoder
    from analysisgnn.utils.chord_representations import available_representations,SimpleRomanNumeral185
    from graphmuse import create_score_graph

    checkpoint=torch.load(args.checkpoint,map_location='cpu',weights_only=True)
    hp=checkpoint['hyper_parameters']
    model=ContinualAnalysisGNN(hp)
    model.load_state_dict(checkpoint['state_dict'],strict=True)
    model.eval()
    reps=dict(available_representations)
    # The DLC training label function uses 185 classes; the generic inference
    # script still points at the older 76-class decoder.
    if hp['task_dict']['romanNumeral']==185:reps['romanNumeral']=SimpleRomanNumeral185
    decoder_mismatches={}
    for task,rep in reps.items():
        if task in hp['task_dict'] and len(rep.classList)!=hp['task_dict'][task]:
            decoder_mismatches[task]={'checkpoint_classes':hp['task_dict'][task],
                'source_vocabulary_classes':len(rep.classList),'status':'decoding_disabled'}
    print('Strict checkpoint loaded; undecodable heads:',decoder_mismatches,flush=True)
    manifest=read(args.output/'manifest.json')
    verify_protected(manifest['protected_inputs'])
    results=[]
    live=read(ROOT/read(DATA/'playback/current.json')['path']/'live.json')
    for case_info in manifest['cases']:
        identity=case_info['id']
        case=read(args.output/'inputs'/f'{identity}.json')
        graph=read(args.output/'graphs'/f'{identity}.json')
        score,divisions,witnesses=make_score(case)
        arr=score.note_array(include_time_signature=True,include_pitch_spelling=True,
            include_key_signature=True,include_staff=True,include_metrical_position=True)
        arr=np.sort(arr,order=['onset_div','pitch'])
        # The checkpoint's 'simple' training branch uses voice features.
        feature_type='voice' if hp['feature_type']=='simple' else hp['feature_type']
        features=select_features(arr,feature_type)
        if features.shape!=(len(arr),hp['in_channels']) or not np.isfinite(features).all():
            raise ValueError('Checkpoint feature dimensions/values mismatch')
        data=create_score_graph(features,arr,measures=score[-1].measures,add_beats=True,labels=None)
        if not np.array_equal(data['note'].onset_div.numpy(),arr['onset_div']):
            raise ValueError('Graph node order changed')
        for kind in ('onset','consecutive','during'):
            edge=data['note',kind,'note'].edge_index.numpy()
            a,b=edge
            if kind=='onset':valid=arr['onset_div'][a]==arr['onset_div'][b]
            elif kind=='consecutive':valid=arr['onset_div'][a]+arr['duration_div'][a]==arr['onset_div'][b]
            else:valid=(arr['onset_div'][a]<arr['onset_div'][b]) & (arr['onset_div'][b]<arr['onset_div'][a]+arr['duration_div'][a])
            if not valid.all():raise ValueError('Invalid C graph edge relation: '+kind)
        pe=PitchEncoder().encode(arr);ke=KeySignatureEncoder().encode(arr)
        if pe.max()>=model.model.pitch_embedding.num_embeddings or ke.max()>=model.model.key_embedding.num_embeddings:
            raise ValueError('Pitch/key outside checkpoint vocabulary')
        data['note'].pitch_spelling=torch.from_numpy(pe).long()
        data['note'].key_signature=torch.from_numpy(ke).long()
        data['note'].batch=torch.zeros(len(arr),dtype=torch.long)
        with torch.inference_mode():
            logits=model.model(pitch_spelling=data['note'].pitch_spelling,
                key_signature=data['note'].key_signature,x_dict=data.x_dict,
                edge_index_dict=data.edge_index_dict,batch_dict=data.batch_dict,
                batch_size=len(arr),neighbor_mask_node=None,neighbor_mask_edge=None)
            probs={k:torch.softmax(v,dim=-1) for k,v in logits.items()}
        if any(not torch.isfinite(v).all() for v in probs.values()):
            raise ValueError('Non-finite model output')
        # Retain note-level model output. Averages below are explicitly a probe
        # aggregation, not the author's posthoc voter or final harmonic truth.
        note_preds=[]
        label_mask=probs['tpc_in_label'].argmax(-1).numpy()==1
        for i,n in enumerate(arr):
            unprefixed=str(n['id']).split('_',1)[-1] if str(n['id']).startswith('P') else str(n['id'])
            if unprefixed not in witnesses:raise ValueError('Source note ID lost')
            q=F(case['context_start_q'])+F(int(n['onset_div']),divisions)
            if not F(case['start_q'])<=q<F(case['end_q']):continue
            note_preds.append({'note_id':unprefixed,'source_event_ids':witnesses[unprefixed]['source_event_ids'],
                'score_q':str(q),'pitch':int(n['pitch']),
                'model_chord_tone':bool(label_mask[i]),
                'model_chord_tone_score':float(probs['tpc_in_label'][i,1]),
                'task_indices':{k:int(v[i].argmax()) for k,v in probs.items()}})
        onsets=[]
        for onset in graph['onsets']:
            indices=np.where(arr['onset_div']==onset['onset_div'])[0]
            selected=indices[label_mask[indices]]
            predictions={}
            if len(selected):
                for task in ('localkey','tonkey','root','quality','inversion','romanNumeral','pcset','bass'):
                    mean=probs[task][selected].mean(0)
                    values,inds=mean.topk(2)
                    predictions[task]={'value':None if task in decoder_mismatches else reps[task].classList[int(inds[0])],
                        'class_index':int(inds[0]),
                        'decode_status':'disabled_vocabulary_mismatch' if task in decoder_mismatches else 'source_vocabulary',
                        'uncalibrated_score':float(values[0]),
                        'alternative':None if task in decoder_mismatches else reps[task].classList[int(inds[1])],
                        'alternative_class_index':int(inds[1])}
            raw=set(onset['sounding_pitch_classes'])
            pcs=predictions.get('pcset',{}).get('value')
            if pcs=='None':pcs=None
            if pcs is not None and not isinstance(pcs,(tuple,list)):
                raise ValueError('Invalid decoded pitch class set')
            windows=[w for w in live['windows'].values() if w['measure_id']==onset['measure_id']
                and F(w['start_q'])<=F(onset['score_q'])<F(w['end_q'])]
            if len(windows)!=1:raise ValueError('Existing window missing/ambiguous')
            window=windows[0]
            row={**onset,'attacked_note_count':len(indices),'model_chord_tone_attacks':len(selected),
                'candidates':predictions,'existing_window_id':window['id'],
                'existing_chord':window['chord'],'existing_pitch_classes':window['pitch_classes'],
                'predicted_pcset_supported_now':None if pcs is None else set(pcs)<=raw,
                'extra_raw_pitch_classes':None if pcs is None else sorted(raw-set(pcs)),
                'missing_predicted_pitch_classes':None if pcs is None else sorted(set(pcs)-raw)}
            onsets.append(row)
        result={'id':identity,'model':'AnalysisGNN successor; not original ChordGNN',
            'status':'inferred_candidate_only','features':list(features.shape),
            'strict_checkpoint_load':True,'notes':note_preds,'onsets':onsets,
            'decoder_mismatches':decoder_mismatches,
            'aggregation':'Mean note-level softmax over chord-tone-classified attacks at each onset; no carry-forward; not author posthoc voter.',
            'limitations':['No human or expert ground truth; scores are not calibrated correctness probabilities.',
                'Pitch-class support is evidence screening, not harmonic accuracy. Missing pitches may be legitimate implied harmony.',
                'Excerpt context can change model results; pedal and reverberation are not inferred.']}
        write(args.output/'analysisgnn'/f'{identity}.json',result)
        summary={'id':identity,'onsets':len(onsets),'candidate_onsets':sum(bool(o['candidates']) for o in onsets),
            'no_chord_tone_onsets':sum(not o['candidates'] for o in onsets),
            'supported_pcset_onsets':sum(o['predicted_pcset_supported_now'] is True for o in onsets),
            'unsupported_pcset_onsets':sum(o['predicted_pcset_supported_now'] is False for o in onsets),
            'unknown_pcset_onsets':sum(bool(o['candidates']) and o['predicted_pcset_supported_now'] is None for o in onsets),
            'existing_unnamed_onsets':sum(not o['existing_chord'] for o in onsets),
            'attacked_notes':len(note_preds),'model_non_chord_tone_notes':sum(not n['model_chord_tone'] for n in note_preds)}
        results.append(summary);print(summary,flush=True)
    verify_protected(manifest['protected_inputs'])
    manifest['analysisgnn']={'status':'inferred_candidate_only','checkpoint':fingerprint(args.checkpoint),
        'summary':results,'feature_type':feature_type,'strict_checkpoint_load':True,
        'decoder_mismatches':decoder_mismatches,
        'activation':False,'human_signoff':None,'expert_review':None}
    manifest['status']='successor_inferred_original_model_weights_unavailable'
    write(args.output/'manifest.json',manifest)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,default=EXPERIMENT)
    p.add_argument('--upstream',type=Path,default=ROOT/'.tools/chordgnn/analysisgnn')
    p.add_argument('--checkpoint',type=Path,default=ROOT/'.tools/chordgnn/analysisgnn-checkpoint/model.ckpt')
    p.add_argument('--graphmuse-source',type=Path)
    run(p.parse_args())
