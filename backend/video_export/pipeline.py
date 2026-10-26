"""Editable export package and event-driven composition using existing HTTP data."""
from contextlib import contextmanager
from pathlib import Path
import json
import math
import re
import shutil
import subprocess
import sys
import threading
import time
from urllib.request import urlopen
from .content import read,write,digest,bounded,review_events,output_events,content_hash,FORBIDDEN,normalized
from .subtitles import analysis_ass,score_ass
from .media import ffmpeg,run,inspect_frames,audio_hash


def validate_config(config):
    if config.get('format_version')!='1.0':raise ValueError('Unknown export configuration')
    if config.get('music_start_confirmation',{}).get('status')!='user_confirmed':raise ValueError('Confirm music entry before release export')
    if not math.isfinite(config['music_start_video']) or config['music_start_video']<3:raise ValueError('Invalid music entry')
    if config.get('intro_clear_video',config['music_start_video']-3)>config['music_start_video']-3:raise ValueError('Intro clear frame is after the three-second deadline')
    if not config['segments']:raise ValueError('No export segments')
    if len(config['segments'])!=1:raise ValueError('This release exports one continuous source interval; montage cuts need separate audio editing')
    if config.get('characters_per_second',7)<=0 or config.get('minimum_caption_seconds',3)<=0 or config['font_size']<=0:raise ValueError('Invalid caption reading/font settings')
    if not isinstance(config['font'],str) or any(c in config['font'] for c in ',\r\n'):raise ValueError('Invalid font')
    if not re.fullmatch(r'#[0-9a-fA-F]{6}',config['yellow']):raise ValueError('Invalid subtitle colour')
    for s in config['segments']:
        if not all(isinstance(s[k],(int,float)) and math.isfinite(s[k]) for k in ['video_start','video_end']) or not 0<=s['video_start']<s['video_end']:raise ValueError('Invalid segment')
    for name,box in config['layout'].items():
        if not all(isinstance(box[k],(int,float)) and math.isfinite(box[k]) for k in ['x','y','w','h']):raise ValueError('Invalid layout')
        if min(box['x'],box['y'])<0 or min(box['w'],box['h'])<=0 or box['x']+box['w']>config['width'] or box['y']+box['h']>config['height']:raise ValueError('Layout outside canvas')
    def overlap(a,b):return a['x']<b['x']+b['w'] and b['x']<a['x']+a['w'] and a['y']<b['y']+b['h'] and b['y']<a['y']+a['h']
    names=['harmony','orchestration','counterpoint','form','guide','score']
    for i,name in enumerate(names):
        for other in names[i+1:]:
            if overlap(config['layout'][name],config['layout'][other]):raise ValueError('Fixed slots overlap: '+name+'/'+other)
    for name in names[:-1]:
        if overlap(config['layout'][name],config['layout']['interpretation']):raise ValueError('Interpretation overlaps regular subtitle')
    if config.get('score_zoom',1)<1:raise ValueError('Invalid score zoom')


@contextmanager
def project_server(root):
    scripts=str(Path(root)/'scripts')
    if scripts not in sys.path:sys.path.insert(0,scripts)
    import serve_review
    class QuietHandler(serve_review.Handler):
        def log_message(self,*args):pass
    server=serve_review.ReviewServer(('127.0.0.1',0),QuietHandler)
    worker=threading.Thread(target=server.serve_forever,daemon=True);worker.start()
    try:yield f'http://127.0.0.1:{server.server_port}'
    finally:server.shutdown();server.server_close();worker.join()


def fetch(url):
    with urlopen(url,timeout=180) as response:return json.load(response)


