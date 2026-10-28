"""Op.96 source-bound repeat-aware synchronization, using the supplied edition.

Processing only. Does not upload or encode video. Playback uses saved JSON.
"""
from collections import Counter, defaultdict
from fractions import Fraction as F
from pathlib import Path
import argparse, json, os, sys, time

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT/'scripts')]
os.environ.setdefault('NUMBA_CACHE_DIR', str(ROOT/'.tools/numba-cache'))
os.environ.setdefault('MPLCONFIGDIR', str(ROOT/'.tools/matplotlib'))
os.environ.setdefault('MPLBACKEND', 'Agg')
from prokofiev2_sync import read, write, digest, record

WORK = ROOT/'works/dvorak-american'
BASE = ROOT/'resource/American'
CACHE = ROOT/'.tools/dvorak-american-sync'
SOURCE = next(BASE.glob('*.mxl'))
PDF = next(BASE.glob('*.pdf'))
LABELS = {'P1':'第一小提琴', 'P2':'第二小提琴', 'P3':'中提琴', 'P4':'大提琴'}
TITLES = ['第一乐章 · Allegro ma non troppo', '第二乐章 · Lento',
          '第三乐章 · Molto vivace', '第四乐章 · Finale']


def log(message):
    print(time.strftime('%H:%M:%S'), message, flush=True)


