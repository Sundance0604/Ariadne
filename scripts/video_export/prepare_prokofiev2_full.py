"""Prepare editable captions, PDF resources and visual layers; never encode video."""
from pathlib import Path
from collections import Counter
import argparse,json,re,shutil,subprocess,sys
ROOT=Path(__file__).resolve().parents[2];sys.path[:0]=[str(ROOT),str(ROOT/'scripts')]
from prokofiev2_sync import WORK,read,write,record,digest,log
from backend.prokofiev2 import bundle
from backend.video_export.content import content_hash,review_events,FORBIDDEN
from backend.video_export.pipeline import make_package,prepare_score,validate_config
from backend.video_export.visual_panels import load_settings,part_registry,activity_payload
from backend.video_export.visual_full import full_layout
from backend.video_export.media import ffmpeg,inspect_frames
from backend.video_export.editor import prepare

DATA=WORK/'video-export';PACKAGE=ROOT/'output/video-export/prokofiev2-full-001'
DOCUMENT=DATA/'captions-editable.json';PROFILE=DATA/'full-profile.json'

def clean(text):
    return re.sub(r'\[[A-Z][^\[\]\n]*[：:][^\[\]\n]*\]','',text).strip()

def sentence(text):
    text=clean(text);return re.split(r'(?<=[。！？])',text)[0].strip()

