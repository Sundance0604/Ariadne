"""Publish the separate complete-ballet playback snapshot from local evidence."""
from pathlib import Path
from fractions import Fraction as F
from collections import defaultdict,Counter
import argparse, json, re, sys
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'scripts')]
from mother_goose_video import DATA,BASE,CACHE,PDF,read,write,digest,log

RANGES=[(3,12),(13,30),(31,37),(38,53),(54,59),(64,86),(91,98)]

def mapping():
    doc=read(DATA/'reference/written.json');alignment=read(DATA/'alignment.json');geometry=read(CACHE/'geometry.raw.json')
    if geometry['pdf_sha256']!=digest(PDF):raise ValueError('Geometry source changed')
    systems=geometry['systems'];corrections=[]
    def correct(page,system,remove=None,add=None):
        s=next(s for s in systems if s['page']==page and s['system']==system);before=s['boundaries'][:]
        if remove is not None:s['boundaries'].remove(remove)
        if add is not None:s['boundaries']=sorted(s['boundaries']+[add])
        corrections.append({'page':page,'system':system,'before_scale2':before,'after_scale2':s['boundaries'],'basis':'agent image review of actual printed staff/bar lines; false aligned stem, missing bar or cautionary signature respectively','human_signoff':None})
    correct(14,0,remove=902);correct(14,1,add=465)
    correct(26,1,remove=1071);correct(58,0,remove=1066)
    write(DATA/'reports/geometry-review.json',{'pdf_sha256':geometry['pdf_sha256'],'corrections':corrections,'note':'Numerical sequence correspondence remains a candidate; visual geometry is not notehead recognition.'})
    bars=[];parents=[];movements=[]
    for mv,(lo,hi) in enumerate(RANGES,1):
        ms=[m for m in alignment['measures'] if m['movement']==mv];ss=[s for s in systems if lo<=s['page']<=hi]
        count=sum(len(s['boundaries'])-1 for s in ss)
        if count!=len(ms):raise ValueError(f'Movement {mv}: observed {count}, source {len(ms)}; no equal-width repair allowed')
        index=0
        for s in ss:
            first=index;sid=f"ballet-p{s['page']:03d}-s{s['system']}"
            for i,(a,b) in enumerate(zip(s['boundaries'],s['boundaries'][1:])):
                m=ms[index];index+=1
                box={'measure_id':m['measure_id'],'region_id':sid+f'-b{i:02d}','parent_region_id':sid,'page_number':s['page'],'system_index':s['system'],'movement':mv,'page_width_pt':s['width'],'page_height_pt':s['height'],'rect_pt':[a/2,max(0,s['top']/2-4),(b-a)/2,(s['bottom']-s['top'])/2+8],'midi_start_seconds':m['midi_start_seconds'],'midi_end_seconds':m['midi_end_seconds'],'alignment_segment':f'movement-{mv}','resolution':'bar_candidate','review_status':'agent_geometry_sequence_candidate','stable_candidate':not bool(m['flags']),'printed_measure_number':None,'source_local_number':m['local_number'],'evidence':{'method':'observed scan bar lines; movement count and rehearsal landmarks checked; local sequence assigned','source_sequence':m['source_sequence'],'source_xml':m['source']}}
                bars.append(box)
            a,b=s['boundaries'][0],s['boundaries'][-1]
            parents.append({**bars[-1],'region_id':sid,'parent_region_id':None,'measure_id':ms[first]['measure_id'],'rect_pt':[a/2,max(0,s['top']/2-4),(b-a)/2,(s['bottom']-s['top'])/2+8],'midi_start_seconds':ms[first]['midi_start_seconds'],'resolution':'system_candidate','stable_candidate':True})
        spec=doc['movements'][mv-1]
        movements.append({**spec,'first_pdf_page':lo,'last_pdf_page':hi,'first_sequence_index':ms[0]['sequence_index']})
    # These page/system times are independent visual/acoustic landmarks. Free
    # cadenzas receive no invented quarter clock, noteheads or moving line.
    bridge_specs=[(5,60,0,1045.2,1082.5,'Lent and the beginning of the harp cadenza'),
                  (5,61,0,1082.5,1106.0,'harp cadenza continuation'),
                  (5,61,1,1106.0,1117.8,'celesta cadenza; keyboard closeups at 1108–1112'),
                  (5,62,0,1117.8,1129.1,'xylophone roll and orchestral glissandi; mallet closeups 1120–1124'),
                  (5,63,0,1129.1,1147.0,'flute cadenza; flute closeups 1132–1136, conductor transition by 1144'),
                  (6,87,0,1361.6,1379.0,'horn call; horn closeups 1368–1372'),
                  (6,88,0,1379.0,1391.0,'bird calls; piccolo closeups 1384–1388'),
                  (6,89,0,1391.0,1424.0,'horn dialogue then solo violin; closeups 1392–1404 and 1412–1424'),
                  (6,90,0,1424.0,1448.8,'solo violin continuation and prelude recollection')]
    landmarks=[]
    for mv,p,si,a,b,basis in bridge_specs:
        s=next(s for s in systems if s['page']==p and s['system']==si);x0,x1=s['boundaries'][0],s['boundaries'][-1]
        region={'region_id':f'ballet-p{p:03d}-s{si}-interlude','page_number':p,'system_index':si,'movement':mv,'page_width_pt':s['width'],'page_height_pt':s['height'],'rect_pt':[x0/2,max(0,s['top']/2-4),(x1-x0)/2,(s['bottom']-s['top'])/2+8],'audio_start_seconds':a,'audio_end_seconds':b,'resolution':'unmetered_cadenza_system_candidate' if p in [60,61,62,63] else 'interlude_system_candidate','review_status':'agent_video_landmark_candidate','stable_candidate':False,'printed_measure_number':None,'evidence':{'method':'separate agent video-instrument and score landmark estimate','basis':basis,'not_duration_or_page_count_allocation':True,'human_signoff':None},'no_symbolic_projection':True}
        parents.append(region);landmarks.append(region)
    result={'format_version':'1.1.0','pdf_path':PDF.relative_to(ROOT).as_posix(),'pdf_sha256':digest(PDF),'page_count':98,'first_score_page':3,'status':'agent_scan_geometry_and_movement_sequence_candidates','symbolic_reference_sha256':alignment['symbolic_reference']['sha256'],'movements':movements,'measures':bars,'score_regions':parents,'bar_regions':bars,'limitations':['Observed rectangles are bar/system regions, never individual notehead boxes.','Paper and source-XML bar sequences are agent candidates; no human/expert signature.','Two interludes use coarser page/system video landmarks; no note-level line or instantaneous XML harmony.']}
    write(DATA/'measure-map.json',result)
    write(DATA/'reports/interlude-landmarks.json',{'video_sha256':alignment['audio']['sha256'],'pdf_sha256':result['pdf_sha256'],'landmarks':landmarks,'review_scope':'agent instrument closeups, score instructions and spectral boundary estimate; no human listening signature','uncertainty':'page/system estimates; harp page transition particularly coarse'})
    for m,box in zip(alignment['measures'],bars):m['pdf_mapping_status']='observed_bar_sequence_candidate';m['pdf_page']=box['page_number']
    write(DATA/'alignment.json',alignment)
    write(DATA/'project.json',{'work_id':'ravel-mother-goose-ballet','title':'鹅妈妈：完整芭蕾版','inputs':[{'path':PDF.relative_to(ROOT).as_posix(),'sha256':digest(PDF),'bytes':PDF.stat().st_size,'page_count':98},alignment['audio'],*doc['sources']],'movements':movements,'processing_status':{'alignment':'seven independent movement DTWs','score_geometry':'746 observed bar candidates and nine separate interlude systems','interpretation':'shared five-scene research plus added ballet observations'},'human_signoff':None})
    log(f'Mapping: {len(bars)} bars; {len(parents)} systems; 96 music pages')


