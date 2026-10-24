"""Structural checks, independent STFT diagnostics, and local review artifacts."""
import json
import os
from pathlib import Path
import time

ROOT=Path(__file__).resolve().parents[1]
os.environ.setdefault('NUMBA_CACHE_DIR',str(ROOT/'.tools/numba-cache'))
os.environ.setdefault('MPLCONFIGDIR',str(ROOT/'.tools/matplotlib'))
os.environ.setdefault('MPLBACKEND','Agg')
import numpy as np
import scipy.signal
import soundfile as sf
import librosa
import matplotlib.pyplot as plt
from midi_score import read_midi
from align_recording import save_json, digest


def main():
    started=time.perf_counter()
    path=ROOT/'alignment.json'
    result=json.loads(path.read_text(encoding='utf-8'))
    audio_file=ROOT/result['audio']['path']
    midi_file=ROOT/result['symbolic_reference']['path']
    assert digest(audio_file)==result['audio']['sha256']
    assert digest(midi_file)==result['symbolic_reference']['sha256']
    measures=result['measures']
    starts=np.array([m['start_seconds'] for m in measures])
    stops=np.array([m['end_seconds'] for m in measures])
    assert np.all(stops>starts) and np.all(np.diff(starts)>0)
    assert starts.min()>=0 and stops.max()<=result['audio']['duration_seconds']
    assert np.allclose(stops[:-1],starts[1:])
    assert len(set(m['measure_id'] for m in measures))==len(measures)
    print('Structural checks passed',flush=True)
    mapping=json.loads((ROOT/'measure-map.json').read_text(encoding='utf-8'))
    assert digest(ROOT/mapping['pdf_path'])==mapping['pdf_sha256']
    by_id={m['measure_id']:m for m in mapping['measures']}
    missing=[m['measure_id'] for m in measures if m['measure_id'] not in by_id]
    for m in mapping['measures']:
        x,y,w,h=m['rect_pt']
        assert 0<=x<x+w<=m['page_width_pt']+1
        assert 0<=y<y+h<=m['page_height_pt']+1
    print(f"PDF mapping: {len(by_id)} distinct bars, {len(missing)} missing",flush=True)
    wave,sr=sf.read(audio_file,dtype='float32',always_2d=True)
    mono=wave.mean(axis=1)
    import math
    divisor=math.gcd(sr,11025)
    low=scipy.signal.resample_poly(mono,11025//divisor,sr//divisor)
    cache=ROOT/'.tools/features'/f"{result['audio']['sha256'][:12]}-independent-stft-v1.npz"
    if cache.exists():
        with np.load(cache) as stored: chroma=stored['chroma']
    else:
        print('Extracting independent STFT chroma for diagnostics',flush=True)
        chroma=librosa.feature.chroma_stft(y=low,sr=11025,n_fft=4096,hop_length=1102,
            tuning=result['algorithm']['tuning_offset_cents']/100,norm=2)
        np.savez_compressed(cache,chroma=chroma)
    score=read_midi(midi_file)
    rate=11025/1102
    expected=np.zeros((12,int(np.ceil(score['duration']*rate))+1))
    for note in score['notes']:
        if note['is_drum']: continue
        first=int(note['start']*rate)
        last=int((note['start']+note['duration'])*rate)+1
        expected[note['pitch']%12,first:last]+=note['velocity']/127
    expected/=np.maximum(np.linalg.norm(expected,axis=0),1e-9)
    map_s=np.array([p['midi_seconds'] for p in result['time_map']])
    map_a=np.array([p['audio_seconds'] for p in result['time_map']])
    sample_s=np.arange(.5,score['duration']-.5,.25)
    sample_a=np.interp(sample_s,map_s,map_a)
    ref=expected[:,np.clip(np.round(sample_s*rate).astype(int),0,expected.shape[1]-1)]
    valid=np.linalg.norm(ref,axis=0)>.1
    similarities={}
    for shift in [0,-8,8,-16,16]:
        indices=np.clip(np.round((sample_a+shift)*rate).astype(int),0,chroma.shape[1]-1)
        similarities[shift]=np.sum(ref*chroma[:,indices],axis=0)
    negative=np.maximum.reduce([similarities[s] for s in [-8,8,-16,16]])
    for m in measures:
        selection=(sample_s>=m['midi_start_seconds'])&(sample_s<m['midi_end_seconds'])&valid
        if np.any(selection):
            m['quality_metrics']['independent_stft_cosine_median']=float(np.median(similarities[0][selection]))
            m['quality_metrics']['shifted_match_margin_median']=float(np.median((similarities[0]-negative)[selection]))
            if m['quality_metrics']['independent_stft_cosine_median']<.5:
                if 'weak_independent_pitch_evidence' not in m['flags']:
                    m['flags'].append('weak_independent_pitch_evidence')
                if m['review_status'] not in {'verified','corrected'}: m['review_status']='needs_review'
        else:
            m['quality_metrics'].pop('independent_stft_cosine_median',None)
            m['quality_metrics'].pop('shifted_match_margin_median',None)
            if 'insufficient_pitched_reference' not in m['flags']: m['flags'].append('insufficient_pitched_reference')
            if m['review_status'] not in {'verified','corrected'}: m['review_status']='needs_review'
        if m['sequence_index'] in [1,2,3,535]:
            if 'recording_edge_requires_listening' not in m['flags']:
                m['flags'].append('recording_edge_requires_listening')
            if m['review_status'] not in {'verified','corrected'}: m['review_status']='needs_review'
        if m['measure_id'] in by_id:
            mapped=by_id[m['measure_id']]
            m['pdf_mapping_status']='candidate_group' if mapped['resolution']!='bar' else 'candidate'
            m['printed_measure_number']=mapped['printed_measure_number']
            if mapped.get('geometry_clipped_to_page'):
                if 'pdf_geometry_extends_past_page' not in m['flags']:
                    m['flags'].append('pdf_geometry_extends_past_page')
                if m['review_status'] not in {'verified','corrected'}: m['review_status']='needs_review'
            if mapped['resolution']!='bar':
                if 'cadenza_pdf_region_has_no_separate_barlines' not in m['flags']:
                    m['flags'].append('cadenza_pdf_region_has_no_separate_barlines')
                if m['review_status'] not in {'verified','corrected'}: m['review_status']='needs_review'
        else:
            m['pdf_mapping_status']='missing'
            if 'pdf_coordinate_missing' not in m['flags']: m['flags'].append('pdf_coordinate_missing')
            if m['review_status'] not in {'verified','corrected'}: m['review_status']='needs_review'
    result['pdf_reference']={'path':mapping['pdf_path'],'sha256':mapping['pdf_sha256'],
        'mapping_file':'measure-map.json','correspondence_status':'numbering_and_geometry_candidate'}
    diagnostics={'method':'independent STFT audio chroma versus symbolic pitch classes',
        'not_ground_truth':True,'sample_rate':11025,'fft_length':4096,'hop_length':1102,
        'valid_pitched_samples':int(valid.sum()),'excluded_unpitched_samples':int((~valid).sum()),
        'median_aligned_cosine':float(np.median(similarities[0][valid])),
        'median_shifted_cosine':{str(s):float(np.median(similarities[s][valid])) for s in [-8,8,-16,16]},
        'fraction_beating_all_four_shifted_alternatives':float(np.mean((similarities[0]>negative)[valid])),
        'limitations':'Chroma cannot distinguish identical harmonies or establish note-accurate ground truth.'}
    result['quality']['independent_diagnostic']=diagnostics
    result['quality']['pdf_missing_measure_ids']=missing
    result['quality']['pdf_mapping_issues']=mapping['issues']
    result['quality']['human_verified_measures']=sum(m['review_status']=='verified' for m in measures)
    from collections import Counter
    result['quality']['flag_counts']=dict(Counter(f for m in measures for f in m['flags']))
    save_json(path,result)
    output=ROOT/'output/alignment'
    output.mkdir(parents=True,exist_ok=True)
    fig,axes=plt.subplots(3,1,figsize=(12,10),layout='constrained')
    axes[0].plot(map_s,map_a,label='MrMsDTW (chroma + DLNCO)',lw=1.2)
    axes[0].plot([0,score['duration']],[0,len(mono)/sr],':',label='Linear duration ratio (comparison only)')
    axes[0].set(xlabel='MIDI reference time (s)',ylabel='Recording time (s)',title='Ravel: full-recording alignment candidate')
    axes[0].legend()
    axes[1].plot(starts,[m['quality_metrics']['chroma_only_start_disagreement_seconds'] for m in measures],lw=.8)
    axes[1].axhline(2,color='darkorange',ls='--')
    axes[1].set(xlabel='Recording time (s)',ylabel='Variant disagreement (s)',title='Chroma-only vs chroma + onset: diagnostic, not accuracy')
    axes[2].plot(sample_a,similarities[0],lw=.3,alpha=.5,label='Independent STFT cosine')
    axes[2].set(xlabel='Recording time (s)',ylabel='Cosine similarity',ylim=(0,1),title='Independent feature check; no human ground truth')
    fig.savefig(output/'alignment-diagnostics.png',dpi=160)
    plt.close(fig)
    # Local review clips: left channel recording, right channel simple pitched
    # reference warped through the calculated path. These are not human-verified.
    clips=[]
    for label,first,last in [('opening',0,45),('cadenza',130,185),('ending',1080,1096)]:
        target_sr=22050
        original=scipy.signal.resample_poly(mono[int(first*sr):int(last*sr)],target_sr,sr)
        synth=np.zeros(len(original))
        for note in score['notes']:
            if note['is_drum']: continue
            a,b=np.interp([note['start'],note['start']+note['duration']],map_s,map_a)
            if b<first or a>last: continue
            begin=max(0,int((a-first)*target_sr)); end=min(len(synth),int((b-first)*target_sr))
            if end<=begin: continue
            t=np.arange(end-begin)/target_sr
            envelope=np.minimum(1,t/.008)*np.minimum(1,(t[-1]-t)/.025)
            synth[begin:end]+=np.sin(2*np.pi*440*2**((note['pitch']-69)/12)*t)*envelope*(note['velocity']/127)
        synth/=max(1,np.max(np.abs(synth)))
        original/=max(.01,np.max(np.abs(original)))
        clip_file=output/f'review-{label}.wav'
        sf.write(clip_file,np.column_stack([original*.8,synth*.6]),target_sr,subtype='PCM_16')
        clips.append({'path':clip_file.relative_to(ROOT).as_posix(),'recording_start_seconds':first,
                      'recording_end_seconds':last,'left':'recording (normalized)','right':'warped sine-note reference'})
    # Export playback-timed MIDI at a fixed file tempo. This is a listening aid,
    # not a replacement score with meaningful notated beat/measure positions.
    import mido
    source=mido.MidiFile(midi_file)
    from midi_score import TempoMap
    tempos=[]
    for track in source.tracks:
        tick=0
        for event in track:
            tick+=event.time
            if event.type=='set_tempo': tempos.append((tick,event.tempo))
    tempo=TempoMap(sorted(tempos),source.ticks_per_beat)
    performance=mido.MidiFile(type=1,ticks_per_beat=9600)
    conductor=mido.MidiTrack([mido.MetaMessage('set_tempo',tempo=500000,time=0)])
    performance.tracks.append(conductor)
    for track in source.tracks:
        output_track=mido.MidiTrack(); tick=0; previous_tick=0
        for event in track:
            tick+=event.time
            if event.type in {'set_tempo','time_signature','end_of_track'}: continue
            audio_sec=float(np.interp(tempo.at(tick),map_s,map_a))
            target_tick=round(audio_sec*19200)
            output_track.append(event.copy(time=max(0,target_tick-previous_tick)))
            previous_tick=target_tick
        output_track.append(mido.MetaMessage('end_of_track',time=0))
        performance.tracks.append(output_track)
    performance.save(output/'ravel-recording-timed.mid')
    loaded=mido.MidiFile(output/'ravel-recording-timed.mid')
    save_json(ROOT/'reports/alignment-validation.json',{'structural_checks_passed':True,
        'measure_count':len(measures),'pdf_distinct_measure_count':len(by_id),
        'pdf_missing':missing,'pdf_issues':mapping['issues'],'independent_diagnostic':diagnostics,
        'review_clips':clips,'playback_midi_reopened':True,'playback_midi_duration_seconds':loaded.length,
        'human_ground_truth_available':False,'elapsed_seconds':time.perf_counter()-started})
    print(json.dumps(diagnostics,indent=2),flush=True)
    print('Validation and local review artifacts saved',flush=True)


if __name__=='__main__': main()
