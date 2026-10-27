"""Full export composition, invoked only when the user renders from the editor."""
from pathlib import Path
import copy,json,os,subprocess
from .content import read,write,digest
from .paths import ROOT,configured_path
from .media import ffmpeg,run
from .visual_panels import load_settings,validate_settings,part_registry,panel_layout
from .visual_raster import raster
from .presentation import presentation_config

def full_layout(config,settings,registry):
    config=presentation_config(config,config.get('presentation_rules',{'分析':{},'诠释':{}}));settings=validate_settings(settings)
    parts=part_registry(registry['parts'],colors=settings['part_colors'])
    groups=registry.get('harmony_groups')
    view=panel_layout(settings,parts=parts,flow_groups=groups)
    top=max(p['y']+p['height'] for p in view['panels'].values())+16
    bottom=config['height']-24;available=bottom-top
    row=min(168,(available-168-16)/2)
    if row<120:raise ValueError('面板太大，下方分析空间不足；请减小面板')
    config['layout']={
        'harmony':{'x':40,'y':top,'w':600,'h':row,'font_size':32},
        'orchestration':{'x':664,'y':top,'w':600,'h':row,'font_size':32},
        'counterpoint':{'x':40,'y':top+row+8,'w':600,'h':row,'font_size':32},
        'form':{'x':664,'y':top+row+8,'w':600,'h':row,'font_size':32},
        'guide':{'x':40,'y':top+2*row+16,'w':1224,'h':168,'font_size':30},
        'interpretation':{'x':220,'y':top+16,'w':1480,'h':available-16,'font_size':44},
        'score':{'x':config['width']-600,'y':top,'w':600,'h':available,'align':'right'},
        'intro':{'x':220,'y':190,'w':1480,'h':700,'font_size':58,'align':'center'}}
    config['visual_layout']=view;config['visual_settings']=settings
    return config

def refreshed_config(package,config):
    if not config.get('visualization'):return config
    return full_layout(config,load_settings(),read(package/config['visualization']['registry']))

def stage_visuals(package,folder,config):
    spec=config['visualization'];registry=read(package/spec['registry']);settings=config['visual_settings']
    activity=read(package/spec['activity']);activity['parts']=part_registry(registry['parts'],colors=settings['part_colors'])
    activity['flow_groups']=[{**g,'color':settings['group_colors'].get(g['id'],g['color'])} for g in registry['harmony_groups']]
    write(folder/'visual-activity.json',activity)
    probes=read(package/'source-frame-timestamps.json')[0]
    duration=config['segments'][0]['video_end']-config['segments'][0]['video_start']
    fps=round(probes['frame_count']/duration)
    residual=max(abs(t-(probes['first_pts']+i/fps)) for i,t in enumerate(probes['frame_pts']))
    if residual>.25/fps:raise ValueError('原视频帧率变化过大，需要独立的变帧率图层适配')
    if abs(probes['frame_count']/fps-duration)>.05:raise ValueError('原片帧数与导出时长不一致')
    value={**config['visual_layout'],'fps':fps,'start':config['segments'][0]['video_start'],
        'duration':duration,'frame_count':probes['frame_count'],'frame_times':probes['frame_pts'],
        'source_grid_residual_seconds':residual,'last_duration_seconds':min(probes['frame_durations'][-1] or 1/fps,
            config['segments'][0]['video_end']-probes['last_pts'])}
    write(folder/'visual-config.json',value)
    return value

