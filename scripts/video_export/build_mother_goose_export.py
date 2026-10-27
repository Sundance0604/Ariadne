"""Independent video editorial JSON: short prose and source-bound intervals.

Does not change webpage prose, score clocks, alignments or user-edited captions.
"""
from pathlib import Path
import json,re,sys
ROOT=Path(__file__).resolve().parents[2];sys.path[:0]=[str(ROOT),str(ROOT/'scripts')]
from backend.video_export.content import read,write,digest,content_hash,review_events,FORBIDDEN
from backend.video_export.pipeline import validate_config

DATA=ROOT/'works/ravel-mother-goose-video'
ROMAN=['I','II','III','IV','V','VI','VII']
HARMONY={
'ballet-extra-1-1':'管乐在相隔的音区展开，圆号以新的节奏层加入。',
'ballet-extra-1-8':'短句中的半音与变化音，让音响逐渐离开开头的静止。',
'ballet-extra-1-20':'短促的发音与延留的背景交替，让和声变化获得空间。',
'ballet-extra-1-32':'持续层托住快速音型，音响逐步加密。',
'ballet-extra-2-1':'低层支点与快速的半音运动，形成不同的变化速度。',
'ballet-extra-2-17':'独奏线条与支撑音分层，和声随着入口改变色彩。',
'ballet-extra-2-38':'反复音、变化音与持续支点共同组织舞蹈的背景。',
'ballet-extra-2-65':'移动的内声穿过较稳定的背景，使音色转换保有联系。',
'ballet-extra-2-98':'色彩性和声逐渐转向静止的背景，低音成为支点。',
'ballet-extra-3-21':'持续音与半音移动交替，间奏逐步准备新的圆舞曲。',
'ballet-extra-4-173':'木管的级进短句与弱奏弦乐，延续对话后的柔和色彩。',
'ballet-I-a':'长笛短句呈五声色彩；下方的音让整体织体更加丰富。',
'ballet-I-b':'E低音与D持续层之上，F—F♯—G—F♯的内声移动。',
'ballet-I-c':'低声部与内声更频繁地移动，改变前段的固定背景。',
'ballet-I-d':'D、F的持续层，为熟悉的旋律换了和声支点。',
'ballet-I-e':'E背景再次承托旋律，弦乐内声带回半音的记忆。',
'ballet-IV-a':'F大调背景中，升四级与半音低音不断偏离平稳的舞步。',
'ballet-IV-b':'全音、八音等对称音集，与持续低音形成粗砺的色彩。',
'ballet-IV-c':'F♯的持续支点，与上方改变的旋律构成复合关系。',
'ballet-IV-d':'半音低音与紧张音程，让终止不断推迟。',
'ballet-IV-e':'上方旋律返回，低层仍保留先前的材料与半音张力。',
'ballet-IV-f':'上行低层与改变的旋律音程共同积累张力，随后留下空白。',
'ballet-IV-g':'F成为终局支点，变音与柔和的音色仍保留着过去的痕迹。',
'ballet-II-a':'流动的三度与变化的调式音，先铺出不断延伸的道路。',
'ballet-II-b':'围绕C展开的旋律，逐步打开降E的色彩区域。',
'ballet-II-c':'较宽的音程让回答舒展；梅西安将这里联系到降E大调。',
'ballet-II-d':'G持续低音托住旧材料，上方的半音变化使归来并不安稳。',
'ballet-II-e':'半音变化与上行模进逐步增添张力，熟悉材料暂时返回。',
'ballet-II-f':'较宽的句子返回；梅西安将这次回归置于降A区域。',
'ballet-II-g':'持续音与短小鸟鸣交错，音响不再只沿原来的步伐流动。',
'ballet-II-h':'C小调材料返回；相隔的音区，让同一旋律显得格外透明。',
'ballet-II-i':'较宽的音程立在带色彩的F背景上，半音内声继续移动。',
'ballet-II-j':'末尾的大三度改变收束色彩，开头的运动仍留在记忆中。',
'ballet-III-a':'F♯五声语汇先从局部音集与相邻二度中浮现。',
'ballet-III-b':'F♯、D♯、C♯、A♯等音，在短笛中织成轻巧花纹。',
'ballet-III-c':'相邻二度与较厚的垂直音响，突出短促的撞击感。',
'ballet-III-d':'五声、调式与半音内声先后转换，材料保持多种色彩。',
'ballet-III-e':'五声材料与E自然音的局部色彩，随乐器入口逐步聚合。',
'ballet-III-f':'F♯、C♯、D♯等支点拉成长音，快速花纹化为轮廓。',
'ballet-III-g':'低音区保留五声支点，持续音把段落重心带向低处。',
'ballet-III-h':'持续支点与平行的和声层，托出较舒展的抒情线。',
'ballet-III-i':'五声支点维持联系，半音与装饰让熟悉材料重新组合。',
'ballet-III-j':'五声性的终止逐步收拢，色彩音仍给结尾留下光泽。',
'ballet-V-a':'C是整体中心，二度、七度与九度关系不断丰富长线。',
'ballet-V-b':'上行过程改变低音支点；梅西安将它联系到E区域。',
'ballet-V-c':'E区域的调式色彩中，分解音响与较长旋律分层存在。',
'ballet-V-d':'音阶上升、音区展开，力度却减弱，声音仿佛逐步远去。',
'ballet-V-e':'C区域恢复，F—C等持续支撑参与后续的上升。',
'ballet-V-f':'C的终局支点在开放音区铺开，上方色彩不断闪动。',
}
INTERPRETATIONS={
1:'前奏像是在搭起一个可以容纳童话的空间。短句与持续背景交错，远近感逐渐形成；末尾密度增加，静止的空间转为动作。',
2:'旋转的连续线条与跳跃的短音，使舞蹈既轻巧又有触点。速度放慢之后，动作逐渐退入背景，留下睡眠般延长的时间。',
3:'旋律可以保持熟悉，下方的支点与说话的音色却不断改变。返回因此带着记忆，也带着新的距离。',
4:'两种角色材料逐步进入共同织体。转化最终改变音区、节奏和音色；我们仍能从其中辨认先前留下的轮廓。',
5:'道路由不断流动的步伐构成，却总在换拍中延长或缩短。鸟鸣的介入让空间突然偏离人物，迷途也成为一种听觉经验。',
6:'细小的攻击和清楚的乐器接力，使声音仿佛拥有微型的体积。材料在快慢之间换形，熟悉的世界随之显出另一种尺度。',
7:'缓慢的上行并不总让声音更近。有时音区升高，力度反而减弱；最后的辉光，来自长期积累的层次重新汇聚。',
}