def make_package(root,track,profile,captions,output):
    root=Path(root).resolve();output=Path(output).resolve()
    if output.exists():raise ValueError('Use a new export directory; existing exports are preserved')
    if not output.is_relative_to(root):raise ValueError('Export must be inside workspace')
    config=read(profile);validate_config(config)
    with project_server(root) as url:
        project=fetch(f'{url}/api/project?track={track}')
    if project.get('xml_navigation_error'):raise ValueError(project['xml_navigation_error'])
    media=project.get('media')
    if not media or media['masterClock']!='video':raise ValueError('This exporter requires a video-master track')
    if not any(s.get('codec_type')=='audio' and s.get('codec_name')=='aac' for s in media['video'].get('streams',[])):
        raise ValueError('This release requires an existing AAC audio track for unchanged MP4 audio copying')
    video=bounded(root,media['video']['path']);pdf=bounded(root,project['mapping']['pdf_path'])
    if digest(video)!=media['video']['sha256'] or digest(pdf)!=project['mapping']['pdf_sha256']:raise ValueError('Media/PDF fingerprint changed')
    if media['video']['sha256']!=project['alignment']['audio']['sha256']:raise ValueError('Alignment belongs to another performance')
    if any(s['video_end']>media['video']['duration_seconds'] for s in config['segments']):raise ValueError('Segment beyond video duration')
    document=read(captions)
    from review_library import track_context
    _,directory=track_context(root,track)
    if document.get('video_sha256')!=media['video']['sha256'] or document.get('alignment_sha256')!=digest(directory/'alignment.json'):raise ValueError('Caption performance/timeline binding changed')
    accepted,excluded=review_events(document,config,root)
    if any(e.get('phase')=='intro' for e in accepted):
        prefix=inspect_frames(ffmpeg(root),video,0,config['music_start_video'])
        cutoff=config['music_start_video']-3
        config['intro_clear_video']=max(t for t in prefix['frame_pts'] if t<=cutoff+1e-7)
        config['intro_clearance_basis']='actual source presentation frame at or before music entry minus three seconds'
    projected=output_events(accepted,config,excluded)
    if not projected:
        output.mkdir(parents=True)
        write(output/'review-report.json',{'status':'publication_review_failed','accepted_ids':[e['id'] for e in accepted],
            'excluded':excluded,'reason':'No readable publication-reviewed subtitles in the output interval'})
        raise ValueError('No readable publication-reviewed subtitles; review-report.json was written without copying media')
    # Run layout/reading checks before creating a large media package.
    ass=analysis_ass(projected,config)
    output.mkdir(parents=True);(output/'score').mkdir();(output/'evidence').mkdir()
    for event in accepted:
        for ref in event['review']['sources']:
            target=bounded(output/'evidence',ref['path']);target.parent.mkdir(parents=True,exist_ok=True)
            if not target.exists():shutil.copy2(bounded(root,ref['path']),target)
    shutil.copy2(video,output/'performance.mp4')
    shutil.copy2(pdf,output/'score/source.pdf')
    write(output/'alignment.json',project['alignment']);write(output/'project.json',project)
    write(output/'annotations.json',{'format_version':'1.0','video_sha256':media['video']['sha256'],
        'alignment_sha256':document['alignment_sha256'],'events':accepted})
    write(output/'export-config.json',config)
    (output/'analysis.ass').write_text(ass,encoding='utf-8-sig')
    # Retain explicit exclusions from the original research materials. They are
    # evidence of omission, never input to the subtitle renderer.
    for name,key in [('analysis/structural-events.json','events'),('analysis/hermeneutic-essays.json','essays'),('analysis/annotations.json','annotations')]:
        if (root/name).exists():
            for row in read(root/name).get(key,[]):
                excluded.append({'id':row.get('id',row.get('annotation_id')),'source':name,
                    'text':row.get('short_label',row.get('title','')),
                    'source_review_status':row.get('review_status',row.get('verification')),
                    'reasons':['research_record_not_individually_publication_reviewed']})
    report={'format_version':'1.0','accepted_ids':[e['id'] for e in accepted],'excluded':excluded,
        'review_scope':'agent source checks on selected captions; no human/expert signature inferred',
        'music_start_confirmation':config['music_start_confirmation'],'checks':{'subtitle_review_before_generation':True},
        'limitations':['Existing DTW is retained; confirming the music entry does not verify every later note.'],
        'status':'package_prepared_video_verification_required'}
    write(output/'review-report.json',report)
    manifest={'format_version':'1.0','track':track,'config':'export-config.json','performance':'performance.mp4',
        'source':media['video'],'source_pdf_sha256':project['mapping']['pdf_sha256'],
        'annotations':'annotations.json','analysis_ass':'analysis.ass','alignment':'alignment.json',
        'time_axes':{'outputTime':'seconds in concatenated output segments','videoTime':'seconds in original performance',
            'musicTime':'videoTime minus confirmed music_start_video'},
        'composition':'original video + cached full PDF pages + JS-derived score vectors + single yellow ASS track',
        'audio':'original AAC packet stream copied; no time stretch or mixing','subtitle_font':config['font'],
        'font_distribution':'font not bundled; final burned-in MP4 needs no viewer fonts',
        'checksums':{name:digest(output/name) for name in ['performance.mp4','score/source.pdf','alignment.json','project.json','annotations.json','analysis.ass','export-config.json']}}
    for path in (output/'evidence').rglob('*'):
        if path.is_file():manifest['checksums'][path.relative_to(output).as_posix()]=digest(path)
    write(output/'export-manifest.json',manifest)
    return output


