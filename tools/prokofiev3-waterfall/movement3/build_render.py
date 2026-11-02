"""Build the complete third-movement visual timeline from the reviewed alignment.

All scene choices and audio-reactive density envelopes live here.  The audio
clock and note releases remain in alignment.json, so a visual revision never
recomputes separation or changes the music geometry.
"""
from __future__ import annotations

from copy import deepcopy
import json
import os
from pathlib import Path

import numpy as np
from scipy.io import wavfile

HERE = Path(__file__).resolve().parent
SOURCE_LOOK = HERE.parent / 'movement1/prokofiev3-opening180.timeline.json'
ALIGNED = HERE / 'alignment-performance-reviewed.json'
BACKDROP_REVIEW = HERE / 'backdrop-review.json'
OUTPUT = HERE / 'prokofiev3-movement3-full.timeline.json'
VIDEO_DURATION = 628.0
LEAD_IN = 5.0
MAX_SUPPORT_VISUAL_SECONDS = 2.0

# These new plates deliberately stay at the edges.  Most of the score is shown
# against black; the images fade in only at a few structural arrivals.
SCENES = [
    # start, transition, name, low piano, high piano, melody, chords,
    # keyboard, material, particle character, density, filament, note glow
    (0,   0, 'Bassoon opening', '#ccbaab', '#a4b8c6', '#d6bd9d', '#aab3bb', '#b6aa9e', 'glass',   'spark', .78, .67, 1.07),
    (20, 12, 'Piano enters', '#e3bb82', '#a9cad8', '#d7c6a0', '#b9b4a9', '#b5b1ad', 'metal',   'spark', .97, .85, 1.14),
    (57, 12, 'Impetuous runs', '#e9bc7a', '#9ad3d3', '#d7c3a0', '#b9b4b2', '#aaaeb0', 'crystal', 'spark', 1.17, 1.05, 1.23),
    (99, 15, 'Crossed accents', '#e2ac87', '#9dbfda', '#e4b48c', '#b9a7aa', '#b3a9ad', 'metal',   'spark', 1.11, 1.10, 1.19),
    (123, 10, 'First bright crest', '#f1c987', '#a9d5d7', '#eacb9d', '#c2b1a3', '#c4b5a4', 'gilded', 'spark', 1.42, 1.35, 1.34),
    (145, 10, 'Clearing air', '#c8c5ba', '#afd0db', '#bed4d8', '#b6b6be', '#aeb5bf', 'glass',   'spark', .79, .72, 1.09),
    (159, 12, 'Lyrical orchestra', '#b5c4cc', '#a9cedd', '#c4d8e4', '#b4b8c8', '#aeb7c1', 'glass',   'smoke', .66, .66, 1.08),
    (207, 14, 'Piano recitative', '#d4c4b4', '#b2c7d6', '#c1cad2', '#b1b6bf', '#b8b4b8', 'glass',   'smoke', .70, .60, 1.09),
    (281, 12, 'Gathering unease', '#bdc2d0', '#a5c4d5', '#bbccdc', '#b8b5c2', '#a8b0c1', 'crystal', 'spark', .82, .88, 1.13),
    (302, 12, 'Piano in shadow', '#d8c1ab', '#a6bbd4', '#c4cbd4', '#abaebc', '#b0b3bb', 'metal',   'smoke', .88, .88, 1.18),
    (345, 15, 'Inner turbulence', '#ddbfa6', '#a5c5d6', '#c5cbd7', '#b2b5bc', '#b1b3b7', 'crystal', 'spark', 1.05, 1.03, 1.22),
    (392, 15, 'Restless current', '#c9c2b5', '#b0cadd', '#bfcdd5', '#b2b9c4', '#aeb7bf', 'glass',   'spark', .81, .92, 1.12),
    (436, 13, 'Orchestra answers', '#e3c6a0', '#a8cbd6', '#dbc5a7', '#bdb8af', '#b6b5b1', 'metal',   'spark', 1.09, 1.08, 1.24),
    (463, 12, 'Broad convergence', '#ebc993', '#a9d4d5', '#e5c9a2', '#c5b9ad', '#c7b8a7', 'gilded', 'spark', 1.33, 1.26, 1.32),
    (491, 15, 'Return to motion', '#dfc49d', '#a8c9d5', '#dfc2a1', '#b6b8bc', '#bcb3ac', 'glass',   'spark', .96, .92, 1.19),
    (521, 10, 'Finale ignition', '#eac583', '#9dd3d9', '#e6c68e', '#bcb6a9', '#bdb5a9', 'crystal', 'spark', 1.31, 1.27, 1.32),
    (558, 13, 'Final struggle', '#e8bb8f', '#a9d3dc', '#e3bd99', '#c1afb0', '#bdb3ae', 'metal',   'spark', 1.29, 1.34, 1.33),
    (586, 11, 'Brilliant drive', '#f2c783', '#a9d5dc', '#eacb97', '#c4b9ae', '#c6b8a6', 'gilded', 'spark', 1.41, 1.45, 1.38),
    (608, 8, 'Closing blaze', '#f2d398', '#bedde0', '#edd2a6', '#c9bdb3', '#cfbaa7', 'gilded', 'spark', 1.58, 1.48, 1.42),
    (619, 3, 'Room decay', '#cbbfb4', '#a9c5d0', '#cbbfb4', '#b8b8bb', '#b9b6b4', 'glass',   'smoke', .72, .55, 1.12),
]