def reference(repeat=True):
    import mido
    index = read(WORK/'analysis/measure-index.json')
    raw = read(WORK/'analysis/musicxml/events.json')
    if index['source']['sha256'] != digest(SOURCE) or raw['source']['sha256'] != digest(SOURCE):
        raise ValueError('Research source changed')
    rows = index['measures']; by_seq = defaultdict(list)
    for e in raw['events']:
        if e['eligible']: by_seq[e['sequence']].append(e)
    routes = [list(range(1,64)) + (list(range(3,64)) if repeat else []) + list(range(64,179)),
              list(range(179,276)), list(range(276,472)) + list(range(276,324)), list(range(472,854))]
    measures, notes, texture, movements, issues = [], [], [], [], []
    visits = Counter(); q = F(0)
    for n, route in enumerate(routes,1):
        q0=q; first=len(measures)+1
        for seq in route:
            r=rows[seq-1]; length=F(next(iter(r['part_extents_q'].values())))
            if not r['extent_agreement'] or length <= 0: raise ValueError('Unresolved local timing')
            visits[seq]+=1; occurrence=len(measures)+1; mid=f'visit-{occurrence:04d}'
            m={'measure_id':mid,'source_measure_id':r['measure_id'],'sequence_index':occurrence,
               'source_sequence':seq,'movement':n,'local_number':r['local_number'],'visit':visits[seq],
               'start_q':str(q),'end_q':str(q+length),'duration_q':str(length),
               'layout_page':r['xml_layout_page'],'layout_system':r['xml_layout_system'],
               'time_signature':f"{r['meter']['beats']}/{r['meter']['beat-type']}",
               'timing_review':'explicit_all_part_extent_agreement'}
            measures.append(m)
            source_notes=by_seq[seq]
            for pid in LABELS:
                es=sorted([e for e in source_notes if e['part_id']==pid],key=lambda e:(F(e['onset_q']),e['id']))
                used=set()
                for i,e in enumerate(es):
                    if e['id'] in used: continue
                    a=F(e['onset_q']); b=a+F(e['duration_q']);
                    start_trem=next((t for t in e.get('tremolo',[]) if t.get('type')=='start'),None)
                    single=next((t for t in e.get('tremolo',[]) if t.get('type')=='single'),None)
                    pair=None
                    if start_trem:
                        pair=next((t for t in es[i+1:] if t['voice']==e['voice'] and t['staff']==e['staff']
                                   and F(t['onset_q'])==b and any(x.get('type')=='stop' for x in t.get('tremolo',[]))),None)
                    source_ids=[e['id']]+([pair['id']] if pair else [])
                    if pair:
                        used.add(pair['id']); b=F(pair['onset_q'])+F(pair['duration_q'])
                    if b>length: raise ValueError('Source event crosses explicit bar extent')
                    original={**e,'id':f'{mid}:{e["id"]}','source_event_ids':source_ids,
                              'measure_id':mid,'source_measure_id':r['measure_id'],'source_sequence':seq,
                              'movement':n,'visit':visits[seq],'label':LABELS[pid],
                              'start_q':str(q+a),'end_q':str(q+b),'ps':float(F(e['concert_ps'])),
                              'kind':'note','analysis_eligible':True,'tie':e.get('ties',[])}
                    pitches=[float(F(e['concert_ps']))]+([float(F(pair['concert_ps']))] if pair else [])
                    for j,pitch in enumerate(dict.fromkeys(pitches)):
                        candidate=e if j==0 else pair
                        texture.append({**original,'id':original['id']+(f':alt{j}' if pair else ''),
                                        'ps':pitch,'concert_pitch':candidate['concert_pitch'],
                                        'tremolo_alternatives':bool(pair),'notation_activity':True,
                                        'tie':[] if pair or single else original['tie']})
                    if start_trem and not pair: issues.append({'event_id':e['id'],'kind':'unpaired_tremolo_start'})
                    stroke=(start_trem or single or {}).get('strokes')
                    if stroke and str(stroke).isdigit():
                        step=F(1,2**int(stroke)); at=a; attack=0
                        while at<b:
                            pitch=pitches[attack%len(pitches)]
                            notes.append({'pitch':round(pitch),'start_q':str(q+at),
                                          'end_q':str(q+min(at+step,b)),'part_id':pid,
                                          'source_event_ids':source_ids,'measure_id':mid,'movement':n,
                                          'basis':'written_tremolo_subdivision_alignment_only'})
                            at+=step;attack+=1
                    else:
                        notes.append({'pitch':round(pitches[0]),'start_q':str(q+a),'end_q':str(q+b),
                                      'part_id':pid,'source_event_ids':source_ids,'measure_id':mid,'movement':n,
                                      'basis':'written_note_interval'})
            q+=length
        movements.append({'movement':n,'title':TITLES[n-1],'start_q':str(q0),'end_q':str(q),
                          'first_sequence_index':first,'last_sequence_index':len(measures),
                          'first_pdf_page':min(rows[x-1]['xml_layout_page'] for x in route),
                          'last_pdf_page':max(rows[x-1]['xml_layout_page'] for x in route),
                          'source_route':route})
    if issues: raise ValueError('Unpaired source tremolos: '+str(issues[:5]))
    destination=WORK/'sync/reference'/('written-repeat.json' if repeat else 'written-no-repeat.json')
    doc={'work_id':'dvorak-american','source':record(SOURCE),'supplied_midi':record(next(BASE.glob('*.mid'))),
         'parts':[{'id':pid,'name':name} for pid,name in LABELS.items()],
         'measures':measures,'events':texture,'alignment_notes':notes,'movements':movements,
         'quarter_duration':str(q),'first_movement_repeat':repeat,
         'policy':'Explicit source repeat3–63 and movement3 Da Capo1–48; occurrence IDs separate from paper IDs.',
         'tremolo_policy':'Alignment alternates written tremolo subdivision; activity displays alternatives over the shared notated span, not a simultaneous chord.',
         'quarantine':{'sequences':[]},'human_signoff':None}
    write(destination,doc)
    midi=mido.MidiFile(ticks_per_beat=960)
    for channel,pid in enumerate(LABELS):
        tr=mido.MidiTrack();midi.tracks.append(tr)
        tr.append(mido.MetaMessage('track_name',name=pid,time=0))
        if channel==0:tr.append(mido.MetaMessage('set_tempo',tempo=500000,time=0))
        messages=[]
        for note in notes:
            if note['part_id']!=pid:continue
            messages.extend([(round(F(note['start_q'])*960),1,note['pitch']),
                             (round(F(note['end_q'])*960),0,note['pitch'])])
        last=0
        for tick,on,pitch in sorted(messages):
            tr.append(mido.Message('note_on' if on else 'note_off',note=pitch,velocity=80 if on else 0,
                                   channel=channel,time=tick-last));last=tick
        tr.append(mido.MetaMessage('end_of_track',time=max(0,round(q*960)-last)))
    midi.save(destination.with_suffix('.mid'))
    log(f'Reference repeat={repeat}: {len(measures)} visits; {len(notes)} alignment intervals; {q} quarters')


