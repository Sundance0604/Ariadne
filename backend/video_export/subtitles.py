"""A single independently editable ASS track, plus text-free score vectors."""
import math,re
from .content import FORBIDDEN,normalized
from .presentation import display_events


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
        if config.get('balanced_caption_wrap'):
            lines.extend(balanced_lines(paragraph,width,size,spacing));continue
        line='';used=0
        for char in paragraph:
            advance=(1 if ord(char)>255 else .65)*size+spacing
            if line and used+advance>width:lines.append(line);line='';used=0
            line+=char;used+=advance
        lines.append(line)
    if len(lines)*size*1.35>box['h']:raise ValueError('Caption exceeds fixed slot; provide a reviewed shorter version')
    return '\n'.join(lines)


def balanced_lines(text,width,size,spacing=0):
    """Keep Latin words whole and rebalance a tiny last line with its neighbour."""
    def extent(value):return sum((1 if ord(c)>255 else .65)*size+spacing for c in value)
    closing='，。！？；：、）》】”’,.!?;:'
    opening='（《【“‘('
    tokens=re.findall(r"[A-Za-z]+(?:['’-][A-Za-z]+)*|[0-9]+(?:\.[0-9]+)?|.",text)
    expanded=[]
    for token in tokens:expanded.extend(list(token) if extent(token)>width else [token])
    lines=[];line=''
    for token in expanded:
        if line and extent(line+token)>width:
            if token[0] in closing or line[-1] in opening:
                tail=re.search(r'[A-Za-z]+$|.$',line)
                if tail and tail.start()>0 and extent(tail[0]+token)<=width:
                    lines.append(line[:tail.start()].rstrip());line=tail[0]+token;continue
            lines.append(line.rstrip());line=''
        line+=token if line else token.lstrip()
    if line or not lines:lines.append(line.rstrip())
    if len(lines)>1 and extent(lines[-1])<min(4*size,width*.4):
        combined=lines[-2]+lines[-1];options=[]
        for i in range(1,len(combined)):
            a,b=combined[:i].rstrip(),combined[i:].lstrip()
            if not a or not b or b[0] in closing or a[-1] in opening:continue
            if combined[i-1].isascii() and combined[i].isascii() and combined[i-1].isalnum() and combined[i].isalnum():continue
            if max(extent(a),extent(b))<=width:options.append((abs(extent(a)-extent(b)),a,b))
        if options:_,lines[-2],lines[-1]=min(options)
    return lines


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


def reading_window(box,size,line_count):
    """Fit complete explicitly positioned rows; never stop on half a row."""
    line_height=size*1.12
    top=box['y']+line_height+8
    padding=max(2,math.ceil(size*.08))
    available=box['y']+box['h']-top
    visible=math.floor((available-2*padding+1e-7)/line_height)
    if visible<1:raise ValueError('字幕区域太矮，标题下须容纳一整行正文及上下留白。')
    return {'top':top,'bottom':box['y']+box['h'],'padding':padding,'line_height':line_height,
        'visible_lines':visible,'initial_y':top+padding,
        'final_y':top+padding-max(0,line_count-visible)*line_height}


