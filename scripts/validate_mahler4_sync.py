"""Independent pitch diagnostics for the existing Mahler 4 video alignment.

This checks pitch-class support with STFT chroma, not the alignment engine's
filterbank. Scores are diagnostic similarities, never accuracy probabilities.
It writes a separate report and does not mutate the alignment under review.
"""
from collections import Counter
import json
import math
import os
from pathlib import Path
import sys

import numpy as np
import scipy.signal
import soundfile as sf

from midi_score import read_midi

ROOT=Path(__file__).resolve().parents[1]
DATA=ROOT/'works/mahler-4'
os.environ.setdefault('NUMBA_CACHE_DIR',str(ROOT/'.tools/numba-cache'))
os.environ.setdefault('MPLCONFIGDIR',str(ROOT/'.tools/matplotlib'))


def validate():
    import librosa
    alignment=json.loads((DATA/'alignment.json').read_text(encoding='utf-8'))
    audio=ROOT/alignment['analysis_audio']['path']
    cache=ROOT/'.tools/features'/f"{alignment['audio']['sha256'][:12]}-independent-stft-v2.npz"
    fs,hop=11025,1102
    rate=fs/hop
    if cache.exists():
        with np.load(cache) as stored:chroma=stored['chroma']
    else:
        columns=[]
        with sf.SoundFile(audio) as stream:
            total=stream.frames/stream.samplerate
            for start in range(0,math.ceil(total),60):
                stream.seek(start*stream.samplerate)
                chunk=stream.read(60*stream.samplerate,dtype='float32',always_2d=True).mean(axis=1)
                divisor=math.gcd(stream.samplerate,fs)
                wave=scipy.signal.resample_poly(chunk,fs//divisor,stream.samplerate//divisor)
                values=librosa.feature.chroma_stft(y=wave,sr=fs,n_fft=4096,hop_length=hop,
                    tuning=alignment['algorithm']['tuning_offset_cents']/100,norm=2)
                times=start+np.arange(values.shape[1])/rate
                columns.append((times,values))
                if start%300==0:print(f'Independent STFT: {start}/{total:.0f} seconds',flush=True)
        # Each chunk has its own frame origin. Regrid to one timeline rather
        # than accumulating fractional rounding errors across all chunks.
        times=np.concatenate([t for t,_ in columns])
        values=np.concatenate([v for _,v in columns],axis=1)
        order=np.argsort(times,kind='stable');times=times[order];values=values[:,order]
        regular=np.arange(0,total,1/rate)
        chroma=np.stack([np.interp(regular,times,row) for row in values])
        np.savez_compressed(cache,chroma=chroma)
    score=read_midi(ROOT/alignment['symbolic_reference']['path'])
    expected=np.zeros((12,math.ceil(score['duration']*rate)+1),dtype=np.float32)
    for note in score['notes']:
        if note['is_drum']:continue
        first=int(note['start']*rate);last=int((note['start']+note['duration'])*rate)+1
        expected[note['pitch']%12,first:last]+=note['velocity']/127
    expected/=np.maximum(np.linalg.norm(expected,axis=0),1e-9)
    reference=np.arange(.5,score['duration']-.5,.5)
    points=alignment['time_map']
    mapped=np.interp(reference,[p['midi_seconds'] for p in points],[p['audio_seconds'] for p in points])
    pitch=expected[:,np.clip(np.round(reference*rate).astype(int),0,expected.shape[1]-1)]
    valid=np.linalg.norm(pitch,axis=0)>.1
    similarities={}
    for shift in [0,-8,8,-16,16]:
        indices=np.clip(np.round((mapped+shift)*rate).astype(int),0,chroma.shape[1]-1)
        similarities[shift]=np.sum(pitch*chroma[:,indices],axis=0)
    negatives=np.maximum.reduce([similarities[s] for s in [-8,8,-16,16]])
    measures=[]
    for measure in alignment['measures']:
        selection=(reference>=measure['midi_start_seconds'])&(reference<measure['midi_end_seconds'])&valid
        similarity=float(np.median(similarities[0][selection])) if np.any(selection) else None
        margin=float(np.median((similarities[0]-negatives)[selection])) if np.any(selection) else None
        measures.append({'measure_id':measure['measure_id'],'movement':measure['movement'],
            'start_seconds':measure['start_seconds'],'end_seconds':measure['end_seconds'],
            'independent_stft_cosine_median':similarity,'shifted_match_margin_median':margin,
            'flag':'insufficient_pitched_reference' if similarity is None else
                   'weak_independent_pitch_evidence' if similarity<.5 else None})
    result={'format_version':'1.0.0','audio_sha256':alignment['audio']['sha256'],
        'symbolic_reference_sha256':alignment['symbolic_reference']['sha256'],
        'method':'independent STFT chroma versus MIDI pitch activation; ±8/16-second controls',
        'parameters':{'sample_rate':fs,'hop_length':hop,'n_fft':4096,'sample_reference_step_seconds':.5},
        'structural':{'measure_count':len(measures),
            'monotone':all(a['start_seconds']<b['start_seconds'] for a,b in zip(measures,measures[1:])),
            'positive_intervals':all(m['end_seconds']>m['start_seconds'] for m in measures)},
        'flag_counts':dict(Counter(m['flag'] for m in measures if m['flag'])),
        'aggregate_cosine_median':float(np.median(similarities[0][valid])),
        'aggregate_shifted_margin_median':float(np.median((similarities[0]-negatives)[valid])),
        'measures':measures,'limitations':['Not an accuracy probability or human listening verification.',
            'Repeated motives, intro applause and movement breaks require separate checks.']}
    output=DATA/'reports/independent-sync-validation.json'
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8',newline='\n')
    print(json.dumps({k:v for k,v in result.items() if k not in {'measures','limitations'}},ensure_ascii=True))


if __name__=='__main__':validate()