def features():
    import numpy as np,soundfile as sf
    from synctoolbox.feature.pitch import audio_to_pitch_features
    from synctoolbox.feature.pitch_onset import audio_to_pitch_onset_features
    from synctoolbox.feature.utils import estimate_tuning
    from synctoolbox.feature.chroma import pitch_to_chroma,quantize_chroma
    from synctoolbox.feature.dlnco import pitch_onset_features_to_DLNCO
    media=read(WORK/'media-sync.json'); video=ROOT/media['video']['path']
    if digest(video)!=media['video']['sha256']: raise ValueError('Video changed')
    dest=CACHE/f'audio-{media["video"]["sha256"][:16]}.npz'
    if dest.exists():log('Reusing source-bound features');return
    wav=ROOT/media['analysisAudio']['path']
    if digest(wav)!=media['analysisAudio']['sha256']:raise ValueError('Analysis audio changed')
    wave,fs=sf.read(wav,dtype='float32')
    if fs!=22050 or wave.ndim!=1:raise ValueError('Expected prepared mono22050 WAV')
    tuning=int(estimate_tuning(np.concatenate([wave[int(t*fs):int((t+8)*fs)]
        for t in np.linspace(30,len(wave)/fs-40,8)]),fs))
    log(f'Pitch features, tuning={tuning}c')
    p=audio_to_pitch_features(wave,Fs=fs,feature_rate=50,tuning_offset=tuning)
    chroma=quantize_chroma(pitch_to_chroma(p)); del p
    log('Onset features')
    peaks=audio_to_pitch_onset_features(wave,Fs=fs,tuning_offset=tuning)
    onset=pitch_onset_features_to_DLNCO(peaks,feature_sequence_length=chroma.shape[1],feature_rate=50)
    CACHE.mkdir(parents=True,exist_ok=True)
    np.savez_compressed(dest,chroma=chroma,onset=onset,tuning=tuning,video_sha256=media['video']['sha256'])
    log(f'Features saved {chroma.shape}')


def reference_features(doc,n):
    import numpy as np
    from midi_score import symbolic_features
    from synctoolbox.feature.chroma import pitch_to_chroma,quantize_chroma
    from synctoolbox.feature.dlnco import pitch_onset_features_to_DLNCO
    mv=doc['movements'][n-1];q0=F(mv['start_q']);scale=3 if n==2 else 1
    duration=float(F(mv['end_q'])-q0)*.5*scale
    # Numerical preconditioning of the slow movement, not a recording clock:
    # the score remains rational quarters and DTW supplies all local timing.
    notes=[{'pitch':e['pitch'],'start':float(F(e['start_q'])-q0)*.5*scale,
            'duration':float(F(e['end_q'])-F(e['start_q']))*.5*scale,'velocity':80,'is_drum':False}
           for e in doc['alignment_notes'] if e['movement']==n]
    p,peaks,_=symbolic_features(notes,duration,50)
    c=quantize_chroma(pitch_to_chroma(p))
    o=pitch_onset_features_to_DLNCO(peaks,feature_sequence_length=c.shape[1],feature_rate=50)
    return c,o,duration


def locate():
    import numpy as np,librosa
    media=read(WORK/'media-sync.json'); audio=np.load(CACHE/f'audio-{media["video"]["sha256"][:16]}.npz')
    def shrink(v):
        count=v.shape[1]//10
        return v[:,:count*10].reshape(12,count,10).mean(axis=2)
    def norm(v):return v/np.maximum(np.linalg.norm(v,axis=0,keepdims=True),1e-9)
    ac,ao=norm(shrink(audio['chroma'])),norm(shrink(audio['onset']))
    rows=[]
    candidates=[(n,r) for n in range(1,5) for r in ([True,False] if n==1 else [True])]
    for n,repeat in candidates:
        refpath=WORK/'sync/reference'/('written-repeat.json' if repeat else 'written-no-repeat.json')
        doc=read(refpath);c,o,_=reference_features(doc,n)
        cost=np.maximum(0,.7*(1-norm(shrink(c)).T@ac)+.3*(1-norm(shrink(o)).T@ao))
        steps=np.array([[1,1],[1,2],[2,1]])
        log(f'Subsequence locator movement{n} repeat={repeat}: {cost.shape}')
        D,path=librosa.sequence.dtw(C=cost,subseq=True,step_sizes_sigma=steps,weights_mul=steps.sum(axis=1).astype(float))
        path=path[::-1]
        result={'movement':n,'first_movement_repeat':repeat,'start':float(path[0,1]/5),
                'end':float(path[-1,1]/5),'cost':float(D[-1,path[-1,1]]/len(path)),
                'method':'full-video open-end chroma+DLNCO locator5Hz','human_signoff':None}
        rows.append(result);log(str(result))
        np.savez_compressed(CACHE/f'locator-{n}-{repeat}.npz',path=path,rate=5,
                            video_sha256=media['video']['sha256'],reference_sha256=digest(refpath))
        del cost,D,path
    write(CACHE/'locator-candidates.json',rows)