def audio_rms(path: Path) -> list[tuple[float, float]]:
    rate, audio = wavfile.read(path, mmap=True)
    result=[]
    for t in range(0, 625, 5):
        sample=audio[int(t*rate):int((t+5)*rate):20].astype(np.float32)
        if audio.dtype==np.int16: sample /= 32768
        result.append((float(t), float(np.sqrt(np.mean(sample*sample))) if len(sample) else 0))
    return result


def scene_at(t):
    return max((scene for scene in SCENES if scene[0]<=t), key=lambda x:x[0])


def look(base, scene, amp):
    (_, _, _, low, high, lead, chord, keyboard, material, particle,
     density_scale, filament_scale, glow)=scene
    out=deepcopy(base)
    out['colors'].update(piano_low=low,piano_high=high,strike=low)
    app=out['appearance']
    app.update(material=material,material_amount=1.17,material_speed=.58,
               keyboard_tint=keyboard,horizon_tint=low,
               orchestra_lead_color=lead,orchestra_chord_color=chord,
               orchestra_neutral_color='#aeb9c0',
               orchestra_base_alpha=.34,orchestra_lead_alpha=.91,
               orchestra_emitter_scale=.64,
               particle_style='crystal' if particle=='smoke' else particle,
               particle_life_scale=.94 if amp>1.2 else 1.08,
               background_tint='#17222f',background_atmosphere=.12,
               keyboard_crystal_amount=.030 if material=='crystal' else .012,
               keyboard_metal_amount=.040 if material=='metal' else .015,
               keyboard_ember_amount=.016 if material=='gilded' else 0,
               refracted_veil=.025,background_dust=.06)
    out['brightness'].update(note_glow=glow,note_material=1.08,
                             strike_flash=1.05+min(.20,max(0,amp-1)*.30),
                             filament=1.13)
    d=out['density']
    for key in ('ember_per_second','streak_per_second','smoke_per_second',
                'light_per_second','glint_per_second'):
        d[key]=round(base['density'][key]*density_scale*amp,4)
    d['ember_attack_count']=round(base['density']['ember_attack_count']*
                                  density_scale*(.85+.15*amp))
    d['filament_attack_count']=2 if amp>1.16 else 1
    d['filament_per_second']=round(max(.18,base['density']['filament_per_second']*3.2)
                                   *filament_scale*amp,4)
    motion=out['motion']
    speed=.88 if particle=='smoke' else 1.00
    motion['flight_speed_scale']=round(base['motion']['flight_speed_scale']*speed,4)
    motion['launch_speed_scale']=round(base['motion']['launch_speed_scale']*speed,4)
    motion['horizontal_wind_scale']=round(base['motion']['horizontal_wind_scale']*
                                          (1.1 if particle=='smoke' else 1.02),4)
    return out


def backdrop(t,a=0,b=0):
    return dict(time=t,plate_a=a,plate_b=b,plate_c=0,plate_d=0,plate_e=0,
                backdrop_light_tint='#d7c6b2',backdrop_second_tint='#a8bdcc')


def reviewed_backdrops():
    """Convert user-reviewed video times to the renderer's recording clock."""
    plan=json.loads(BACKDROP_REVIEW.read_text())
    if plan['title_lead_seconds']!=LEAD_IN:
        raise ValueError('Backdrop/video lead-in mismatch')
    keyframes={0:{'A':0.0,'B':0.0}}
    for cue in plan['cues']:
        plate=cue['plate']
        for frame in cue['keyframes']:
            t=frame['time']-LEAD_IN
            keyframes.setdefault(t,{'A':0.0,'B':0.0})[plate]=(
                frame['opacity']*plan['maximum_blend'][plate])
    return [backdrop(t,a=value['A'],b=value['B'])
            for t,value in sorted(keyframes.items())]