def regenerate_ass(package):
    package=Path(package);config=read(package/'export-config.json');validate_config(config)
    document=read(package/'annotations.json');events,excluded=review_events(document,config,package/'evidence')
    report=read(package/'review-report.json');report['subtitle_regeneration_excluded']=excluded
    report['status']='subtitles_updated_render_required'
    write(package/'review-report.json',report)
    if excluded:raise ValueError('Edited captions require source review and a new content_sha256; see review-report.json')
    clipping=[]
    (package/'analysis.ass').write_text(analysis_ass(output_events(events,config,clipping),config),encoding='utf-8-sig')
    report['output_clipping_excluded']=clipping;write(package/'review-report.json',report)
    manifest=read(package/'export-manifest.json')
    for name in ['annotations.json','analysis.ass','export-config.json']:manifest['checksums'][name]=digest(package/name)
    write(package/'export-manifest.json',manifest)
    return len(events)


def review_caption(package,identifier,reviewer,scope):
    """Record an explicit editor review; never infer a human/expert signature."""
    package=Path(package);document=read(package/'annotations.json');config=read(package/'export-config.json')
    event=next((e for e in document['events'] if e['id']==identifier),None)
    if not event:raise ValueError('Unknown caption ID')
    previous=dict(event['review'])
    event['review']={**previous,'status':'approved','reviewer':reviewer,'scope':scope,
        'human_signature':None,'content_sha256':content_hash(event)}
    accepted,excluded=review_events({'events':[event]},config,package/'evidence')
    if excluded:raise ValueError('Review rejected: '+str(excluded))
    write(package/'annotations.json',document)
    history=package/'caption-review-history.json'
    rows=read(history) if history.exists() else []
    rows.append({'id':identifier,'previous_review':previous,'new_review':event['review']})
    write(history,rows)
    return identifier


