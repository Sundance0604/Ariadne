import os,sys,json
from pathlib import Path
import numpy as np
from numba import njit
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'scripts'))
from midi_score import read_midi,TempoMap
import mido
from .features import observations
ROOT=Path(__file__).resolve().parents[2]
CACHE=Path(os.environ.get('MAHLER4_SCORE_CACHE',str(ROOT/'.tools/mahler4-score-v1')))


@njit
def metric_dp(observed,prefix,onset_prefix,lengths,prior,nominal):
    n=len(observed);m=prefix.shape[0]-1
    cost=np.full((n+1,m+1),np.inf,np.float32);steps=np.zeros((n+1,m+1),np.int16);cost[0,0]=0
    for i in range(1,n+1):
      for j in range(1,m+1):
        best=np.inf;bestL=0
        for L in lengths:
          if j<L or not np.isfinite(cost[i-1,j-L]):continue
          midi=prefix[j]-prefix[j-L];norm=np.sqrt((midi*midi).sum());o=observed[i-1];onorm=np.sqrt((o*o).sum())
          similarity=(midi*o).sum()/max(.00001,norm*onorm)
          local=1-similarity if norm>.001 and onorm>.001 else 0.0 if norm<.001 and onorm<.001 else .8
          penalty=prior*abs(L-nominal)/nominal
          value=cost[i-1,j-L]+local+penalty
          if value<best:best=value;bestL=L
        cost[i,j]=best;steps[i,j]=bestL
    out=[];i=n;j=m
    if not np.isfinite(cost[-1,-1]):raise ValueError('No metric path')
    while i:
      L=steps[i,j]
      if not L:raise ValueError('Broken path')
      out.append((j-L,j));j-=L;i-=1
    return out[::-1],float(cost[-1,-1])

def tempo_time(score,quarter):
    return float(score['_tempo'].at(quarter*score['ppq']))


def main():
    data=json.loads((CACHE/'poly-tokens.json').read_text());allresults=[]
    masks=[[0],[0,1],[1],[1,2],[2],[3],[3,4],[4],[4,5],[5],[5,6],[6]]
    for movement,(first,last,nominal) in enumerate([(5,48,8),(49,77,3),(78,101,8),(102,127,8)],1):
      systems=[s for s in data if first<=s['page']<=last];score=read_midi(next((ROOT/'resource/mahler No.4').glob(f'mahler_symphony_4_{movement}_*.mid')))
      events=[]
      for track in mido.MidiFile(next((ROOT/'resource/mahler No.4').glob(f'mahler_symphony_4_{movement}_*.mid'))).tracks:
        tick=0
        for event in track:
          tick+=event.time
          if event.type=='set_tempo':events.append((tick,event.tempo))
      score['_tempo']=TempoMap(sorted(events),score['ppq'])
      endq=score['measures'][-1]['score_end_quarter'];M=round(endq*2);roll=np.zeros((M,7));counts=np.zeros(M)
      for note in score['notes']:
        if note['track_index'] not in [11,12,13,14,15,16]:continue
        idx=min(M-1,round(note['start_tick']/score['ppq']*2));counts[idx]+=1
        for pc in masks[note['pitch']%12]:roll[idx,pc]+=1/len(masks[note['pitch']%12])
      prefix=np.concatenate([np.zeros((1,7)),np.cumsum(roll,axis=0)]);onsetprefix=np.r_[0,np.cumsum(counts)]
      results=[]
      for threshold,prior in [(.60,.25),(.64,.25),(.60,.4)]:
        obs=observations(systems,threshold);bars=[]
        for si,s in enumerate(systems):
          for bi,(x0,x1) in enumerate(zip(s['boundaries'],s['boundaries'][1:])):
            heads=[x for x in obs if x['sys']==si and x0<=x['x']<x1];vec=np.sum([x['vector'] for x in heads],axis=0) if heads else np.zeros(7)
            bars.append({'sys':si,'bar':bi,'vector':vec,'heads':len(heads),'x0':x0,'x1':x1})
        lengths=np.array([2,3,4,5,6,8,10,12,16] if movement!=2 else [2,3,4,6,9,12],dtype=np.int64)
        path,cost=metric_dp(np.array([b['vector'] for b in bars]),prefix,onsetprefix,lengths,prior,nominal)
        for bar,(start,end) in zip(bars,path):
          midi=prefix[end]-prefix[start];o=bar['vector'];cos=float(midi@o/max(.00001,np.linalg.norm(midi)*np.linalg.norm(o)))
          bar.update(start_quarter=start/2,end_quarter=end/2,start=tempo_time(score,start/2),end=tempo_time(score,end/2),similarity=cos)
          bar['vector']=bar['vector'].tolist()
        regions=[]
        for si,s in enumerate(systems):
          bs=[b for b in bars if b['sys']==si];regions.append({'start':bs[0]['start'],'end':bs[-1]['end'],'bars':bs,'similarity':float(np.mean([b['similarity'] for b in bs]))})
        results.append(regions);print('METRIC',movement,threshold,prior,len(bars),cost,flush=True)
      for si,s in enumerate(systems):
        primary=results[0][si];comp=results[1][si];comp2=results[2][si]
        delta=max(abs(primary[k]-other[k]) for other in [comp,comp2] for k in ['start','end'])
        allresults.append({**s,'movement':movement,'match':primary,'comparison':comp,'prior_comparison':comp2,'variant_disagreement_seconds':delta})
      print('BOUNDS',movement,[(s['page'],s['system'],round(v['start']),round(v['end']),round(v['similarity'],2)) for s,v in zip(systems,results[0])],flush=True)
    (CACHE/'metric-alignment.json').write_text(json.dumps(allresults,indent=2),encoding='utf8')

if __name__=='__main__':main()
