"""Conservative note-tail bounds from the separated piano's pitch energy."""

from __future__ import annotations

import json

import numpy as np

from prepare_preview import EXPECTED_AUDIO_SHA256, HERE


class PianoSustain:
    def __init__(self):
        directory=HERE/'piano-sustain-features'
        manifest=json.loads((directory/'manifest.json').read_text())
        if manifest['source_audio_sha256']!=EXPECTED_AUDIO_SHA256:
            raise ValueError('Piano sustain features belong to another recording')
        self.interval=manifest['sample_interval_seconds']
        self.regions=[]
        crops=[tuple(item) for item in manifest['crops']]
        for index,(start,stop) in enumerate(crops):
            left=start if index==0 else (crops[index-1][1]+start)/2
            right=stop if index==len(crops)-1 else (stop+crops[index+1][0])/2
            with np.load(directory/f'energy-{start:03}-{stop:03}.npz') as data:
                energy=data['energy'].astype(np.float32)
            self.regions.append((left,right,start,energy))

    def sample(self,pitch:int,times:np.ndarray)->np.ndarray:
        out=np.zeros(len(times),np.float32)
        for left,right,start,energy in self.regions:
            valid=(times>=left)&(times<right)
            if not np.any(valid):continue
            row=energy[pitch-21]
            out[valid]=np.interp((times[valid]-start)/self.interval,
                                 np.arange(len(row)),row,left=0,right=0)
        return out


def bound_releases(notes:list[dict],evidence:PianoSustain)->dict:
    changed=[]
    for note in notes:
        if note['part_id']!='P14':continue
        start,end=note['audio_start'],note['audio_end']
        if end-start<.32 or not 21<=note['midi_pitch']<=108:continue
        grid=np.arange(start,min(end,580),.02)
        if len(grid)<16:continue
        energy=evidence.sample(note['midi_pitch'],grid)
        peak=float(np.max(energy[:min(10,len(energy))]))
        if peak<.000045:continue
        # A single dip can be caused by interference; require sustained decay.
        # This is a *tail bound*, not a claim to know the mechanical key-off.
        below=energy<.115*peak
        earliest=max(10,round(.20/.02))
        for index in range(earliest,len(grid)-5):
            if np.all(below[index:index+6]):
                bound=float(grid[index]+.04)
                if bound<end-.08:
                    note['audio_end']=round(max(start+.22,bound),4)
                    note['release_source']='separated_piano_decay_bound'
                    changed.append(end-note['audio_end'])
                break
    return {'energy_bounded':len(changed),
            'median_removed_ms':round(float(np.median(changed))*1000,1)
            if changed else 0}