def boundaries():
    import numpy as np,librosa,shutil
    media=read(WORK/'media-sync.json'); video=media['video']
    audio=np.load(CACHE/f'audio-{video["sha256"][:16]}.npz')
    candidates=read(CACHE/'locator-candidates.json')
    # A skipped repeat only matches the second exposition and leaves the opening
    # unmatched. Preserve both costs and choose the score-indicated route that
    # independently covers the opening; never stretch one pass across two.
    repeat=min((r for r in candidates if r['movement']==1),key=lambda r:r['cost'])['first_movement_repeat']
    ref=WORK/'sync/reference'/('written-repeat.json' if repeat else 'written-no-repeat.json')
    doc=read(ref)
    shutil.copyfile(ref,WORK/'sync/reference/written.json')
    shutil.copyfile(ref.with_suffix('.mid'),WORK/'sync/reference/derived.mid')
    def shrink(v):
        count=v.shape[1]//10
        return v[:,:count*10].reshape(12,count,10).mean(axis=2)
    def norm(v):return v/np.maximum(np.linalg.norm(v,axis=0,keepdims=True),1e-9)
    steps=np.array([[1,1],[1,2],[2,1],[1,3],[3,1],[1,4],[4,1]])
    rows=[next(r for r in candidates if r['movement']==n and (n!=1 or r['first_movement_repeat']==repeat)) for n in range(1,5)]
    # Slow movement has a larger ratio than the initial 2:1 search allowed.
    for n in [2]:
        lo,hi=rows[n-2]['end'],rows[n]['start']
        c,o,_=reference_features(doc,n)
        ac=norm(shrink(audio['chroma'][:,round(lo*50):round(hi*50)]))
        ao=norm(shrink(audio['onset'][:,round(lo*50):round(hi*50)]))
        cost=np.maximum(0,.7*(1-norm(shrink(c)).T@ac)+.3*(1-norm(shrink(o)).T@ao))
        D,path=librosa.sequence.dtw(C=cost,subseq=True,step_sizes_sigma=steps,weights_mul=steps.sum(axis=1).astype(float))
        path=path[::-1]
        rows[n-1]={**rows[n-1],'start':lo+float(path[0,1]/5),'end':lo+float(path[-1,1]/5),
                   'method':'order-constrained slow-movement locator, ratios up to4:1',
                   'cost':float(D[-1,path[-1,1]]/len(path))}
        log(str(rows[n-1]))
    checks=[];updated=[]
    for mv,row in zip(doc['movements'],rows):
        n=mv['movement'];c,o,_=reference_features(doc,n)
        ms=[m for m in doc['measures'] if m['movement']==n];found={}
        for kind,group in [('prefix',ms[:12]),('suffix',ms[-12:])]:
            if kind=='prefix':
                lo=max(0,row['start']-45);hi=min(row['end'],row['start']+130)
                if n>1:lo=max(lo,rows[n-2]['end'])
            else:
                lo=max(row['start'],row['end']-100);hi=min(video['duration_seconds'],row['end']+80)
                if n<4:hi=min(hi,rows[n]['start'])
            scale=3 if n==2 else 1
            a=float(F(group[0]['start_q'])-F(mv['start_q']))*.5*scale
            b=float(F(group[-1]['end_q'])-F(mv['start_q']))*.5*scale
            ac=norm(shrink(audio['chroma'][:,round(lo*50):round(hi*50)]))
            ao=norm(shrink(audio['onset'][:,round(lo*50):round(hi*50)]))
            cc=norm(shrink(c[:,round(a*50):round(b*50)]));oo=norm(shrink(o[:,round(a*50):round(b*50)]))
            cost=np.maximum(0,.7*(1-cc.T@ac)+.3*(1-oo.T@ao))
            D,path=librosa.sequence.dtw(C=cost,subseq=True,step_sizes_sigma=steps,weights_mul=steps.sum(axis=1).astype(float))
            path=path[::-1]
            check={'movement':n,'kind':kind,'start':lo+float(path[0,1]/5),'end':lo+float(path[-1,1]/5),
                   'search_window':[lo,hi],'source_local_range':[group[0]['local_number'],group[-1]['local_number']],
                   'cost':float(D[-1,path[-1,1]]/len(path)),'human_signoff':None}
            found[kind]=check;checks.append(check);log(str(check))
        updated.append({**row,'start':found['prefix']['start'],'end':found['suffix']['end'],
                        'boundary_method':'independent prefix/suffix feature checks', 'whole_movement_locator':row})
    if any(b['start']<=a['end'] for a,b in zip(updated,updated[1:])):raise ValueError('Located movements overlap')
    write(CACHE/'boundary-checks.json',{'video_sha256':video['sha256'],'reference_sha256':digest(ref),'checks':checks})
    write(CACHE/'localized.json',updated)