def import_ass_text(package,source,reviewer,scope):
    """Import independently edited ASS text while preserving fixed styles/times."""
    package=Path(package);config=read(package/'export-config.json');document=read(package/'annotations.json')
    projected=output_events(document['events'],config)
    original=analysis_ass(projected,config).splitlines()
    edited=Path(source).read_text(encoding='utf-8-sig').splitlines()
    if len(original)!=len(edited):raise ValueError('ASS text import preserves dialogue count, styles and timing; edit annotations for new events')
    changed={}
    for old,new in zip(original,edited):
        if old==new:continue
        if not old.startswith('Dialogue:') or not new.startswith('Dialogue:'):raise ValueError('Fixed ASS styles/positions cannot be changed during text import')
        a,b=old.split(',',9),new.split(',',9)
        if a[:9]!=b[:9]:raise ValueError('ASS timing/style changes require annotation review')
        old_tags=re.match(r'^\{[^}]*\}',a[9]);new_tags=re.match(r'^\{[^}]*\}',b[9])
        if not old_tags or not new_tags or old_tags[0]!=new_tags[0]:raise ValueError('Fixed ASS position/animation tags changed')
        text=b[9][len(new_tags[0]):].replace(r'\N','\n')
        if any(c in text for c in '{}\\'):raise ValueError('ASS text cannot inject overrides')
        def seconds(s):
            h,m,v=s.split(':');return int(h)*3600+int(m)*60+float(v)
        start,end=seconds(a[1]),seconds(a[2]);style=a[3]
        matches=[e for e in projected if ('intro' if e.get('phase')=='intro' else e['slot'])==style and
            e['output_start']>=start-.011 and e['output_end']<=end+.011]
        if not matches:raise ValueError('Cannot identify source caption for edited dialogue')
        for e in matches:changed[e['id']]=text
    for event in document['events']:
        if event['id'] not in changed:continue
        event['text']=changed[event['id']]
        event['review']={**event['review'],'reviewer':reviewer,'scope':scope,'human_signature':None,
            'content_sha256':content_hash(event)}
    accepted,excluded=review_events(document,config,package/'evidence')
    if excluded:raise ValueError('Edited ASS failed publication review: '+str(excluded))
    write(package/'annotations.json',document);regenerate_ass(package)
    return list(changed)