def editorial(doc):
    sections=[];old=read(ROOT/'works/ravel-mother-goose/analysis/guide.json')['sections'];mvmap={1:3,2:5,3:6,4:4,5:7}
    for s in old:sections.append({**s,'id':'ballet-'+s['id'],'movement':mvmap[s['movement']],'prior_source_movement':s['movement']})
    new=[
        (1,1,7,'从两条管乐线打开帷幕','开头长笛与巴松的音程和具体低音逐时点列在音符证据中；三连音圆号材料属于另一个进入层。','两支长笛同奏与第一巴松相隔音区，第三小节加入加弱音器的圆号，随后弱音弦乐接入。','管乐的附点长短节奏、圆号的细碎三连音与弦乐长时值形成不同层级。','起始材料以后还会被回忆；先辨认音程轮廓与节奏，再判断相似程度。','听柔和的管乐开场，留意圆号进入后背景怎样开始流动。'),
        (1,8,19,'鸟鸣式短句与开头材料交错','片段的半音与变化音扩大音集，音高集合不自动成为功能和弦。','短笛和长笛交错出现短小装饰音型；回到原速时，音区与材料重新分层。','短句的接续与持续背景并存；鸟鸣式模仿是音响比喻，不是严格卡农。','排练号1的短句与排练号2的返回，形成可回访的材料关系。','把短促、高处的呼应与较长的背景线分开听。'),
        (1,20,31,'钟状音色让时间伸缩','此处分析按独立记谱窗口取音，长时段集合不合并成一个同时和弦。','木管逐渐退后，钢片琴形成清楚的钟状攻击；谱面有渐快与渐慢的文字。','短攻击和乐器之间的空隙也是组织线条的手段。','动作密度与速度文字共同塑造过渡，不能只把乐器更换当作新主题。','留意钢片琴每次发音之间的空间，感受速度的伸缩。'),
        (1,32,50,'材料回返并积聚成开场的亮度','各层的持续音与快速经过音并列保存；高潮音集不追溯覆盖前面的静止音响。','木管短句逐步密集，竖琴滑奏、弦乐震音和打击乐共同扩展声音。','长时值的低层与快速音型可同时存在，密度增加不等于所有声部同节奏。','前奏以增密过程指向纺车舞；完整芭蕾总谱在下一页进入6/8。','听熟悉的短句如何被越来越多的音色包围。'),
        (2,1,16,'纺车的旋转与跳跃','半音运动和低层支点分别记录，不将经过音逐个强加功能名称。','开头合奏之后，单簧管和第一小提琴的快速音型突出；随后木管的短音与拨弦相呼应。','连续快速线条与间断的舞步攻击构成两层。','6/8的运动从开场强奏中抽离，转向轻巧的局部交接。','先抓住快速旋转的音型，再听短促的木管与拨弦。'),
        (2,17,37,'独奏线条从合奏中浮现','旋律与支撑音的时点分开取样；和声事实可在上方实时窗口查阅。','木管独奏与弦乐背景交替，音色和音区的接力使线条保持清晰。','乐器交接有时继续同一条线，有时形成回应，须同时看攻击和节奏。','排练号12至14提供回访地标；这些地标不自动等于严格曲式边界。','把注意力从背景的运动移向正在独奏的木管。'),
        (2,38,64,'步伐与流动背景交替','反复音、变化音与背景支点并存，局部和声应按窗口查看。','短音的管乐组合与弦乐的运动互相照应，重音的轮廓比长音更显眼。','成组的加倍可合为一个层；不同攻击时间才支持新的活动层。','既有步态反复出现，同时以音色和力度改变方向。','听重音如何从一组乐器移到另一组。'),
        (2,65,97,'短句接续与音色换景','移动的内声与持续层分别观察，调性归属需要前后句法支持。','双簧管等木管的线条先后出现，弦乐由拨奏、弓奏及不同音区参与。','上下两层可以延续不同长度的句子，不机械以小节线截断。','材料的接续使舞蹈保持连续；排练号19至23便于对照。','循着木管的长线，听背景的步伐怎样继续。'),
        (2,98,121,'跌倒的场景与漫长睡眠','色彩性和声转向较静止的背景；低音与上方移动音仍需分别观察。','从稍慢转入很慢；弱奏弦乐、低音、竖琴和木管短句取代先前的密集运动。','攻击密度降低，持续音与零星入口之间形成更宽的间隔。','总谱的舞台文字写出公主受伤及入睡，随后衔接帕凡舞。叙事解释以这些文字为依据。','在速度放缓后，留意细小的木管入口和低声部的支点。'),
        (3,21,45,'帕凡舞后的舞台转换','持续层与半音移动分开看；过渡材料的音集不直接移用帕凡舞的功能标签。','短笛的强奏上行、钢片琴和打击乐的突入，与后段竖琴和独奏小提琴形成对照。','密集的共同攻击先打断前景，随后让独奏线条浮在长音之上。','总谱先后写出Allegro、Plus lent、Allegro及圆舞曲速度；间奏最终准备下一场。','听突出的短笛和闪光音色退下之后，圆舞曲的空间如何出现。'),
        (4,173,191,'对话之后的柔和过渡','木管的级进线与弦乐背景分开观察，色彩变化承接前景的收束。','长笛、双簧管等木管短句相继出现，弱奏弦乐维持过渡。','短句接力与持续层共同形成连续性。','此段属于芭蕾版衔接，接向小拇指的不规则步伐。','听清接话的木管，再感受下一场弦乐脚步的变化。'),
    ]
    for mv,lo,hi,title,h,o,c,f,l in new:sections.append({'id':f'ballet-extra-{mv}-{lo}','movement':mv,'local_measures':[lo,hi],'title':title,'harmony':h,'orchestration':o,'counterpoint':c,'form':f,'listening':l,'sources':['B:complete ballet score; stated page/bar scope checked by agent'],'evidence_parts':[]})
    return sorted(sections,key=lambda s:(s['movement'],s['local_measures'][0]))


