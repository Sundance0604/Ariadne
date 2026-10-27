"""Package Prokofiev II score review; never render or insert video frames."""
from pathlib import Path
from collections import defaultdict,Counter
from fractions import Fraction as F
import argparse,copy,json,re,shutil,subprocess,sys
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'scripts')]
from prokofiev2_sync import WORK,PDF,SOURCE,CACHE,MOVEMENTS,read,write,digest,record,log

def mapping():
    raw=read(CACHE/'geometry.raw.json');doc=read(WORK/'sync/reference/written.json')
    alignment=read(WORK/'sync/alignment.raw.json')
    if raw['pdf']['sha256']!=digest(PDF) or raw['source_xml']['sha256']!=digest(SOURCE):raise ValueError('Geometry source changed')
    review_path=WORK/'sync/geometry-review.json';review=read(review_path) if review_path.exists() else None
    if review and review['pdf_sha256']!=raw['pdf']['sha256']:raise ValueError('Geometry review belongs to another PDF')
    systems=copy.deepcopy(raw['systems']);applied=[]
    for patch in (review or {}).get('pages',[]):
        before=[s for s in systems if s['page_number']==patch['page']]
        if 'replace_systems' in patch:
            if not before:raise ValueError('Cannot review absent page')
            template=before[0]
            revised=[{**template,**s,'page_number':patch['page'],'system_index':i,
                'geometry_status':'agent_image_checked_human_pending'} for i,s in enumerate(patch['replace_systems'])]
            systems=[s for s in systems if s['page_number']!=patch['page']]+revised
        else:
            for change in patch['systems']:
                s=next(s for s in systems if s['page_number']==patch['page'] and s['system_index']==change['system'])
                s.update({k:v for k,v in change.items() if k!='system'},geometry_status='agent_image_checked_human_pending')
        applied.append({'page':patch['page'],'before':before,'after':[s for s in systems if s['page_number']==patch['page']],
            'reason':patch['reason'],'human_signoff':None})
    systems.sort(key=lambda s:(s['page_number'],s['system_index']))
    layout=defaultdict(list)
    for m in doc['measures']:layout[m['layout_page'],m['layout_system']].append(m)
    aligned={m['measure_id']:m for m in alignment['measures']};allboxes=[];fine=[];parents=[];issues=[]
    def make_region(s,ms,identity,rect,resolution):
        first,last=ms[0],ms[-1];timed=[aligned[m['measure_id']] for m in ms]
        stable=not any('weak_independent_pitch_evidence' in m['flags'] or 'feature_variant_disagreement_over_2s' in m['flags'] for m in timed)
        return {'region_id':identity,'measure_id':first['measure_id'],'page_number':s['page_number'],
            'system_index':s['system_index'],'movement':first['movement'],'rect_pt':rect,
            'page_width_pt':s['page_width_pt'],'page_height_pt':s['page_height_pt'],
            'midi_start_seconds':float(F(first['start_q']))*.5,'midi_end_seconds':float(F(last['end_q']))*.5,
            'alignment_segment':f"movement-{first['movement']}",'resolution':resolution,
            'coordinate_origin':'top_left','printed_measure_number':None,
            'source_sequence_range':[first['sequence_index'],last['sequence_index']],
            'source_local_range':[first['local_number'],last['local_number']],
            'review_status':s.get('geometry_status','observed_geometry_layout_sequence_candidate'),
            'stable_candidate':stable,'human_signoff':None,
            'evidence':{'geometry':'observed staff and connecting verticals in source scan',
                'association':'per-page and system XML layout/count comparison; not printed-number recognition'}}
    for page in range(1,169):
        ss=[s for s in systems if s['page_number']==page]
        expected=[ms for (p,i),ms in layout.items() if p==page]
        if len(ss)!=len(expected):
            issues.append({'page':page,'kind':'unresolved_system_correspondence','observed':len(ss),'expected':len(expected)})
            template=ss[0] if ss else {'page_number':page,'system_index':0,'page_width_pt':619.2,'page_height_pt':800.64}
            ms=[m for m in doc['measures'] if m['layout_page']==page]
            region=make_region(template,ms,f'prok2-p{page:03d}-page',[0,0,template['page_width_pt'],template['page_height_pt']],'page_candidate')
            region.update(stable_candidate=False,suppress_playhead=True)
            parents.append(region)
            for m in ms:allboxes.append({**region,'measure_id':m['measure_id']})
            continue
        for s,ms in zip(ss,expected):
            xs=s['boundaries'];count_ok=len(xs)-1==len(ms) and not s.get('force_shared_system')
            top=max(0,s['top']/2-3);bottom=min(s['page_height_pt'],s['bottom']/2+4)
            right=xs[-1] if xs else s['right']
            region=make_region(s,ms,f"prok2-p{page:03d}-s{s['system_index']}",
                [s['left']/2,top,(right-s['left'])/2,bottom-top],
                'system_candidate' if count_ok else 'shared_cadenza_system' if ms[0]['movement']==1 or page==140 else 'shared_system_candidate')
            if not count_ok:
                region.update(stable_candidate=False,suppress_playhead=True)
                issues.append({'page':page,'system':s['system_index'],'kind':'shared_observed_system','source_intervals':len(ms),'observed_bar_candidates':len(xs)-1})
            parents.append(region)
            if count_ok:
                for i,(m,a,b) in enumerate(zip(ms,xs,xs[1:])):
                    child=make_region(s,[m],region['region_id']+f'-b{i:02d}',[a/2,top,(b-a)/2,bottom-top],'bar_candidate')
                    child.update(parent_region_id=region['region_id'],source_local_number=m['local_number'])
                    if m['sequence_index'] in {811,812}:child.update(suppress_playhead=True,resolution='unbarred_system_continuation')
                    fine.append(child);allboxes.append(child)
            else:
                for m in ms:allboxes.append({**region,'measure_id':m['measure_id']})
    if [b['measure_id'] for b in allboxes]!=[m['measure_id'] for m in doc['measures']]:raise ValueError('PDF coverage/order differs from source intervals')
    movements=[]
    for mv in doc['movements']:
        ms=[m for m in alignment['measures'] if m['movement']==mv['movement']]
        movements.append({**mv,'start_seconds':ms[0]['start_seconds'],'end_seconds':ms[-1]['end_seconds']})
    result={'format_version':'1.1.0','pdf_path':PDF.relative_to(ROOT).as_posix(),'pdf_sha256':digest(PDF),
        'page_count':168,'symbolic_reference_sha256':alignment['symbolic_reference']['sha256'],
        'movements':movements,'measures':allboxes,'score_regions':parents,'bar_regions':fine,
        'status':'scan_geometry_and_XML_correspondence_candidates_for_user_review',
        'numbering_policy':'Source local labels are references; no rehearsal numbers or detector counts promoted to printed measure numbers.',
        'limitations':['Rectangles describe observed bars or shared systems, never notehead positions.',
            'Shared/ambiguous systems have no fabricated internal bar boxes or moving line.',
            'Matching counts alone do not certify notes, printed numbers or timing.'],'human_signoff':None}
    write(WORK/'measure-map.json',result)
    alignment['score_time_coverage']['segments']=[{'start_seconds':r['start_seconds'],'end_seconds':r['end_seconds']} for r in alignment['time_maps']]
    for m,b in zip(alignment['measures'],allboxes):
        m.update(pdf_page=b['page_number'],pdf_mapping_status=b['resolution'])
        if b.get('suppress_playhead'):m['flags'].append('shared_pdf_region_requires_review')
    alignment['quality']['flag_counts']=dict(Counter(f for m in alignment['measures'] for f in m['flags']))
    if (WORK/'alignment.json').exists():raise ValueError('Published alignment already exists; use a new review snapshot')
    write(WORK/'alignment.json',alignment)
    write(WORK/'sync/geometry-audit.json',{'pdf_sha256':digest(PDF),'raw_geometry':record(CACHE/'geometry.raw.json'),
        'corrected_pages':applied,'remaining_shared_regions':issues,'observed_fine_boxes':len(fine),
        'systems':len(parents),'source_intervals':len(allboxes),'human_signoff':None})
    log(f'PDF mapping: {len(fine)} fine rectangles, {len(parents)} system/page regions, {len(issues)} shared ranges')

