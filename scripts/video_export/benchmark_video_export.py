"""Compare uncached per-frame PDF drawing with cached event drawing on real PTS."""
import argparse
import ctypes
import hashlib
from pathlib import Path
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from backend.video_export.content import read,write


def peak_rss():
    if sys.platform=='win32':
        class Counters(ctypes.Structure):
            _fields_=[('cb',ctypes.c_ulong),('PageFaultCount',ctypes.c_ulong)]+[(n,ctypes.c_size_t) for n in
                ['PeakWorkingSetSize','WorkingSetSize','QuotaPeakPagedPoolUsage','QuotaPagedPoolUsage','QuotaPeakNonPagedPoolUsage','QuotaNonPagedPoolUsage','PagefileUsage','PeakPagefileUsage']]
        value=Counters();value.cb=ctypes.sizeof(value)
        handle=ctypes.windll.kernel32.GetCurrentProcess;handle.restype=ctypes.c_void_p
        get=ctypes.windll.psapi.GetProcessMemoryInfo;get.argtypes=[ctypes.c_void_p,ctypes.c_void_p,ctypes.c_ulong]
        if not get(handle(),ctypes.byref(value),value.cb):raise OSError('Memory measurement unavailable')
        return value.PeakWorkingSetSize
    import resource
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*(1 if sys.platform=='darwin' else 1024)


def worker(package,mode,states):
    from PIL import Image,ImageDraw
    import pypdfium2 as pdfium
    config=read(package/'export-config.json');v=config['layout']['score'];cache={};hashes=[];renders=0
    start=time.perf_counter()
    with pdfium.PdfDocument(str(package/'score/source.pdf')) as document:
        for state in states:
            image=Image.new('RGBA',(v['w'],v['h']),(0,0,0,0));page=state['page'];g=state['pageGeometry']
            if state['visible'] and g:
                key=(page,round(g['width']),round(g['height']))
                if mode=='direct' or key not in cache:
                    pdf_page=document[page-1];bitmap=pdf_page.render(scale=config.get('score_dpi',144)/72)
                    picture=bitmap.to_pil().convert('RGBA').resize(key[1:],Image.Resampling.LANCZOS)
                    bitmap.close();pdf_page.close();renders+=1
                    if mode=='cached':cache[key]=picture
                else:picture=cache[key]
                image.alpha_composite(picture,(round(g['x']-g['scroll']['left']),round(g['y']-g['scroll']['top'])))
                draw=ImageDraw.Draw(image,'RGBA')
                if state['highlight']:
                    x,y,w,h=state['highlight'];draw.rectangle((x-v['x'],y-v['y'],x+w-v['x'],y+h-v['y']),fill=(255,223,66,64))
                if state['playhead']:
                    p=state['playhead'];draw.line((p['x']-v['x'],p['y']-v['y'],p['x']-v['x'],p['y']+p['height']-v['y']),fill=(214,58,66,255),width=2)
            hashes.append(hashlib.sha256(image.tobytes()).hexdigest())
    return {'mode':mode,'frames':len(states),'pdf_rasterizations':renders,'seconds':time.perf_counter()-start,
        'peak_process_rss_bytes':peak_rss(),'pixel_hashes':hashes}


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--package',type=Path,required=True)
    parser.add_argument('--frames',type=int,default=50);parser.add_argument('--worker',choices=['direct','cached'])
    args=parser.parse_args();package=args.package.resolve()
    if args.worker:
        result=worker(package,args.worker,read(package/'score/benchmark-states.json')['states'])
        write(package/f'score/benchmark-{args.worker}.json',result);return
    data=read(package/'score/render-input.json');plan=read(package/'score/plan.json');pts=read(package/'source-frame-timestamps.json')
    sample=[]
    for segment,probe in zip(plan['segments'],pts):
        for t in probe['frame_pts']:
            output=t-segment['video_start']+segment['output_start']
            state=next((e for e in plan['events'] if e['start']<=output<e['end']),None)
            if state and state['visible'] and state['pageGeometry']:sample.append(output)
    if not sample:raise ValueError('No visible score frames to benchmark')
    count=min(args.frames,len(sample));data['sample_times']=[sample[round(i*(len(sample)-1)/max(1,count-1))] for i in range(count)]
    write(package/'score/benchmark-input.json',data)
    subprocess.run(['node',str(ROOT/'scripts/video_export/export_score_plan.mjs'),str(package/'score/benchmark-input.json'),str(package/'score/benchmark-states.json')],check=True)
    for mode in ['direct','cached']:
        subprocess.run([sys.executable,str(Path(__file__).resolve()),'--package',str(package),'--worker',mode],check=True)
    direct=read(package/'score/benchmark-direct.json');cached=read(package/'score/benchmark-cached.json')
    equal=direct.pop('pixel_hashes')==cached.pop('pixel_hashes')
    result={'scope':'Score-only raster/viewport/highlight model on sampled real presentation timestamps; not a full Chromium or full-length composition benchmark.',
        'direct':direct,'cached':cached,'sampled_frame_pixels_identical':equal,
        'strategy':'Cache full PDF pages; compute shared-JS state at events; ASS interpolates playhead. No browser fallback needed for these effects.'}
    write(package/'benchmark-report.json',result);print(result)
    if not equal:raise ValueError('Cached and direct score frames differ')


if __name__=='__main__':main()
