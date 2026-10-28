"""Publish the Op.96 synchronization, original score, research and four-part panels.

Uses the frozen repeat-aware reference; no raw sources or essays are rewritten.
"""
from collections import Counter,defaultdict
from fractions import Fraction as F
from bisect import bisect_right
from pathlib import Path
import copy,json,sys
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'scripts')]
from dvorak_american_sync import WORK,BASE,SOURCE,PDF,LABELS,read,write,digest,record,log


def compact(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,ensure_ascii=False,separators=(',',':'))+'\n',encoding='utf8')


def projection(alignment):
    maps={m['movement']:m['time_map'] for m in alignment['time_maps']}
    def seconds(q,movement):
        points=maps[movement];xs=[p['midi_seconds'] for p in points];x=float(F(q))*.5
        if x<xs[0]-1e-7 or x>xs[-1]+1e-7:raise ValueError('Outside movement map')
        i=max(0,bisect_right(xs,x)-1)
        if i>=len(xs)-1:return points[-1]['audio_seconds']
        a,b=points[i],points[i+1]
        return a['audio_seconds']+(x-a['midi_seconds'])/(b['midi_seconds']-a['midi_seconds'])*(b['audio_seconds']-a['audio_seconds'])
    return seconds


def build():
    import mistune
    from backend.musicxml_analysis.analyze import chord_description
    from backend.video_export.visual_panels import part_registry
    pointer=WORK/'playback/current.json'
    if pointer.exists():raise ValueError('Playback snapshot exists; preserve it and use a new version')
    out=WORK/'playback/stradivari-20261028-v1'
    if out.exists():raise ValueError('Use a new snapshot directory')
    doc=read(WORK/'sync/reference/written.json');alignment=read(WORK/'sync/alignment.raw.json')
    geo=read(WORK/'sync/geometry.raw.json');media=read(WORK/'media-sync.json')
    if geo['pdf']['sha256']!=digest(PDF) or geo['source_xml']['sha256']!=digest(SOURCE):raise ValueError('Geometry identity changed')
    if alignment['audio']['sha256']!=media['video']['sha256'] or digest(ROOT/media['video']['path'])!=media['video']['sha256']:raise ValueError('Video changed')
    original={b['source_sequence']:b for b in geo['bars']};boxes=[]
    for m in alignment['measures']:
        b=original[m['source_sequence']]
        boxes.append({**b,'measure_id':m['measure_id'],'region_id':'american-'+m['measure_id'],
                      'source_measure_id':m['source_measure_id'],'movement':m['movement'],'visit':m['visit'],
                      'midi_start_seconds':m['midi_start_seconds'],'midi_end_seconds':m['midi_end_seconds'],
                      'alignment_segment':f'movement-{m["movement"]}','coordinate_origin':'top_left',
                      'review_status':'vector_geometry_XML_layout_candidate_agent_images_checked',
                      'stable_candidate':'feature_variant_disagreement_over_2s' not in m['flags']})
        m.update(pdf_page=b['page_number'],pdf_mapping_status=b['resolution'])
    mapping={'format_version':'1.1.0','pdf_path':PDF.relative_to(ROOT).as_posix(),'pdf_sha256':digest(PDF),
             'page_count':34,'symbolic_reference_sha256':alignment['symbolic_reference']['sha256'],
             'movements':alignment['movements'],'measures':boxes,'bar_regions':boxes,'score_regions':[],
             'status':'observed_vector_bar_geometry_with_repeat_visit_mapping','human_signoff':None,
             'limitations':['853 physical bars reused by962 explicit visits; no invented internal divisions.',
                            'XML labels are not independently certified printed measure numbers.']}
    write(WORK/'alignment.json',alignment);write(WORK/'measure-map.json',mapping)
    seconds=projection(alignment);renderer=mistune.create_markdown(escape=True,plugins=['table','url'])
    sections=read(WORK/'analysis/sections.json')['sections']
    section_by_sequence={seq:s for s in sections for seq in range(s['first_sequence'],s['last_sequence']+1)}
    runs=[]
    for m in doc['measures']:
        s=section_by_sequence[m['source_sequence']]
        if runs and runs[-1]['section']['id']==s['id'] and m['source_sequence']==runs[-1]['measures'][-1]['source_sequence']+1:
            runs[-1]['measures'].append(m)
        else:runs.append({'section':s,'measures':[m]})
    notes=[];events=[];forms=[];timed={m['measure_id']:m for m in alignment['measures']}
    source_rows=read(WORK/'analysis/sources.json')['sources'];sources=[]
    for s in source_rows:
        note=s.get('read_scope',s.get('reading','资料身份见来源台账'))
        title=s.get('title',s['id']);url=s.get('url')
        sources.append({'source_id':s['id'],'title':title,'citation_label':title,'kind':s.get('kind','research_article'),
                        'reading_status':'relevant_sections_checked' if s['id'] in ['R01','R02','R03','R04','R07'] else 'scope_limited',
                        'verification_evidence':note,'urls':[url] if url else [],
                        'html':renderer(title+'\n\n'+note+ ('\n\n[来源]('+url+')' if url else ''))})
    clock=[{'tick':0,'midi_seconds':0,'seconds_per_tick':.5/960}]
    labels={'harmony':'和声','orchestration':'配器与织体','voices':'声部关系与复调','form':'曲式与主题发展'}
    for i,run in enumerate(runs,1):
        s,ms=run['section'],run['measures'];a,b=ms[0],ms[-1];ts=[timed[m['measure_id']] for m in ms]
        identity=f'american-guide-{i:03d}';pages=[original[m['source_sequence']]['page_number'] for m in ms]
        span={'precision':'reference_interval_candidate','reference_sha256':alignment['symbolic_reference']['sha256'],
              'reference_start_tick':float(F(a['start_q'])*960),'reference_end_tick':float(F(b['end_q'])*960),
              'pdf_page_start':min(pages),'pdf_page_end':max(pages),
              'region_ids':['american-'+m['measure_id'] for m in ms]}
        md='\n\n'.join('**'+label+'。** '+s[key] for key,label in labels.items())+'\n\n**聆听线索。** '+s['listening']+'\n\n'+s['source_locator']
        title=s['title']+(' · 再次经过' if a['visit']>1 else '')
        refs=[{'source_id':'S','locator':s['source_locator'],'claim_attribution':'score'},
              {'source_id':'X','locator':'源小节及音符台账','claim_attribution':'score'}]
        note={'annotation_id':identity,'movement':s['movement'],'title':title,
              'start_measure_id':a['measure_id'],'end_measure_id':b['measure_id'],
              'start_sequence_index':a['sequence_index'],'end_sequence_index':b['sequence_index'],
              'start_seconds':ts[0]['start_seconds'],'end_seconds':ts[-1]['end_seconds'],
              'start_pdf_page':min(pages),'end_pdf_page':max(pages),'markdown':md,'html':renderer(md),
              'review_status':'agent_editorial_human_review_pending','locator_precision':'bar_sequence_candidate',
              'source_section_id':s['id'],'visit':a['visit'],'source_ids':['S','X']}
        notes.append(note)
        forms.append({'id':identity,'title':title,'start_q':a['start_q'],'end_q':b['end_q'],
                      'xml_range':[a['sequence_index'],b['sequence_index']+1],'level':'guide_segment',
                      'argument':'已有分析阅读范围的反复路线投影，不冒充严格曲式边界'})
        for key,label in labels.items():
            dimension='counterpoint' if key=='voices' else key
            events.append({'id':identity+'-'+dimension,'dimension':dimension,'short_label':s[key],
                           'claim_level':'theoretical_analysis','analysis_origin':'score_study','score_spans':[span],
                           'verification':{'score':'key_pages_checked','literature':'relevant_sections_checked',
                                           'location':'score_segment_candidate','timing':'candidate_alignment'},
                           'sources':refs,'detail_markdown':s[key],'html':renderer(s[key]),
                           'related_essay_ids':[f'american-essay-{s["movement"]}']})
    essays=[]
    for mv in doc['movements']:
        body='\n\n'.join('### '+s['title']+'\n\n'+'\n\n'.join('**'+v+'。** '+s[k] for k,v in labels.items())
                           +'\n\n**聆听线索。** '+s['listening']+'\n\n'+s['source_locator']
                           for s in sections if s['movement']==mv['movement'])
        essays.append({'id':f'american-essay-{mv["movement"]}','title':mv['title'],'claim_level':'hermeneutic_interpretation',
                       'reading_mode':'persistent','markdown':body,'html':renderer(body),
                       'score_spans':[{'precision':'page_range','pdf_page_start':mv['first_pdf_page'],'pdf_page_end':mv['last_pdf_page']}],
                       'verification':{'score':'key_pages_checked','location':'page_range','timing':'candidate_alignment'},
                       'sources':[{'source_id':'S','locator':'各段定位','claim_attribution':'score'}]})
    work={'work_id':'dvorak-american','title':'第十二弦乐四重奏 美国','original_title':'String Quartet No.12 in F major, Op.96, B.179',
          'composer':{'name':'安东宁·德沃夏克','original_name':'Antonín Dvořák'},'instrumentation':'两把小提琴、中提琴、大提琴'}
    recording={'recording_id':'dvorak-american-stradivari-local','audio_sha256':media['video']['sha256'],
               'ensemble':{'name':'斯特拉迪瓦里四重奏','original_name':'Stradivari Quartet'},'soloists':[],
               'duration_seconds':media['video']['duration_seconds'],
               'artist_information_note':'依据用户文件名登记团名；演出日期和人员尚未独立核实。同步使用此视频自身音轨。'}
    analysis={'format_version':'1.1.0','work':work,'recording':recording,'audio_sha256':media['video']['sha256'],
              'pdf_sha256':digest(PDF),'source_document':{'path':(WORK/'analysis/full-analysis.md').relative_to(ROOT).as_posix(),
                                                       'title':'美国四重奏全谱分析','review_status':'agent_draft'},
              'annotations':notes,'movement_essays':[],'navigation_mode':'bar_sequence_candidate',
              'references':sources,'full_html':renderer((WORK/'analysis/full-analysis.md').read_text(encoding='utf8')),
              'coverage':{'guide_sections':len(notes),'movement_sections':4,'pdf_pages':34},
              'notice':'四乐章41段研究 · 含反复49次段落投影 · 同源视频候选同步',
              'provenance_notice':'谱面、文献观点、编号和演出时钟分别保留证据。'}
    # State frames are built from written activity. A two-note tremolo carries
    # alternatives across the shared span and never claims a literal chord.
    starts=defaultdict(list);ends=defaultdict(list);by_measure=defaultdict(list)
    for e in doc['events']:
        e.update(score_start_q=e['start_q'],score_end_q=e['end_q'],encoded_pitch=e['concert_pitch'],
                 exclusion_reason=None,technique_context=[])
        starts[F(e['start_q'])].append(e);ends[F(e['end_q'])].append(e);by_measure[e['measure_id']].append(e)
    points=sorted(set(starts)|set(ends)|{F(m['start_q']) for m in doc['measures']}|{F(doc['quarter_duration'])})
    frames=[];windows={};active={};mi=0;cache={};harmonies=defaultdict(list)
    for a,b in zip(points,points[1:]):
        for e in ends[a]:active.pop(e['id'],None)
        for e in starts[a]:active[e['id']]=e
        while mi+1<len(doc['measures']) and F(doc['measures'][mi+1]['start_q'])<=a:mi+=1
        m=doc['measures'][mi];es=list(active.values());grouped=defaultdict(list)
        for e in es:grouped[e['part_id']].append(e)
        identity=f'american-live-{len(frames)+1:06d}'
        f={'id':identity,'start_q':float(a),'end_q':float(b),'measure_id':m['measure_id'],
           'number':f'{m["movement"]}-{m["local_number"]}'+('（再次经过）' if m['visit']>1 else ''),
           'page':original[m['source_sequence']]['page_number'],'onset_q':str(a-F(m['start_q'])),
           'harmony_window_id':identity if es else None,'activity_uncertainty':[],
           'active_instruments':[{'part_id':pid,'label':LABELS[pid],'family':'弦乐','instrument_names':[LABELS[pid]],
                                  'pitches':sorted({e['concert_pitch']['name'] for e in ee}),'roles':[],
                                  'event_ids':[e['id'] for e in ee]} for pid,ee in grouped.items()]}
        frames.append(f)
        if es:
            key=tuple(sorted({e['concert_pitch']['name'] for e in es}))
            if key not in cache:cache[key]=chord_description(es)
            w={**copy.deepcopy(cache[key]),'id':identity,'measure_id':m['measure_id'],'start_q':str(a),'end_q':str(b),
               'onset_q':f['onset_q'],'event_ids':[e['id'] for e in es],
               'pitches':sorted({e['concert_pitch']['name'] for e in es})}
            if any(e.get('tremolo_alternatives') for e in es):
                w['chord']=None;w['display_label']='含震音交替音集 · '+'、'.join(w['pitches'])
            windows[identity]=w;harmonies[m['measure_id']].append({**w,'sonority':{**w,'label':w.get('display_label',w['label'])}})
    measures=[{**m,'sequence':m['sequence_index'],'number':f'{m["movement"]}-{m["local_number"]} · {m["visit"]}次',
               'page':original[m['source_sequence']]['page_number']} for m in doc['measures']]
    scope='四个弦乐分部的实际记谱区间；两音震音显示交替范围，非声学响度或人类逐音认证。'
    research={'available':True,'schema_version':'1.0.0','work_id':work['work_id'],
              'edition':{'edition_id':'american-openscore-user-edition','pdf_sha256':digest(PDF)},
              'events':events,'essays':essays,'sources':sources,'reference_clock':clock,
              'engine':{'reference_sha256':alignment['symbolic_reference']['sha256']},
              'musicxml':{'summary':{'measures':len(measures),'parts':4,'events':len(doc['events'])},
                          'measures':measures,'scope_note':scope},'notice':scope}
    live={'available':True,'work_id':work['work_id'],
          'projection':{'ppq':960,'reference_clock':clock,'reference_end_seconds':float(F(doc['quarter_duration']))*.5,
                        'reference_end_quarter':float(F(doc['quarter_duration'])),'audio_sha256':media['video']['sha256'],
                        'alignment_sha256':digest(WORK/'alignment.json'),'source_sha256':digest(SOURCE)},
          'frames':frames,'windows':windows,'readings':{},'form':{'sections':forms,'models':[]},
          'hud_cases':{'cases':[],'contexts':[]},'limitations':[scope]}
    evidence={'measures':{m['measure_id']:{'measure':m,'scope_note':scope,'events':by_measure[m['measure_id']],
              'part_registry':doc['parts'],'harmony':harmonies[m['measure_id']],'harmonic_readings':{},
              'orchestration':[],'intervals':[],'chordal_intervals':[],'hierarchy':[],
              'motif_comparisons':[],'cadences':[]} for m in measures}}
    # Join only explicit contiguous ties. Movement-local projection prevents
    # a final tied note from stretching across the following movement pause.
    flow_notes=[];pending={};joined=0
    for e in sorted(doc['events'],key=lambda e:(F(e['start_q']),e['id'])):
        key=(e['movement'],e['part_id'],e['staff'],e['voice'],e['ps'])
        previous=pending.pop(key,None)
        if 'stop' in e['tie'] and previous and F(previous['end_q'])==F(e['start_q']):
            previous['end_q']=e['end_q'];previous['event_ids'].append(e['id']);row=previous;joined+=1
        else:
            row={'id':e['id'],'event_ids':[e['id']],'part_id':e['part_id'],'label':e['label'],'family':'弦乐',
                 'pitch':e['ps'],'pc':int(e['ps'])%12,'name':e['concert_pitch']['name'],'movement':e['movement'],
                 'start_q':e['start_q'],'end_q':e['end_q'],'tremolo_alternatives':e.get('tremolo_alternatives',False)}
            flow_notes.append(row)
        if 'start' in e['tie']:pending[key]=row
    for row in flow_notes:
        row['start_seconds']=seconds(row['start_q'],row['movement']);row['end_seconds']=seconds(row['end_q'],row['movement'])
        if row['end_seconds']<=row['start_seconds']:raise ValueError('Nonpositive projected note')
    registry_parts=part_registry([{**p,'family':'弦乐'} for p in doc['parts']],labels=LABELS)
    groups=[{'id':p['id'],'label':p['label'],'color':p['color'],'part_ids':[p['id']]} for p in registry_parts]
    registry={'parts':registry_parts,'harmony_groups':groups,'flow_groups':groups}
    flow={'work_id':work['work_id'],'notes':flow_notes,'coverage':alignment['score_time_coverage'],
          'source':record(SOURCE),'video':media['video'],'alignment_sha256':digest(WORK/'alignment.json'),
          'tied_segments_joined':joined,'limitations':[scope]}
    activity={'parts':registry_parts,'events':[{**n,'kind':'note'} for n in flow_notes],
              'flow_groups':groups,'coverage':flow['coverage'],'unknown_intervals':[],'activity_basis':scope}
    panels={'available':True,'flow':flow,'activity':activity,'flow_groups':groups}
    out.mkdir(parents=True)
    for name,value in [('analysis.json',analysis),('research.json',research),('live.json',live),
                       ('evidence.json',evidence),('flow.json',flow),('activity.json',activity),('visual-panels.json',panels)]:compact(out/name,value)
    write(WORK/'metadata/visual-parts.json',registry)
    write(WORK/'metadata/recording.json',{'work':work,'recording':{**recording,'media':media['video']},
                                        'analysis_document':record(WORK/'analysis/full-analysis.md')})
    write(WORK/'sync/playback-audit.json',{'source_visits':len(measures),'paper_measures':853,'guide_runs':len(notes),
          'frames':len(frames),'flow_notes':len(flow_notes),'tied_segments_joined':joined,
          'written_activity_not_acoustic':True,'human_signoff':None,'expert_review':None})
    manifest={'schema_version':1,'work_id':work['work_id'],
              'inputs':[record(p) for p in [SOURCE,PDF,ROOT/media['video']['path'],WORK/'alignment.json',WORK/'measure-map.json',
                                            WORK/'media-sync.json',WORK/'sync/reference/written.json',WORK/'analysis/full-analysis.md',
                                            WORK/'analysis/sections.json',WORK/'analysis/sources.json']],
              'files':{p.name:{'sha256':digest(p),'bytes':p.stat().st_size} for p in out.glob('*.json')},
              'human_signoff':None,'expert_review':None}
    write(out/'manifest.json',manifest)
    write(pointer,{'path':out.relative_to(ROOT).as_posix(),'manifest_sha256':digest(out/'manifest.json')})
    project=read(WORK/'project.json');write(WORK/'sync/history/project-before-sync.json',project)
    project.update(stage='web_sync_and_visual_panels_candidate',alignment='works/dvorak-american/alignment.json',
                   measure_map='works/dvorak-american/measure-map.json',video=media['video'],player_registration=True)
    write(WORK/'project.json',project)
    library=read(ROOT/'library.json');write(WORK/'sync/history/library-before-sync.json',library)
    if any(t['id']==work['work_id'] for t in library['tracks']):raise ValueError('Track already registered')
    library['tracks'].append({'id':work['work_id'],'title':'德沃夏克 · 美国弦乐四重奏（Stradivari Quartet）',
                              'data_root':'works/dvorak-american','analysis_adapter':'score-snapshot-v1','visual_panels':True})
    write(ROOT/'library.json',library)
    log(f'Published {len(measures)} visits, {len(notes)} guide runs, {len(frames)} live frames')


if __name__=='__main__':build()
