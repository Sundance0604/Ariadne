"""Measure separated-piano pitch energy in small disposable audio crops.

Energy decay only bounds visually implausible note tails. It does not identify
the exact mechanical key-release moment when pedal or hall reverb is present.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import subprocess
import tempfile

import numpy as np
from scipy.ndimage import gaussian_filter1d
from scipy.signal import stft

from prepare_preview import (AUDIO, EXPECTED_AUDIO_SHA256, FFMPEG, HERE, digest)

RATE = 22050
HOP = 220
FFT = 4096
CROPS = ((0,90),(85,180),(175,250),(245,320),(315,390),
         (385,460),(455,530),(525,580))
OUT = HERE/'piano-sustain-features'


def main() -> None:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--separator',required=True)
    parser.add_argument('--model-dir',type=Path,required=True)
    parser.add_argument('--scratch',type=Path,
                        default=Path(tempfile.gettempdir())/'prok3-sustain-scratch')
    args=parser.parse_args()
    if digest(AUDIO)!=EXPECTED_AUDIO_SHA256:
        raise ValueError('Recording fingerprint changed')
    scratch=args.scratch.resolve()
    if scratch==Path('/') or scratch==HERE.resolve():
        raise ValueError('Unsafe scratch directory')
    OUT.mkdir(exist_ok=True)
    for start,stop in CROPS:
        output=OUT/f'energy-{start:03}-{stop:03}.npz'
        if output.is_file():
            print('reusing',output.name,flush=True)
            continue
        scratch.mkdir(parents=True,exist_ok=True)
        source=scratch/f'crop-{start}-{stop}.wav'
        subprocess.run([str(FFMPEG),'-hide_banner','-loglevel','error','-y',
                        '-ss',str(start),'-i',str(AUDIO),'-t',str(stop-start),
                        '-ar','44100','-ac','2','-c:a','pcm_s16le',str(source)],
                       check=True)
        stem_dir=scratch/'stems';stem_dir.mkdir(exist_ok=True)
        subprocess.run([args.separator,str(source),'-m','BS-Roformer-SW.ckpt',
                        '--model_file_dir',str(args.model_dir),'--single_stem',
                        'piano','--output_format','WAV','--output_dir',str(stem_dir)],
                       check=True,stdout=subprocess.DEVNULL)
        candidates=list(stem_dir.glob('*piano*.wav'))
        if len(candidates)!=1:raise RuntimeError(candidates)
        command=[str(FFMPEG),'-hide_banner','-loglevel','error',
                 '-i',str(candidates[0]),'-ac','1','-ar',str(RATE),
                 '-f','f32le','pipe:1']
        wave=np.frombuffer(subprocess.run(command,capture_output=True,
                                          check=True).stdout,'<f4').copy()
        _,_,spectrum=stft(wave,fs=RATE,nperseg=FFT,noverlap=FFT-HOP,
                          boundary='zeros')
        magnitude=abs(spectrum).astype(np.float32)
        energy=[]
        for pitch in range(21,109):
            hz=440*2**((pitch-69)/12)
            components=[]
            for harmonic in (1,2,3):
                k=round(hz*harmonic*FFT/RATE)
                if k>=len(magnitude)-2:continue
                components.append(np.max(magnitude[max(0,k-1):k+2],axis=0)
                                  /harmonic**1.6)
            energy.append(sum(components))
        energy=np.asarray(energy,np.float32)
        energy=gaussian_filter1d(energy,1.2,axis=1)
        np.savez_compressed(output,energy=energy.astype(np.float16))
        print('saved',output.name,energy.shape,flush=True)
        shutil.rmtree(stem_dir)
        source.unlink()
    (OUT/'manifest.json').write_text(json.dumps({
        'source_audio_sha256':EXPECTED_AUDIO_SHA256,
        'crops':CROPS,'sample_interval_seconds':HOP/RATE,
        'pitch_min':21,'pitch_max':108},indent=2)+'\n')
    scratch.rmdir()


if __name__=='__main__':main()
