"""Extract the 419-bar third movement with a shared orchestral bar clock.

The source MXL holds all three movements. Its piano part is overfilled in
bars 200–231 while the orchestra remains in 3/4; normalize that part's local
positions to the shared bar boundaries before score/audio synchronization.
"""
from __future__ import annotations

from collections import Counter
from hashlib import sha256
import json
import os
from pathlib import Path
from zipfile import ZipFile
from xml.etree import ElementTree as ET

HERE = Path(__file__).resolve().parent
SOURCE = Path(os.environ.get('PROK3_M3_SCORE_PATH', str(HERE / 'inputs/score.mxl')))
AUDIO = Path(os.environ.get('PROK3_M3_AUDIO_PATH', str(HERE / 'inputs/audio.wav')))
FIRST_GLOBAL_BAR = 496
LAST_GLOBAL_BAR = 914
PART_FAMILY = {
    'P1':'woodwind','P2':'woodwind','P3':'woodwind','P4':'woodwind',
    'P5':'woodwind','P6':'brass','P7':'brass','P8':'brass',
    'P14':'piano','P15':'strings','P16':'strings','P17':'strings',
    'P18':'strings','P19':'strings',
}
STEPS = {'C':0,'D':2,'E':4,'F':5,'G':7,'A':9,'B':11}


def digest(path):
    h=sha256()
    with path.open('rb') as stream:
        for block in iter(lambda:stream.read(1<<20),b''):h.update(block)
    return h.hexdigest()


def measure_cursor(measure):
    cursor=maximum=0
    for item in measure:
        if item.tag=='backup':cursor-=int(item.findtext('duration','0'))
        elif item.tag=='forward':
            cursor+=int(item.findtext('duration','0'));maximum=max(maximum,cursor)
        elif item.tag=='note' and item.find('chord') is None:
            cursor+=int(item.findtext('duration','0'));maximum=max(maximum,cursor)
    return maximum


def merge_ties(events):
    active={};kept=[]
    for event in sorted(events,key=lambda e:(e['start_beat'],e['part_id'],e['midi_pitch'])):
        key=(event['part_id'],event['midi_pitch'],event['voice'])
        prior=active.get(key)
        if event['tie_stop'] and prior and abs(prior['end_beat']-event['start_beat'])<.03:
            prior['end_beat']=event['end_beat']
            prior['tie_merged']+=1
            if not event['tie_start']:active.pop(key,None)
        else:
            kept.append(event)
            if event['tie_start']:active[key]=event
    return sorted(kept,key=lambda e:(e['start_beat'],e['part_id'],e['midi_pitch']))


