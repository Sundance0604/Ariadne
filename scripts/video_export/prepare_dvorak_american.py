"""Prepare editable Op.96 captions and the complete local export package.

No final video is encoded. Existing drafts and packages are never replaced.
"""
from collections import Counter
from pathlib import Path
import argparse,json,re,shutil,sys
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT),str(ROOT/'scripts')]
from dvorak_american_sync import WORK,read,write,record,digest,log
from backend.score_snapshot import bundle
from backend.video_export.content import content_hash,review_events,FORBIDDEN
from backend.video_export.pipeline import make_package,prepare_score,validate_config
from backend.video_export.visual_panels import validate_settings
from backend.video_export.visual_full import full_layout
from backend.video_export.media import ffmpeg,inspect_frames
from backend.video_export.editor import prepare,export as export_captions,score_resources

DATA=WORK/'video-export'
PACKAGE=ROOT/'output/video-export/dvorak-american-full-001'
DOCUMENT=DATA/'captions-editable.json'
PROFILE=DATA/'full-profile.json'

# Authored interpretations address an actual source range and its prior context.
ESSAYS=[
 (1,1,'旋律换了说话者','开头的中提琴给主题一个亲近的距离。第一小提琴接手后，同一条旋律提高两个八度，浮动的背景却继续存在。主题的身份由方向和节奏保持，音色与音区让它获得新的分量。可以跟着旋律换一个聆听位置，听原来的发言者怎样退入伴奏。'),
 (1,84,'发展中的共同发言','发展的力量不只来自越来越响。短句先在不同声部之间移动，继而由两把小提琴共同放大；中提琴和大提琴仍在下方保持推进。分散的发言逐渐合到一起，又为后来中提琴的轻声回归拉开距离。材料仍可相认，它们之间的关系已经改变。'),
 (2,10,'低声部也能成为歌唱的中心','大提琴把先前的小提琴旋律接到较低音区，中提琴则改用拨奏维持支点，第二小提琴接过细密流动。主题的转交使四件乐器一起更换职责。此时最高的声音未必最重要，顺着那条能够继续哼唱的长线，便能听见新的中心。'),
 (2,49,'高潮有一条不断的内声','旋律向高处伸展，内声仍以细密音型维持呼吸。几次增长并非彼此分开的强奏，而是同一支歌在不同和声和低音承托中继续争取落点。随后减弱时，伴奏尚未停息，歌唱也就仍然保留继续展开的可能。'),
 (3,49,'三拍中的两种重心','小调段的长线与中提琴较集中的重音同时存在，较低处的句子又跨过它们继续。三拍没有消失，听觉重心却不断偏向另一处。把连线与攻击都留在耳中，就能感到这种牵制；它让旋律保持连贯，也让舞步保留棱角。'),
 (3,97,'返回从较低音色发生','最初由第二小提琴和大提琴提出的短句，这次先回到中提琴和大提琴。高声部暂时让出空间，熟悉节奏因而在较低的音色中重新取得身份。随后上层再加入长音和短叫，回归逐渐长出新的层次，而不只是把开头整页重复一次。'),
 (4,179,'运动容纳一处长久停留','持续的跳跃暂时退下，四部以长音共同呼吸，形成近似圣咏的合奏。后面第一小提琴转轻，大提琴接过更有表现力的回答，静止内部又生出流动。这里的平静有自己的变化，正因为它保留了时间和距离，快速步态的回返才会显得鲜明。'),
 (4,280,'慢步获得主调归属','中央慢区曾从A小调出发；这一次，F大调的支撑让相近的长线取得另一种归属。第一小提琴在G弦上歌唱，下方长音先为它保留空间，再逐步恢复运动。平静没有直接结束全章，尾声仍要把共同的节奏重新点燃。')]


def excerpt(text,limit=48):
    text=re.sub(r'\[[^\]\n]+\]','',text).strip()
    sentence=re.split(r'(?<=[。！？])',text)[0]
    if len(sentence)<=limit:return sentence
    clauses=re.split(r'(?<=[，；：])',sentence)
    result=''
    for clause in clauses:
        if len(result+clause)>limit:break
        result+=clause
    if not result:raise ValueError('Need an authored shorter caption: '+text)
    return result.rstrip('，；：。')+'。'


