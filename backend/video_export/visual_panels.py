"""Portable panel settings and symbolic activity projection; no analysis runtime."""
from bisect import bisect_right
from collections import Counter
from fractions import Fraction as F
from pathlib import Path
import copy,json,math,re
from .paths import configured_path

ROOT=Path(__file__).resolve().parents[2]
SETTINGS=configured_path('visual_panel_settings')
DEFAULTS={'flow':{'enabled':True,'scale':1.0},'orchestration':{'enabled':True,'scale':1.0},
    'color_mode':'part','part_colors':{},'group_colors':{},'sample_start':615.0}

def validate_settings(value):
    result=copy.deepcopy(DEFAULTS)
    for name in ('flow','orchestration'):
        result[name].update(value.get(name,{}));row=result[name]
        if not isinstance(row['enabled'],bool):raise ValueError('面板显示开关须为是或否')
        scale=row['scale']
        if isinstance(scale,bool) or not isinstance(scale,(int,float)) or not math.isfinite(scale) or not .6<=scale<=1.5:
            raise ValueError('面板整体大小须为60%至150%')
    if not any(result[k]['enabled'] for k in ('flow','orchestration')):raise ValueError('请至少显示一个面板')
    result['color_mode']=value.get('color_mode','part')
    if result['color_mode'] not in ('family','part'):raise ValueError('未知分色方式')
    result['color_mode']='part'  # Orchestration stays per instrument; flow grouping is edition metadata.
    result['part_colors']=dict(value.get('part_colors',{}))
    result['group_colors']=dict(value.get('group_colors',{}))
    result['sample_start']=value.get('sample_start',615.0)
    if result['sample_start'] not in (91.4,615.0):raise ValueError('请选择抒情或全奏核查片段')
    if any(not re.fullmatch(r'#[0-9a-fA-F]{6}',c) for c in [*result['part_colors'].values(),*result['group_colors'].values()]):raise ValueError('颜色须为六位色值')
    return result

def load_settings(path=SETTINGS):
    return validate_settings(json.loads(path.read_text(encoding='utf8')) if path.exists() else {})

def save_settings(value,path=SETTINGS):
    value=validate_settings(value);path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_suffix('.tmp');temp.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf8');temp.replace(path)
    return value

def family_for(name):
    name=name.lower()
    for family,words in [('木管',['flut','flaut','oboe','oboi','clar','fagott','bassoon','piccolo','english horn']),
        ('铜管',['tromb','trump','corni','horn','tuba']),('打击乐',['timpan','tamb','piatti','cassa','drum','cymbal','percussion']),
        ('弦乐',['violin','viola','viole','cello','violoncell','contrabass','double bass']),
        ('键盘／拨弦',['piano','harp','arpa','celesta','keyboard'])]:
        if any(w in name for w in words):return family
    return '其他'