def align():
    import numpy as np
    from synctoolbox.dtw.mrmsdtw import sync_via_mrmsdtw
    from align_recording import reduce_path
    doc=read(WORK/'sync/reference/written.json');media=read(WORK/'media-sync.json')
    review=read(WORK/'sync/boundary-review.json')
    if review['video_sha256']!=media['video']['sha256']:raise ValueError('Boundary source differs')
    audio=np.load(CACHE/f'audio-{media["video"]["sha256"][:16]}.npz')
    maps=[];measures=[]
    params=dict(input_feature_rate=50,step_weights=np.array([1.5,1.5,2.0]),threshold_rec=10**6,verbose=False)
    for mv,row in zip(doc['movements'],review['movements']):
        n=mv['movement'];lo,hi=row['start'],row['end'];scale=3 if n==2 else 1
        c,o,_=reference_features(doc,n);a=audio['chroma'][:,round(lo*50):round(hi*50)]
        ao=audio['onset'][:,round(lo*50):round(hi*50)]
        log(f'MrMsDTW movement{n} {lo}..{hi}, features{a.shape}/{c.shape}')
        path=sync_via_mrmsdtw(f_chroma1=a,f_chroma2=c,f_onset1=ao,f_onset2=o,**params)
        baseline=sync_via_mrmsdtw(f_chroma1=a,f_chroma2=c,**params)
        s,t=reduce_path(path);bs,bt=reduce_path(baseline)
        np.savez_compressed(CACHE/f'refined-{n}.npz',path=path,baseline=baseline,rate=50,offset=lo,
                            video_sha256=media['video']['sha256'],reference_sha256=digest(WORK/'sync/reference/written.json'))
        # Merge a plateau's score indices at their median. Interpolate only
        # between distinct DTW-supported audio positions, not over fake bars.
        def strict(score,actual):
            unique=np.unique(actual)
            score=np.array([np.median(score[actual==v]) for v in unique])
            return score,unique
        s,t=strict(s,t);bs,bt=strict(bs,bt)
        q0=F(mv['start_q']);duration=float(F(mv['end_q'])-q0)*.5
        sx=np.concatenate([[0],s[1:-1]/50/scale,[duration]])
        ty=np.concatenate([[lo],lo+t[1:-1]/50,[hi]])
        # Exact duplicate reference endpoints are removed before interpolation.
        ix=np.flatnonzero(np.r_[True,np.diff(sx)>1e-9]);sx=sx[ix];ty=ty[ix]
        if np.any(np.diff(ty)<=0):raise ValueError('Nonmonotonic recording map')
        keep=list(range(0,len(sx),5))+[len(sx)-1]
        points=[{'midi_seconds':float(q0)*.5+float(sx[i]),'audio_seconds':float(ty[i])} for i in sorted(set(keep))]
        maps.append({'id':f'movement-{n}','movement':n,'start_seconds':lo,'end_seconds':hi,'time_map':points})
        for m in [m for m in doc['measures'] if m['movement']==n]:
            x=float(F(m['start_q'])-q0)*.5;z=float(F(m['end_q'])-q0)*.5
            start=float(np.interp(x,sx,ty));end=float(np.interp(z,sx,ty))
            delta=abs(float(np.interp(x*50*scale,bs,bt)/50+lo)-start)
            flags=[]
            if delta>2:flags.append('feature_variant_disagreement_over_2s')
            if end<=start:raise ValueError('Collapsed occurrence interval')
            if end-start>20:flags.append('long_interval_check_cadenza_or_fermata')
            if m['sequence_index'] in (mv['first_sequence_index'],mv['last_sequence_index']):flags.append('movement_boundary_requires_listening')
            measures.append({**m,'score_start_quarter':float(F(m['start_q'])),'score_end_quarter':float(F(m['end_q'])),
                             'score_start_tick':float(F(m['start_q'])*960),'score_end_tick':float(F(m['end_q'])*960),
                             'midi_start_seconds':float(F(m['start_q']))*.5,'midi_end_seconds':float(F(m['end_q']))*.5,
                             'start_seconds':start,'end_seconds':end,'printed_measure_number':None,
                             'flags':flags,'review_status':'needs_review' if flags else 'unreviewed',
                             'quality_metrics':{'chroma_only_start_disagreement_seconds':delta}})
        log(f'Movement{n} flags '+str(Counter(f for m in measures if m['movement']==n for f in m['flags'])))
    result={'format_version':'1.0.0','status':'repeat_aware_automatic_candidates_agent_boundary_review',
            'audio':media['video'],'analysis_audio':media['analysisAudio'],'playback_clock':'video',
            'symbolic_reference':{**record(WORK/'sync/reference/derived.mid'),'duration_seconds':float(F(doc['quarter_duration']))*.5},
            'algorithm':{'name':'Sync Toolbox MrMsDTW','features':['chroma','DLNCO'],'feature_rate_hz':50,
                         'reference_preconditioning':{'2':3},'reference_clock':'explicit MusicXML quarters at auxiliary0.5s, not performance tempo'},
            'score_time_coverage':{'start_seconds':maps[0]['start_seconds'],'end_seconds':maps[-1]['end_seconds'],
                                   'segments':[{'start_seconds':r['start_seconds'],'end_seconds':r['end_seconds']} for r in maps]},
            'movements':[{**mv,'start_seconds':r['start'],'end_seconds':r['end']} for mv,r in zip(doc['movements'],review['movements'])],
            'measures':measures,'time_maps':maps,'time_map':[p for r in maps for p in r['time_map']],
            'quality':{'flag_counts':dict(Counter(f for m in measures for f in m['flags']))},'human_anchors':[],
            'limitations':['Repeated visits have independent time and shared observed paper geometry.',
                           'Automatic candidates and spectral boundary estimates are not human listening signoff.',
                           'Tremolo matching subdivisions do not certify individual performed attacks.'],
            'human_signoff':None,'expert_review':None}
    write(WORK/'sync/alignment.raw.json',result)