def editorial():
    if DOCUMENT.exists():raise ValueError('已有可编辑文稿，不能覆盖；请保留用户修改')
    snapshot,_=bundle(ROOT,WORK);web=read(snapshot/'analysis.json');alignment=read(WORK/'alignment.json')
    sections=read(WORK/'analysis/sections.json')['sections'];media=read(WORK/'media-sync.json')
    end=round(alignment['score_time_coverage']['end_seconds']+4,3)
    config={'format_version':'1.0','title':'普罗科菲耶夫 · 第二钢琴协奏曲｜王羽佳／雅尔维',
        'width':1920,'height':1080,'music_start_video':43.2,'intro_clear_video':40.2,
        'music_start_confirmation':{'status':'agent_checked','reviewer':'Codex','basis':'Existing source-bound boundary review and same-video DTW; user will check rendering','human_signature':None},
        'segments':[{'video_start':0,'video_end':end}],
        'chapters':[{'start':m['start_seconds'],'title':f'{i+1} · '+read(WORK/'measure-map.json')['movements'][i]['title']} for i,m in enumerate(alignment['score_time_coverage']['segments'])],
        'font':'KaiTi','font_size':32,'yellow':'#FFDF42','spacing':0,'bold':True,'web_video_layout':True,
        'minimum_caption_seconds':3,'characters_per_second':7,'scroll_speed':1.5,'score_zoom':1,
        'score_dpi':144,'crf':20,'preset':'veryfast','interpretation_hides_score':False,'interpretation_suppresses_slots':[],
        'slot_labels':{'harmony':'和声分析','orchestration':'配器分析','counterpoint':'声部关系与复调','form':'曲式与主题发展'},
        'visualization':{'registry':'visuals/registry.json','flow':'visuals/flow.json','activity':'visuals/activity.json',
            'renderer':'visuals/renderer/stream.mjs','coverage':'same-source four movement DTW; no encore'}}
    config=full_layout(config,load_settings(),read(WORK/'metadata/visual-parts.json'));validate_config(config)
    refs=[{'path':p.relative_to(ROOT).as_posix(),'sha256':digest(p)} for p in [WORK/'analysis/sections.json',
        WORK/'analysis/full-analysis.md',WORK/'analysis/sources.json',WORK/'metadata/recording.json']]
    events=[];rows=[];decisions=[]
    labels={'harmony':'和弦','orchestration':'配器','counterpoint':'声部关系与复调','form':'曲式与主题发展','guide':'导聆','interpretation':'诠释'}
    def add(identity,slot,a,b,text,source,phase='performance',title=''):
        if not text or FORBIDDEN.search(text):raise ValueError('需整理完整文案：'+identity+' '+text)
        required=max(3,len(text.replace('\n',''))/7)
        if b-a<required:raise ValueError(f'阅读时间不足：{identity} {b-a:.2f}s < {required:.2f}s；需另行精简，不自动截断')
        e={'id':identity,'slot':slot,'video_start':round(a,3),'video_end':round(b,3),'text':text,
            'phase':phase,'timing_precision':'source_interval' if phase=='intro' else 'score_segment','display_title':title}
        e['review']={'status':'approved','reviewer':'Codex','scope':'Complete source sentences selected from the existing attributed analysis; no human or expert signature',
            'sources':refs,'content_sha256':content_hash(e),'human_signature':None};events.append(e)
        rows.append({'编号':identity,'栏目':'片头' if phase=='intro' else labels[slot],
            '开始秒':e['video_start'],'结束秒':e['video_end'],'标题':title,'文字':text,'显示':True,
            '出处':source,'原文范围':'已有谱面分析与文献归属；本次不新增演奏细节判断'})
    add('prok2-intro','interpretation',3,40.2,'谢尔盖·普罗科菲耶夫\n第二钢琴协奏曲 Op.16\n钢琴：王羽佳\n指挥：帕沃·雅尔维\n柏林爱乐乐团','版本阵容与本地视频说明','intro','四乐章导聆')
    for s in sections:
        note=next(n for n in web['annotations'] if n['annotation_id']==s['id']);a=note['start_seconds'];b=note['end_seconds']
        for slot,key in [('harmony','harmony'),('orchestration','orchestration'),('counterpoint','voices'),('form','form'),('guide','listening')]:
            text=sentence(s[key]);identity=s['id']+'-'+slot
            add(identity,slot,a,b,text,s['source_locator'],title=config['slot_labels'].get(slot,''))
            decisions.append({'id':identity,'section':s['id'],'source_text':s[key],'video_text':text,'method':'first complete sentence; citations retained in editable provenance'})
        match=re.search(r'\*\*演奏诠释。\*\*\s*(.*?)(?:\n\n|$)',note['markdown'],re.S)
        if match:
            text=sentence(match.group(1));start=a+min(2,(b-a)*.05);finish=min(b,start+max(15,len(text)/5.5))
            add(s['id']+'-interpretation','interpretation',start,finish,text,s['source_locator']+'；演奏诠释原段','performance','演奏诠释')
    DATA.mkdir(parents=True,exist_ok=True)
    write(PROFILE,config)
    write(DATA/'annotations-source.json',{'video_sha256':media['video']['sha256'],'alignment_sha256':digest(WORK/'alignment.json'),'events':events})
    accepted,excluded=review_events({'events':events},config,ROOT)
    if excluded:raise ValueError('文稿检查未通过：'+str(excluded))
    doc={'说明':'时间为原视频秒数。完整四乐章及停顿，末章结束后留4秒；不包含后段加演。编辑后由用户生成和核查。',
        '字号':{'和弦':32,'配器':32,'声部关系与复调':32,'曲式与主题发展':32,'导聆':30,'诠释':30,'片头':58},
        '栏目名称':{'和弦':'和声分析','配器':'配器分析','对位':'声部关系与复调','曲式':'曲式与主题发展'},
        '字幕':rows,'视频指纹':media['video']['sha256'],'对齐指纹':digest(WORK/'alignment.json'),
        '复核状态':'用户生成与核查；未代填人工或专家签核'}
    write(DOCUMENT,doc);write(DATA/'editorial-ledger.json',{'decisions':decisions,'events':len(events),'sections':38,
        'counts':dict(Counter(r['栏目'] for r in rows)),'full_video_encoded':False,'human_signoff':None})
    log(f'Editable captions: {len(rows)} entries; '+str(dict(Counter(r['栏目'] for r in rows))))

