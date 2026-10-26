"""Immutable independent round, followed by a separately recorded comparison."""
import hashlib
import json
import platform
from importlib.metadata import version
from datetime import datetime,timezone
from pathlib import Path
from . import VERSION
from .common import read, write, digest, bounded_path, pitch_name

FILES=('profile.json','pdf-observations.json','notes.json','correspondence.json','harmony.json',
       'counterpoint.json','instrument-activity.json','theme-identities.json','form.json','hud-events.json','validation.json')


def source_code_hash():
    folder=Path(__file__).parent
    return hashlib.sha256(b''.join(p.read_bytes() for p in sorted(folder.glob('*.py')))).hexdigest()


def span_for(start,end,notes,profile):
    refs=[]
    for note in notes:
        for loc in note['score_locations']:
            if loc.get('bar_start_tick') is None or loc['bar_start_tick']<end and loc['bar_end_tick']>start:
                refs.append(loc)
    if not refs:return [{'precision':'unlocated'}]
    return [{'precision':'reference_interval_candidate','pdf_page_start':min(p['page'] for p in refs),
        'pdf_page_end':max(p['page'] for p in refs),'reference_start_tick':start,'reference_end_tick':end,
        'reference_sha256':profile['midi']['sha256'],'region_ids':[],
        'location_basis':'native_notehead_boxes_plus_candidate_reference_correspondence'}]


def hud_events(profile,notes,harmony,counterpoint,orchestration,form):
    byid={n['id']:n for n in notes};events=[]
    def event(record,dimension,label,detail,kind,refs,scope='instant'):
        chosen=[byid[id] for id in record.get('note_ids',[]) if id in byid]
        spans=span_for(record['start_tick'],record['end_tick'],chosen,profile)
        if spans[0]['precision']=='unlocated':return
        events.append({'id':'engine-'+record['id'],'dimension':dimension,'claim_level':'theoretical_analysis',
            'short_label':label,'detail_markdown':detail,'score_spans':spans,
            'analysis_framework':record.get('framework','explicit note intervals, activity and candidate correspondence'),
            'rationale':record.get('rationale',detail),'uncertainties':record.get('alternatives',[])+[
                '参考时值来自辅助MIDI；原PDF完整节奏、连线与踏板解释尚未全部核查。',
                '参考时间经既有候选对齐投影，不是已验收的逐音播放位置。'],
            'sources':[{'source_id':'ravel-target-score','locator':'源PDF音头、谱表与记谱标记，见原始证据','claim_attribution':'score'},
                {'source_id':'engine-methods-v1','locator':kind+'；独立阶段冻结文件','claim_attribution':'project'}],
            'verification':{'score':'pending','literature':'not_applicable','location':'reference_interval_candidate','timing':'candidate_alignment'},
            'related_essay_ids':[],'analysis_origin':'engine_candidate','scope_kind':scope,
            'raw_evidence_ids':record.get('note_ids',[]),'evidence_records':[{'file':kind,'id':id} for id in refs],
            'related_structure_ids':[]})
    names=('C','C♯','D','E♭','E','F','F♯','G','A♭','A','B♭','B')
    qualities={'major':'大三和弦','minor':'小三和弦','diminished':'减三和弦','augmented':'增三和弦',
        'dominant7':'属七形态','major7':'大七形态','minor7':'小七形态','half_diminished7':'半减七形态','diminished7':'减七形态'}
    for w in harmony['windows']:
        s=w['sonority'];c=s['candidates'];bass=s['bass'];pcs='、'.join(names[p] for p in s['pitch_classes'])
        if not w['pdf_input_complete']:label='待分析：音符／八度对应有缺口'
        elif len(c)==1:label=f'{names[c[0]["root_pc"]]}{qualities[c[0]["quality"]]} · '+('原位','第一转位','第二转位','第三转位')[c[0]['inversion_index']]
        else:label='音集 '+pcs+' · '+('四度结构候选' if 'stacked_fourths' in s['structures'] else '未定功能')
        detail=f'同时结构音级：{pcs}。辅助符号延音模型低音：{pitch_name(bass)}。原始记录逐音保留乐器、起止位置、PDF音头及对应状态。'
        if not w['pdf_input_complete']:detail+=' 本窗口存在未定位或八度不一致的音符，暂不把识别到的和弦候选当作当前总谱结论。'
        if c:
            detail+=' 形态候选：'+'；'.join(names[a['root_pc']]+qualities[a['quality']]+('，'+('、'.join(k['context']+'语境：'+k['roman'] for k in a['roman_candidates'])) if a['roman_candidates'] else '') for a in c)+'。级数为竞争调性语境下的候选，不能据形态自动确认功能。'
        if w['pedal_residue_note_ids']:detail+=f' 本窗口另有{len(w["pedal_residue_note_ids"])}条CC64延音模型余音；按键层与整体延音模型分别列出，不能混称整体实际低音。'
        event(w,'harmony',label,detail,'harmony',[w['id']])
    groups={}
    for r in counterpoint['relations']+counterpoint['compound_melodies']:
        key=(r['excerpt'],r['start_tick'],r['end_tick']);groups.setdefault(key,[]).append(r)
    for (excerpt,start,end),records in groups.items():
        doubling=sum(r.get('kind')=='unison_or_octave_doubling' for r in records)
        r={'id':f'counterpoint-{excerpt}-{start}','start_tick':start,'end_tick':end,
           'note_ids':sorted({i for r in records for i in r['note_ids']})}
        event(r,'counterpoint',f'声部关系：{doubling}组加倍／{len(records)-doubling}组其他候选',
            '比较音程、实际入口、节奏网格和运动方向；高低音投影不冒充原谱独立声部。详见可检查的逐音对应；没有凭同时奏响判定卡农或赋格。',
            'counterpoint',[r['id'] for r in records],scope='span')
    edges=orchestration['activity_edges']
    for i,edge in enumerate(edges):
        excerpt=next(e for e in profile['excerpts'] if e['id']==edge['excerpt'])
        end=next((e['tick'] for e in edges[i+1:] if e['excerpt']==edge['excerpt']),excerpt['end_tick'])
        if end<=edge['tick']:continue
        r={**edge,'start_tick':edge['tick'],'end_tick':end}
        region=next((r for r in orchestration['regions'] if r['excerpt']==edge['excerpt'] and r['start_tick']<=edge['tick']<r['end_tick']),None)
        detail='活动进入：'+('、'.join(edge['entered']) or '无')+'；退出：'+('、'.join(edge['exited']) or '无')+'。有原生震音记号支持的短离键间隙合并为持续活动候选；原MIDI活动边缘另存，其余短离键仍不能自动等同音乐性退出。'
        if region:detail+=' 乐器职责为可修订假设，谱面力度／奏法另列为原始标记；层数与音域变化不直接证明曲式边界。'
        event(r,'orchestration',f'{len(edge["active_parts"])}组乐器发音 · 进入／退出候选',detail,
            'instrument-activity',[edge['id']]+([] if not region else [region['id']]))
    for unit in form['units']:
        if unit['level']!='section':continue
        event(unit,'form','结构候选区间 · 功能待判',
            '结合多类证据提出区间，不预设奏鸣曲式。节选首尾是处理范围截断，不是已查明的曲式边界。乐句节点保留为片段候选，主题身份尚未强行命名。',
            'form',[unit['id']]+unit['boundary_ids'],scope='background')
    for e in events:
        for boundary in form['boundaries']:
            if len(e['related_structure_ids'])>=8:break
            if any(s.get('reference_start_tick',-1)<=boundary['tick']<s.get('reference_end_tick',-1) for s in e['score_spans']):e['related_structure_ids'].append(boundary['id'])
    return events