def editorial():
    if DOCUMENT.exists():raise ValueError('Existing user draft protected')
    snapshot,_=bundle(ROOT,WORK);analysis=read(snapshot/'analysis.json')
    alignment=read(WORK/'alignment.json');media=read(WORK/'media-sync.json')
    sections={s['id']:s for s in read(WORK/'analysis/sections.json')['sections']}
    registry=read(WORK/'metadata/visual-parts.json')
    end=min(media['video']['duration_seconds'],alignment['score_time_coverage']['end_seconds']+4)
    start=alignment['score_time_coverage']['start_seconds']
    config={'format_version':'1.0','title':'德沃夏克 · 美国弦乐四重奏｜Stradivari Quartet',
            'width':1920,'height':1080,'music_start_video':start,'intro_clear_video':max(0,start-3),
            'music_start_confirmation':{'status':'agent_checked','reviewer':'Codex',
                                        'basis':'Source-bound feature DTW plus recorded spectral boundary review; human listening remains separate',
                                        'human_signature':None},
            'segments':[{'video_start':0,'video_end':round(end,3)}],
            'chapters':[{'start':m['start_seconds'],'title':m['title']} for m in alignment['movements']],
            'font':'KaiTi','font_size':32,'yellow':'#FFDF42','spacing':0,'bold':True,
            'web_video_layout':True,'minimum_caption_seconds':3,'characters_per_second':7,
            'scroll_speed':1.5,'score_zoom':1,'score_dpi':144,'crf':20,'preset':'veryfast',
            'slot_labels':{'harmony':'和声分析','orchestration':'配器与织体','counterpoint':'声部关系与复调','form':'曲式与主题发展'},
            'visualization':{'registry':'visuals/registry.json','flow':'visuals/flow.json','activity':'visuals/activity.json',
                             'renderer':'visuals/renderer/stream.mjs','coverage':'four source-audio DTWs; explicit repeat and Da Capo visits'},
            'presentation_rules':{'分析':{'读完自动隐去':True,'每秒阅读字数':5,'最短显示秒':10,'读后停留秒':3,
                                          '滚动像素每秒':26,'淡入毫秒':450,'淡出毫秒':1600},
                                  '诠释':{'模式':'宽幅缓升','上移像素':75,'淡入毫秒':1400,'淡出毫秒':4000},
                                  '诠释时隐藏栏目':['和弦','配器','声部关系与复调','曲式与主题发展','导聆'],
                                  '诠释时隐藏乐谱':True}}
    config=full_layout(config,validate_settings({}),registry);validate_config(config)
    refs=[{'path':p.relative_to(ROOT).as_posix(),'sha256':digest(p)} for p in
          [WORK/'analysis/full-analysis.md',WORK/'analysis/sections.json',WORK/'analysis/sources.json',
           WORK/'alignment.json',WORK/'sync/boundary-review.json']]
    events=[];rows=[];ledger=[]
    names={'harmony':'和弦','orchestration':'配器','counterpoint':'声部关系与复调','form':'曲式与主题发展','guide':'导聆','interpretation':'诠释'}
    def add(identity,slot,a,b,text,source,title='',music_scope=None):
        if FORBIDDEN.search(text):raise ValueError('Unfinished caption '+identity+' '+text)
        required=max(3,len(text.replace('\n',''))/7)
        if b-a<required:raise ValueError(f'Insufficient reading {identity}: {b-a:.2f} < {required:.2f}: {text}')
        event={'id':identity,'slot':slot,'video_start':round(a,3),'video_end':round(b,3),'text':text,
               'phase':'performance','timing_precision':'score_segment','display_title':title}
        event['review']={'status':'approved','reviewer':'Codex',
                         'scope':'Agent editorial sentence/clause selection or authored interpretation with source-range evidence; no human signature',
                         'sources':refs,'content_sha256':content_hash(event),'human_signature':None}
        events.append(event)
        rows.append({'编号':identity,'栏目':names[slot],'开始秒':event['video_start'],'结束秒':event['video_end'],
                     '标题':title,'文字':text,'显示':True,'出处':source,
                     '音乐范围':music_scope or [a,b],'复核':'代理文案与谱面范围核查；非人类逐音签核'})
    for note in analysis['annotations']:
        s=sections[note['source_section_id']];a=note['start_seconds'];b=note['end_seconds']
        for j,(slot,key) in enumerate([('harmony','harmony'),('orchestration','orchestration'),
                                       ('counterpoint','voices'),('form','form'),('guide','listening')]):
            limit=min(48,max(16,int((b-a-1)*7)))
            text=excerpt(s[key],limit)
            required=max(3,len(text)/7)
            offset=min(j*.6,max(0,b-a-required-1))
            add(note['annotation_id']+'-'+slot,slot,a+offset,b,text,s['source_locator'],
                config['slot_labels'].get(slot,''),[a,b])
            ledger.append({'id':events[-1]['id'],'source_section_id':s['id'],'visit':note['visit'],
                           'source_text':s[key],'caption':text,'selection':'first complete sentence or initial clause, editorial punctuation'})
    for n,first,title,text in ESSAYS:
        s=next(s for s in sections.values() if s['movement']==n and s['local_measure_range'][0]==first)
        note=next(x for x in analysis['annotations'] if x['source_section_id']==s['id'] and x['visit']==1)
        a=note['start_seconds'];b=note['end_seconds'];source_locator=s['source_locator']
        if n==3 and first==97:
            continuation=next(x for x in analysis['annotations'] if sections[x['source_section_id']]['movement']==3
                              and sections[x['source_section_id']]['local_measure_range'][0]==117 and x['visit']==1)
            b=continuation['end_seconds'];source_locator+='；并含117–148小节的同次回返延续'
        required=max(24,len(text)/5+4)
        offset=min(8,max(1,b-a-required-1))
        if b-a-offset<required:raise ValueError('Interpretation source window too short '+title)
        add(f'american-essay-{n}-{first}','interpretation',a+offset,min(b,a+offset+required),text,
            source_locator,title,[a,b])
    DATA.mkdir(parents=True,exist_ok=True)
    write(PROFILE,config)
    accepted,excluded=review_events({'events':events},config,ROOT)
    if excluded:
        write(DATA/'editorial-review-errors.json',excluded)
        raise ValueError('Caption validation failed; inspect editorial-review-errors.json')
    write(DATA/'annotations-source.json',{'video_sha256':media['video']['sha256'],
          'alignment_sha256':digest(WORK/'alignment.json'),'events':events})
    document={'说明':'时间为原视频秒数，反复每次独立安排。四个实际弦乐分部；乐章停顿清空。音乐开始较早，不覆盖片头文字。',
              '字号':{'和弦':32,'配器':32,'声部关系与复调':32,'曲式与主题发展':32,'导聆':30,'诠释':44,'片头':58},
              '栏目名称':{'和弦':'和声分析','配器':'配器与织体','声部关系与复调':'声部关系与复调','曲式与主题发展':'曲式与主题发展'},
              '呈现规则':config['presentation_rules'],'字幕':rows,
              '视频指纹':media['video']['sha256'],'对齐指纹':digest(WORK/'alignment.json'),
              '复核状态':'同源自动同步与代理文案；乐章首尾、标记位置及演出细节可继续人工校正'}
    write(DOCUMENT,document)
    write(DATA/'editorial-ledger.json',{'entries':ledger,'counts':dict(Counter(r['栏目'] for r in rows)),
                                      'guide_runs':len(analysis['annotations']),'human_signoff':None})
    log(f'Captions {len(rows)}: {dict(Counter(r["栏目"] for r in rows))}')