def package():
    if PACKAGE.exists():raise ValueError('已有导出包，不能覆盖；先核对既有成果')
    make_package(ROOT,'prokofiev-piano-concerto-2',PROFILE,DATA/'annotations-source.json',PACKAGE)
    log('Media/PDF source-bound package created; preparing visual payloads')
    snapshot,_=bundle(ROOT,WORK);config=read(PACKAGE/'export-config.json')
    folder=PACKAGE/'visuals';renderer=folder/'renderer';renderer.mkdir(parents=True)
    shutil.copy2(WORK/'metadata/visual-parts.json',folder/'registry.json');shutil.copy2(snapshot/'flow.json',folder/'flow.json')
    registry=read(folder/'registry.json');settings=config['visual_settings'];flow=read(snapshot/'flow.json')
    activity=activity_payload(flow,read(snapshot/'evidence.json'),read(WORK/'sync/reference/written.json'),read(WORK/'alignment.json'),
        part_registry(registry['parts'],colors=settings['part_colors']),0,config['segments'][0]['video_end']+4)
    activity['flow_groups']=registry['harmony_groups'];write(folder/'activity.json',activity)
    for name in ['harmonic-flow.mjs','orchestration-activity.mjs','interval-index.mjs','visual-export.mjs']:
        shutil.copy2(ROOT/'review'/name,renderer/name)
    (renderer/'stream.mjs').write_text("import fs from 'node:fs';import {once} from 'node:events';import {createVisualExport} from './visual-export.mjs';const [f,a,c]=process.argv.slice(2),read=p=>JSON.parse(fs.readFileSync(p,'utf8')),config=read(c),render=createVisualExport(read(f),read(a),config);for(let i=0;i<config.frame_count;i++){const line=JSON.stringify(render.at(config.frame_times?.[i]??(config.start+i/config.fps)))+'\\n';if(!process.stdout.write(line))await once(process.stdout,'drain');}\n",encoding='utf8')
    log('Preparing all original PDF pages with the existing JS score renderer')
    prepare_score(ROOT,PACKAGE)
    log('Reading original source frame timestamps; no video encoding')
    probes=inspect_frames(ffmpeg(ROOT),PACKAGE/'performance.mp4',0,config['segments'][0]['video_end'])
    write(PACKAGE/'source-frame-timestamps.json',[probes])
    shutil.copy2(DOCUMENT,PACKAGE/'captions-initial.json')
    manifest=read(PACKAGE/'export-manifest.json');manifest['visualization']=config['visualization'];manifest['video_encoding_performed']=False
    for p in (PACKAGE/'visuals').rglob('*'):
        if p.is_file():manifest['checksums'][p.relative_to(PACKAGE).as_posix()]=digest(p)
    manifest['checksums']['source-frame-timestamps.json']=digest(PACKAGE/'source-frame-timestamps.json')
    write(PACKAGE/'export-manifest.json',manifest)
    prepare(read(DOCUMENT),PACKAGE)
    catalog=read(ROOT/'config/video-export.json')
    if any(p['id']=='prokofiev2-full' for p in catalog['editor_projects']):raise ValueError('已有同名项目，不覆盖其文稿设置')
    catalog['editor_projects'].insert(0,{'id':'prokofiev2-full','title':'普罗第二钢协 · 王羽佳／雅尔维完整版',
        'package':PACKAGE.relative_to(ROOT).as_posix(),'document':DOCUMENT.relative_to(ROOT).as_posix()})
    catalog['editor_default_project']='prokofiev2-full';write(ROOT/'config/video-export.json',catalog)
    write(DATA/'package-ready.json',{'package':PACKAGE.relative_to(ROOT).as_posix(),'document':DOCUMENT.relative_to(ROOT).as_posix(),
        'frame_count':probes['frame_count'],'duration_seconds':config['segments'][0]['video_end'],'pdf_pages':168,
        'video_generated':False,'user_will_render_and_review':True})
    log('Full package ready. Open 编辑视频字幕.bat and choose 普罗第二钢协; no MP4 encoded.')

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('stage',choices=['editorial','package','all']);args=p.parse_args()
    if args.stage in ('editorial','all'):editorial()
    if args.stage in ('package','all'):package()