def build(root,profile_path,output,activate=False):
    from .extract import native_pdf,midi_reference,correlate
    from . import harmony,counterpoint,orchestration,form
    from .motif import MotifAnalyzer
    root=Path(root).resolve();profile_path=Path(profile_path).resolve();output=Path(output).resolve()
    if not output.is_relative_to(root) or output==root or output.suffix:
        raise ValueError('Output must be a dedicated directory inside the project')
    profile=read(profile_path);code_hash=source_code_hash()
    runtime={'python':platform.python_version(),**{name:version(name) for name in ['pdfplumber','pdfminer.six','mido']}}
    run_id=hashlib.sha256((digest(profile_path)+code_hash+json.dumps(runtime,sort_keys=True)).encode()).hexdigest()[:16]
    run=output/('round1-'+run_id)
    if run.exists():
        manifest=read(run/'manifest.json')
        if not all(digest(run/name)==value for name,value in manifest['files'].items()):raise ValueError('Frozen round was modified; do not overwrite history')
    else:
        pdf=native_pdf(root,profile);midi=midi_reference(root,profile);correspondence=correlate(pdf,midi,profile['excerpts'])
        notes=[n for n in midi['notes'] if any(n['start_tick']<e['end_tick'] and n['sounding_end_tick']>e['start_tick'] for e in profile['excerpts'])]
        h=harmony.analyze(notes,profile['excerpts'],midi['ppq'])
        cp=counterpoint.analyze(notes,profile['excerpts'],midi['ppq'])
        motifs=MotifAnalyzer().analyze(cp['streams'],notes,profile['excerpts'])
        orch=orchestration.analyze(notes,pdf,profile['excerpts'],midi['ppq'],cp)
        f=form.analyze(notes,profile['excerpts'],midi['ppq'],midi['meters'],orch,h,motifs,midi['reference_clock'])
        events=hud_events(profile,notes,h,cp,orch,f)
        summary={}
        for dimension in ['harmony','counterpoint','orchestration','form']:
            selected=[e for e in events if e['dimension']==dimension]
            evidence={id for e in selected for id in e['raw_evidence_ids']}
            locations=[loc for n in notes if n['id'] in evidence for loc in n['score_locations']]
            summary[dimension]={'events':len(selected),'reference_interval_candidates':len(selected),
                'precise_verified_score_events':0,'page_only_events':0,'with_raw_note_evidence':sum(bool(e['raw_evidence_ids']) for e in selected),
                'with_native_pdf_evidence':sum(any(by['score_locations'] for by in notes if by['id'] in set(e['raw_evidence_ids'])) for e in selected),
                'pdf_pages_with_candidate_evidence':sorted({loc['page'] for loc in locations}),
                'reference_measure_candidates':sorted({n['midi_measure_candidate'] for n in notes if n['id'] in evidence}),
                'human_checked':0,'expert_checked':0,'candidate_or_undetermined':len(selected),
                'covered_excerpt_ids':sorted({s['id'] for s in profile['excerpts'] if any(
                    any(sp.get('reference_start_tick',-1)<s['end_tick'] and sp.get('reference_end_tick',-1)>s['start_tick'] for sp in e['score_spans']) for e in selected)})}
        validation={'algorithm_version':VERSION,'dimensions':summary,'pdf_noteheads':len(pdf['notes']),
            'midi_notes':len(notes),'unlocated_midi_notes':sum(not n['score_locations'] for n in notes),
            'unlocated_pitched_midi_notes':sum(not n['score_locations'] and not n['is_drum'] for n in notes),
            'unlocated_unpitched_midi_notes':sum(not n['score_locations'] and n['is_drum'] for n in notes),
            'octave_disputed_notes':sum(bool(n['score_locations']) and not n['correspondence']['octave_agrees'] for n in notes),
            'unmatched_pdf_heads':len(correspondence['unmatched_pdf_head_ids']),
            'software_validation':'referential integrity checked separately; no musicological certification',
            'human_review_count':0,'expert_review_count':0,
            'expansion_gate':{'C_D_enabled':False,'reason':'A/B contain pitch/rhythm/voice uncertainties; require recorded content review before expansion.'},
            'prior_exposure_note':'Earlier discussion already used literature. This round is input-independent and frozen before comparison, not historically blind.'}
        documents={'profile':profile,'pdf-observations':pdf,'notes':{'notes':notes,'reference_clock':midi['reference_clock'],
            'metrical_reference':midi['metrical_reference'],'pedal_controls':midi['pedal_controls'],'ppq':midi['ppq'],'issues':midi['issues']},
            'correspondence':correspondence,'harmony':h,'counterpoint':cp,'instrument-activity':orch,
            'theme-identities':motifs,'form':f,'hud-events':{'events':events},'validation':validation}
        # This is a new immutable round: no original annotations, sync or media writes.
        run.mkdir(parents=True)
        for key,value in documents.items():write(run/(key+'.json'),value)
        manifest={'schema_version':'1.0.0','engine_version':VERSION,'work_id':profile['work_id'],'run_id':run_id,
            'created_at':datetime.now(timezone.utc).isoformat(),'runtime_versions':runtime,
            'source_code_sha256':code_hash,'profile_sha256':digest(profile_path),'sources':{'pdf':profile['pdf'],'midi':profile['midi']},
            'independent_inputs':['fingerprint-bound vector PDF','auxiliary MIDI','staff/transposition adapter','general theory rules'],
            'excluded_inputs':['recording seconds','existing structural-events/essays','literature text'],
            'files':{name:digest(run/name) for name in FILES}}
        write(run/'manifest.json',manifest)
    from .store import validate_run
    validate_run(run,root,check_sources=True)
    if activate:
        if not output.is_relative_to(root/'analysis'/'engine'):raise ValueError('Activate only a dedicated analysis/engine run')
        write(root/'analysis/engine/current.json',{'run_path':run.relative_to(root).as_posix(),'manifest_sha256':digest(run/'manifest.json')})
    return run
