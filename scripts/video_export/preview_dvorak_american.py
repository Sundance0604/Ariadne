"""Render representative source frames with the actual shared export layers."""
from pathlib import Path
import json,subprocess,sys
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from backend.video_export.content import read,write
from backend.video_export.media import ffmpeg
from backend.video_export.visual_raster import raster
from backend.video_export.editor import prepare
from backend.video_export.coverage import caption_coverage,blank_intervals

def main():
    from PIL import Image
    package=ROOT/'output/video-export/dvorak-american-full-001'
    ready=read(ROOT/'works/dvorak-american/video-export/package-ready.json')
    revision=ROOT/ready['prepared_revision'];config=read(revision/'config.json')
    folder=package/'previews-v2';folder.mkdir(exist_ok=True)
    times=[6,21,105,628,679,1112,1208,1297,1519,1638]
    visual={**config['visual_layout'],'frame_count':len(times),'frame_times':times}
    write(folder/'visual-config.json',visual)
    result=subprocess.run(['node',str(package/'visuals/renderer/stream.mjs'),str(package/'visuals/flow.json'),
        str(package/'visuals/activity.json'),str(folder/'visual-config.json')],capture_output=True,encoding='utf8',check=True)
    frames=[json.loads(line) for line in result.stdout.splitlines()]
    original=read(package/'score/plan.json')['events'];page_events=read(package/'score/page-events.json')
    plan=read(revision/'score-plan.json')['events'];cache={};j=0
    def key(e):return json.dumps([e['page'],e['pageGeometry']],sort_keys=True)
    for e in original:
        while j+1<len(page_events) and page_events[j]['end']<=e['start']+1e-7:j+=1
        if e['visible'] and e.get('pageGeometry'):cache[key(e)]=package/'score'/page_events[j]['file']
    _,events,_=prepare(read(ROOT/ready['document']),package)
    records=[]
    for time,frame in zip(times,frames):
        name=f'{time:07.2f}';source=folder/(name+'-source.png');base=folder/(name+'-base.png');output=folder/(name+'.png')
        subprocess.run([ffmpeg(ROOT),'-v','error','-n','-ss',str(time),'-i',str(package/'performance.mp4'),
            '-frames:v','1','-update','1',str(source)],check=True)
        image=Image.open(source).convert('RGBA');e=next(e for e in plan if e['start']<=time<e['end'])
        if e['visible']:
            image.alpha_composite(Image.open(cache[key(e)]).convert('RGBA'),(config['layout']['score']['x'],config['layout']['score']['y']))
        image.alpha_composite(raster(frame,Path('C:/Windows/Fonts/msyh.ttc')),(visual['overlay_x'],visual['overlay_y']))
        image.convert('RGB').save(base)
        relative=revision.name
        subprocess.run([ffmpeg(ROOT),'-v','error','-n','-i',str(base),'-vf',
            f"setpts=PTS+{time}/TB,ass=filename='{relative}/score.ass',ass=filename='{relative}/analysis.ass'",
            '-frames:v','1','-update','1',str(output)],cwd=package,check=True)
        records.append({'video_seconds':time,'path':output.relative_to(ROOT).as_posix(),'page':e['page'],
            'score_visible':e['visible'],'interpretation':any(x['slot']=='interpretation' and x['output_start']<=time<x['output_end'] for x in events)})
        print('Preview',time,flush=True)
    ranges=read(ROOT/'works/dvorak-american/alignment.json')['score_time_coverage']['segments']
    coverage=caption_coverage(events,config);scopes=[[r['start_seconds'],r['end_seconds']] for r in ranges]
    write(ROOT/'works/dvorak-american/video-export/preview-and-coverage.json',{'previews':records,
        'visible_caption_union':coverage,'listening_gaps':blank_intervals(coverage,scopes),
        'basis':'Actual ASS display times; blank areas retained as listening space; not musical boundaries',
        'full_video_encoded':False,'human_signoff':None})

if __name__=='__main__':main()
