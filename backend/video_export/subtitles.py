"""A single independently editable ASS track, plus text-free score vectors."""
import math
from .content import FORBIDDEN,normalized


def stamp(seconds):
    n=max(0,int(math.floor(seconds*100+1e-7)))
    return f'{n//360000}:{n//6000%60:02}:{n//100%60:02}.{n%100:02}'


def color(rgb):
    r,g,b=rgb.lstrip('#')[0:2],rgb.lstrip('#')[2:4],rgb.lstrip('#')[4:6]
    return f'&H00{b}{g}{r}'


def header(config,graphics=False):
    width,height=config['width'],config['height'];font=config['font'];yellow=color(config['yellow'])
    rows=['[Script Info]','ScriptType: v4.00+',f'PlayResX: {width}',f'PlayResY: {height}',
        'ScaledBorderAndShadow: yes','WrapStyle: 2','Collisions: Normal','','[V4+ Styles]',
        'Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding']
    for name,box in config['layout'].items():
        if name=='score':continue
        size=box.get('font_size',config['font_size'])
        bold=-1 if config.get('bold') else 0
        rows.append(f'Style: {name},{box.get("font",font)},{size},{yellow},{yellow},&HFF000000,&HFF000000,{bold},0,0,0,100,100,{config.get("spacing",0)},0,1,0,0,7,0,0,0,1')
    if graphics:rows.append(f'Style: vector,{font},10,{yellow},{yellow},&HFF000000,&HFF000000,0,0,0,0,100,100,0,0,1,0,0,7,0,0,0,1')
    rows+=['','[Events]','Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text']
    return rows


def escape(text):
    # Prevent text from injecting ASS override commands or additional dialogues.
    return text.replace('\\','＼').replace('{','｛').replace('}','｝').replace('\r','').replace('\n',r'\N')


def wrap(text,box,config):
    size=box.get('font_size',config['font_size']);spacing=config.get('spacing',0)
    width=box['w'];lines=[]
    for paragraph in text.splitlines():
        line='';used=0
        for char in paragraph:
            advance=(1 if ord(char)>255 else .65)*size+spacing
            if line and used+advance>width:lines.append(line);line='';used=0
            line+=char;used+=advance
        lines.append(line)
    if len(lines)*size*1.35>box['h']:raise ValueError('Caption exceeds fixed slot; provide a reviewed shorter version')
    return '\n'.join(lines)


def analysis_ass(events,config):
    if config.get('web_video_layout'):return web_analysis_ass(events,config)
    rows=header(config);previous=None;dialogues=[]
    for e in sorted(events,key=lambda e:(e['slot'],e['output_start'])):
        name='intro' if e.get('phase')=='intro' else e['slot'];box=config['layout'][name]
        text=wrap(e['text'],box,config)
        if FORBIDDEN.search(normalized(text)):raise ValueError('Publication text failed final scan')
        start,end=e['output_start'],e['output_end']
        # No entrance animation on regular updates. Only the intro fades.
        fade=r'\fad(400,400)' if name=='intro' else ''
        tags=f'{{\\an7\\q2\\pos({box["x"]},{box["y"]}){fade}}}'
        item=[start,end,name,tags+escape(text)]
        if previous and previous[2:]==item[2:] and abs(previous[1]-start)<.011:previous[1]=end
        else:
            if previous:dialogues.append(previous)
            previous=item
    if previous:dialogues.append(previous)
    rows.extend(dialogue(*d) for d in sorted(dialogues,key=lambda d:(d[0],d[2])))
    return '\n'.join(rows)+'\n'