def build():
    with ZipFile(SOURCE) as archive:
        root=ET.fromstring(archive.read('score.xml'))
    names={p.get('id'):p.findtext('part-name') for p in root.findall('./part-list/score-part')}
    parts={part.get('id'):part.findall('measure') for part in root.findall('./part')}
    reference=parts['P1']
    if len(reference)!=LAST_GLOBAL_BAR or reference[FIRST_GLOBAL_BAR-1].get('number')!='1':
        raise ValueError('Third-movement boundary changed')
    bar_starts=[];bar_lengths=[];tempi=[];beat=0.;divisions=480
    for global_number in range(FIRST_GLOBAL_BAR,LAST_GLOBAL_BAR+1):
        measure=reference[global_number-1]
        attrs=measure.find('attributes')
        if attrs is not None and attrs.findtext('divisions'):
            divisions=int(attrs.findtext('divisions'))
        duration=measure_cursor(measure)/divisions
        if not 2.9<=duration<=4.1:raise ValueError((global_number,duration))
        bar_starts.append(round(beat,7));bar_lengths.append(round(duration,7))
        for sound in measure.findall('.//sound'):
            if sound.get('tempo'):
                item=(round(beat,7),float(sound.get('tempo')),global_number-FIRST_GLOBAL_BAR+1)
                if not tempi or item[:2]!=tempi[-1][:2]:tempi.append(item)
        beat+=duration
    events=[];normalized=[];index=0
    for part_id,measures in parts.items():
        if part_id not in PART_FAMILY:continue
        divisions=480;transpose=0
        for global_number,measure in enumerate(measures,1):
            attrs=measure.find('attributes')
            if attrs is not None:
                if attrs.findtext('divisions'):divisions=int(attrs.findtext('divisions'))
                setting=attrs.find('transpose')
                if setting is not None:
                    transpose=(int(setting.findtext('chromatic','0'))+
                               12*int(setting.findtext('octave-change','0')))
            if global_number<FIRST_GLOBAL_BAR:continue
            if global_number>LAST_GLOBAL_BAR:break
            movement_bar=global_number-FIRST_GLOBAL_BAR+1
            source_duration=measure_cursor(measure)/divisions
            target_duration=bar_lengths[movement_bar-1]
            if source_duration<=0:raise ValueError((global_number,part_id,'empty measure'))
            scale=target_duration/source_duration
            if abs(scale-1)>.02:
                normalized.append({'measure':movement_bar,'part_id':part_id,
                                   'source_beats':round(source_duration,5),
                                   'shared_beats':target_duration,
                                   'scale':round(scale,6)})
            cursor=last_onset=0
            for item in measure:
                if item.tag=='backup':cursor-=int(item.findtext('duration','0'))
                elif item.tag=='forward':cursor+=int(item.findtext('duration','0'))
                elif item.tag=='note':
                    length=int(item.findtext('duration','0'))
                    if item.find('chord') is None:last_onset=cursor
                    pitch=item.find('pitch')
                    if (pitch is not None and item.findtext('notehead')!='none'
                            and item.get('print-object')!='no'):
                        midi=(12*(int(pitch.findtext('octave'))+1)
                              +STEPS[pitch.findtext('step')]
                              +int(pitch.findtext('alter','0'))+transpose)
                        if 21<=midi<=108 and length>0:
                            start=bar_starts[movement_bar-1]+last_onset/divisions*scale
                            end=start+length/divisions*scale
                            events.append({
                                'score_id':f'p3iii-m{movement_bar}-{part_id}-{index}',
                                'part_id':part_id,'part_name':names[part_id],
                                'family':PART_FAMILY[part_id],
                                'measure':movement_bar,'midi_pitch':midi,
                                'start_beat':round(start,7),'end_beat':round(end,7),
                                'voice':item.findtext('voice','1'),
                                'staff':item.findtext('staff','1'),
                                'tie_start':any(x.get('type')=='start' for x in item.findall('tie')),
                                'tie_stop':any(x.get('type')=='stop' for x in item.findall('tie')),
                                'tie_merged':0,
                            })
                            index+=1
                    if item.find('chord') is None:cursor+=length
    events=merge_ties(events)
    if len(bar_starts)!=419 or abs(beat-1287)>.01:raise ValueError((len(bar_starts),beat))
    record={
        'source_score':str(SOURCE),'source_score_sha256':digest(SOURCE),
        'source_audio':str(AUDIO),'source_audio_sha256':digest(AUDIO),
        'third_movement_global_bars':[FIRST_GLOBAL_BAR,LAST_GLOBAL_BAR],
        'bar_starts':bar_starts,'bar_lengths':bar_lengths,'total_beats':round(beat,7),
        'tempo_markings':tempi,'normalized_part_measures':normalized,
        'notes':events,
    }
    output=HERE/'score-events.json'
    output.write_text(json.dumps(record,ensure_ascii=False,separators=(',',':')))
    print(json.dumps({'score':str(output),'notes':len(events),'piano':sum(e['part_id']=='P14' for e in events),
                      'meter':Counter(bar_lengths),'tempo':tempi,
                      'normalized_measures':len(normalized),'tied_notes':sum(e['tie_merged'] for e in events)},
                     ensure_ascii=False,default=str,indent=2))


if __name__=='__main__':build()
