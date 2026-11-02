"""Sample compact pitch-specific orchestra evidence at arbitrary times."""
from __future__ import annotations

from collections import OrderedDict
import json
import numpy as np

from parse_score import HERE


class OrchestraEvidence:
    def __init__(self,score):
        self.directory=HERE/'orchestra-evidence'
        self.manifest=json.loads((self.directory/'manifest.json').read_text())
        if (self.manifest['source_score_sha256']!=score['source_score_sha256'] or
                self.manifest['source_audio_sha256']!=score['source_audio_sha256']):
            raise ValueError('Orchestra evidence belongs to different media')
        self.cache=OrderedDict()
        self.interval=self.manifest['sample_interval_seconds']
        self.pitch_min=self.manifest['pitch_min']
        self.pitch_max=self.manifest['pitch_max']
        self.chunk_seconds=self.manifest['chunk_seconds']
        self.limit=self.manifest['limit_seconds']

    def _chunk(self,start):
        if start in self.cache:
            self.cache.move_to_end(start)
            return self.cache[start]
        stop=min(start+self.chunk_seconds,self.limit)
        with np.load(self.directory/f'features-{start:03}-{stop:03}.npz') as data:
            result={key:data[key].astype(np.float32) for key in data.files}
        self.cache[start]=result
        if len(self.cache)>3:self.cache.popitem(last=False)
        return result

    def sample(self,part,pitches,times,kind='onset'):
        times=np.asarray(times,dtype=float)
        result=np.zeros(len(times),np.float32)
        selected=np.array([p-self.pitch_min for p in set(pitches)
                           if self.pitch_min<=p<=self.pitch_max],dtype=int)
        if not len(selected):return result
        view=('first' if part in ('P1','P2','P15') else
              'second' if part=='P16' else 'mid')
        for start in np.unique((np.maximum(0,times)//self.chunk_seconds).astype(int)*self.chunk_seconds):
            valid=(times>=start)&(times<min(start+self.chunk_seconds,self.limit))
            if not np.any(valid):continue
            matrix=self._chunk(int(start))[f'{view}_{kind}'][selected]
            index=(times[valid]-start)/self.interval
            result[valid]=np.max(np.array([
                np.interp(index,np.arange(len(row)),row,left=0,right=0)
                for row in matrix]),axis=0)
        return result