def web_analysis_ass(events,config):
    """Large KaiTi captions: fixed labels, full web text, upward reading windows."""
    rows=header(config)
    labels={'harmony':'和声／和弦','orchestration':'配器与织体','counterpoint':'对位','form':'曲式','guide':'导聆','interpretation':'诠释','intro':'作品介绍与诠释'}
    labels.update(config.get('slot_labels',{}))
    interpretations=[(e['output_start'],e['output_end']) for e in events if e['slot']=='interpretation' and e.get('phase')!='intro']
    for e in events:
        name='intro' if e.get('phase')=='intro' else e['slot'];box={**config['layout'][name],**e.get('render_style',{})};size=box.get('font_size',config['font_size'])
        face=box.get('font',config['font'])
        style=f'\\fn{face}\\fs{size}'
        text=e['text']
        if FORBIDDEN.search(normalized(text)):raise ValueError('Research placeholder in video text')
        intervals=[(e['output_start'],e['output_end'])]
        # The larger interpretation occupies the reading space; the guide
        # returns at its original fixed position without changing score geometry.
        if name in {'guide','form'}:
            for a,b in interpretations:
                intervals=[part for start,end in intervals for part in [(start,min(end,a)),(max(start,b),end)] if part[1]>part[0]]
        line_height=size*1.12;body_y=box['y']+line_height+8
        body_h=box['h']-line_height-8
        wrapped=wrap(text,{**box,'h':100000},config);lines=wrapped.splitlines()
        align=box.get('align','left');anchor=8 if align=='center' else 9 if align=='right' else 7
        x=box['x']+box['w']/2 if align=='center' else box['x']+box['w'] if align=='right' else box['x']
        title=e.get('display_title') or labels[name]
        for start,end in intervals:
            if end<=start:continue
            fade=r'\fad(350,350)' if name=='intro' else ''
            rows.append(dialogue(start,end,name,f'{{\\an{anchor}{style}\\pos({x},{box["y"]}){fade}}}【{escape(title)}】'))
            height=len(lines)*line_height
            scroll=box.get('scroll') or height>body_h
            clip=f'\\clip({box["x"]},{body_y:.2f},{box["x"]+box["w"]},{box["y"]+box["h"]})'
            if scroll and end-start>=3:
                # Start with several lines already readable. Move upwards,
                # allowing old lines to leave at the top, then pause to read.
                initial=body_y+min(body_h*.32,line_height*2)
                final=body_y-max(line_height*.5,height-body_h+line_height*.5)
                speed=box.get('scroll_speed',config.get('scroll_speed',1))
                if isinstance(speed,bool) or not isinstance(speed,(int,float)) or not math.isfinite(speed) or not .25<=speed<=4:raise ValueError('Scroll speed must be between 0.25 and 4')
                travel=650+max(100,int(max(.1,end-start-2-.65)*1000/speed))
                move=f'\\move({x},{initial:.2f},{x},{final:.2f},650,{travel})'
                tags=f'{{\\an{anchor}{style}{clip}{move}{fade}}}'
            else:tags=f'{{\\an{anchor}{style}{clip}\\pos({x},{body_y:.2f}){fade}}}'
            rows.append(dialogue(start,end,name,tags+escape(wrapped)))
    return '\n'.join(rows)+'\n'


def dialogue(start,end,style,text,layer=10):
    return f'Dialogue: {layer},{stamp(start)},{stamp(end)},{style},,0,0,0,,{text}'


def polygon(w,h):
    return f'm 0 0 l {w:.2f} 0 {w:.2f} {h:.2f} 0 {h:.2f}'


def score_ass(plan,config):
    rows=header(config,True);v=config['layout']['score'];clip=f'\\clip({v["x"]},{v["y"]},{v["x"]+v["w"]},{v["y"]+v["h"]})'
    # Merge static highlights. Keep moving line knots at DTW changes; ASS move
    # interpolates only the positions computed by the existing JS algorithm.
    highlights=[]
    for e in plan['events']:
        r=e.get('highlight')
        if r:
            if highlights and highlights[-1]['rect']==r and abs(highlights[-1]['end']-e['start'])<1e-6:highlights[-1]['end']=e['end']
            else:highlights.append({'start':e['start'],'end':e['end'],'rect':r})
        a,b=e.get('playhead'),e.get('playheadEnd')
        if a and b and stamp(e['start'])!=stamp(e['end']):
            text=f'{{\\an7\\bord0\\shad0{clip}\\1c&H423AD6&\\move({a["x"]:.2f},{a["y"]:.2f},{b["x"]:.2f},{b["y"]:.2f})\\p1}}'+polygon(2,a['height'])
            rows.append(dialogue(e['start'],e['end'],'vector',text,2))
    for e in highlights:
        x,y,w,h=e['rect']
        text=f'{{\\an7\\bord0\\shad0{clip}\\pos({x:.2f},{y:.2f})\\1c&H42DFFF&\\1a&HC0&\\p1}}'+polygon(w,h)
        rows.append(dialogue(e['start'],e['end'],'vector',text,1))
    return '\n'.join(rows)+'\n'
