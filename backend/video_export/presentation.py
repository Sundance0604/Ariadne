"""Opt-in caption presentation rules stored in the editable document."""
import copy,math

SLOTS={'和弦':'harmony','配器':'orchestration','声部关系与复调':'counterpoint',
       '曲式与主题发展':'form','导聆':'guide'}


def presentation_config(config,rules):
    if not rules:return config
    config=copy.deepcopy(config)
    config['presentation_rules']=copy.deepcopy(rules)
    def number(group,key,default,low,high):
        value=group.get(key,default)
        if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value) or not low<=value<=high:
            raise ValueError(f'呈现规则“{key}”须在{low}至{high}之间。')
        return value
    analysis=rules.get('分析',{})
    enabled=analysis.get('读完自动隐去',True)
    if not isinstance(enabled,bool):raise ValueError('读完自动隐去须为true或false。')
    interpretation=rules.get('诠释',{})
    mode=interpretation.get('模式','宽幅缓升')
    if mode not in ('宽幅缓升','普通'):raise ValueError('未知诠释呈现模式。')
    suppressed=rules.get('诠释时隐藏栏目',list(SLOTS))
    if not isinstance(suppressed,list) or any(s not in SLOTS for s in suppressed):raise ValueError('诠释时隐藏栏目名称无效。')
    hide_score=rules.get('诠释时隐藏乐谱',True)
    if not isinstance(hide_score,bool):raise ValueError('诠释时隐藏乐谱须为true或false。')
    config['interpretation_suppresses_slots']=[SLOTS[s] for s in suppressed]
    config['interpretation_hides_score']=hide_score
    config['balanced_caption_wrap']=True
    config['caption_presentation']={
        'analysis':{'enabled':enabled,'characters_per_second':number(analysis,'每秒阅读字数',5,1,15),
            'minimum_seconds':number(analysis,'最短显示秒',10,3,60),
            'hold_seconds':number(analysis,'读后停留秒',3,0,30),
            'scroll_pixels_per_second':number(analysis,'滚动像素每秒',26,8,120),
            'fade_in_ms':number(analysis,'淡入毫秒',450,0,5000),
            'fade_out_ms':number(analysis,'淡出毫秒',1600,0,10000)},
        'interpretation':{'mode':'cinematic' if mode=='宽幅缓升' else 'normal',
            'travel_px':number(interpretation,'上移像素',100,0,300),
            'fade_in_ms':number(interpretation,'淡入毫秒',1400,0,5000),
            'fade_out_ms':number(interpretation,'淡出毫秒',4000,0,10000)}}
    return config


def display_events(events,config):
    """Apply reading lifetime without moving source/music boundaries in the JSON."""
    policy=config.get('caption_presentation',{}).get('analysis',{})
    if not policy.get('enabled'):return events
    merged=[]
    for event in sorted(events,key=lambda e:(e['slot'],e['output_start'])):
        e=copy.deepcopy(event)
        if (merged and e['slot'] in SLOTS.values() and e.get('phase')!='intro'
                and all(merged[-1].get(k)==e.get(k) for k in ('slot','text','display_title','render_style'))
                and abs(merged[-1]['output_end']-e['output_start'])<.011):
            merged[-1]['output_end']=e['output_end']
        else:merged.append(e)
    for e in merged:
        if e['slot'] not in SLOTS.values() or e.get('phase')=='intro':continue
        reading=len(''.join(e['text'].split()))/policy['characters_per_second']
        lifetime=max(reading+policy['hold_seconds'],policy['minimum_seconds'])
        e['output_end']=min(e['output_end'],e['output_start']+lifetime)
    return merged
