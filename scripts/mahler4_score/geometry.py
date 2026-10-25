import os
from pathlib import Path
from collections import Counter
import json
import numpy as np
import pypdfium2 as pdfium
from scipy import ndimage as ndi

ROOT=Path(__file__).resolve().parents[2]
CACHE=Path(os.environ.get('MAHLER4_SCORE_CACHE',str(ROOT/'.tools/mahler4-score-v1')))

PDF=next((ROOT/'resource/mahler No.4').glob('*.pdf'))
def runs(xs,gap=2):return [g for g in np.split(xs,np.where(np.diff(xs)>gap)[0]+1) if len(g)]
def extract(page):
    a=np.asarray(page.render(scale=2).to_pil().convert('L'));b=a<150
    h=ndi.binary_opening(b,structure=np.ones((1,45)))
    v=ndi.binary_opening(ndi.maximum_filter(b,size=(1,3)),structure=np.ones((35,1)))
    lab,num=ndi.label(h)
    lines=[(s[1].start,s[1].stop,s[0].start,s[0].stop) for s in ndi.find_objects(lab) if s and s[1].stop-s[1].start>a.shape[1]*.3]
    candidates=[x for x,z,y,q in lines if x<a.shape[1]*.4]
    lefts=[]
    while candidates:
        counter=Counter(round(x/10)*10 for x in candidates);center=counter.most_common(1)[0][0]
        cluster=[x for x in candidates if abs(x-center)<25]
        candidates=[x for x in candidates if abs(x-center)>=25]
        if len(cluster)<12:continue
        lefts.append(round(float(np.median(cluster))))
    systems=[]
    for left in lefts:
        ys=runs(np.flatnonzero(v[:,max(0,left-10):left+12].any(axis=1)),12)
        for group in ys:
            t,z=int(group[0]),int(group[-1]);height=z-t
            if height<90:continue
            matching=[l for l in lines if abs(l[0]-left)<25 and t-10<l[2]<z+10]
            if len(matching)<8:continue
            col=v[t:z+1].sum(axis=0)
            xs=[int(g[np.argmax(col[g])]) for g in runs(np.flatnonzero(col>height*.55),7)]
            if len(xs)<2:continue
            systems.append({'top':t,'bottom':z,'left':left,'boundaries':xs})
    systems.sort(key=lambda s:s['top'])
    return systems
