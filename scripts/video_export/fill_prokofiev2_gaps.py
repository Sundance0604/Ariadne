"""Add score-anchored follow-up captions to the ten discussed gaps; no encoding."""
from pathlib import Path
from collections import Counter
import argparse,copy,datetime,shutil,subprocess,sys

ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from backend.video_export.content import read,write,digest
from backend.video_export.editor import prepare,export
from backend.video_export.coverage import schedule_entries,caption_coverage,blank_intervals
from backend.video_export.pipeline import validate_config,verify_bindings
from backend.video_export.subtitles import score_ass,wrap,reading_window

WORK=ROOT/'works/prokofiev-piano-concerto-2';DATA=WORK/'video-export'
DOCUMENT=DATA/'captions-editable.json';PACKAGE=ROOT/'output/video-export/prokofiev2-full-001'


def coverage_report(events,config,alignment):
    offset=config['segments'][0]['video_start']
    scopes=[[s['start_seconds']-offset,s['end_seconds']-offset] for s in alignment['score_time_coverage']['segments']]
    gaps=blank_intervals(caption_coverage(events,config),scopes);music=sum(b-a for a,b in scopes)
    blank=sum(b-a for a,b in gaps)
    return {'music_seconds':music,'blank_seconds':round(blank,3),'blank_percent':round(blank/music*100,2),
        'blank_count':len(gaps),'largest_music_blank_seconds':round(max((b-a for a,b in gaps),default=0),3)}


def build():
    plan=read(DATA/'gap-fill-plan.json');original=read(DOCUMENT)
    if digest(DOCUMENT)!=plan['base_document_sha256']:
        raise ValueError('文稿已变化，保留当前用户修改；不能重复套用或覆盖此版补充计划。')
    config,before,_=prepare(original,PACKAGE);alignment=read(WORK/'alignment.json')
    if original.get('对齐指纹')!=digest(WORK/'alignment.json'):
        raise ValueError('录音同步已变化，先复核语义入口；不能沿用本版补写时点。')
    entries=schedule_entries(plan,alignment,config);sections={s['id']:s for s in read(WORK/'analysis/sections.json')['sections']}
    old_coverage=caption_coverage(before,config)
    for e in entries:
        span=[e['start_seconds'],e['end_seconds']]
        if blank_intervals(old_coverage,[span])!=[span]:
            raise ValueError('补写时段已存在可见文字，不能覆盖：'+e['id'])
    revised=copy.deepcopy(original);added=[];evidence=[]
    for e in entries:
        s=sections[e['source_section']]
        row={'编号':e['id'],'栏目':e['column'],'开始秒':e['start_seconds'],'结束秒':e['end_seconds'],
            '标题':e['title'],'文字':e['text'],'显示':True,'出处':s['source_locator'],
            '原文范围':'已有谱面分析的接续展开；选定原谱图像复核，不新增本场演奏实测结论。',
            '接续分析':{'计划':plan['id'],'原空白排名':e['gap_rank'],'源段落':s['id'],
                'XML起始序列':e['start_sequence'],'XML结束序列':e['last_sequence'],
                '候选入口说明':e['anchor_reason'],'时点来源':'既有同源DTW的XML小节入口；未新增试听锚点',
                'source_status':'agent_score_and_manuscript_synthesis','human_signoff':None}}
        added.append(row)
        at=next((i for i,r in enumerate(revised['字幕']) if float(r['开始秒'])>row['开始秒']),len(revised['字幕']))
        revised['字幕'].insert(at,row)
        evidence.append({**e,'source_text':{k:s[k] for k in e['source_fields']},'source_locator':s['source_locator'],
            'human_signoff':None,'scope':'Selected score images, XML directions and existing analysis; not independently heard performance timing.'})
    revised['空白补充']={'plan':plan['id'],'date':'2026-10-27','新增条数':len(added),
        '规则':'音乐事件决定入口，阅读长度决定停留；在谱面范围内均衡文字密度，保护乐章间停顿与末尾弱音。',
        '原字幕保留':True,'video_generated':False,'human_signoff':None}
    active,after,excluded=prepare(revised,PACKAGE);validate_config(active)
    assert not excluded
    assert [r for r in revised['字幕'] if r['编号'] not in {r['编号'] for r in added}]==original['字幕']
    coverage=caption_coverage(after,active)
    for a,b in caption_coverage(before,config):
        assert not blank_intervals(coverage,[[a,b]]),'原可见字幕不可因填充而被截断'
    for event in after:
        slot='intro' if event['phase']=='intro' else event['slot'];box={**active['layout'][slot],**event.get('render_style',{})}
        lines=wrap(event['text'],{**box,'h':100000},active).splitlines();size=box['font_size']
        if slot=='interpretation':
            window=reading_window(box,size,len(lines))
            assert len(lines)*window['line_height']<=window['bottom']-window['initial_y']-window['padding']
        for line in lines:
            assert sum((1 if ord(c)>255 else .65)*size+active.get('spacing',0) for c in line)<=box['w']+.01
    gap_results=[]
    for g in plan['gaps']:
        music=next(s for s in alignment['score_time_coverage']['segments'] if s['start_seconds']<=g['start_seconds']<s['end_seconds'])
        end=min(g['end_seconds'],music['end_seconds']);remaining=blank_intervals(coverage,[[g['start_seconds'],end]])
        seconds=sum(b-a for a,b in remaining)
        gap_results.append({**g,'music_end_seconds':end,'music_seconds':round(end-g['start_seconds'],3),
            'added_ids':[r['编号'] for r in added if r['接续分析']['原空白排名']==g['rank']],
            'remaining_music_blank_seconds':round(seconds,3),'remaining_music_intervals':remaining,
            'longest_remaining_music_blank_seconds':round(max((b-a for a,b in remaining),default=0),3),
            'music_text_coverage_percent':round((1-seconds/(end-g['start_seconds']))*100,2)})
    refs=[WORK/'alignment.json',WORK/'analysis/sections.json',WORK/'analysis/material-relations.json',WORK/'analysis/sources.json']
    refs += [ROOT/p for p in [read(WORK/'sync/reference/written.json')['source']['path'],read(WORK/'measure-map.json')['pdf_path']]]
    report={'date':'2026-10-27','plan_id':plan['id'],'original_document_sha256':digest(DOCUMENT),'plan_sha256':digest(DATA/'gap-fill-plan.json'),
        'original_entries':len(original['字幕']),'added_entries':len(added),'total_entries':len(revised['字幕']),
        'counts':dict(Counter(r['栏目'] for r in revised['字幕'])),'before':coverage_report(before,config,alignment),
        'after':coverage_report(after,active,alignment),'gaps':gap_results,'entries':evidence,
        'sources':[{'path':p.relative_to(ROOT).as_posix(),'sha256':digest(p)} for p in refs],
        'validation':['Original caption rows preserved exactly','Added starts taken from existing XML measure recording times',
            'All ten gaps filled inside music; movement pauses and tail silence protected','Actual ASS display intervals and same-slot non-overlap checked',
            'Earlier visible text coverage retained','Full paragraphs fit interpretation rectangle; wrapped widths checked'],
        'video_generated':False,'human_signoff':None,'expert_signoff':None}
    return revised,active,after,report