def composition_command(package,folder,config,visual):
    relative=folder.name;score=config['layout']['score'];segment=config['segments'][0]
    graph=(f'[0:v]settb=AVTB,scale={config["width"]}:{config["height"]}:flags=lanczos,setsar=1[base];'
        '[1:v]format=rgba[paper];'
        f'[base][paper]overlay={score["x"]}:{score["y"]}:eof_action=repeat:repeatlast=1:format=auto[withpaper];'
        f'[withpaper][2:v]overlay={visual["overlay_x"]}:{visual["overlay_y"]}:eof_action=pass:repeatlast=0:ts_sync_mode=nearest:format=auto,'
        f"ass=filename='{relative}/score.ass',ass=filename='{relative}/analysis.ass',format=yuv420p[out]")
    (folder/'compose.ffgraph').write_text(graph,encoding='utf8')
    tail=f'setts=duration=if(eq(N\\,{visual["frame_count"]-1})\\,{visual["last_duration_seconds"]:.9f}/TB\\,DURATION)'
    return [ffmpeg(ROOT),'-hide_banner','-nostdin','-n','-ss',str(segment['video_start']),'-i','performance.mp4',
        '-safe','0','-f','concat','-i',f'{relative}/pages.ffconcat','-f','rawvideo','-pixel_format','rgba',
        '-video_size',f'{visual["width"]}x{visual["height"]}','-framerate',str(visual['fps']),'-i','pipe:0',
        '-filter_complex_script',f'{relative}/compose.ffgraph','-map','[out]','-map','0:a:0',
        '-t',str(visual['duration']),'-c:v','libx264','-crf',str(config.get('crf',20)),'-preset',config.get('preset','veryfast'),
        '-bf','0','-fps_mode:v','passthrough','-enc_time_base:v','demux','-bsf:v',tail,
        '-c:a','copy','-map_metadata','-1','-movflags','+faststart',str(folder/'导聆视频.mp4')]

def export_visual_revision(package,folder,config,emit):
    from .pipeline import verify_bindings
    verify_bindings(package)
    visual=stage_visuals(package,folder,config);cmd=composition_command(package,folder,config,visual)
    spec=config['visualization'];font=Path(os.environ.get('WINDIR','C:/Windows'))/'Fonts/msyh.ttc'
    if not font.exists():raise ValueError('缺少面板中文字体 Microsoft YaHei')
    renderer=package/spec['renderer'];flow=package/spec['flow']
    hidden=getattr(subprocess,'CREATE_NO_WINDOW',0)
    emit(0,'正在合成谱面、字幕、和声五类与逐件配器……')
    with (folder/'export.log').open('wb') as err,(folder/'visual-render.log').open('wb') as node_err:
        node=subprocess.Popen(['node',str(renderer),str(flow),str(folder/'visual-activity.json'),str(folder/'visual-config.json')],
            stdout=subprocess.PIPE,stderr=node_err,text=True,encoding='utf8',creationflags=hidden)
        encoder=subprocess.Popen(cmd,cwd=package,stdin=subprocess.PIPE,stdout=subprocess.DEVNULL,stderr=err,creationflags=hidden)
        count=0
        try:
            for line in node.stdout:
                encoder.stdin.write(raster(json.loads(line),font).tobytes());count+=1
                if count%30==0:emit(min(99,int(count/visual['frame_count']*100)),f'正在生成视频：{count}/{visual["frame_count"]}帧')
            encoder.stdin.close()
            if node.wait() or encoder.wait() or count!=visual['frame_count']:raise RuntimeError('合成未完成，请查看本次export.log与visual-render.log')
        except BaseException:
            node.kill();encoder.kill();node.wait();encoder.wait();raise
        finally:node.stdout.close()
    output=folder/'导聆视频.mp4'
    if config.get('chapters'):
        rows=[';FFMETADATA1']
        for i,c in enumerate(config['chapters']):
            end=config['chapters'][i+1]['start'] if i+1<len(config['chapters']) else visual['duration']
            title=c['title'].replace('\\','\\\\').replace('\n',' ').replace('=','\\=').replace(';','\\;').replace('#','\\#')
            rows+=['[CHAPTER]','TIMEBASE=1/1000',f'START={round(c["start"]*1000)}',f'END={round(end*1000)}','title='+title]
        (folder/'chapters.ffmetadata').write_text('\n'.join(rows)+'\n',encoding='utf8')
        chaptered=folder/'导聆视频-含章节.mp4'
        run([ffmpeg(ROOT),'-v','error','-n','-i',str(output),'-i',str(folder/'chapters.ffmetadata'),'-map','0','-map_metadata','1',
            '-map_chapters','1','-c','copy','-movflags','+faststart',str(chaptered)],folder/'chapters.log');output=chaptered
    report=read(folder/'review-report.json');report.update(status='rendered_for_user_viewing',
        output={'video':output.name,'bytes':output.stat().st_size,'duration_seconds':visual['duration'],'rendered_frames':count},
        audio='original AAC stream copied',human_signoff=None)
    write(folder/'review-report.json',report)
    write(package/'latest-caption-export.json',{'video':str(output),'subtitles':str(folder/'analysis.ass')})
    configured_path('latest_video').write_text(str(output)+'\n',encoding='utf-8-sig')
    emit(100,'已完成：'+str(output));return output