def geometry():
    import pdfplumber
    import pypdfium2 as pdfium
    from PIL import ImageDraw
    source=read(WORK/'analysis/measure-index.json')['measures'];layout=defaultdict(list)
    for m in source:layout[m['xml_layout_page'],m['xml_layout_system']].append(m)
    systems=[];bars=[];issues=[]
    preview=ROOT/'tmp/dvorak-american-sync/geometry';preview.mkdir(parents=True,exist_ok=True)
    def clusters(values,tolerance):
        groups=[]
        for item in sorted(values):
            if groups and item-groups[-1][-1]<=tolerance:groups[-1].append(item)
            else:groups.append([item])
        return groups
    with pdfplumber.open(PDF) as pdf, pdfium.PdfDocument(PDF) as renderer:
        for page_number,p in enumerate(pdf.pages,1):
            horizontal=[l for l in p.lines if l['width']>30 and l['height']<.25]
            ys=[sum(g)/len(g) for g in clusters([round(l['top'],2) for l in horizontal],.3)]
            staffs=[g for g in clusters(ys,4.5) if len(g)==5]
            expected=[(key,ms) for key,ms in layout.items() if key[0]==page_number]
            if len(staffs)!=4*len(expected):
                raise ValueError(f'Page{page_number}: observed staffs {len(staffs)} != expected {4*len(expected)}')
            image=renderer[page_number-1].render(scale=1.5).to_pil().convert('RGB');draw=ImageDraw.Draw(image)
            for i,((_,system_index),ms) in enumerate(expected):
                ss=staffs[i*4:i*4+4];top,bottom=ss[0][0],ss[-1][-1]
                lines=[l for l in horizontal if top-.5<=l['top']<=bottom+.5]
                left=min(l['x0'] for l in lines);right=max(l['x1'] for l in lines)
                vertical=[l for l in p.lines if l['width']<.3 and l['height']>7 and l['bottom']>=top and l['top']<=bottom]
                candidates=[]
                for group in clusters([round(l['x0'],2) for l in vertical],1.2):
                    x=sum(group)/len(group)
                    ranges=sorted((max(top,l['top']),min(bottom,l['bottom'])) for l in vertical
                                  if abs(l['x0']-x)<=1.3 and min(bottom,l['bottom'])>max(top,l['top']))
                    merged=[]
                    for a,b in ranges:
                        if merged and a<=merged[-1][1]+.6:merged[-1][1]=max(merged[-1][1],b)
                        else:merged.append([a,b])
                    coverage=sum(b-a for a,b in merged)/(bottom-top)
                    if coverage>.93 and left-2<=x<=right+2:candidates.append(x)
                xs=[sum(g)/len(g) for g in clusters(candidates,3.1)]
                # The observed staff endpoint is used only for the first/last edge;
                # no internal boundary is inferred from source widths or equal splitting.
                if not xs or xs[0]>left+4:xs.insert(0,left)
                else:xs[0]=left
                next_seq=ms[-1]['sequence']+1
                courtesy=next_seq<=len(source) and source[next_seq-1]['key_signature']!=ms[-1]['key_signature']
                if courtesy and 0<=right-xs[-1]<20:
                    pass  # observed final bar precedes a courtesy key signature
                elif right-xs[-1]<=8:xs[-1]=right  # final double-line/staff-end spacing
                else:xs.append(right)
                count_ok=len(xs)-1==len(ms)
                row={'page_number':page_number,'system_index':system_index,
                     'page_width_pt':p.width,'page_height_pt':p.height,
                     'rect_pt':[left,max(0,top-12),right-left,min(p.height,bottom+12)-max(0,top-12)],
                     'boundaries_pt':xs,'source_sequences':[m['sequence'] for m in ms],
                     'count_agrees':count_ok,'resolution':'system_candidate',
                     'method':'vector_staff_lines_and_connected_vertical_union_across_four_staves',
                     'human_signoff':None}
                systems.append(row)
                if not count_ok:issues.append({'page':page_number,'system':system_index,
                                              'observed_bars':len(xs)-1,'xml_measures':len(ms)})
                for j,m in enumerate(ms):
                    rect=[xs[j],row['rect_pt'][1],xs[j+1]-xs[j],row['rect_pt'][3]] if count_ok else row['rect_pt']
                    bars.append({'source_sequence':m['sequence'],'source_measure_id':m['measure_id'],
                                 'page_number':page_number,'system_index':system_index,
                                 'page_width_pt':p.width,'page_height_pt':p.height,'rect_pt':rect,
                                 'resolution':'bar_candidate' if count_ok else 'shared_system_candidate',
                                 'suppress_playhead':not count_ok,'printed_measure_number':None,
                                 'source_local_number':m['local_number'],'human_signoff':None})
                    x,y,w,h=rect
                    draw.rectangle([x*1.5,y*1.5,(x+w)*1.5,(y+h)*1.5],outline='green' if count_ok else 'red',width=2)
                    draw.text((x*1.5+2,y*1.5+2),m['local_number'],fill='blue')
            image.save(preview/f'{page_number:02}.png')
            log(f'Vector page{page_number}: {len(expected)} systems')
    if sorted(b['source_sequence'] for b in bars)!=list(range(1,854)):raise ValueError('Geometry coverage differs')
    write(WORK/'sync/geometry.raw.json',{'pdf':record(PDF),'source_xml':record(SOURCE),
          'systems':systems,'bars':bars,'issues':issues,'human_signoff':None})
    log(f'Geometry {len(systems)} systems, {len(bars)} source bars, {len(issues)} shared issues')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('stage',choices=['reference','features','locate','boundaries','geometry','align'])
    args=parser.parse_args()
    if args.stage=='reference': reference(True);reference(False)
    elif args.stage=='features':features()
    elif args.stage=='geometry':geometry()
    elif args.stage=='boundaries':boundaries()
    elif args.stage=='align':align()
    else:locate()