def web_analysis_ass(events,config):
    """Large KaiTi captions: fixed labels, full web text, upward reading windows."""
    rows=header(config)
    labels={'harmony':'和声／和弦','orchestration':'配器与织体','counterpoint':'对位','form':'曲式','guide':'导聆','interpretation':'诠释','intro':'作品介绍与诠释'}
    labels.update(config.get('slot_labels',{}))
    interpretations=[(e['output_start'],e['output_end']) for e in events if e['slot']=='interpretation' and e.get('phase')!='intro']
    for e in display_events(events,config):
        name='intro' if e.get('phase')=='intro' else e['slot'];box={**config['layout'][name],**e.get('render_style',{})};size=box.get('font_size',config['font_size'])
        face=box.get('font',config['font'])
        style=f'\\fn{face}\\fs{size}'
        text=e['text']
        if FORBIDDEN.search(normalized(text)):raise ValueError('Research placeholder in video text')
        intervals=[(e['output_start'],e['output_end'])]
        # The larger interpretation occupies the reading space; the guide
        # returns at its original fixed position without changing score geometry.
        if name in config.get('interpretation_suppresses_slots',['guide','form']):
            for a,b in interpretations:
                intervals=[part for start,end in intervals for part in [(start,min(end,a)),(max(start,b),end)] if part[1]>part[0]]
        wrapped=wrap(text,{**box,'h':100000},config);lines=wrapped.splitlines()
        window=reading_window(box,size,len(lines));line_height=window['line_height'];body_y=window['top']
        align=box.get('align','left');anchor=8 if align=='center' else 9 if align=='right' else 7
        x=box['x']+box['w']/2 if align=='center' else box['x']+box['w'] if align=='right' else box['x']
        title=e.get('display_title') or labels[name]
        for start,end in intervals:
            if end<=start:continue
            fade=r'\fad(350,350)' if name=='intro' else ''
            policy=config.get('caption_presentation',{})
            if name in ('harmony','orchestration','counterpoint','form','guide') and policy.get('analysis',{}).get('enabled'):
                p=policy['analysis'];fade=f'\\fad({int(p["fade_in_ms"])},{int(p["fade_out_ms"])})'
            cinematic=policy.get('interpretation',{}) if name=='interpretation' else {}
            if cinematic.get('mode')=='cinematic':
                duration=int((end-start)*1000);speed=box.get('scroll_speed',config.get('scroll_speed',1))
                # All rows travel as a single flat rectangle. The complete last
                # paragraph remains in view until the whole block fades out.
                travel=min(cinematic['travel_px']*speed,max(0,window['bottom']-window['initial_y']-len(lines)*line_height-window['padding']))
                if len(lines)*line_height>window['bottom']-window['initial_y']-window['padding']:
                    raise ValueError('诠释长文超出矩形区域，请增加高度或减小字号。')
                fade=f'\\fad({int(min(cinematic["fade_in_ms"],duration*.2))},{int(min(cinematic["fade_out_ms"],duration*.3))})'
                rows.append(dialogue(start,end,name,f'{{\\an{anchor}{style}\\pos({x},{box["y"]}){fade}}}【{escape(title)}】'))
                clip=f'\\clip({box["x"]},{body_y:.2f},{box["x"]+box["w"]},{box["y"]+box["h"]})'
                for i,line in enumerate(lines):
                    final=window['initial_y']+i*line_height;initial=final+travel
                    move=f'\\move({x},{initial:.2f},{x},{final:.2f},0,{duration})'
                    rows.append(dialogue(start,end,name,f'{{\\an{anchor}{style}{clip}{move}{fade}}}'+escape(line)))
                continue
            rows.append(dialogue(start,end,name,f'{{\\an{anchor}{style}\\pos({x},{box["y"]}){fade}}}【{escape(title)}】'))
            scroll=len(lines)>window['visible_lines']
            clip=f'\\clip({box["x"]},{body_y:.2f},{box["x"]+box["w"]},{box["y"]+box["h"]})'
            if scroll and end-start>=3:
                speed=box.get('scroll_speed',config.get('scroll_speed',1))
                if isinstance(speed,bool) or not isinstance(speed,(int,float)) or not math.isfinite(speed) or not .25<=speed<=4:raise ValueError('Scroll speed must be between 0.25 and 4')
                travel=650+max(100,int(max(.1,end-start-2-.65)*1000/speed))
                if policy.get('analysis',{}).get('enabled'):
                    distance=window['initial_y']-window['final_y']
                    travel=650+int(distance/(policy['analysis']['scroll_pixels_per_second']*speed)*1000)
                travel=int(min(travel,(end-start-1)*1000)//10)*10
                stop=start+travel/1000
                # Separate source lines give ASS an explicit shared row pitch.
                # At rest only the complete tail rows are present: preceding
                # glyphs cannot leave clipped fragments above the first row.
                for i,line in enumerate(lines):
                    initial=window['initial_y']+i*line_height;final=window['final_y']+i*line_height
                    move=f'\\move({x},{initial:.2f},{x},{final:.2f},650,{travel})'
                    entrance=r'\fad(350,0)' if name=='intro' else (f'\\fad({int(policy["analysis"]["fade_in_ms"])},0)' if fade else '')
                    rows.append(dialogue(start,stop,name,f'{{\\an{anchor}{style}{clip}{move}{entrance}}}'+escape(line)))
                held=lines[-window['visible_lines']:]
                hold_fade=r'\fad(0,350)' if name=='intro' else (f'\\fad(0,{int(policy["analysis"]["fade_out_ms"])})' if fade else '')
                for i,line in enumerate(held):
                    y=window['initial_y']+i*line_height
                    rows.append(dialogue(stop,end,name,f'{{\\an{anchor}{style}{clip}\\pos({x},{y:.2f}){hold_fade}}}'+escape(line)))
            else:
                # Fitting captions stay still, even if the slot permits scroll.
                # Brief updates show complete available rows without half-glyphs.
                for i,line in enumerate(lines[:window['visible_lines']]):
                    y=window['initial_y']+i*line_height
                    rows.append(dialogue(start,end,name,f'{{\\an{anchor}{style}{clip}\\pos({x},{y:.2f}){fade}}}'+escape(line)))
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