def publish():
    import mistune
    renderer=mistune.create_markdown(escape=True,plugins=['table','url'])
    pointer=WORK/'playback/current.json'
    if pointer.exists():raise ValueError('Playback snapshot already activated; preserve it')
    for p in ['review-anchors.json','score-region-anchors.json','score-measure-corrections.json']:
        if (WORK/p).exists():raise ValueError('Existing user review protected')
    history=WORK/'sync/history';history.mkdir(parents=True,exist_ok=True)
    for p in [ROOT/'library.json',WORK/'project.json',WORK/'metadata/recording.json',WORK/'analysis/full-analysis.md',WORK/'analysis/performance-context.json']:
        target=history/('library-before-sync.json' if p.name=='library.json' else 'project-before-sync.json' if p.name=='project.json' else 'recording-before-sync.json' if p.name=='recording.json' else p.name)
        if not target.exists():shutil.copyfile(p,target)
    protected=read(WORK/'analysis/build-audit.json')['protected_files']
    preservation=[]
    for row in protected:
        p=ROOT/row['path'];actual=digest(p)
        if actual!=row['sha256']:raise ValueError('Previously protected playback input changed before publication: '+row['path'])
        preservation.append(row)
    doc=read(WORK/'sync/reference/written.json');alignment=read(WORK/'alignment.json');mapping_doc=read(WORK/'measure-map.json')
    media=read(WORK/'media-sync.json');metadata=read(WORK/'metadata/recording.json');context=read(WORK/'analysis/performance-context.json')
    if digest(ROOT/media['video']['path'])!=media['video']['sha256']:raise ValueError('Video changed')
    metadata['recording'].update(media=media['video'],selection_status='user_selected_file_bound_for_web_review',
        identity_status='user_selected_performance; embedded title and Berlin venue opening text checked',
        source_url='https://www.bilibili.com/video/BV1j741177rT/',
        embedded_upstream_url='https://www.youtube.com/watch?v=Il95HXvCdH4&t=714s',
        audio_sha256=media['video']['sha256'],duration_seconds=media['video']['duration_seconds'],
        score_alignment='works/prokofiev-piano-concerto-2/alignment.json')
    write(WORK/'metadata/recording.json',metadata)
    context.update(local_recording_id=context['target_recording_id'],local_file_verification_status='fingerprint_bound; user selection, embedded title and Berlin venue checked; exact paper-upload equivalence not certified')
    for s in context['sources']:
        if s['id']=='VT':s.update(local_media=media['video'],local_file_verified=True,
            identity_verification_scope='actual file fingerprint, embedded title, opening Berlin venue text; paper upload/year equivalence remains unverified')
    write(WORK/'analysis/performance-context.json',context)
    manuscript=WORK/'analysis/full-analysis.md';text=manuscript.read_text(encoding='utf8')
    text=text.replace('用户已选择这一版本，新视频正在下载；以下先依据文献和谱面修订诠释，文件放入后再核对身份。',
        '用户已提供这一合作阵容的新视频，现已绑定本地文件并建立候选曲谱同步；以下演奏评价仍区分文献归属与谱面解释，具体声音处理待网页试听核查。')
    text=text.replace('独立试听、触键与踏板判断，以及录音秒数仍待新文件到位后另行核对。',
        '录音时间已通过视频自身音轨独立计算，当前仍为供网页核查的候选；触键、踏板及演奏细节的独立试听继续另行记录。')
    text=text.replace('新文件正在下载，尚未绑定文件路径、指纹或时长。',
        '新文件已绑定路径、指纹与时长，并使用自身音轨计算同步；原引上传与本地上传是否逐帧等同仍未认证。')
    text=text.replace('新视频正在下载，文件核对与独立试听尚未完成，暂不生成录音映射或自动翻谱。',
        '新文件已绑定并建立网页端自动翻谱及候选高亮；同步边界、谱面区域和独立试听仍待用户核查。本轮没有生成视频或向视频插入谱面。')
    manuscript.write_text(text,encoding='utf8')
    subprocess.run([sys.executable,str(ROOT/'scripts/package_prokofiev2_analysis.py')],check=True)
    sections=read(WORK/'analysis/sections.json')['sections'];source_rows=read(WORK/'analysis/sources.json')['sources']
    boxes={b['measure_id']:b for b in mapping_doc['measures']};timed={m['measure_id']:m for m in alignment['measures']}
    written={m['measure_id']:m for m in doc['measures']}
    verification={'score':'key_pages_checked','literature':'relevant_sections_checked','location':'score_segment_candidate','timing':'candidate_alignment'}
    sources=[]
    for s in source_rows:
        title=s.get('title',s['id']);urls=[s['url']] if s.get('url') else []
        note=s.get('read_scope',s.get('reading',s.get('method','局部研究依据，详见来源台账。')))
        sources.append({'source_id':s['id'],'title':title,'citation_label':f"{s.get('author','')} · {title}",
            'kind':'thesis' if s['id']=='M' else 'research_article' if s['id'] in ['R','G'] else 'source_index',
            'reading_status':'relevant_sections_checked' if s['id'] in ['M','R','G'] else 'primary_page_checked',
            'verification_evidence':note,'urls':urls,'html':renderer(title+'\n\n'+note+'\n\n'+'\n\n'.join(f'[来源]({u})' for u in urls))})
    notes=[];events=[];essays=[];labels={'harmony':'和声','orchestration':'配器与织体','voices':'声部关系与复调','form':'曲式与主题发展'}
    for s in sections:
        ms=[written[mid] for mid in s['measure_ids']];bs=[boxes[m['measure_id']] for m in ms];ts=[timed[m['measure_id']] for m in ms]
        page_start=min(b['page_number'] for b in bs);page_end=max(b['page_number'] for b in bs)
        span={'precision':'reference_interval_candidate','reference_sha256':alignment['symbolic_reference']['sha256'],
            'reference_start_tick':float(F(ms[0]['start_q'])*960),'reference_end_tick':float(F(ms[-1]['end_q'])*960),
            'pdf_page_start':page_start,'pdf_page_end':page_end,'region_ids':list(dict.fromkeys(b['region_id'] for b in bs))}
        refs=[{'source_id':'M','locator':s['source_locator'],'claim_attribution':'authors'},
              {'source_id':'S','locator':f'物理页 {page_start}–{page_end}','claim_attribution':'score'}]
        md='\n\n'.join('**'+label+'。** '+s[key] for key,label in labels.items())+'\n\n**聆听线索。** '+s['listening']
        if s.get('performance_interpretation'):md+='\n\n**演奏诠释。** '+s['performance_interpretation']
        md+='\n\n'+s['source_locator']
        notes.append({'annotation_id':s['id'],'movement':s['movement'],'title':s['title'],
            'start_measure_id':ms[0]['measure_id'],'end_measure_id':ms[-1]['measure_id'],
            'start_sequence_index':ms[0]['sequence_index'],'end_sequence_index':ms[-1]['sequence_index'],
            'start_seconds':ts[0]['start_seconds'],'end_seconds':ts[-1]['end_seconds'],
            'start_pdf_page':page_start,'end_pdf_page':page_end,'markdown':md,'html':renderer(md),
            'review_status':'agent_editorial_human_review_pending','locator_precision':'bar_sequence_candidate','source_ids':[r['source_id'] for r in refs]})
        for key,label in labels.items():
            dimension='counterpoint' if key=='voices' else key
            events.append({'id':s['id']+'-'+dimension,'dimension':dimension,'short_label':s[key],
                'claim_level':'theoretical_analysis','analysis_origin':'score_study','score_spans':[span],
                'verification':verification,'sources':refs,'detail_markdown':s[key],'html':renderer(s[key]),
                'related_essay_ids':[f'prok2-essay-{s["movement"]}']})
    for mv in doc['movements']:
        n=mv['movement'];parts=[x for x in notes if x['movement']==n]
        body='\n\n'.join('### '+x['title']+'\n\n'+x['markdown'] for x in parts)
        essays.append({'id':f'prok2-essay-{n}','title':mv['title'],'claim_level':'hermeneutic_interpretation',
            'reading_mode':'persistent','markdown':body,'html':renderer(body),
            'score_spans':[{'precision':'page_range','pdf_page_start':mv['first_pdf_page'],'pdf_page_end':mv['last_pdf_page']}],
            'verification':{**verification,'location':'page_range'},'sources':[{'source_id':'M','locator':'实际选读范围见来源台账','claim_attribution':'authors'}],
            'related_event_ids':[e['id'] for e in events if e['id'].startswith(f'prokofiev2-{n}-')]})
    clock=[{'tick':0,'midi_seconds':0,'seconds_per_tick':.5/960}]
    work={'work_id':'prokofiev-piano-concerto-2','title':'第二钢琴协奏曲','original_title':'Piano Concerto No. 2 in G minor, Op.16',
        'composer':{'name':'谢尔盖·普罗科菲耶夫','original_name':'Sergei Prokofiev'},'instrumentation':'钢琴独奏与管弦乐队；四乐章，修订版'}
    recording={'recording_id':metadata['recording']['id'],'audio_sha256':media['video']['sha256'],
        'soloists':[{'name':'王羽佳','original_name':'Yuja Wang','role':'钢琴独奏'}],
        'conductor':{'name':'帕沃·雅尔维','original_name':'Paavo Järvi'},
        'ensemble':{'name':'柏林爱乐乐团','original_name':'Berliner Philharmoniker','abbreviation':'BPhil'},
        'duration_seconds':media['video']['duration_seconds'],
        'artist_information_note':'依据用户选择、文件内标题及开场柏林场地字幕登记。使用本视频自身音轨同步；文件包含片头、掌声及后段加演，这些区间不启用本协奏曲谱面跟随。准确演出日期及论文原引上传的逐帧等同性未认证。'}
    analysis={'format_version':'1.1.0','work':work,'recording':recording,'audio_sha256':media['video']['sha256'],
        'pdf_sha256':mapping_doc['pdf_sha256'],'source_document':{'path':manuscript.relative_to(ROOT).as_posix(),'title':'普罗第二钢协分析','review_status':'editorially_revised'},
        'annotations':notes,'movement_essays':[],'navigation_mode':'bar_sequence_candidate','event_candidates':[],
        'references':sources,'full_html':renderer(manuscript.read_text(encoding='utf8')),
        'coverage':{'guide_sections':38,'movement_sections':4,'pdf_pages':168},
        'notice':'四乐章38段分析 · 视频同源候选同步 · 高亮和首尾待网页核查',
        'provenance_notice':'谱面、文献观点与演奏评价分别保留依据。','reference_note':'相关章节选读不等于全文校核；视频文件身份、谱面几何和录音时间各自记录。'}
    research={'available':True,'schema_version':'1.0.0','work_id':work['work_id'],
        'edition':{'edition_id':'prokofiev2-original-scan-66128','pdf_sha256':mapping_doc['pdf_sha256']},
        'events':events,'essays':essays,'sources':sources,'reference_clock':clock,
        'engine':{'reference_sha256':alignment['symbolic_reference']['sha256']},
        'notice':'四维卡片展示已写好的谱面分析；当前工作是候选同步，不将辅助对齐时钟扩充为全曲和声认证。'}
    out=WORK/'playback/yuja-jarvi-20261027-v1';out.mkdir(parents=True,exist_ok=True)
    for name,value in [('analysis.json',analysis),('research.json',research)]:write(out/name,value)
    inputs=[WORK/'alignment.json',WORK/'measure-map.json',WORK/'media-sync.json',WORK/'sync/reference/written.json',
        WORK/'sync/geometry-audit.json',WORK/'sync/boundary-review.json',manuscript,WORK/'analysis/sections.json',
        WORK/'analysis/sources.json',WORK/'metadata/recording.json',PDF,SOURCE,ROOT/'scripts/prokofiev2_sync.py',
        Path(__file__),ROOT/media['video']['path']]
    manifest={'schema_version':1,'work_id':work['work_id'],'scope':'Web score synchronization and existing analytical prose; no video production',
        'inputs':[record(p) for p in inputs],'files':{p.name:{'sha256':digest(p),'bytes':p.stat().st_size} for p in out.glob('*.json')},
        'human_signoff':None,'expert_review':None}
    write(out/'manifest.json',manifest);write(pointer,{'path':out.relative_to(ROOT).as_posix(),'manifest_sha256':digest(out/'manifest.json')})
    project=read(WORK/'project.json');project.update(stage='web_sync_candidate_user_review_pending',
        alignment='works/prokofiev-piano-concerto-2/alignment.json',measure_map='works/prokofiev-piano-concerto-2/measure-map.json',
        player_registration=True,video=media['video'],recording_projection=None,
        processing_status={'alignment':'four independent video-audio movement DTWs','score_geometry':'original scanned PDF; observed regions with explicit shared systems',
            'human_listening_review':'pending','video_export':'not_requested_not_generated'})
    write(WORK/'project.json',project)
    library=read(ROOT/'library.json')
    if any(t['id']=='prokofiev-piano-concerto-2' for t in library['tracks']):raise ValueError('Track already registered')
    library['tracks'].append({'id':'prokofiev-piano-concerto-2','title':'普罗科菲耶夫 · 第二钢琴协奏曲（王羽佳／雅尔维）',
        'data_root':'works/prokofiev-piano-concerto-2','analysis_adapter':'prokofiev2-score-review-v1'})
    write(ROOT/'library.json',library)
    checks=[]
    for row in preservation:
        p=ROOT/row['path']
        if row['path']=='library.json':
            old=read(history/'library-before-sync.json');now=copy.deepcopy(library);now['tracks']=[t for t in now['tracks'] if t['id']!='prokofiev-piano-concerto-2']
            if old!=now:raise ValueError('Unrelated library entries changed')
            checks.append({'path':'library.json','old_snapshot':record(history/'library-before-sync.json'),'previous_tracks_unchanged':True})
        else:
            if digest(p)!=row['sha256']:raise ValueError('Unrelated playback changed')
            checks.append({'path':row['path'],'sha256':row['sha256'],'unchanged':True})
    write(WORK/'sync/source-preservation.json',{'checks':checks,'video_generated':False,'pdf_video_insertion':False,'human_signoff':None})
    log(f'Published web review: {len(alignment["measures"])} source intervals, {len(notes)} guide paragraphs, {len(events)} four-dimensional entries')

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('stage',choices=['mapping','publish']);args=parser.parse_args()
    mapping() if args.stage=='mapping' else publish()
