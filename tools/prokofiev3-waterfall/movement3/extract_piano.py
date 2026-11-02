"""Separate, transcribe and measure piano in disposable overlapping crops."""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import sys

import numpy as np
from scipy.ndimage import gaussian_filter1d
from scipy.signal import stft

from parse_score import HERE,AUDIO,digest

FFMPEG=Path(os.environ.get('PROK3_FFMPEG') or shutil.which('ffmpeg') or 'ffmpeg')
SEPARATOR=Path(os.environ.get('PROK3_M3_SEPARATOR') or shutil.which('mlx-audio-separator') or 'mlx-audio-separator')
TRANSKUN=Path(os.environ.get('PROK3_M3_TRANSKUN') or shutil.which('transkun') or 'transkun')
MODEL=Path(os.environ.get('PROK3_M3_MODEL_DIR', str(HERE/'model')))
SCRATCH=Path(os.environ.get('PROK3_M3_SCRATCH', str(Path(tempfile.gettempdir())/'prokofiev3-third-piano')))
CROPS=((0,80),(70,150),(140,220),(210,290),(280,360),
       (350,430),(420,500),(490,570),(560,620))
RATE=22050;HOP=220;FFT=4096


def run(command,**kwargs):
    subprocess.run([str(item) for item in command],check=True,**kwargs)


def pitch_energy(stem,output):
    command=[FFMPEG,'-hide_banner','-loglevel','error','-nostdin','-i',stem,
             '-ac','1','-ar',RATE,'-f','f32le','pipe:1']
    audio=np.frombuffer(subprocess.run([str(x) for x in command],check=True,
                       capture_output=True).stdout,'<f4').copy()
    _,_,spectrum=stft(audio,fs=RATE,nperseg=FFT,noverlap=FFT-HOP,
                      boundary='zeros')
    mag=abs(spectrum).astype(np.float32)
    rows=[]
    for pitch in range(21,109):
        hz=440*2**((pitch-69)/12)
        components=[]
        for harmonic in (1,2,3):
            k=round(hz*harmonic*FFT/RATE)
            if k>=len(mag)-2:continue
            components.append(np.max(mag[max(0,k-1):k+2],axis=0)/harmonic**1.6)
        rows.append(sum(components))
    energy=gaussian_filter1d(np.asarray(rows,np.float32),1.2,axis=1)
    np.savez_compressed(output,energy=energy.astype(np.float16))


def main():
    score=json.loads((HERE/'score-events.json').read_text())
    if digest(AUDIO)!=score['source_audio_sha256']:
        raise ValueError('Recording fingerprint changed')
    for name in ('BS-Roformer-SW.ckpt','BS-Roformer-SW.yaml'):
        if not (MODEL/name).is_file():raise FileNotFoundError(MODEL/name)
    output_dir=HERE/'piano-evidence';output_dir.mkdir(exist_ok=True)
    manifest=output_dir/'manifest.json'
    if manifest.exists():
        prior=json.loads(manifest.read_text())
        if prior.get('source_audio_sha256')!=score['source_audio_sha256']:
            raise ValueError('Cached piano transcription belongs to another recording; use a fresh project directory')
    for start,stop in CROPS:
        midi=output_dir/f'piano-{start:03}-{stop:03}.mid'
        energy=output_dir/f'energy-{start:03}-{stop:03}.npz'
        if midi.is_file() and energy.is_file() and midi.stat().st_size>100:
            print('reusing',midi.name,flush=True);continue
        print('piano crop',start,stop,flush=True)
        scratch=SCRATCH/f'crop-{start:03}-{stop:03}'
        scratch.mkdir(parents=True,exist_ok=True)
        source=scratch/'source.wav'
        if not source.exists():
            run([FFMPEG,'-hide_banner','-loglevel','error','-nostdin','-y',
                 '-ss',start,'-i',AUDIO,'-t',stop-start,'-ar',44100,'-ac',2,
                 '-c:a','pcm_s16le',source])
        stem_dir=scratch/'stems';stem_dir.mkdir(exist_ok=True)
        stems=list(stem_dir.glob('*piano*.wav'))
        if not stems:
            run([SEPARATOR,source,'--model_filename','BS-Roformer-SW.ckpt',
                 '--model_file_dir',MODEL,'--single_stem','piano',
                 '--output_format','WAV','--output_dir',stem_dir])
            stems=list(stem_dir.glob('*piano*.wav'))
        if len(stems)!=1:raise RuntimeError(f'Expected one piano stem: {stems}')
        stem=stems[0]
        if not midi.is_file() or midi.stat().st_size<100:
            temp=scratch/'piano.mid'
            device=os.environ.get('PROK3_M3_TRANSKUN_DEVICE',
                                  'mps' if sys.platform=='darwin' else 'cpu')
            run([TRANSKUN,stem,temp,'--device',device])
            if temp.stat().st_size<100:raise RuntimeError('Empty Transkun MIDI')
            shutil.copy2(temp,midi)
        if not energy.is_file():pitch_energy(stem,energy)
        print('saved',midi.name,energy.name,flush=True)
        shutil.rmtree(scratch)
    if SCRATCH.is_dir():SCRATCH.rmdir()
    (output_dir/'manifest.json').write_text(json.dumps({
        'source_audio_sha256':score['source_audio_sha256'],
        'crops':CROPS,'sample_interval_seconds':HOP/RATE,
        'pitch_min':21,'pitch_max':108},indent=2)+'\n')


if __name__=='__main__':main()
