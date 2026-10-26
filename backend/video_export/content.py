"""Fail-closed publication review, independent of the research UI's labels."""
import hashlib
import json
import math
from pathlib import Path
import re
import unicodedata

SLOTS=('harmony','orchestration','counterpoint','form','guide','interpretation')
FORBIDDEN=re.compile(r'待分析|待核查|待核对|待审|待复核|尚未.{0,8}复核|未经.{0,8}(确认|核验|复核)|'
    r'未验证|未核验|估计位置|待补充|待定位|占位|置信度|调试|TODO|FIXME|DEBUG|candidate|pending|unreviewed',re.I)


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def write(path,data):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')


def digest(path):
    with Path(path).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()


def bounded(root,name):
    path=(Path(root)/name).resolve()
    if not path.is_relative_to(Path(root).resolve()):raise ValueError('Path outside package/project')
    return path


def content_hash(event):
    fields={k:event.get(k) for k in ['id','slot','text','video_start','video_end','phase','timing_precision']}
    return hashlib.sha256(json.dumps(fields,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()


def normalized(text):
    return ''.join(c for c in unicodedata.normalize('NFKC',text) if unicodedata.category(c)!='Cf')


def review_events(document,config,root):
    accepted=[];excluded=[];seen=set()
    for event in document.get('events',[]):
        reasons=[];identifier=event.get('id');text=event.get('text','');review=event.get('review',{})
        if not identifier or identifier in seen:reasons.append('missing_or_duplicate_id')
        seen.add(identifier)
        if event.get('slot') not in SLOTS:reasons.append('unknown_slot')
        if not isinstance(text,str) or not text.strip():reasons.append('empty_text')
        elif FORBIDDEN.search(normalized(text)):reasons.append('research_or_placeholder_text')
        if review.get('status')!='approved' or not review.get('reviewer') or not review.get('scope'):
            reasons.append('not_publication_reviewed')
        if review.get('content_sha256')!=content_hash(event):reasons.append('changed_since_review')
        refs=review.get('sources',[])
        if not refs:reasons.append('missing_evidence')
        for ref in refs:
            try:
                if digest(bounded(root,ref['path']))!=ref['sha256']:reasons.append('changed_source_evidence')
            except (OSError,ValueError,KeyError):reasons.append('unavailable_source_evidence')
        start,end=event.get('video_start'),event.get('video_end')
        valid=all(isinstance(v,(float,int)) and not isinstance(v,bool) and math.isfinite(v) for v in [start,end]) and 0<=start<end
        if not valid:reasons.append('invalid_time_interval')
        elif event.get('phase')=='intro':
            if event.get('slot')!='interpretation' or end>config['music_start_video']-3:reasons.append('intro_three_second_violation')
        elif start<config['music_start_video']:reasons.append('regular_caption_before_music')
        if event.get('timing_precision') not in {'source_interval','score_segment','page_range','user_confirmed'}:
            reasons.append('unreliable_timing')
        if valid and isinstance(text,str):
            required=max(config.get('minimum_caption_seconds',3),len(text.replace('\n',''))/config.get('characters_per_second',7))
            if end-start+1e-6<required:reasons.append('insufficient_reading_time')
        if isinstance(text,str) and event.get('slot') in SLOTS:
            from .subtitles import wrap
            name='intro' if event.get('phase')=='intro' else event['slot']
            try:wrap(text,config['layout'][name],config)
            except ValueError:reasons.append('text_overflows_fixed_slot')
            except KeyError:reasons.append('missing_caption_layout')
        if reasons:excluded.append({'id':identifier,'text':text,'reasons':sorted(set(reasons))})
        else:accepted.append(dict(event))
    # Conflicts are rejected, never silently select whichever item came last.
    conflicts=set()
    for slot in SLOTS:
        rows=sorted((e for e in accepted if e['slot']==slot),key=lambda e:e['video_start'])
        for i,row in enumerate(rows):
            for other in rows[i+1:]:
                if other['video_start']>=row['video_end']:break
                conflicts.update([row['id'],other['id']])
    for e in accepted:
        if e['id'] in conflicts:excluded.append({'id':e['id'],'text':e['text'],'reasons':['overlapping_same_slot']})
    return [e for e in accepted if e['id'] not in conflicts],excluded


def output_events(events,config,exclusions=None):
    result=[];offset=0
    for segment in config['segments']:
        for e in events:
            start=max(e['video_start'],segment['video_start']);end=min(e['video_end'],segment['video_end'])
            if e.get('phase')=='intro':end=min(end,config.get('intro_clear_video',config['music_start_video']-3))
            if end>start:
                required=max(config.get('minimum_caption_seconds',3),len(e['text'].replace('\n',''))/config.get('characters_per_second',7))
                if end-start+1e-6<required:
                    if exclusions is not None:exclusions.append({'id':e['id'],'text':e['text'],'reasons':['clip_leaves_insufficient_reading_time']})
                    continue
                result.append({**e,'output_start':offset+start-segment['video_start'],
                    'output_end':offset+end-segment['video_start']})
        offset+=segment['video_end']-segment['video_start']
    return sorted(result,key=lambda e:(e['output_start'],e['slot']))
