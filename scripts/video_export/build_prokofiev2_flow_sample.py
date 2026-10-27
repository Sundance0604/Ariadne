"""Render a short Harmonic Flow video from the activated web note projection.

Only the new sample is encoded. The source performance, subtitles, PDF and
other video packages stay unchanged. Offline rasterization consumes the same
deterministic drawing commands as the Canvas 2D renderer.
"""
from pathlib import Path
from functools import lru_cache
import argparse, json, math, os, subprocess, sys

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT),str(ROOT/'scripts')]
from prokofiev2_sync import WORK, read, write, record, log
from backend.prokofiev2 import bundle
from backend.video_export.media import ffmpeg
from backend.video_export.paths import configured_path


def raster(frame,font_path):
    from PIL import Image,ImageDraw,ImageFont,ImageColor
    image=Image.new('RGBA',(frame['width'],frame['height']))
    @lru_cache(maxsize=32)
    def font(size):return ImageFont.truetype(str(font_path),size)
    for c in frame['commands']:
        color=(*ImageColor.getrgb(c['color']),round(255*c['alpha']))
        if c['op']=='rect':
            x,y=round(c['x']),round(c['y']);w,h=round(c['x']+c['w'])-x,round(c['y']+c['h'])-y
            if w>0 and h>0:image.alpha_composite(Image.new('RGBA',(w,h),color),(x,y))
        elif c['op']=='line':
            x,y=round(min(c['x'],c['x2'])),round(min(c['y'],c['y2']))
            w,h=round(abs(c['x2']-c['x']))+1,round(abs(c['y2']-c['y']))+1
            small=Image.new('RGBA',(w,h));draw=ImageDraw.Draw(small)
            draw.line((c['x']-x,c['y']-y,c['x2']-x,c['y2']-y),fill=color,width=1);image.alpha_composite(small,(x,y))
        elif c['op']=='text':
            f=font(round(c['size']));box=f.getbbox(c['text']);w=math.ceil(f.getlength(c['text']))+3;h=box[3]-box[1]+3
            small=Image.new('RGBA',(w,h));ImageDraw.Draw(small).text((0,-box[1]),c['text'],font=f,fill=color)
            image.alpha_composite(small,(round(c['x']),round(c['y'])))
    return image


