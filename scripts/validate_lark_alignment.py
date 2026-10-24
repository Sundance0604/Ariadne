"""Independent acoustic diagnostics and review clips for the Lark candidate."""
import os
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
os.environ.setdefault('NUMBA_CACHE_DIR',str(ROOT/'.tools/numba-cache'))
os.environ.setdefault('MPLCONFIGDIR',str(ROOT/'.tools/matplotlib'))
os.environ.setdefault('MPLBACKEND','Agg')
import json
import hashlib
from collections import Counter
import numpy as np
import scipy.signal
import soundfile as sf
import librosa
import matplotlib.pyplot as plt
from midi_score import read_midi

DATA=ROOT/'works/lark-ascending'


def main():
    alignment=json.loads((DATA/'alignment.json').read_text(encoding='utf8'))
    mapping=json.loads((DATA/'measure-map.json').read_text(encoding='utf8'))
    audio=ROOT/alignment['audio']['path']
    midi=ROOT/alignment['symbolic_reference']['path']
    assert hashlib.sha256(audio.read_bytes()).hexdigest()==alignment['audio']['sha256']
    assert hashlib.sha256(midi.read_bytes()).hexdigest()==alignment['symbolic_reference']['sha256']
    assert hashlib.sha256((ROOT/mapping['pdf_path']).read_bytes()).hexdigest()==mapping['pdf_sha256']
    measures=alignment['measures']
    assert len(measures)==len(mapping['measures'])==309
    assert set(m['page_number'] for m in mapping['measures'])==set(range(1,36))
    assert all(m['end_seconds']>m['start_seconds'] for m in measures)
    assert all(abs(x['end_seconds']-y['start_seconds'])<1e-7 for x,y in zip(measures,measures[1:]))
    for m in mapping['measures']:
        x,y,w,h=m['rect_pt']
        assert 0<=x<x+w<=m['page_width_pt'] and 0<=y<y+h<=m['page_height_pt']
    wave,sr=sf.read(audio,dtype='float32',always_2d=True)
    mono=wave.mean(axis=1)
    assert abs(len(mono)/sr-alignment['audio']['duration_seconds'])<.001
    low=scipy.signal.resample_poly(mono,1,4)
    chroma=librosa.feature.chroma_stft(y=low,sr=11025,n_fft=4096,hop_length=1102,
                                     tuning=alignment['algorithm']['tuning_offset_cents']/100,norm=2)
    score=read_midi(midi)
    rate=11025/1102
    expected=np.zeros((12,int(np.ceil(score['duration']*rate))+1))
    for n in score['notes']:
        if not n['is_drum']:
            expected[n['pitch']%12,int(n['start']*rate):int((n['start']+n['duration'])*rate)+1]+=n['velocity']/127
    expected/=np.maximum(np.linalg.norm(expected,axis=0),1e-9)
    map_s=np.array([p['midi_seconds'] for p in alignment['time_map']])
    map_a=np.array([p['audio_seconds'] for p in alignment['time_map']])
    sample_s=np.arange(.5,score['duration']-.5,.25)
    sample_a=np.interp(sample_s,map_s,map_a)
    ref=expected[:,np.clip(np.round(sample_s*rate).astype(int),0,expected.shape[1]-1)]
    valid=np.linalg.norm(ref,axis=0)>.1
    similarities={shift:np.sum(ref*chroma[:,np.clip(np.round((sample_a+shift)*rate).astype(int),0,chroma.shape[1]-1)],axis=0)
                  for shift in [0,-8,8,-16,16]}
    shifted=np.maximum.reduce([similarities[s] for s in [-8,8,-16,16]])
    groups={}
    for name,first,last in [('opening',0,170),('middle',350,650),('ending',880,len(mono)/sr)]:
        selection=(sample_a>=first)&(sample_a<last)&valid
        groups[name]=dict(valid_samples=int(selection.sum()),
            aligned_cosine_median=float(np.median(similarities[0][selection])),
            fraction_beating_four_shifted_alternatives=float(np.mean((similarities[0]>shifted)[selection])))
    for m in measures:
        selection=(sample_s>=m['midi_start_seconds'])&(sample_s<m['midi_end_seconds'])&valid
        if selection.any():
            value=float(np.median(similarities[0][selection]))
            m['quality_metrics']['independent_stft_cosine_median']=value
            m['quality_metrics']['shifted_match_margin_median']=float(np.median((similarities[0]-shifted)[selection]))
            if value<.5 and 'weak_independent_pitch_evidence' not in m['flags']:
                m['flags'].append('weak_independent_pitch_evidence');m['review_status']='needs_review'
        if m['sequence_index'] in {1,2,309}:
            if 'recording_edge_requires_listening' not in m['flags']:m['flags'].append('recording_edge_requires_listening')
            m['review_status']='needs_review'
    diagnostic=dict(method='independent STFT chroma vs symbolic pitch classes',not_ground_truth=True,
        sample_rate=11025,fft_length=4096,hop_length=1102,valid_pitched_samples=int(valid.sum()),
        median_aligned_cosine=float(np.median(similarities[0][valid])),
        median_shifted_cosine={str(s):float(np.median(similarities[s][valid])) for s in [-8,8,-16,16]},
        fraction_beating_all_four_shifted_alternatives=float(np.mean((similarities[0]>shifted)[valid])),regions=groups,
        limitations='Chroma similarity cannot resolve repeated notes, identical harmonies or note-accurate timing.')
    alignment['quality']['independent_diagnostic']=diagnostic
    alignment['quality']['flag_counts']=dict(Counter(f for m in measures for f in m['flags']))
    alignment['quality']['human_verified_measures']=0
    alignment['pdf_reference']=dict(path=mapping['pdf_path'],sha256=mapping['pdf_sha256'],
        mapping_file='works/lark-ascending/measure-map.json',correspondence_status='contour_and_geometry_candidate')
    (DATA/'alignment.json').write_text(json.dumps(alignment,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    output=DATA/'output';output.mkdir(exist_ok=True)
    clips=[]
    for name,first,last in [('opening',0,55),('middle',455,490),('ending',930,977.893)]:
        original=scipy.signal.resample_poly(mono[int(first*sr):int(last*sr)],1,2)
        synth=np.zeros(len(original));target_sr=22050
        for note in score['notes']:
            if note['is_drum']:continue
            a,b=np.interp([note['start'],note['start']+note['duration']],map_s,map_a)
            begin=max(0,int((a-first)*target_sr));end=min(len(synth),int((b-first)*target_sr))
            if end<=begin:continue
            t=np.arange(end-begin)/target_sr
            envelope=np.minimum(1,t/.008)*np.minimum(1,(t[-1]-t)/.025)
            synth[begin:end]+=np.sin(2*np.pi*440*2**((note['pitch']-69)/12)*t)*envelope*(note['velocity']/127)
        original/=max(.01,np.max(np.abs(original)));synth/=max(1,np.max(np.abs(synth)))
        destination=output/f'review-{name}.wav'
        sf.write(destination,np.column_stack([original*.8,synth*.6]),target_sr,subtype='PCM_16')
        clips.append(dict(path=destination.relative_to(ROOT).as_posix(),recording_start_seconds=first,
                          recording_end_seconds=last,left='normalized recording',right='warped sine-note reference'))
    fig,axes=plt.subplots(2,1,figsize=(11,7),layout='constrained')
    axes[0].plot(map_s,map_a,lw=1,label='MrMsDTW')
    axes[0].plot([0,score['duration']],[0,len(mono)/sr],':',label='linear comparison only')
    axes[0].set(xlabel='MIDI seconds',ylabel='Recording seconds',title='The Lark Ascending: candidate alignment');axes[0].legend()
    axes[1].plot(sample_a,similarities[0],lw=.4)
    axes[1].set(xlabel='Recording seconds',ylabel='Independent STFT cosine',ylim=(0,1))
    fig.savefig(output/'alignment-diagnostics.png',dpi=140);plt.close(fig)
    report=dict(structural_checks_passed=True,measure_count=309,pdf_page_count=35,pdf_system_count=53,
                decoded_audio_frames=len(mono),decoded_audio_sample_rate=sr,decoded_audio_duration_seconds=len(mono)/sr,
                independent_diagnostic=diagnostic,review_clips=clips,human_ground_truth_available=False,
                review_counts=dict(Counter(m['review_status'] for m in measures)))
    (DATA/'reports/alignment-validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print(json.dumps(report,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