def part_registry(parts,solo_ids=(),labels=None,colors=None):
    """Solo identity is explicit; orchestral first violins are never inferred solo."""
    labels=labels or {};colors=colors or {};result=[]
    # Interleave well-separated positions in a broad warm-to-cool gradient.
    # Adjacent modules remain easier to distinguish than sequential near-yellows.
    positions=[];remaining=set(range(len(parts)))
    if remaining:positions.append((len(parts)-1)//2);remaining.remove(positions[0])
    while remaining:
        selected=max(remaining,key=lambda i:(min(abs(i-j) for j in positions),-i))
        positions.append(selected);remaining.remove(selected)
    for index,part in enumerate(parts):
        pid=part['id'];family=part.get('family') or family_for(part['name']);solo=pid in solo_ids or part.get('role')=='solo'
        # A shared part-indexed gradient, centred on subtitle yellow; no piano
        # category is required for a concerto, quartet or other instrumentation.
        position=positions[index]/max(1,len(parts)-1) if len(parts)>1 else .5
        low,high,mix=('#F27943','#FFDF42',position*2) if position<=.5 else ('#FFDF42','#77CBB1',(position-.5)*2)
        tone='#'+''.join(f'{round(int(low[i:i+2],16)*(1-mix)+int(high[i:i+2],16)*mix):02X}' for i in (1,3,5))
        result.append({'id':pid,'label':labels.get(pid,part.get('label') or part['name']),
            'family':family,'role':'solo' if solo else part.get('role','ensemble'),
            'color':colors.get(pid,tone),'flow_group':pid})
    return result

def panel_layout(value,width=1920,height=1080,parts=None,flow_groups=None):
    value=validate_settings(value);panels={}
    groups=Counter(('独奏' if p.get('role')=='solo' else p.get('family','其他')) for p in parts or [])
    panel_height=65+43*sum(math.ceil(count/5) for count in groups.values()) if parts else 280
    flow_count=len(flow_groups) if flow_groups is not None else len(parts or [])
    flow_height=240 if flow_count<=5 else 252+16*math.ceil(flow_count/5)
    for name,(base_w,base_h) in {'flow':(400,flow_height),'orchestration':(520,panel_height)}.items():
        row=value[name]
        if not row['enabled']:continue
        w,h=round(base_w*row['scale']),round(base_h*row['scale'])
        if w>width-48 or h>height-48:raise ValueError('声部较多，面板超出画面；请减小整体大小')
        panels[name]={'x':24 if name=='flow' else width-24-w,'y':24,'width':w,'height':h}
    x=min(p['x'] for p in panels.values());y=min(p['y'] for p in panels.values())
    return {'panels':panels,'overlay_x':x,'overlay_y':y,
        'width':max(p['x']+p['width'] for p in panels.values())-x,
        'height':max(p['y']+p['height'] for p in panels.values())-y}

def recording_time(points,q):
    x=float(F(q))*.5;xs=[p['midi_seconds'] for p in points];i=bisect_right(xs,x)-1
    if i<0 or x>xs[-1]+1e-8:raise ValueError('音符超出录音映射范围')
    if i==len(xs)-1:return points[-1]['audio_seconds']
    a,b=points[i],points[i+1]
    return a['audio_seconds']+(x-a['midi_seconds'])/(b['midi_seconds']-a['midi_seconds'])*(b['audio_seconds']-a['audio_seconds'])

def activity_payload(flow,evidence,reference,alignment,parts,start,end):
    events=[{**n,'kind':'note'} for n in flow['notes'] if n['end_seconds']>start-.3 and n['start_seconds']<end+.3]
    pending={}
    for m in evidence['measures'].values():
        for e in m['events']:
            if e['kind']!='unpitched':continue
            a=recording_time(alignment['time_map'],e['score_start_q']);b=recording_time(alignment['time_map'],e['score_end_q'])
            key=(e['part_id'],e['staff'],e['voice']);previous=pending.pop(key,None)
            if 'stop' in e.get('tie',[]) and previous and abs(previous['end_seconds']-a)<1e-7:
                previous['end_seconds']=b;previous['event_ids'].append(e['id']);row=previous
            else:
                row={'id':e['id'],'event_ids':[e['id']],'part_id':e['part_id'],'kind':'unpitched',
                    'start_seconds':a,'end_seconds':b};events.append(row)
            if 'start' in e.get('tie',[]):pending[key]=row
    events=[e for e in events if e['end_seconds']>start-.3 and e['start_seconds']<end+.3]
    unknown=[]
    for sequence in reference['quarantine']['sequences']:
        m=reference['measures'][sequence-1]
        unknown.append({'part_id':reference['quarantine']['piano_part'],
            'start_seconds':recording_time(alignment['time_map'],m['start_q']),
            'end_seconds':recording_time(alignment['time_map'],m['end_q'])})
    return {'parts':parts,'events':events,'unknown_intervals':unknown,'coverage':flow['coverage'],
        'activity_basis':'source XML notated intervals projected through the same recording DTW; no acoustic source separation'}