def build(output,start=91.4,duration=45.0,panels=None,progress=None):
    # Legacy flow-only callers also receive the complete instrument registry,
    # rather than collapsing the available pitched notes to five families.
    flow_only=panels is None
    if flow_only:panels={'flow':{'enabled':True,'scale':1},'orchestration':{'enabled':False,'scale':1}}
    snapshot,manifest=bundle(ROOT,WORK)
    if 'flow.json' not in manifest['files']:raise ValueError('Activate web note projection first')
    output=output.resolve()
    if not output.is_relative_to(ROOT/'output/video-export'):raise ValueError('Sample output must stay under output/video-export')
    if output.exists():raise ValueError('Preserve existing sample; choose a new output directory')
    flow=read(snapshot/'flow.json');video=ROOT/flow['video']['path']
    if not any(s['start_seconds']<=start and start+duration<=s['end_seconds'] for s in flow['coverage']['segments']):raise ValueError('Sample crosses an uncovered gap')
    font_path=Path(os.environ.get('WINDIR','C:/Windows'))/'Fonts/msyh.ttc'
    if not font_path.exists():raise ValueError('Specify an available Chinese font before rendering')
    output.mkdir(parents=True)
    config={'start':start,'duration':duration,'fps':30,'width':400,'height':240,
        'video_width':1920,'video_height':1080,'overlay_x':24,'overlay_y':24,
        'description':'第一乐章XML第13–25小节附近：钢琴流动与弦乐、木管进入；原视频01:31.40起。',
        'source_scope':'XML notation projected through existing DTW; not live acoustic transcription',
        'pdf_inserted':False,'existing_subtitles_modified':False}
    additional_inputs=[]
    if panels is not None:
        from backend.video_export.visual_panels import validate_settings,part_registry,panel_layout,activity_payload
        panels=validate_settings(panels)
        registry_path=configured_path('visual_parts');registry_doc=read(registry_path)
        if registry_doc['xml_sha256']!=flow['source']['sha256']:raise ValueError('乐器清单与当前XML版本不匹配')
        parts=part_registry(registry_doc['parts'],colors=panels['part_colors'])
        flow_groups=[{**g,'color':panels['group_colors'].get(g['id'],g['color'])} for g in registry_doc.get('harmony_groups',[])] or None
        if flow_groups is not None:
            members=[pid for g in flow_groups for pid in g['part_ids']]
            if len(members)!=len(set(members)) or set(members)!={p['id'] for p in parts}:raise ValueError('和声分类与配器清单不一致')
        config.update(panel_layout(panels,parts=parts,flow_groups=flow_groups),panel_settings=panels)
        reference=read(WORK/'sync/reference/written.json');alignment=read(WORK/'alignment.json')
        activity=activity_payload(flow,read(snapshot/'evidence.json'),reference,alignment,parts,start-2,start+duration+4)
        if flow_groups is not None:activity['flow_groups']=flow_groups
        write(output/'activity.json',activity)
        additional_inputs=[registry_path,snapshot/'evidence.json',ROOT/'backend/video_export/visual_panels.py',
            ROOT/'review/orchestration-activity.mjs',ROOT/'scripts/video_export/export_visual_panels_plan.mjs',output/'activity.json']
    write(output/'config.json',config)
    plan=output/'flow-frames.jsonl'
    planner=['node',str(ROOT/'scripts/video_export/export_harmonic_flow_plan.mjs'),str(snapshot/'flow.json')]
    if panels is not None:planner=['node',str(ROOT/'scripts/video_export/export_visual_panels_plan.mjs'),str(snapshot/'flow.json'),str(output/'activity.json')]
    subprocess.run([*planner,str(output/'config.json'),str(plan)],check=True)
    binary=ffmpeg(ROOT);destination=output/('prokofiev2-harmonic-flow-sample.mp4' if flow_only else 'prokofiev2-visual-panels-sample.mp4')
    overlay_x,overlay_y=config.get('overlay_x',24),config.get('overlay_y',24)
    cmd=[binary,'-hide_banner','-nostdin','-n','-ss',str(start),'-i',str(video),
        '-f','rawvideo','-pixel_format','rgba','-video_size',f'{config["width"]}x{config["height"]}','-framerate','30','-i','pipe:0',
        '-filter_complex',f'[0:v]scale=1920:1080:flags=lanczos,setsar=1[base];[base][1:v]overlay={overlay_x}:{overlay_y}:shortest=1:format=auto,format=yuv420p[v]',
        '-map','[v]','-map','0:a:0','-t',str(duration),'-r','30','-c:v','libx264','-preset','veryfast','-crf','20',
        '-c:a','aac','-b:a','192k','-movflags','+faststart','-progress',str(output/'encoding-progress.txt'),str(destination)]
    count=0
    with (output/'encoding.log').open('wb') as log_file:
        proc=subprocess.Popen(cmd,stdin=subprocess.PIPE,stdout=subprocess.DEVNULL,stderr=log_file)
        try:
            with plan.open(encoding='utf8') as stream:
                for row in stream:
                    frame=json.loads(row);image=raster(frame,font_path)
                    if count in {0,450,960}:image.save(output/f'flow-{count:04d}.png')
                    proc.stdin.write(image.tobytes());count+=1
                    if count%300==0:log(f'Flow sample: {count}/1350 frames')
                    if progress and count%15==0:progress(min(99,count/(duration*30)*100),'正在生成可视化样片')
            proc.stdin.close()
            if proc.wait()!=0:raise RuntimeError('FFmpeg failed; inspect encoding.log')
        except BaseException:
            proc.kill();proc.wait();raise
    write(output/'manifest.json',{'source_video':record(video),'snapshot':snapshot.relative_to(ROOT).as_posix(),
        'inputs':[record(p) for p in [snapshot/'flow.json',WORK/'alignment.json',Path(__file__),ROOT/'review/harmonic-flow.mjs',
            ROOT/'scripts/video_export/export_harmonic_flow_plan.mjs',output/'config.json',*additional_inputs]],
        'output':record(destination),'frames':count,'audio':'same source performance, clipped and AAC encoded',
        'rasterization':'shared JS drawing geometry; Canvas browser and Pillow offline font rasterization can differ',
        'human_signoff':None,'browser_playback_review':False,'video_export_authorized':True,
        'pdf_inserted':False,'existing_subtitles_modified':False})
    log(f'Created {destination}')
    if progress:progress(100,'样片已生成')
    return destination


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,default=ROOT/'output/video-export/prokofiev2-harmonic-flow-sample-001')
    args=p.parse_args();build(args.output)
