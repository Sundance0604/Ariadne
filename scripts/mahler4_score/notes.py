import os
from pathlib import Path
import json
import numpy as np
from scipy import ndimage as ndi
from scipy.signal import find_peaks
from PIL import Image,ImageDraw
import pypdfium2 as pdfium
from .geometry import extract

ROOT=Path(__file__).resolve().parents[2]
CACHE=Path(os.environ.get('MAHLER4_SCORE_CACHE',str(ROOT/'.tools/mahler4-score-v1')))

PDF=next((ROOT/'resource/mahler No.4').glob('*.pdf'))

def noteheads(a,system,rank=1):
    t,b=system['top'],system['bottom'];x0,x1=system['boundaries'][0],system['boundaries'][-1]
    # Locate the last staff's five lines from long horizontal evidence.
    ink=a<150;h=ndi.binary_opening(ink,structure=np.ones((1,45)))
    rows=h[:,x0:x1].sum(axis=1)
    ys=np.flatnonzero(rows>(x1-x0)*.25)
    groups=[g for g in np.split(ys,np.where(np.diff(ys)>2)[0]+1) if len(g)]
    lines=np.array([g[np.argmax(rows[g])] for g in groups if t-8<g.mean()<b+8])
    # Last staff bottom is near the left brace endpoint, and interline ~7 px.
    line_groups=[]
    for y in lines:
        if line_groups and y-line_groups[-1][-1]<11:line_groups[-1].append(int(y))
        else:line_groups.append([int(y)])
    staff=[g for g in line_groups if len(g)>=4][-rank]
    bottom=staff[-1];spacing=float(np.median(np.diff(staff)))
    top=staff[0]
    # Flatten gentle scan tilt using each column's strongest expected staff line.
    shift=[]
    for x in range(a.shape[1]):
        scores=[]
        for off in range(-4,5):
            scores.append(sum(h[int(y+off),max(0,x-15):x+16].sum() for y in staff[-5:]))
        shift.append(int(np.argmax(scores))-4)
    shift=ndi.median_filter(np.array(shift),size=41)
    patch=np.ones((int(spacing*9),a.shape[1]),dtype=np.uint8)*255
    baseline=int(spacing*6)
    for x in range(x0,x1):
        y0=int(bottom+shift[x]-baseline)
        patch[:,x]=a[y0:y0+patch.shape[0],x]
    binary=1-patch.astype(float)/255
    yy,xx=np.mgrid[-5:6,-8:9]
    ellipse=((xx+.45*yy)/5.3)**2+(yy/3.1)**2<=1
    kernel=ellipse/ellipse.sum()-(~ellipse)/(~ellipse).sum()
    response=ndi.correlate(binary,kernel)
    peaks=(response==ndi.maximum_filter(response,size=(5,9)))&(response>.43)
    labels,n=ndi.label(peaks)
    result=[]
    for obj in ndi.find_objects(labels):
        if obj is None:continue
        sy,sx=obj;y=(sy.start+sy.stop-1)/2;x=(sx.start+sx.stop-1)/2
        if x<x0+65 or x>x1-5 or any(abs(x-z)<7 for z in system['boundaries']):continue
        step=round((baseline-y)/(spacing/2))
        if abs((baseline-y)/(spacing/2)-step)>.4:continue
        result.append({'x':x,'y':float(bottom+shift[int(x)]-baseline+y),'step':int(step),'pc':int((4+step)%7),'response':float(response[int(y),int(x)])})
    return sorted(result,key=lambda n:n['x']),{'staff':staff,'spacing':spacing,'bottom':bottom}