def prepare_score(root,package):
    from PIL import Image
    package=Path(package).resolve();config=read(package/'export-config.json');project=read(package/'project.json')
    validate_config(config)
    annotations=read(package/'annotations.json')['events'];start=time.perf_counter()
    shown={e['id'] for e in output_events(annotations,config)}
    annotations=[e for e in annotations if e['id'] in shown]
    renderer=package/'score/renderer';renderer.mkdir(exist_ok=True)
    for name in ['video-export.mjs','score-display.mjs','score-follow.mjs','playhead.mjs']:
        shutil.copy2(Path(root)/'review'/name,renderer/name)
    (renderer/'render-plan.mjs').write_text("import fs from 'node:fs';import {createExportRenderer} from './video-export.mjs';const [i,o]=process.argv.slice(2);fs.writeFileSync(o,JSON.stringify(createExportRenderer(JSON.parse(fs.readFileSync(i,'utf8'))).plan()));",encoding='utf-8')
    write(package/'score/render-input.json',{'config':config,'project':project,'annotations':annotations})
    result=subprocess.run(['node',str(renderer/'render-plan.mjs'),str(package/'score/render-input.json'),str(package/'score/plan.json')],capture_output=True,text=True,encoding='utf-8')
    if result.returncode:raise RuntimeError(result.stderr)
    plan=read(package/'score/plan.json');v=config['layout']['score'];size=(v['w'],v['h'])
    blank=Image.new('RGBA',size,(0,0,0,0));blank.save(package/'score/blank.png')
    from scripts.pdf_render import render_page
    pages={};page_events=[];issues=[];previous_page=None
    for event in plan['events']:
        if event.get('issue'):issues.append({'time':event['videoTime'],'measure_id':event['measureId'],'reason':event['issue'],'action':'highlight_and_line_hidden'})
        key='blank';geometry=event.get('pageGeometry')
        if event['visible'] and geometry:
            page=event['page'];key=json.dumps([page,geometry],sort_keys=True)
            if previous_page is not None and page<previous_page:
                issues.append({'time':event['videoTime'],'reason':'page_regression','from':previous_page,'to':page})
            previous_page=page
            if key not in pages:
                raster=package/f'score/page-{page:03}.png'
                if not raster.exists():render_page(package/'score/source.pdf',page,raster,dpi=config.get('score_dpi',144))
                canvas=blank.copy()
                with Image.open(raster) as image:
                    scaled=image.convert('RGBA').resize((round(geometry['width']),round(geometry['height'])),Image.Resampling.LANCZOS)
                canvas.alpha_composite(scaled,(round(geometry['x']-geometry['scroll']['left']),round(geometry['y']-geometry['scroll']['top'])))
                name=f'view-{len(pages):04}.png';canvas.save(package/'score'/name);pages[key]=name
        name=pages.get(key,'blank.png')
        if page_events and page_events[-1]['file']==name:page_events[-1]['end']=event['end']
        else:page_events.append({'start':event['start'],'end':event['end'],'file':name})
    # Microsecond image time base; no 25-fps quantisation of event boundaries.
    concat=['ffconcat version 1.0']
    for e in page_events:
        concat += [f"file '{e['file']}'",'option framerate 1000000',f"duration {e['end']-e['start']:.6f}"]
    concat += [f"file '{page_events[-1]['file']}'",'option framerate 1000000']
    (package/'score/pages.ffconcat').write_text('\n'.join(concat)+'\n',encoding='utf-8')
    (package/'score/graphics.ass').write_text(score_ass(plan,config),encoding='utf-8-sig')
    write(package/'score/page-events.json',page_events)
    report=read(package/'review-report.json');report['score_issues']=list({json.dumps(i,sort_keys=True):i for i in issues}.values())
    report['checks'].update({'fixed_score_viewport':True,'original_js_modules_used':plan['reuse'],
        'interpretation_hides_score':all(not e['visible'] for e in plan['events'] if any(a['slot']=='interpretation' and a.get('phase')!='intro' and a['video_start']<=e['videoTime']<a['video_end'] for a in annotations)),
        'no_unexpected_page_regression':not any(i['reason']=='page_regression' for i in issues)})
    report['performance']={'score_prepare_seconds':time.perf_counter()-start,'cached_view_count':len(pages),
        'event_count':len(plan['events']),'page_switch_events':len(page_events),'browser_frames_rendered':0}
    write(package/'review-report.json',report)
    manifest=read(package/'export-manifest.json');manifest['score']={'plan':'score/plan.json','graphics':'score/graphics.ass','pages':'score/pages.ffconcat'}
    manifest['checksums']={k:v for k,v in manifest['checksums'].items() if not k.startswith('score/benchmark-')}
    for p in (package/'score').rglob('*'):
        if p.is_file() and not p.name.startswith('benchmark-'):manifest['checksums'][p.relative_to(package).as_posix()]=digest(p)
    write(package/'export-manifest.json',manifest)
    return report['performance']


def verify_bindings(package):
    manifest=read(package/'export-manifest.json')
    for name,sha in manifest['checksums'].items():
        if digest(bounded(package,name))!=sha:raise ValueError('Export input changed: '+name)
    return manifest