def publish():
    import mistune, music21 as m21
    from html import escape
    doc=read(DATA/'reference/written.json');alignment=read(DATA/'alignment.json');mapping=read(DATA/'measure-map.json')
    out=DATA/'playback/ballet-20261026-v2'
    if out.exists() and (DATA/'playback/current.json').exists():raise ValueError('Use a new snapshot; activated work is protected')
    out.mkdir(parents=True,exist_ok=True);render=mistune.create_markdown(escape=True,plugins=['table','url'])
    boxby={b['measure_id']:b for b in mapping['measures']};byid={m['measure_id']:m for m in doc['measures']}
    sections=editorial(doc);write(DATA/'analysis/ballet-guide.json',{'sections':sections,'policy':'core guide retains the prior suite witness; ballet additions are separately identified'})
    prior=ROOT/'works/ravel-mother-goose/analysis'
    source_rows=read(prior/'sources.json')['sources'];sources=[]
    for s in source_rows:
        urls=[s['url']] if s.get('url') else []
        sources.append({'source_id':s['id'],'title':s['title'],'citation_label':s['title'],'kind':'book' if s['id'] in ['A','M05'] else 'research_article','reading_status':'abstract_checked' if s['id']=='KT' else 'relevant_sections_checked','reading_note':s.get('read_status','')+'；'+s.get('use',''),'urls':urls,'html':render(s['title']+'\n\n'+s.get('read_status','')),'verification_evidence':s.get('read_status','')})
    sources.append({'source_id':'B','title':'Ravel · Ma mère l’Oye, complete ballet, Durand full score (98 physical pages)','kind':'score','reading_status':'key_pages_checked','reading_note':'全谱系统与小节线图像检查；关键奏法与乐章页界核对。没有人类或专家逐音签核。','urls':['https://imslp.org/wiki/Special:ReverseLookup/62635'],'html':render('完整芭蕾总谱；98个物理页，音乐为第3–98页。')})
    verification={'score':'key_pages_checked','literature':'relevant_sections_checked','location':'score_segment_candidate','timing':'candidate_alignment'}
    span_for=lambda ms:{'precision':'score_segment_candidate','pdf_page_start':min(boxby[m['measure_id']]['page_number'] for m in ms),'pdf_page_end':max(boxby[m['measure_id']]['page_number'] for m in ms),'region_ids':[boxby[m['measure_id']]['region_id'] for m in ms]}
    curated=[];notes=[];forms=[];module=[];contexts=[]
    dimension_labels={'harmony':'和声','orchestration':'配器与织体','counterpoint':'声部关系与复调','form':'曲式与主题发展'}
    for s in sections:
        ms=[m for m in doc['measures'] if m['movement']==s['movement'] and s['local_measures'][0]<=m['local_number']<=s['local_measures'][1]]
        span=span_for(ms);s.update(start_q=ms[0]['start_q'],end_q=ms[-1]['end_q'],score_spans=[span])
        md='\n\n'.join(f'**{label}**\n\n{s[d]}' for d,label in dimension_labels.items())+'\n\n**听什么**\n\n'+s['listening']
        refs=[]
        for text in s['sources']:
            key=text.split(':')[0]
            if key in {r['source_id'] for r in sources}:refs.append({'source_id':key,'locator':text.split(':',1)[-1],'claim_attribution':'score' if key in ['S','X','B'] else 'authors'})
        refs.append({'source_id':'B','locator':f"PDF {span['pdf_page_start']}–{span['pdf_page_end']}; source local bars {s['local_measures']}",'claim_attribution':'score'})
        for d in dimension_labels:
            curated.append({'id':s['id']+'-'+d,'dimension':d,'short_label':s[d],'claim_level':'theoretical_analysis','analysis_origin':'score_study','score_spans':[span],'verification':verification,'sources':refs,'detail_markdown':s[d],'html':render(s[d]),'related_essay_ids':[f"ballet-essay-{s['movement']}"]})
            if d in ['counterpoint','form']:module.append({'id':s['id']+'-'+d,'dimension':d,'priority':10,'start_q':s['start_q'],'end_q':s['end_q'],'title':s['title'],'summary':s[d],'detail':s['listening'],'score_spans':[span],'source_events':[{'id':s['id'],'path':'works/ravel-mother-goose-video/analysis/ballet-guide.json'}],'relation_ids':[]})
        forms.append({'id':s['id'],'level':'scene_phrase','title':s['title'],'start_q':s['start_q'],'end_q':s['end_q'],'xml_range':[ms[0]['sequence_index'],ms[-1]['sequence_index']+1],'argument':s['form']})
        contexts.append({'id':s['id']+'-context','label':s['harmony'],'start_q':s['start_q'],'end_q':s['end_q']})
        timed=[m for m in alignment['measures'] if m['measure_id'] in {m['measure_id'] for m in ms}]
        notes.append({'annotation_id':s['id'],'movement':s['movement'],'title':s['title'],'start_measure_id':ms[0]['measure_id'],'end_measure_id':ms[-1]['measure_id'],'start_sequence_index':ms[0]['sequence_index'],'end_sequence_index':ms[-1]['sequence_index'],'start_seconds':timed[0]['start_seconds'],'end_seconds':timed[-1]['end_seconds'],'start_pdf_page':span['pdf_page_start'],'end_pdf_page':span['pdf_page_end'],'markdown':md,'html':render(md),'source_ids':[r['source_id'] for r in refs],'review_status':'agent_revised_human_pending','locator_precision':'bar_sequence_candidate'})
    # Independent interpretation reading: source chapter order is remapped,
    # while the source document itself is never overwritten.
    original=(prior/'full-analysis.md').read_text(encoding='utf-8');chapters={int(n):body for n,body in re.findall(r'^## 第(\d)曲[^\n]*\n(.*?)(?=^## |\Z)',original,re.M|re.S)}
    extra_essays={1:'前奏并不急于把一个人物推到台前。长笛与巴松在不同音区说出相近的附点姿态，弱音圆号随后以更细碎的节奏加入。可以把这种层次听成空间逐渐获得深度：近处是短句，较远处是持续和流动的背景。这个空间读法是一种听觉解释，实际依据仍是乐器入口、时值与音区。\n\n高处短句、钟状音色和较长背景不断交错，使童话的时间一会儿凝住，一会儿向前。总谱的渐快、渐慢和原速返回，给这种经验以具体的写作根据。这里不必先把每个片段装进固定曲式；材料的返回、间隔和加密已经形成可以追踪的关系。\n\n到末尾，竖琴滑奏、弦乐震音与打击乐把音响推向更明亮的密度。接入纺车舞时，空间中的微小动作成为持续的旋转。前奏也为后面的回忆留下音色和节奏线索；辨认这些线索，应比较具体轮廓，而不是把每次相似音色都命名为同一主题。',2:'纺车舞把动作放在叙事前面。6/8的快速音型不断流动，木管的短音和拨弦却把步伐分成轻小的片段。旋转与跳跃并存，让音乐同时拥有连续性和细密的接触点。\n\n人物的轻巧感并不只来自快速：线条如何交给另一件乐器，背景怎样在前景喘息时继续，重音如何改变方向，都会影响动作的重量。对这些关系的分析应保留乐器加倍与独立声部的区别。\n\n总谱后来写出公主受伤及入睡的舞台情节。速度放慢、攻击稀疏、低音与长音成为支点，使此前的身体运动逐渐退到背景。这一转变可以理解为外部动作转入内部时间；它是依据谱面叙事与织体变化提出的解释，而不是对指挥心理的判断。随后的帕凡舞把这种静止扩展成缓慢的仪式。'}
    inverse={3:1,5:2,6:3,4:4,7:5};essays=[]
    for mv in doc['movements']:
        n=mv['movement'];lo,hi=RANGES[n-1]
        body=extra_essays[n] if n in extra_essays else chapters[inverse[n]]
        if n in [3,4,5,6]:body+='\n\n**芭蕾版的位置**\n\n本页延续组曲共享场景的研究，章节顺序按本次完整芭蕾演出重排。新增间奏单独显示谱面与来源；自由华彩没有被换算成虚构的逐拍和声。'
        essays.append({'id':f'ballet-essay-{n}','title':f"{n} · {mv['title']}",'claim_level':'hermeneutic_interpretation','reading_mode':'persistent','markdown':body,'html':render(body),'score_spans':[{'precision':'page_range','pdf_page_start':lo,'pdf_page_end':RANGES[n][0]-1 if n<7 else hi}],'verification':{**verification,'location':'page_range'},'sources':[{'source_id':'B','locator':f'PDF {lo}–{hi}','claim_attribution':'score'}]+([] if n<3 else [{'source_id':'A','locator':'原组曲相关章节；实际阅读范围见来源记录','claim_attribution':'authors'}]),'related_event_ids':[]})
    work={'work_id':'ravel-mother-goose-ballet','title':'鹅妈妈：完整芭蕾版','original_title':"Ma mère l’Oye — Ballet",'composer':{'name':'莫里斯·拉威尔','original_name':'Maurice Ravel'},'instrumentation':'管弦乐；前奏、五场及终曲，保留四段间奏'}
    recording={'recording_id':'mother-goose-benjamin-radio-france-20211210','audio_sha256':alignment['audio']['sha256'],'soloists':[],'conductor':{'name':'乔治·本杰明','original_name':'George Benjamin'},'ensemble':{'name':'法国广播爱乐乐团','original_name':'Orchestre philharmonique de Radio France','abbreviation':'Radio France'},'duration_seconds':alignment['audio']['duration_seconds'],'artist_information_note':'阵容、地点与2021年12月10日演出日期来自用户视频内嵌的France Musique说明；同一视频的音轨用于同步。'}
    analysis={'format_version':'1.1.0','work':work,'recording':recording,'audio_sha256':alignment['audio']['sha256'],'pdf_sha256':mapping['pdf_sha256'],'source_document':{'path':'works/ravel-mother-goose-video/analysis/ballet-guide.json','title':'鹅妈妈完整芭蕾导聆','review_status':'editorially_revised'},'annotations':notes,'movement_essays':[],'navigation_mode':'bar_sequence_candidate','event_candidates':[],'references':sources,'full_html':'<h1>鹅妈妈：完整芭蕾导聆</h1>'+''.join('<h2>'+escape(n['title'])+'</h2>'+n['html'] for n in notes),'coverage':{'guide_sections':len(notes),'movement_sections':7,'pdf_pages':98},'notice':f'{len(notes)}段谱面导聆 · 七章完整演出 · 时间为代理候选同步','provenance_notice':'组曲研究保留；芭蕾新增材料及演出时间独立记录。','reference_note':'每项资料保留实际阅读范围；不把局部阅读标成全文核验。'}
    # Instantaneous written activity uses half-open note intervals. It is an
    # offline score projection, not live acoustic source separation.
    pitch_cache={}
    def pitch(ps):
        if ps not in pitch_cache:
            p=m21.pitch.Pitch();p.ps=ps;pitch_cache[ps]={'name':p.nameWithOctave.replace('-','b'),'ps':ps,'pc':int(ps)%12}
        return pitch_cache[ps]
    events=doc['events'];starts=defaultdict(list);ends=defaultdict(list)
    for e in events:starts[F(e['start_q'])].append(e);ends[F(e['end_q'])].append(e)
    points=sorted(set(starts)|set(ends)|{F(m['start_q']) for m in doc['measures']}|{F(doc['quarter_duration'])})
    frames=[];windows={};readings={};active={};mi=0;chord_cache={}
    def sonority(es):
        ps=tuple(sorted({e['ps'] for e in es}));pcs=sorted({int(p)%12 for p in ps});bass=pitch(ps[0]) if ps else None
        triads={'major triad':(0,4,7),'minor triad':(0,3,7),'diminished triad':(0,3,6),'augmented triad':(0,4,8),'dominant seventh chord':(0,4,7,10),'major seventh chord':(0,4,7,11),'minor seventh chord':(0,3,7,10),'half-diminished seventh chord':(0,3,6,10),'diminished seventh chord':(0,3,6,9)}
        chord=None
        for quality,intervals in triads.items():
            for root in pcs:
                tones=[(root+i)%12 for i in intervals]
                if set(tones)==set(pcs):chord={'root':pitch(root+60)['name'][:-1],'quality':quality,'inversion':tones.index(int(ps[0])%12)};break
            if chord:break
        value={'pitches':[pitch(p)['name'] for p in ps],'pitch_classes':pcs,'bass':bass,'chord':chord,'structures':[]}
        if any(e['harmonic'] for e in es):value['display_label']='含泛音记号的XML编码音：'+'、'.join(value['pitches'])+'（泛音实响另核）';value['chord']=None
        return value
    def family(name):
        text=name.lower()
        if any(x in text for x in ['flut','flû','picc','hautb','oboe','cor a','anglais','clar','bassoon','basson','bason','bns','bn.']):return '木管'
        if any(x in text for x in ['horn','cors','corni','cor ']):return '铜管'
        if any(x in text for x in ['violin','violon','viola','alto','cello','celle','bass','basse']):return '弦乐'
        if any(x in text for x in ['harp','harpe','celest','célest','glock','keyboard','timbres']):return '键盘／拨弦'
        return '打击乐'
    for start,end in zip(points,points[1:]):
        for e in ends[start]:active.pop(e['id'],None)
        for e in starts[start]:active[e['id']]=e
        while mi+1<len(doc['measures']) and F(doc['measures'][mi+1]['start_q'])<=start:mi+=1
        m=doc['measures'][mi];es=list(active.values());wid=f'ballet-w{len(frames)+1:05d}';group=defaultdict(list)
        for e in es:group[e['part_id']].append(e)
        instruments=[{'part_id':pid,'label':re.sub(r'\s+',' ',rows[0]['label']).strip(),'family':family(rows[0]['label']),'instrument_names':[rows[0]['label']],'pitches':sorted({pitch(e['ps'])['name'] for e in rows}),'roles':[],'event_ids':[e['id'] for e in rows]} for pid,rows in group.items()]
        frame={'id':wid,'start_q':float(start),'end_q':float(end),'measure_id':m['measure_id'],'number':f"{m['movement']}-{m['local_number']}",'page':boxby[m['measure_id']]['page_number'],'onset_q':str(start-F(m['start_q'])),'harmony_window_id':wid if es else None,'active_instruments':instruments}
        frames.append(frame)
        if es:windows[wid]={'id':wid,'measure_id':m['measure_id'],'start_q':str(start),'end_q':str(end),'onset_q':frame['onset_q'],'event_ids':sorted(active),**sonority(es)};readings[wid]=[]
    clock=[{'tick':0,'midi_seconds':0,'seconds_per_tick':.5/960}]
    live={'available':True,'work_id':doc['work_id'],'projection':{'ppq':960,'reference_clock':clock,'reference_end_seconds':float(F(doc['quarter_duration']))*.5,'reference_end_quarter':float(F(doc['quarter_duration'])),'audio_sha256':alignment['audio']['sha256'],'alignment_sha256':digest(DATA/'alignment.json'),'source_sha256':digest(DATA/'reference/written.json')},'frames':frames,'windows':windows,'readings':readings,'form':{'sections':forms,'models':[]},'hud_cases':{'cases':[],'contexts':contexts},'roman_audit':None,'limitations':['Instantaneous written activity projected by offline DTW; no live audio instrument recognition.','Harmonic notation and the two source-free cadenzas are explicitly limited.']}
    measures=[{**m,'sequence':m['sequence_index'],'number':f"{m['movement']}-{m['local_number']}",'page':boxby[m['measure_id']]['page_number'],'duration_q':str(F(m['end_q'])-F(m['start_q']))} for m in doc['measures']]
    research={'available':True,'schema_version':'1.0.0','work_id':doc['work_id'],'edition':{'edition_id':'complete-ballet-durand-62635','pdf_sha256':mapping['pdf_sha256']},'events':curated,'essays':essays,'sources':sources,'reference_clock':clock,'engine':{'reference_sha256':alignment['symbolic_reference']['sha256']},'musicxml':{'summary':{'measures':len(measures),'parts':len(doc['parts']),'events':len(events)},'measures':measures,'table_scope':'eligible_pitched_intervals','scope_note':'当前表显示有效定音音符的记谱时值；源声部、谱表、连音及记号分别保存。休止、装饰音和被隔离事件请回到原XML及原组曲快照查阅。','review_status':'agent_research_human_pending'},'module_profile':{'labels':{'counterpoint':'声部关系与复调','form':'曲式与主题发展'},'readings':module,'relations':[]}}
    evidence={};eventby=defaultdict(list)
    for e in events:
        m=byid[e['measure_id']];a=F(e['start_q']);b=F(e['end_q']);p=pitch(e['ps'])
        eventby[e['measure_id']].append({**e,'kind':'note','voice':e.get('voice'),'staff':e.get('staff'),'instrument_ref':e.get('instrument_ref'),'encoded_pitch':e.get('encoded_pitch') or {'name':e['encoded_name']},'written_pitch':e.get('written_pitch'),'concert_pitch':p,'score_start_q':str(a),'score_end_q':str(b),'onset_q':str(a-F(m['start_q'])),'duration_q':str(b-a),'analysis_eligible':True,'exclusion_reason':None,'tie':e.get('tie') or [],'articulations':e.get('articulations') or [],'notations_xml':e.get('notations_xml') or [],'technique_context':[]})
    for m in measures:
        ws=[{**w,'sonority':{**{k:w[k] for k in ['bass','chord','pitches','pitch_classes']},'label':w.get('display_label','、'.join(w['pitches']))}} for w in windows.values() if w['measure_id']==m['measure_id']]
        evidence[m['measure_id']]={'measure':m,'scope_note':research['musicxml']['scope_note'],'events':eventby[m['measure_id']],'part_registry':doc['parts'],'harmony':ws,'harmonic_readings':{},'orchestration':[],'intervals':[],'chordal_intervals':[],'hierarchy':[s for s in forms if F(s['start_q'])<=F(m['start_q'])<F(s['end_q'])],'motif_comparisons':[],'cadences':[],'limitations':['Original raw XML and the prior suite snapshot retain full rests, ties, articulations and source metadata; this playback table contains eligible pitched intervals only.','No new counterpoint interval engine or functional-harmony verdict is implied.']}
    for name,value in [('research.json',research),('analysis.json',analysis),('live.json',live),('evidence.json',{'measures':evidence})]:write(out/name,value)
    inputs=[DATA/'alignment.json',DATA/'measure-map.json',DATA/'media-sync.json',DATA/'reference/written.json',PDF,DATA/'analysis/ballet-guide.json',prior/'full-analysis.md',prior/'guide.json',prior/'sources.json',ROOT/'scripts/build_mother_goose_playback.py',ROOT/'scripts/mother_goose_video.py']+[ROOT/s['path'] for s in doc['sources']]
    manifest={'schema_version':'1.0','work_id':doc['work_id'],'review_scope':'agent source/geometry/structural review; automatic timing with explicit unreferenced interludes','human_signoff':None,'expert_review':None,'inputs':[{'path':p.relative_to(ROOT).as_posix(),'sha256':digest(p),'bytes':p.stat().st_size} for p in dict.fromkeys(inputs)],'files':{p.name:{'sha256':digest(p),'bytes':p.stat().st_size} for p in out.glob('*.json')}}
    write(out/'manifest.json',manifest);write(DATA/'playback/current.json',{'path':out.relative_to(ROOT).as_posix(),'manifest_sha256':digest(out/'manifest.json')})
    library=read(ROOT/'library.json')
    if not any(t['id']=='ravel-mother-goose-video' for t in library['tracks']):library['tracks'].append({'id':'ravel-mother-goose-video','title':'拉威尔 · 鹅妈妈（完整芭蕾视频）','data_root':'works/ravel-mother-goose-video','analysis_adapter':'mother-goose-ballet-v1'})
    write(ROOT/'library.json',library)
    log(f'Activated ballet: {len(measures)} bars, {len(frames)} written windows, {len(notes)} guide sections, seven essays')

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('stage',choices=['mapping','publish']);args=p.parse_args()
    mapping() if args.stage=='mapping' else publish()