def package():
    if PACKAGE.exists():raise ValueError('Existing local export package protected')
    make_package(ROOT,'dvorak-american',PROFILE,DATA/'annotations-source.json',PACKAGE)
    snapshot,_=bundle(ROOT,WORK)
    folder=PACKAGE/'visuals';renderer=folder/'renderer';renderer.mkdir(parents=True)
    shutil.copy2(WORK/'metadata/visual-parts.json',folder/'registry.json')
    for name in ['flow.json','activity.json']:shutil.copy2(snapshot/name,folder/name)
    for name in ['harmonic-flow.mjs','orchestration-activity.mjs','interval-index.mjs','visual-export.mjs']:
        shutil.copy2(ROOT/'review'/name,renderer/name)
    (renderer/'stream.mjs').write_text("import fs from 'node:fs';import {once} from 'node:events';import {createVisualExport} from './visual-export.mjs';const [f,a,c]=process.argv.slice(2),read=p=>JSON.parse(fs.readFileSync(p,'utf8')),config=read(c),render=createVisualExport(read(f),read(a),config);for(let i=0;i<config.frame_count;i++){const line=JSON.stringify(render.at(config.frame_times?.[i]??(config.start+i/config.fps)))+'\\n';if(!process.stdout.write(line))await once(process.stdout,'drain');}\n",encoding='utf8')
    log('Preparing34 original PDF pages and the shared JS score plan')
    prepare_score(ROOT,PACKAGE)
    config=read(PACKAGE/'export-config.json')
    probes=inspect_frames(ffmpeg(ROOT),PACKAGE/'performance.mp4',0,config['segments'][0]['video_end'])
    write(PACKAGE/'source-frame-timestamps.json',[probes])
    shutil.copy2(DOCUMENT,PACKAGE/'captions-initial.json')
    manifest=read(PACKAGE/'export-manifest.json');manifest['visualization']=config['visualization']
    manifest['video_encoding_performed']=False
    for p in (PACKAGE/'visuals').rglob('*'):
        if p.is_file():manifest['checksums'][p.relative_to(PACKAGE).as_posix()]=digest(p)
    manifest['checksums']['source-frame-timestamps.json']=digest(PACKAGE/'source-frame-timestamps.json')
    write(PACKAGE/'export-manifest.json',manifest)
    config,events,excluded=prepare(read(DOCUMENT),PACKAGE)
    result=export_captions(read(DOCUMENT),PACKAGE,ass_only=True)
    score_resources(PACKAGE,result.parent,config,events)
    catalog=read(ROOT/'config/video-export.json')
    if any(p['id']=='dvorak-american-full' for p in catalog['editor_projects']):raise ValueError('Editor project already exists')
    catalog['editor_projects'].append({'id':'dvorak-american-full','title':'德沃夏克美国四重奏 · Stradivari Quartet',
                                     'package':PACKAGE.relative_to(ROOT).as_posix(),'document':DOCUMENT.relative_to(ROOT).as_posix()})
    write(ROOT/'config/video-export.json',catalog)
    write(DATA/'package-ready.json',{'package':PACKAGE.relative_to(ROOT).as_posix(),'document':DOCUMENT.relative_to(ROOT).as_posix(),
                                    'frame_count':probes['frame_count'],'pdf_pages':34,'video_generated':False,
                                    'prepared_revision':result.parent.relative_to(ROOT).as_posix(),
                                    'caption_count':len(events),'excluded':excluded,'human_signoff':None})
    log('Local package and subtitle editor project ready; no full video encoded')


