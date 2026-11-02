"""Multiresolution chroma/onset score-to-recording clock for movement III."""
from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
import subprocess

import numpy as np
import pandas as pd
from synctoolbox.dtw.mrmsdtw import sync_via_mrmsdtw
from synctoolbox.dtw.utils import make_path_strictly_monotonic
from synctoolbox.feature.csv_tools import df_to_pitch_features,df_to_pitch_onset_features
from synctoolbox.feature.chroma import pitch_to_chroma,quantize_chroma
from synctoolbox.feature.dlnco import pitch_onset_features_to_DLNCO
from synctoolbox.feature.pitch import audio_to_pitch_features
from synctoolbox.feature.pitch_onset import audio_to_pitch_onset_features
from synctoolbox.feature.utils import estimate_tuning

from parse_score import HERE,AUDIO,digest

FFMPEG=Path(os.environ.get('PROK3_FFMPEG') or shutil.which('ffmpeg') or 'ffmpeg')
RATE=22050
FEATURE_RATE=25
MUSIC_SECONDS=618.0


def score_seconds(beat,tempi):
    value=0.
    for i,(start,bpm,_) in enumerate(tempi):
        stop=tempi[i+1][0] if i+1<len(tempi) else beat
        if beat<=start:break
        value+=(min(beat,stop)-start)*60/bpm
        if beat<stop:break
    return value


def annotations(events,tempi):
    rows=[]
    for note in events:
        start=score_seconds(note['start_beat'],tempi)
        end=score_seconds(note['end_beat'],tempi)
        part=note['part_id']
        weight=(100 if part=='P14' else
                87 if part in ('P4','P15','P16') else
                76 if part in ('P2','P3','P17') else 58)
        rows.append({'start':start,'duration':max(.035,end-start),
                     'pitch':note['midi_pitch'],'velocity':weight,
                     'instrument':note['part_name']})
    return pd.DataFrame(rows)


def main():
    score=json.loads((HERE/'score-events.json').read_text())
    if digest(AUDIO)!=score['source_audio_sha256']:
        raise ValueError('Audio changed since score extraction')
    tempi=score['tempo_markings']
    event_frame=annotations(score['notes'],tempi)
    command=[str(FFMPEG),'-hide_banner','-loglevel','error','-nostdin',
             '-i',str(AUDIO),'-t',str(MUSIC_SECONDS),'-ac','1','-ar',str(RATE),
             '-f','f32le','pipe:1']
    audio=np.frombuffer(subprocess.run(command,check=True,capture_output=True).stdout,
                        '<f4').copy()
    tuning=estimate_tuning(audio[:RATE*75],RATE)
    print('notes',len(score['notes']),'nominal',round(score_seconds(score['total_beats'],tempi),2),
          'audio',len(audio)/RATE,'tuning',round(float(tuning),2),flush=True)
    audio_pitch=audio_to_pitch_features(f_audio=audio,Fs=RATE,
                                        tuning_offset=tuning,
                                        feature_rate=FEATURE_RATE,verbose=False)
    audio_chroma=quantize_chroma(pitch_to_chroma(f_pitch=audio_pitch))
    del audio_pitch
    audio_peaks=audio_to_pitch_onset_features(f_audio=audio,Fs=RATE,
                                              tuning_offset=tuning,verbose=False)
    audio_onset=pitch_onset_features_to_DLNCO(
        f_peaks=audio_peaks,feature_rate=FEATURE_RATE,
        feature_sequence_length=audio_chroma.shape[1],visualize=False)
    del audio_peaks,audio
    print('audio feature frames',audio_chroma.shape[1],flush=True)
    score_pitch=df_to_pitch_features(event_frame,feature_rate=FEATURE_RATE)
    score_chroma=quantize_chroma(pitch_to_chroma(f_pitch=score_pitch))
    del score_pitch
    score_peaks=df_to_pitch_onset_features(event_frame)
    score_onset=pitch_onset_features_to_DLNCO(
        f_peaks=score_peaks,feature_rate=FEATURE_RATE,
        feature_sequence_length=score_chroma.shape[1],visualize=False)
    del score_peaks
    print('score feature frames',score_chroma.shape[1],flush=True)
    path=sync_via_mrmsdtw(f_chroma1=audio_chroma,f_chroma2=score_chroma,
                          f_onset1=audio_onset,f_onset2=score_onset,
                          input_feature_rate=FEATURE_RATE,
                          step_weights=np.array([1.5,1.5,2.0]),
                          threshold_rec=10**6,verbose=False)
    path=make_path_strictly_monotonic(path)
    score_times=path[1]/FEATURE_RATE
    audio_times=path[0]/FEATURE_RATE
    beats=np.arange(0,score['total_beats']+.001,.25)
    nominal=np.array([score_seconds(float(b),tempi) for b in beats])
    mapped=np.interp(nominal,score_times,audio_times)
    if np.any(np.diff(mapped)<-1e-7):raise RuntimeError('Nonmonotone score clock')
    result={
        'source_score_sha256':score['source_score_sha256'],
        'source_audio_sha256':score['source_audio_sha256'],
        'method':'Sync Toolbox 1.4.2 multiresolution chroma+DLNCO',
        'tuning_cents':float(tuning),'score_events':len(score['notes']),
        'audio_endpoint_seconds':MUSIC_SECONDS,
        'path_points':int(path.shape[1]),
        'beat_time':[[round(float(b),5),round(float(t),5)] for b,t in zip(beats,mapped)],
    }
    out=HERE/'score-audio-clock.json'
    out.write_text(json.dumps(result,ensure_ascii=False,separators=(',',':')))
    print('wrote',out,'mapped endpoint',round(float(mapped[-1]),3),flush=True)


if __name__=='__main__':main()