def compose(root,package):
    package=Path(package).resolve();manifest=verify_bindings(package);config=read(package/'export-config.json')
    validate_config(config)
    score_input=read(package/'score/render-input.json')
    timeline=lambda rows:[{k:e.get(k) for k in ['id','slot','phase','video_start','video_end']} for e in rows]
    annotations=read(package/'annotations.json')['events'];shown={e['id'] for e in output_events(annotations,config)}
    if score_input['config']!=config or timeline(score_input['annotations'])!=timeline([e for e in annotations if e['id'] in shown]):
        raise ValueError('Score-event times changed; run the score step again (cached PDF pages are reused)')
    binary=ffmpeg(root);filters=run([binary,'-hide_banner','-filters']).stdout
    if ' ass ' not in filters:raise RuntimeError('FFmpeg needs libass')
    report=read(package/'review-report.json')
    if not report['checks'].get('no_unexpected_page_regression'):raise ValueError('Correct page regressions before composition')
    start=time.perf_counter();offset=0;parts=[];probes=[]
    for i,segment in enumerate(config['segments']):
        duration=segment['video_end']-segment['video_start'];name=f'part-{i:03}.mp4';parts.append(name)
        print(f'Inspecting source timestamps: segment {i+1}',flush=True)
        probe=inspect_frames(binary,package/'performance.mp4',segment['video_start'],duration,package/f'source-pts-{i:03}.log');probes.append(probe)
        if (probe['stream']['width'],probe['stream']['height'])!=(config['width'],config['height']):raise ValueError('Export canvas must match source dimensions in this version')
        v=config['layout']['score'];(package/f'compose-{i:03}.ffgraph').write_text(
            f'[0:v]settb=AVTB[base];[1:v]format=rgba[paper];'
            f'[base]setpts=PTS+{offset}/TB[timed];'
            f'[timed][paper]overlay=x={v["x"]}:y={v["y"]}:eof_action=repeat:repeatlast=1:format=auto,'
            "ass=filename='score/graphics.ass',ass=filename='analysis.ass',"
            f'setpts=PTS-{offset}/TB,format=yuv420p[out]',encoding='utf-8')
        # Seek shifts source timestamps by the requested start. Do not reset the
        # first video frame to zero: its fractional delay relative to AAC matters.
        # Sparse secondary images make overlay advertise an artificial nominal
        # frame rate. Preserve source PTS and explicitly give the final packet
        # its measured source duration, otherwise MP4 edit lists can drop it.
        last_duration=probe['frame_durations'][-1] or probe['min_frame_delta']
        last_duration=min(last_duration,segment['video_end']-probe['last_pts'])
        duration_bsf=f'setts=duration=if(eq(N\\,{probe["frame_count"]-1})\\,{last_duration:.9f}/TB\\,DURATION)'
        command=[binary,'-hide_banner','-nostdin','-y','-ss',str(segment['video_start']),'-i','performance.mp4',
            '-safe','0','-f','concat','-i','score/pages.ffconcat','-filter_complex_script',f'compose-{i:03}.ffgraph',
            '-map','[out]','-map','0:a:0','-t',str(duration),'-c:v','libx264','-crf',str(config.get('crf',18)),
            '-preset',config.get('preset','medium'),'-bf','0','-fps_mode:v','passthrough','-enc_time_base:v','demux','-bsf:v',duration_bsf,
            '-c:a','copy','-map_metadata','-1','-movflags','+faststart',name]
        print(f'Compositing segment {i+1}',flush=True);run(command,package/f'compose-{i:03}.log',package)
        offset+=duration
    if len(parts)==1:shutil.copy2(package/parts[0],package/'guided-performance.mp4')
    else:
        rows=['ffconcat version 1.0']
        for name,s in zip(parts,config['segments']):rows += [f"file '{name}'",f"duration {s['video_end']-s['video_start']:.9f}"]
        (package/'parts.ffconcat').write_text('\n'.join(rows)+'\n',encoding='utf-8')
        run([binary,'-v','error','-y','-safe','0','-f','concat','-i','parts.ffconcat','-c','copy','-movflags','+faststart','guided-performance.mp4'],package/'join.log',package)
    report['source_timestamp_inspection']=[{k:v for k,v in p.items() if k not in {'frame_pts','frame_durations'}} for p in probes]
    write(package/'source-frame-timestamps.json',probes)
    report['performance']['composition_seconds']=time.perf_counter()-start
    report['render_manifest_sha256']=digest(package/'export-manifest.json')
    report['status']='composed_verification_required';write(package/'review-report.json',report)
    return package/'guided-performance.mp4'