def main(apply=False):
    revised,config,events,report=build()
    if not apply:
        print({'added':report['added_entries'],'before':report['before'],'after':report['after']});return
    verify_bindings(PACKAGE)
    movies={str(p.relative_to(PACKAGE)):p.stat().st_size for p in PACKAGE.glob('edits-*/*.mp4')}
    backup=ROOT/'local/video-export/backups'/('prokofiev2-gaps-'+datetime.datetime.now().strftime('%Y%m%d-%H%M%S'))
    backup.mkdir(parents=True);shutil.copy2(DOCUMENT,backup/DOCUMENT.name)
    write(DOCUMENT,revised)
    ass=export(revised,PACKAGE,ass_only=True);folder=ass.parent
    source=read(PACKAGE/'score/render-input.json');source.update(config=config,annotations=events)
    write(folder/'score-input.json',source)
    subprocess.run(['node',str(PACKAGE/'score/renderer/render-plan.mjs'),str(folder/'score-input.json'),str(folder/'score-plan.json')],check=True)
    score_plan=read(folder/'score-plan.json');(folder/'score.ass').write_text(score_ass(score_plan,config),encoding='utf-8-sig')
    for event in (e for e in events if e['slot']=='interpretation' and e['phase']!='intro'):
        assert all(not p['visible'] for p in score_plan['events'] if event['video_start']<=p['videoTime']<event['video_end'])
    assert movies=={str(p.relative_to(PACKAGE)):p.stat().st_size for p in PACKAGE.glob('edits-*/*.mp4')}
    report.update(document_sha256=digest(DOCUMENT),revision=folder.relative_to(ROOT).as_posix(),
        backup=backup.relative_to(ROOT).as_posix(),existing_user_movies_preserved=movies)
    write(DATA/'gap-fill-evidence.json',report);write(folder/'gap-fill-check.json',report)
    write(DATA/'presentation-ready.json',{'revision':folder.relative_to(ROOT).as_posix(),
        'document':DOCUMENT.relative_to(ROOT).as_posix(),'ass':ass.relative_to(ROOT).as_posix(),
        'score_plan':(folder/'score-plan.json').relative_to(ROOT).as_posix(),'caption_count':len(revised['字幕']),
        'video_encoded':False,'instructions':'关闭旧字幕编辑窗口后重新打开普二完整版，再由用户自行生成。'})
    print({'revision':report['revision'],'total':len(revised['字幕']),'before':report['before'],'after':report['after']})


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--apply',action='store_true')
    main(parser.parse_args().apply)