def build():
    base=json.loads(SOURCE_LOOK.read_text())
    alignment=json.loads(ALIGNED.read_text())
    # Very long, low-opacity support bars read as vertical guide tracks once a
    # picture is behind them. Keep the full score/alignment in its source JSON;
    # omit only these background bars from the visual timeline. Foreground
    # orchestral melody and chords retain their true lengths and key lights.
    notes=[deepcopy(note) for note in alignment['notes']
           if not (note['family'] != 'piano' and
                   note.get('visual_role') == 'support' and
                   note['audio_end'] - note['audio_start'] >=
                   MAX_SUPPORT_VISUAL_SECONDS)]
    for note in notes:
        if note['family']=='piano':continue
        if note.get('visual_role')=='lead':
            chord=note['musical_role']=='orchestra_chord'
            note['accent_emitter_scale']=.52 if chord else .76
            note['accent_filament_attack_count']=1 if chord else 2
            note['accent_filament_per_second']=.58 if chord else 1.05
            note['accent_light_per_second']=.85 if chord else 1.28
        else:
            note['accent_emitter_scale']=0
    # The quiet opening bassoon theme is foreground even before the piano's
    # first note; these pixels and their pressed keys use recorded note times.
    audio=Path(os.environ.get('PROK3_M3_AUDIO_PATH', alignment['sources']['audio']['path']))
    if not audio.is_absolute():
        audio=HERE/audio
    levels=audio_rms(audio)
    base_look=base['visual_sections'][0]['preset']
    sections=[]
    for index,scene in enumerate(SCENES):
        t=scene[0]
        next_time=SCENES[index+1][0] if index+1<len(SCENES) else 624
        scene_levels=[value for at,value in levels if t<=at<next_time]
        rms=float(np.median(scene_levels)) if scene_levels else \
            min(levels,key=lambda x:abs(x[0]-t))[1]
        ratio=max(.68,min(1.38,(rms/.085)**.30))
        sections.append(dict(name=scene[2],start_seconds=t,
                             end_seconds=VIDEO_DURATION,
                             transition_seconds=scene[1],
                             preset=look(base_look,scene,ratio)))
    timeline={
        'format_version':base['format_version'],
        'title':'Prokofiev Piano Concerto No. 3 — movement III',
        'orchestra_pressed_keys':True,
        'sources':alignment['sources'],
        'render_interval':dict(start_seconds=0,duration_seconds=VIDEO_DURATION,
                               lookahead_seconds=5),
        'intro':dict(lead_in_seconds=LEAD_IN,title='PIANO CONCERTO',
                     subtitle='NO. 3 IN C MAJOR  ·  OP. 26  ·  III. ALLEGRO MOLTO',
                     composer='PROKOFIEV',
                     credit='LANG LANG  ·  SIR SIMON RATTLE  ·  BERLINER PHILHARMONIKER',
                     title_fade_in_seconds=.85,title_fade_out_start_seconds=3.35,
                     title_fade_out_end_seconds=5.55,
                     keyboard_fade_start_seconds=4.25,
                     keyboard_fade_end_seconds=6.5),
        'outro':dict(fade_start_seconds=619.8,fade_end_seconds=623.0),
        'visual_sections':sections,
        'backdrop_asset_set':'prokofiev3_movement3',
        'backdrop_sections':reviewed_backdrops(),
        'backdrop_cues':[
            dict(time=123.4,attack=.18,decay=1.8,strength=.16,
                 x=.13,y=.26,radius=.22,color='#e3c28d'),
            dict(time=463.0,attack=.24,decay=1.8,strength=.13,
                 x=.88,y=.22,radius=.24,color='#d8bf9d'),
            dict(time=608.1,attack=.18,decay=2.1,strength=.18,
                 x=.12,y=.28,radius=.23,color='#ecd7aa'),
        ],
        'upward_motes':[
            dict(start=211,end=281,family='piano',color='#b6d0df',count=3),
            dict(start=392,end=434,family='piano',color='#b9cfdd',count=3),
        ],
        'notes':notes,
    }
    OUTPUT.write_text(json.dumps(timeline,ensure_ascii=False,separators=(',',':')))
    print(f'{OUTPUT}: {len(notes)} notes, {len(sections)} visual sections')


if __name__=='__main__':build()