def short(text,limit):
    sentence=re.split(r'(?<=[。！？])',text)[0]
    if len(sentence)<=limit:return sentence
    clause=re.split(r'[；;]',sentence)[0].rstrip('，。')+'。'
    if len(clause)<=limit:return clause
    # No mechanical mid-clause truncation. Keep the complete source sentence
    # and let the explicit reading/layout checks report any issue.
    return sentence

def build():
    target=DATA/'video-export';target.mkdir(parents=True,exist_ok=True)
    if (target/'captions-optimized.json').exists():raise ValueError('Preserve existing video editorial JSON; create a named revision')
    alignment=read(DATA/'alignment.json');mapping=read(DATA/'measure-map.json')
    pointer=read(DATA/'playback/current.json');base=ROOT/pointer['path'];web=read(base/'analysis.json')
    guide=read(DATA/'analysis/ballet-guide.json')['sections'];maps=alignment['time_maps'];duration=alignment['audio']['duration_seconds']
    config={'format_version':'1.0','title':'拉威尔 · 鹅妈妈｜完整芭蕾导聆','width':1920,'height':1080,'music_start_video':maps[0]['start_seconds'],
            'music_start_confirmation':{'status':'agent_checked','reviewer':'Codex','basis':'same-video pitch/onset open-end localization plus conductor frames; candidate boundary, no human listening signature','human_signature':None},
            'segments':[{'video_start':0,'video_end':duration}],'chapters':[{'start':s['start_seconds'],'title':ROMAN[i]+' · '+mapping['movements'][i]['title']} for i,s in enumerate(maps)],
            'font':'KaiTi','font_size':36,'spacing':0,'yellow':'#FFDF42','minimum_caption_seconds':3,'characters_per_second':7,'score_zoom':1,'score_dpi':144,'crf':20,'preset':'veryfast','bold':True,'web_video_layout':True,'caption_lifecycle':'single_pass','intro_clear_video':24.48,
            'slot_labels':{'harmony':'和声背景','orchestration':'本段配器','counterpoint':'声部关系与复调','form':'曲式与主题发展'},
            'layout':{'harmony':{'x':50,'y':30,'w':1000,'h':270,'font_size':36},'orchestration':{'x':1090,'y':24,'w':780,'h':190,'font_size':36,'align':'right'},'counterpoint':{'x':50,'y':330,'w':1130,'h':180,'font_size':36},'form':{'x':50,'y':540,'w':1130,'h':160,'font_size':36},'guide':{'x':50,'y':730,'w':1130,'h':140,'font_size':36},'score':{'x':1260,'y':230,'w':600,'h':800},'interpretation':{'x':260,'y':900,'w':1400,'h':160,'font_size':44,'align':'center','scroll':True},'intro':{'x':220,'y':190,'w':1480,'h':700,'font_size':58,'align':'center','scroll':True}}}
    validate_config(config)
    source_paths=[DATA/'analysis/ballet-guide.json',DATA/'reference/written.json',DATA/'project.json',ROOT/'works/ravel-mother-goose/analysis/full-analysis.md']
    refs=[{'path':p.relative_to(ROOT).as_posix(),'sha256':digest(p)} for p in source_paths]
    events=[];edits=[];excluded=[]
    def add(id,slot,start,end,text,title='',phase='performance',basis='separately edited segment commentary; not an instantaneous all-instruments list'):
        e={'id':id,'slot':slot,'video_start':round(start,3),'video_end':round(end,3),'text':text,'display_title':title,'phase':phase,'timing_precision':'source_interval' if phase=='intro' else 'score_segment'}
        e['review']={'status':'approved','reviewer':'Codex','scope':'agent review of the source-bound complete-ballet video prose, reading time and fixed-slot layout; human/expert signatures absent','human_signature':None,'basis':basis,'sources':refs,'content_sha256':content_hash(e)}
        events.append(e)
    add('ballet-intro','interpretation',3,24.48,'莫里斯·拉威尔\n《鹅妈妈》完整芭蕾版\n法国广播爱乐乐团 · 乔治·本杰明\n2021年12月10日','前奏、五场与仙境花园','intro',basis='embedded video description and complete ballet score contents')
    for s in guide:
        note=next(n for n in web['annotations'] if n['annotation_id']==s['id']);a=note['start_seconds']+.2;b=note['end_seconds']-.25
        texts={'harmony':HARMONY[s['id']], 'orchestration':short(s['orchestration'],68),'counterpoint':short(s['counterpoint'],76),'form':short(s['form'],76),'guide':s['listening']}
        # Video wording deliberately omits implementation and long scholarly
        # apparatus. The webpage keeps the complete discussion and attribution.
        replacements={'XML中的三份中提琴副本不等于三条额外对位。':'','当前录音':'这场演奏','；逐音证据另存':'','XML':'谱面'}
        for slot,text in texts.items():
            for old,new in replacements.items():text=text.replace(old,new)
            if FORBIDDEN.search(text):
                excluded.append({'id':s['id']+'-'+slot,'reason':'retained in webpage; contains unresolved research wording'});continue
            required=max(3,len(text.replace('\n',''))/7)
            if b-a<required:
                excluded.append({'id':s['id']+'-'+slot,'reason':'source interval too short for a complete sentence','available':b-a,'required':required});continue
            title='曲式分析与主题发展' if slot=='form' else ''
            add(s['id']+'-'+slot,slot,a,b,text,title)
            edits.append({'id':s['id']+'-'+slot,'web_text':s['harmony'] if slot=='harmony' else s[slot] if slot!='guide' else s['listening'],'video_text':text,'timing_basis':'existing independent movement DTW / source bar interval; no page-duration averaging'})
    for i,segment in enumerate(maps,1):
        # A single interpretive paragraph per chapter, followed by a quiet gap.
        # It is distinct from the shorter technical subtitles and hides the PDF.
        a=segment['start_seconds']+min(35,(segment['end_seconds']-segment['start_seconds'])*.25)
        text=INTERPRETATIONS[i];length=max(17,len(text)/5.5)
        add(f'ballet-interpretation-{i}','interpretation',a,a+length,text,'诠释 · '+mapping['movements'][i-1]['title'],basis='independently rewritten listening interpretation; based on score texture and prior essays, no performer intention asserted')
    bridges=[(1050,1072,'木管把短句逐层接起，弦乐在较长的时值中维持背景。','先听短句相互呼应，再听竖琴如何接过前景。'),(1074,1105,'竖琴展开自由华彩；弦乐的延留音托住流动的分解音响。','这里不必数整齐的拍子，听音区与发音密度怎样变化。'),(1107,1117,'钢片琴接过自由华彩，竖琴滑奏继续扩大音色的空间。','从竖琴的弦音转向钢片琴的钟状攻击。'),(1130,1144,'长笛的自由独奏延长过渡，随后才进入行进速度。','让长笛带着时间伸缩，再留意新的步伐出现。'),(1364,1378,'远处的圆号呼唤，与弦乐短促的动作形成对比。','听呼唤如何逐步接近，再辨认重新出现的鸟鸣音色。'),(1380,1407,'短笛、长笛与其他木管交错，圆号在背景中回应。','试着追踪高处短句的接力，而不只听最亮的一个音。'),(1411,1436,'独奏小提琴从较密的音响中浮现，弦乐长音维持背景。','记住这条抒情线怎样变得安静，为终曲留出空间。')]
    for j,(a,b,o,g) in enumerate(bridges,1):
        for slot,text in [('orchestration',o),('guide',g)]:add(f'ballet-interlude-{j}-{slot}',slot,a,b,text,basis='coarse score-system and video instrument landmarks; no fabricated instantaneous harmony during free cadenzas')
    accepted,bad=review_events({'events':events},config,ROOT)
    if bad:
        write(target/'caption-preflight-failed.json',bad)
        raise ValueError('Video editorial check failed; inspect explicit report before packaging')
    labels={'harmony':'和弦','orchestration':'配器','counterpoint':'声部关系与复调','form':'曲式与主题发展','guide':'导聆','interpretation':'诠释'}
    editable={'作品':'鹅妈妈｜完整芭蕾版','说明':'视频专用优化稿。单部完整视频、七个章节；时间为原视频秒数。网页研究正文独立保留。含和声背景、分段配器及听觉诠释，不冒充实时音频分离。','优化原则':['每条使用完整短句，保留原结论的限定与作者归属','起止来自已保存的音乐定位；不按页数或文字长度均分','同栏目不重叠，按7字/秒及最短3秒核查','每章一段诠释，显示时隐藏乐谱，内部同步继续','自由华彩只显示有依据的音色与听觉提示'], '章节':config['chapters'],'栏目名称':{'声部关系与复调':'声部关系与复调','曲式与主题发展':'曲式与主题发展'},'字号':{'和弦':36,'配器':36,'声部关系与复调':36,'曲式与主题发展':36,'导聆':36,'诠释':44,'片头':58},'字幕':[{'编号':e['id'],'栏目':'片头' if e['phase']=='intro' else labels[e['slot']],'开始秒':e['video_start'],'结束秒':e['video_end'],'标题':e['display_title'],'文字':e['text'],'显示':True} for e in sorted(accepted,key=lambda e:(e['video_start'],e['slot']))]}
    write(target/'full-profile.json',config);write(target/'captions-optimized.json',editable)
    write(target/'captions-reviewed.json',{'format_version':'1.0','video_sha256':alignment['audio']['sha256'],'alignment_sha256':digest(DATA/'alignment.json'),'events':accepted})
    write(target/'optimization-report.json',{'status':'agent_editorial_and_readability_checks_passed','caption_count':len(accepted),'chapter_count':7,'separate_from_web':True,'rewrites':edits,'omitted':excluded,'human_signoff':None,'expert_review':None,'input_fingerprints':refs,'editable_sha256':digest(target/'captions-optimized.json'),'reviewed_sha256':digest(target/'captions-reviewed.json')})
    print(json.dumps({'captions':len(accepted),'omitted':len(excluded),'chapters':7,'video_files_to_deliver':1}))

if __name__=='__main__':build()