def verify_video(root,package):
    package=Path(package).resolve();verify_bindings(package);config=read(package/'export-config.json');binary=ffmpeg(root)
    output=package/'guided-performance.mp4';report=read(package/'review-report.json')
    if report.get('render_manifest_sha256')!=digest(package/'export-manifest.json'):raise ValueError('Export inputs changed after composition; render again')
    pts=read(package/'source-frame-timestamps.json');duration=sum(s['video_end']-s['video_start'] for s in config['segments'])
    actual=inspect_frames(binary,output,0,duration+.1,package/'output-pts.log')
    expected=[];offset=0
    audio=[]
    for i,s in enumerate(config['segments']):
        expected += [t-s['video_start']+offset for t in pts[i]['frame_pts'] if s['video_start']-1e-5<=t<s['video_end']-1e-5]
        length=s['video_end']-s['video_start']
        a=audio_hash(binary,package/'performance.mp4',s['video_start'],length);b=audio_hash(binary,package/f'part-{i:03}.mp4',duration=length)
        audio.append({'segment':i,'source_hash':a,'output_hash':b,'unchanged':a==b});offset+=length
    errors=[abs(a-b) for a,b in zip(expected,actual['frame_pts'])]
    preserved=len(expected)==actual['frame_count'] and max(errors,default=1)<.002
    ass=(package/'analysis.ass').read_text(encoding='utf-8-sig')
    texts=[line.split(',',9)[-1] for line in ass.splitlines() if line.startswith('Dialogue:')]
    clean=all(not FORBIDDEN.search(normalized(t)) for t in texts)
    annotations=read(package/'annotations.json')
    approved,excluded=review_events(annotations,config,package/'evidence')
    canonical=analysis_ass(output_events(approved,config),config)
    reviewed=not excluded and ass==canonical
    intro_clear=True
    for e in output_events(approved,config):
        if e.get('phase')!='intro':continue
        deadline=config['music_start_video']-3-config['segments'][0]['video_start']
        # A frame remains visible until the next presentation timestamp. Check
        # the first frame with no intro text, not just the ASS cue end number.
        first_clear=next((t for t in actual['frame_pts'] if t>=e['output_end']-1e-6),duration)
        if first_clear>deadline+1e-6:intro_clear=False
    from PIL import Image
    with Image.open(package/'score/blank.png') as blank:alpha_clear=blank.mode=='RGBA' and blank.getextrema()[3]==(0,0)
    log='\n'.join(p.read_text(encoding='utf-8') for p in package.glob('compose-*.log'))
    missing_glyph=bool(__import__('re').search(r'failed to find|Glyph .*not found|fontselect:.*failed',log,__import__('re').I))
    run([binary,'-v','error','-nostdin','-i',output,'-map','0:v:0','-map','0:a:0','-f','null','-'],package/'decode-check.log')
    report['checks'].update({'all_output_frames_decode':True,'source_video_pts_preserved':preserved,
        'max_pts_error_seconds':max(errors,default=None),'audio_packets_unchanged':all(a['unchanged'] for a in audio),
        'actual_ass_dialogues_clean':clean,'all_rendered_subtitles_review_bound':reviewed,
        'intro_three_seconds_clear':intro_clear,'transparent_hidden_score_layer':alpha_clear,
        'no_missing_subtitle_glyphs':not missing_glyph})
    report['audio_checks']=audio
    report['intro_clearance']={'music_start_video':config['music_start_video'],
        'deadline_video':config['music_start_video']-3,'clear_source_frame':config.get('intro_clear_video'),
        'checked_against_actual_output_frames':True}
    success=preserved and all(a['unchanged'] for a in audio) and clean and reviewed and intro_clear and alpha_clear and not missing_glyph
    report['status']='automated_checks_passed_visual_review_required' if success else 'verification_failed'
    report['output']={'path':output.name,'sha256':digest(output),'bytes':output.stat().st_size,'frames':actual['frame_count']}
    write(package/'review-report.json',report)
    if not success:raise ValueError('Output verification failed; see review-report.json')
    return report['checks']
