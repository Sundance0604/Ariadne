"""Cache stereo pitch-energy and attack features in small recording windows."""
from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
import subprocess

import numpy as np
from scipy.ndimage import gaussian_filter1d
from scipy.signal import stft

from parse_score import HERE,AUDIO,digest

FFMPEG=Path(os.environ.get('PROK3_FFMPEG') or shutil.which('ffmpeg') or 'ffmpeg')
RATE=22050; HOP=220; DT=HOP/RATE; FFT=4096
PITCH_MIN=36;PITCH_MAX=100
LIMIT=620;CHUNK=50


def decode(start,seconds):
    command=[str(FFMPEG),'-hide_banner','-loglevel','error','-nostdin',
             '-ss',str(start),'-i',str(AUDIO),'-t',str(seconds),
             '-ac','2','-ar',str(RATE),'-f','f32le','pipe:1']
    raw=subprocess.run(command,check=True,capture_output=True).stdout
    return np.frombuffer(raw,'<f4').reshape(-1,2).T.copy()


def features(stereo,tuning):
    spectra={}
    for name,signal in {'left':stereo[0],'right':stereo[1],
                        'mid':(stereo[0]+stereo[1])*.5}.items():
        _,_,z=stft(signal,fs=RATE,nperseg=FFT,noverlap=FFT-HOP,boundary='zeros')
        spectra[name]=abs(z).astype(np.float32)
    spectra['first']=np.maximum(0,spectra['left']-.55*spectra['right'])
    spectra['second']=np.maximum(0,spectra['right']-.55*spectra['left'])
    result={}
    for name in ('mid','first','second'):
        mag=spectra[name]
        rows=[]
        for pitch in range(PITCH_MIN,PITCH_MAX+1):
            hz=440*2**((pitch-69)/12+tuning/1200)
            components=[]
            for harmonic in (1,2,3):
                index=round(hz*harmonic*FFT/RATE)
                if index+2>=len(mag):break
                peak=np.max(mag[max(0,index-1):index+2],axis=0)
                components.append(peak/harmonic**1.45)
            rows.append(sum(components))
        raw=gaussian_filter1d(np.asarray(rows,np.float32),.7,axis=1)
        floor=gaussian_filter1d(raw,1.25,axis=0)
        energy=np.maximum(0,raw-.34*floor)
        log=np.log1p(energy*220)
        onset=np.maximum(0,log-np.roll(log,5,axis=1));onset[:,:5]=0
        onset=gaussian_filter1d(onset,1.0,axis=1)
        result[f'{name}_energy']=energy.astype(np.float16)
        result[f'{name}_onset']=onset.astype(np.float16)
    return result


def main():
    score=json.loads((HERE/'score-events.json').read_text())
    clock=json.loads((HERE/'score-audio-clock.json').read_text())
    if digest(AUDIO)!=score['source_audio_sha256'] or clock['source_score_sha256']!=score['source_score_sha256']:
        raise ValueError('Source mismatch')
    directory=HERE/'orchestra-evidence';directory.mkdir(exist_ok=True)
    manifest=directory/'manifest.json'
    if manifest.exists():
        prior=json.loads(manifest.read_text())
        if (prior.get('source_score_sha256')!=score['source_score_sha256'] or
                prior.get('source_audio_sha256')!=score['source_audio_sha256']):
            raise ValueError('Cached orchestra features belong to another score/recording; use a fresh project directory')
    for start in range(0,LIMIT,CHUNK):
        stop=min(start+CHUNK,LIMIT)
        output=directory/f'features-{start:03}-{stop:03}.npz'
        if output.exists():print('reusing',output.name,flush=True);continue
        print('orchestra evidence',start,stop,flush=True)
        data=features(decode(start,stop-start),clock['tuning_cents'])
        np.savez_compressed(output,**data)
        print('saved',output.name,data['mid_onset'].shape,flush=True)
    (directory/'manifest.json').write_text(json.dumps({
        'source_score_sha256':score['source_score_sha256'],
        'source_audio_sha256':score['source_audio_sha256'],
        'limit_seconds':LIMIT,'chunk_seconds':CHUNK,
        'sample_interval_seconds':DT,'pitch_min':PITCH_MIN,'pitch_max':PITCH_MAX,
    },indent=2)+'\n')


if __name__=='__main__':main()
