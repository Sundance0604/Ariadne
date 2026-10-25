import os,sys,json
from pathlib import Path
import numpy as np
import pypdfium2 as pdfium
from numba import njit
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'scripts'))
from midi_score import read_midi
from .geometry import extract
from .notes import noteheads
ROOT=Path(__file__).resolve().parents[2]
CACHE=Path(os.environ.get('MAHLER4_SCORE_CACHE',str(ROOT/'.tools/mahler4-score-v1')))


@njit
def dtw(a,b):
    n,m=len(a),len(b);cost=np.empty((n+1,m+1),np.float32);step=np.zeros((n+1,m+1),np.int8)
    cost[:,0]=np.arange(n+1)*.8;cost[0,:]=np.arange(m+1)*.8
    for i in range(1,n+1):
      for j in range(1,m+1):
        similarity=(a[i-1]*b[j-1]).sum()
        local=1-similarity
        options=(cost[i-1,j-1]+local,cost[i-1,j]+local+.15,cost[i,j-1]+local+.15)
        k=0 if options[0]<=options[1] and options[0]<=options[2] else 1 if options[1]<=options[2] else 2
        cost[i,j]=options[k];step[i,j]=k
    pairs=[];i=n;j=m
    while i>0 and j>0:
      pairs.append((i-1,j-1));k=step[i,j]
      if k==0:i-=1;j-=1
      elif k==1:i-=1
      else:j-=1
    return pairs[::-1],float(cost[-1,-1])

def extract_all():
    cache=CACHE/'poly-tokens.json'
    if cache.exists():return json.loads(cache.read_text())
    bass=json.loads((CACHE/'note-tokens.json').read_text());output=[]
    pdf=pdfium.PdfDocument(next((ROOT/'resource/mahler No.4').glob('*.pdf')))
    for number in range(5,128):
      page=pdf[number-1];a=np.asarray(page.render(scale=2).to_pil().convert('L'))
      for s in [x for x in bass if x['page']==number]:
        channels=[{'rank':1,'notes':s['notes'],'staff':s['staff']}]
        for rank in [2,3,4,5]:
          try:ns,staff=noteheads(a,s,rank)
          except Exception:ns=[];staff={}
          channels.append({'rank':rank,'notes':ns,'staff':staff})
        output.append({**{k:v for k,v in s.items() if k not in ['notes','staff']},'channels':channels})
      print('EXTRACT',number,flush=True)
    cache.write_text(json.dumps(output,indent=2),encoding='utf8');return output

def observations(systems,threshold):
    shifts={1:[0],2:[0],3:[-1,0],4:[-2,-1],5:[-2]}
    observed=[]
    for k,s in enumerate(systems):
      notes=sorted([{**n,'rank':ch['rank']} for ch in s['channels'] for n in ch['notes'] if n['response']>=threshold],key=lambda n:n['x'])
      clusters=[]
      for note in notes:
        if clusters and note['x']-clusters[-1][0]['x']<=7:clusters[-1].append(note)
        else:clusters.append([note])
      for cluster in clusters:
        vec=np.zeros(7)
        for note in cluster:
          for shift in shifts[note['rank']]:vec[(note['pc']+shift)%7]+=1/len(shifts[note['rank']])
        vec/=np.linalg.norm(vec)
        observed.append({'sys':k,'x':float(np.mean([n['x'] for n in cluster])),'vector':vec.tolist(),'heads':cluster})
    return observed

def main():
    data=extract_all();results=[]
    for movement,(first,last) in enumerate([(5,48),(49,77),(78,101),(102,127)],1):
      systems=[s for s in data if first<=s['page']<=last]
      score=read_midi(next((ROOT/'resource/mahler No.4').glob(f'mahler_symphony_4_{movement}_*.mid')))
      original=sorted([n for n in score['notes'] if n['track_index'] in [11,12,13,14,15,16]],key=lambda n:n['start_tick'])
      masks=[[0],[0,1],[1],[1,2],[2],[3],[3,4],[4],[4,5],[5],[5,6],[6]]
      midi_notes=[]
      for note in original:
        if midi_notes and abs(midi_notes[-1]['start']-note['start'])<.03:group=midi_notes[-1]
        else:
          group={'start':note['start'],'tick':note['start_tick'],'notes':[],'vec':np.zeros(7)};midi_notes.append(group)
        group['notes'].append(note)
        for pc in masks[note['pitch']%12]:group['vec'][pc]+=1/len(masks[note['pitch']%12])
      midi_vectors=np.array([n['vec']/np.linalg.norm(n['vec']) for n in midi_notes])
      variants=[]
      for threshold in [.60,.64]:
        obs=observations(systems,threshold);arr=np.array([o['vector'] for o in obs]);pairs,cost=dtw(arr,midi_vectors)
        bounds=[]
        for i,system in enumerate(systems):
          matches=[(obs[x],midi_notes[y],float(arr[x]@midi_vectors[y])) for x,y in pairs if obs[x]['sys']==i]
          count=sum(o['sys']==i for o in obs)
          values=[n['start'] for o,n,c in matches]
          bounds.append({'observed':count,'path_pairs':len(matches),'similarity':float(np.mean([c for o,n,c in matches])) if matches else 0,
             'start':min(values) if values else None,'end':max(values) if values else None,
             'evidence':[{'x':o['x'],'midi_seconds':n['start'],'midi_tick':n['tick'],'similarity':c,'heads':o['heads']} for o,n,c in matches]})
        variants.append(bounds);print('ALIGN',movement,threshold,len(obs),len(midi_notes),'cost',cost,flush=True)
      for i,s in enumerate(systems):
        primary,secondary=variants[0][i],variants[1][i]
        delta=max(abs(primary['start']-secondary['start']),abs(primary['end']-secondary['end'])) if primary['start'] is not None and secondary['start'] is not None else None
        results.append({**s,'movement':movement,'match':primary,'comparison':secondary,'variant_disagreement_seconds':delta})
      print('BOUNDS',movement,[(s['page'],s['system'],v['observed'],round(v['start'] or 0),round(v['end'] or 0),round(v['similarity'],2)) for s,v in zip(systems,variants[0])],flush=True)
    (CACHE/'poly-alignment.json').write_text(json.dumps(results,indent=2),encoding='utf8')

if __name__=='__main__':main()
