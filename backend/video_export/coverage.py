"""Measure caption coverage and schedule authored text at existing score anchors.

This does not infer musical structure or generate prose. Semantic ranges are
editorial input; coverage is a soft objective inside those hard music bounds.
"""
import math
from .subtitles import analysis_ass


def merge_intervals(intervals):
    result=[]
    for start,end in sorted(intervals):
        if end<=start:continue
        if result and start<=result[-1][1]+1e-7:result[-1][1]=max(result[-1][1],end)
        else:result.append([start,end])
    return result


def caption_coverage(events,config):
    def seconds(value):
        h,m,s=value.split(':');return int(h)*3600+int(m)*60+float(s)
    intervals=[]
    for row in analysis_ass(events,config).splitlines():
        if row.startswith('Dialogue:'):
            values=row.split(',',9);intervals.append([seconds(values[1]),seconds(values[2])])
    return merge_intervals(intervals)


def blank_intervals(coverage,scopes):
    result=[]
    for low,high in scopes:
        cursor=low
        for start,end in coverage:
            if end<=low or start>=high:continue
            if start>cursor:result.append([cursor,min(start,high)])
            cursor=max(cursor,min(end,high))
        if cursor<high:result.append([cursor,high])
    return result


def schedule_entries(plan,alignment,config):
    """Respect supplied semantic anchors, movement pauses and reading budgets."""
    offset=config['segments'][0]['video_start']
    measures={m['sequence_index']:m for m in alignment['measures']}
    gaps={g['rank']:g for g in plan['gaps']}
    policy=config['caption_presentation']['analysis'];result=[]
    for entry in plan['entries']:
        gap=gaps[entry['gap_rank']];a=measures[entry['start_sequence']];b=measures[entry['last_sequence']]
        if a['movement']!=b['movement']:raise ValueError('补充文案不能跨越乐章停顿')
        if a['sequence_index']>b['sequence_index']:raise ValueError('谱面范围倒置')
        start=a['start_seconds']-offset
        music=next((s for s in alignment['score_time_coverage']['segments']
            if s['start_seconds']<=a['start_seconds']<s['end_seconds']),None)
        if music is None:raise ValueError('补充入口不在音乐范围内')
        if start<gap['start_seconds']+plan.get('minimum_head_silence_seconds',5)-1e-7:
            raise ValueError('补充入口须保留原分析结束后的聆听间隔')
        limit=min(gap['end_seconds'],music['end_seconds']-offset)-gap.get('tail_silence_seconds',3)
        limit=min(limit,b['end_seconds']-offset)
        count=len(''.join(entry['text'].split()));long=entry['column']=='诠释'
        cps=plan.get('interpretation_characters_per_second',4.4) if long else policy['characters_per_second']
        hold=plan.get('interpretation_hold_seconds',5) if long else policy['hold_seconds']
        desired=max(25 if long else policy['minimum_seconds'],count/cps+hold)
        end=round(min(start+desired,limit),3)
        fade=config['caption_presentation']['interpretation']['fade_out_ms']/1000 if long else policy['fade_out_ms']/1000
        if not math.isfinite(start+end) or end-start+1e-7<count/cps+fade:
            raise ValueError('谱面范围不足以容纳完整阅读与渐隐：'+entry['id'])
        result.append({**entry,'start_seconds':round(start,3),'end_seconds':end,
            'reading_characters':count,'characters_per_second':round(count/(end-start),3),
            'anchor_movement':a['movement'],'anchor_local_number':a['local_number'],
            'anchor_rehearsals':a.get('rehearsals',[]),'anchor_pdf_page':a['pdf_page']})
    for rank in gaps:
        entries=sorted((e for e in result if e['gap_rank']==rank),key=lambda e:e['start_seconds'])
        for a,b in zip(entries,entries[1:]):
            if b['start_seconds']-a['end_seconds']<plan.get('minimum_between_readings_seconds',5)-1e-7:
                raise ValueError('接续文案之间的聆听间隔不足：'+a['id']+'/'+b['id'])
    return result