def polish():
    """Review the newly selected clauses, preserving every music interval."""
    document=read(DOCUMENT);source=read(DATA/'annotations-source.json');events={e['id']:e for e in source['events']}
    ledger=read(DATA/'editorial-ledger.json');entries={e['id']:e for e in ledger['entries']}
    sections={s['id']:s for s in read(WORK/'analysis/sections.json')['sections']}
    changes={
      (1,1,'counterpoint'):'第3–4小节的中提琴旋律，由第7–8小节第一小提琴提高两个八度重述。',
      (1,17,'form'):'主部的熟悉轮廓进入新的低音背景，逐渐取得过渡功能。',
      (1,26,'form'):'较尖锐的对比材料先聚起力量，再通过下落和减弱走向新的歌唱。',
      (1,44,'form'):'轻声的新陈述在A大调中展开，逐渐成为这一段的中心。',
      (1,112,'counterpoint'):'主题按熟悉的次序交接，伴奏的改写又使这次回归具有新的重量。',
      (2,10,'counterpoint'):'第3–4小节的小提琴旋律，由第11–12小节大提琴低八度重述。',
      (3,49,'form'):'小调长线继续歌唱，内声的重音仍让三拍保留牵制。',
      (3,149,'orchestration'):'第一小提琴扩大高处线条，其他声部从长音背景逐步形成更有重量的协同。',
      (3,173,'form'):'小调段收拢后，音乐还将返回开头，在第48小节Fine结束。',
      (4,179,'orchestration'):'四部起初以连贯长音共同呼吸，随后重新分出较轻上层和大提琴的回答。',
      (4,280,'form'):'慢速长线在F大调中回返，使先前的停留获得新的主调归属。'
    }
    before=digest(DOCUMENT);applied=[]
    for row in document['字幕']:
        identity=row['编号'];event=events[identity]
        if row['文字']!=event['text'] or row['开始秒']!=event['video_start'] or row['结束秒']!=event['video_end']:
            raise ValueError('User edit detected; preserve draft and review targeted changes separately')
        if identity not in entries:continue
        s=sections[entries[identity]['source_section_id']]
        text=changes.get((s['movement'],s['local_measure_range'][0],event['slot']))
        if text:
            applied.append({'id':identity,'old':row['文字'],'new':text})
            row['文字']=text;event['text']=text;event['review']['content_sha256']=content_hash(event)
            entries[identity]['caption']=text;entries[identity]['selection']='agent authored revision after sentence and source review'
    config=read(PROFILE);accepted,excluded=review_events(source,config,ROOT)
    if excluded:raise ValueError(str(excluded))
    write(DOCUMENT,document);write(DATA/'annotations-source.json',source);write(DATA/'editorial-ledger.json',ledger)
    write(DATA/'caption-polish-audit.json',{'before_sha256':before,'after_sha256':digest(DOCUMENT),
          'changes':applied,'all_source_music_intervals_preserved':True,'human_signoff':None})
    log(f'Polished {len(applied)} entries; music intervals unchanged')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('stage',choices=['editorial','polish','package'])
    args=parser.parse_args()
    {'editorial':editorial,'polish':polish,'package':package}[args.stage]()
