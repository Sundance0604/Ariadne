"""Prepare the supplied Prokofiev II video for local score review.

Processing dependencies are optional. Original research and source media stay
unchanged; recording time, XML sequence, PDF geometry and printed numbering
have separate evidence. No video export is performed by this module.
"""
from pathlib import Path
from collections import Counter, defaultdict
from fractions import Fraction as F
import argparse, hashlib, json, os, sys, time

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'scripts')]
os.environ.setdefault('NUMBA_CACHE_DIR',str(ROOT/'.tools/numba-cache'))
os.environ.setdefault('MPLCONFIGDIR',str(ROOT/'.tools/matplotlib'))
os.environ.setdefault('MPLBACKEND','Agg')
WORK=ROOT/'works/prokofiev-piano-concerto-2'
BASE=ROOT/'resource/PROKOFIEV PIANO CONCERTO 2'
CACHE=ROOT/'.tools/prokofiev2-sync'
SOURCE=BASE/'piano-concerto-no2-op16-s-prokofiev.mxl'
PDF=BASE/'IMSLP66128-PMLP04521-Prokofiev_-_Piano_Concerto_No._2,_Op._16_(orch._score).pdf'
MOVEMENTS=[(1,1,200,'第一乐章 · Andantino',1,37),
 (2,201,387,'第二乐章 · Scherzo',38,69),
 (3,388,546,'第三乐章 · Intermezzo',70,108),
 (4,547,864,'第四乐章 · Finale',109,168)]

def read(path):return json.loads(path.read_text(encoding='utf8'))
def write(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    pending=path.with_suffix(path.suffix+'.tmp')
    pending.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    pending.replace(path)
def digest(path):
    with path.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()
def record(path):return {'path':path.relative_to(ROOT).as_posix(),'sha256':digest(path),'bytes':path.stat().st_size}
def log(message):print(time.strftime('%H:%M:%S'),message,flush=True)

def features():
    import numpy as np,soundfile as sf
    from synctoolbox.feature.pitch import audio_to_pitch_features
    from synctoolbox.feature.pitch_onset import audio_to_pitch_onset_features
    from synctoolbox.feature.utils import estimate_tuning
    from synctoolbox.feature.chroma import pitch_to_chroma,quantize_chroma
    from synctoolbox.feature.dlnco import pitch_onset_features_to_DLNCO
    media=read(WORK/'media-sync.json');video=ROOT/media['video']['path']
    if digest(video)!=media['video']['sha256']:raise ValueError('Video fingerprint changed')
    destination=CACHE/f"audio-{media['video']['sha256'][:16]}.npz"
    if destination.exists():log('Reusing source-bound audio features');return
    wav=ROOT/media['analysisAudio']['path']
    if digest(wav)!=media['analysisAudio']['sha256']:raise ValueError('Analysis audio changed')
    wave,fs=sf.read(wav,dtype='float32')
    if wave.ndim!=1 or fs!=22050:raise ValueError('Prepare the mono 22050-Hz video audio first')
    tuning=int(estimate_tuning(np.concatenate([wave[int(t*fs):int((t+8)*fs)]
        for t in np.linspace(45,len(wave)/fs-60,8)]),fs))
    log(f'Audio tuning {tuning} cents; extracting pitch features')
    pitch=audio_to_pitch_features(wave,Fs=fs,feature_rate=50,tuning_offset=tuning)
    chroma=quantize_chroma(pitch_to_chroma(pitch));del pitch
    log('Extracting onset features')
    peaks=audio_to_pitch_onset_features(wave,Fs=fs,tuning_offset=tuning)
    onset=pitch_onset_features_to_DLNCO(peaks,feature_sequence_length=chroma.shape[1],feature_rate=50)
    CACHE.mkdir(parents=True,exist_ok=True)
    np.savez_compressed(destination,chroma=chroma,onset=onset,tuning=tuning,video_sha256=media['video']['sha256'])
    log(f'Audio features saved: {chroma.shape}')

def reference():
    """Separate auxiliary written clock; never modifies the local research clock."""
    from backend.musicxml_analysis.ingest import xml_root
    from compare_mother_goose_sources import xml_events
    import mido
    data=xml_events(SOURCE);root,_=xml_root(SOURCE)
    index=read(WORK/'analysis/measure-index.json')['measures']
    audit=read(WORK/'reports/source-audit-20261027.json')
    if digest(SOURCE)!=audit['mxl']['sha256']:raise ValueError('Audited XML changed')
    quarantine=set(audit['timing_review_classification']['large_extent_difference_sequences'])
    first=root.find('part');div=None;meter=None;q=F(0);page=1;system=0;measures=[]
    for seq,m in enumerate(first.findall('measure'),1):
        a=m.find('attributes')
        if a is not None:
            if a.find('divisions') is not None:div=int(a.findtext('divisions'))
            if a.find('time') is not None:meter=(int(a.findtext('time/beats')),int(a.findtext('time/beat-type')))
        if not div or not meter:raise ValueError('Missing explicit divisions or initial meter')
        printing=m.find('print')
        if printing is not None:
            if printing.get('new-page')=='yes':page+=1;system=0
            elif printing.get('new-system')=='yes':system+=1
        cursor=F(0);previous=F(0);extent=F(0)
        for child in m:
            if child.tag in {'backup','forward'}:cursor+=(1 if child.tag=='forward' else -1)*F(child.findtext('duration','0'))/div
            elif child.tag=='note':
                d=F(child.findtext('duration','0'))/div
                onset=previous if child.find('chord') is not None else cursor
                extent=max(extent,onset+d)
                if child.find('chord') is None:
                    previous=onset
                    if child.find('grace') is None:cursor+=d
        nominal=F(meter[0]*4,meter[1])
        # The two unbarred Andante systems explicitly encode 13 and 12.5
        # quarters of whole-bar rests; keeping those extents avoids splitting
        # or compressing them to the nominal 3/2. Final decay remains limited
        # by the independently located recording endpoint.
        length=extent if seq in {811,812} else nominal
        if length<=0:raise ValueError('Nonpositive reference interval')
        entry=index[seq-1];mv=next(row for row in MOVEMENTS if row[1]<=seq<=row[2])
        measures.append({'measure_id':entry['measure_id'],'sequence_index':seq,'movement':mv[0],
            'local_number':m.get('number'),'start_q':str(q),'end_q':str(q+length),
            'duration_q':str(length),'time_signature':f'{meter[0]}/{meter[1]}',
            'layout_page':page,'layout_system':system,'layout_width':float(m.get('width','0')),
            'rehearsals':entry['rehearsals'],'timing_review':entry['timing_review'],
            'clock_basis':'explicit_P1_rest_extent_unbarred_continuation' if seq in {811,812} else 'explicit_meter_auxiliary_clock'})
        q+=length
    events=[];excluded=Counter();clipped=[]
    for e in data['events']:
        if not e['eligible'] or e['part_id']=='P14':excluded['hidden_grace_ossia_or_nonpositive']+=1;continue
        if e['sequence'] in quarantine and e['part_id']=='P15':excluded['quarantined_piano_bar']+=1;continue
        m=measures[e['sequence']-1];a=F(e['onset_q']);b=a+F(e['duration_q']);length=F(m['duration_q'])
        if a<0 or a>=length:excluded['outside_auxiliary_bar']+=1;continue
        if b>length:
            clipped.append({'event_id':e['id'],'encoded_end_q':str(b),'auxiliary_end_q':str(length)});b=length
        events.append({**e,'measure_id':m['measure_id'],'movement':m['movement'],
            'start_q':str(F(m['start_q'])+a),'end_q':str(F(m['start_q'])+b),
            'ps':float(F(e['concert_ps'])),'label':next(p['name'] for p in data['parts'] if p['id']==e['part_id'])})
    movements=[{'movement':n,'title':title,'first_sequence_index':lo,'last_sequence_index':hi,
        'start_q':measures[lo-1]['start_q'],'end_q':measures[hi-1]['end_q'],
        'first_pdf_page':p,'last_pdf_page':z} for n,lo,hi,title,p,z in MOVEMENTS]
    doc={'work_id':'prokofiev-piano-concerto-2','source':record(SOURCE),'parts':data['parts'],
        'measures':measures,'events':events,'movements':movements,'quarter_duration':str(q),
        'purpose':'auxiliary alignment clock, not a new certified musical chronology',
        'quarantine':{'piano_part':'P15','sequences':sorted(quarantine)},
        'excluded_counts':dict(excluded),'clipped_reference_ends':clipped,
        'limitations':['Original local-only research snapshot is unchanged.',
            'Normal intervals use explicit meter; P15 large timing disagreements are omitted from matching.',
            'XML 811/812 use encoded P1 rest extents in unbarred systems, not invented physical bars.',
            'MIDI reference seconds never stand in for recording seconds.'],'human_signoff':None}
    write(WORK/'sync/reference/written.json',doc)
    midi=mido.MidiFile(ticks_per_beat=960);track=mido.MidiTrack();midi.tracks.append(track)
    track.append(mido.MetaMessage('set_tempo',tempo=500000,time=0))
    intervals=defaultdict(list)
    for e in events:
        if not e['ps'].is_integer() or not 21<=e['ps']<=108:continue
        intervals[int(e['ps'])].append((round(F(e['start_q'])*960),round(F(e['end_q'])*960)))
    messages=[]
    for pitch,spans in intervals.items():
        merged=[]
        for a,b in sorted(spans):
            if merged and a<merged[-1][1]:merged[-1][1]=max(b,merged[-1][1])
            else:merged.append([a,b])
        for a,b in merged:messages.extend([(a,1,pitch),(b,0,pitch)])
    last=0
    for tick,on,pitch in sorted(set(messages)):
        track.append(mido.Message('note_on' if on else 'note_off',note=pitch,velocity=80 if on else 0,time=tick-last));last=tick
    track.append(mido.MetaMessage('end_of_track',time=max(0,round(q*960)-last)))
    midi.save(WORK/'sync/reference/derived.mid')
    log(f'Auxiliary reference: {len(measures)} intervals, {len(events)} pitch intervals, {q} quarters; exclusions={dict(excluded)}')

def reference_features(n):
    import numpy as np
    from midi_score import symbolic_features
    from synctoolbox.feature.chroma import pitch_to_chroma,quantize_chroma
    from synctoolbox.feature.dlnco import pitch_onset_features_to_DLNCO
    doc=read(WORK/'sync/reference/written.json');mv=doc['movements'][n-1];q0=F(mv['start_q'])
    duration=float(F(mv['end_q'])-q0)*.5
    notes=[{'pitch':round(e['ps']),'start':float(F(e['start_q'])-q0)*.5,
        'duration':float(F(e['end_q'])-F(e['start_q']))*.5,'velocity':80,'is_drum':False}
        for e in doc['events'] if e['movement']==n]
    p,peaks,_=symbolic_features(notes,duration,50)
    c=quantize_chroma(pitch_to_chroma(p))
    o=pitch_onset_features_to_DLNCO(peaks,feature_sequence_length=c.shape[1],feature_rate=50)
    return c,o,duration

def locate():
    import numpy as np,librosa
    media=read(WORK/'media-sync.json');video=media['video']
    audio=np.load(CACHE/f"audio-{video['sha256'][:16]}.npz")
    def shrink(v):
        count=v.shape[1]//10
        return v[:,:count*10].reshape(12,count,10).mean(axis=2)
    def norm(x):return x/np.maximum(np.linalg.norm(x,axis=0,keepdims=True),1e-9)
    ac=norm(shrink(audio['chroma']));ao=norm(shrink(audio['onset']));rows=[]
    for n in range(1,5):
        c,o,d=reference_features(n);cc=norm(shrink(c));oo=norm(shrink(o))
        cost=.7*(1-cc.T@ac)+.3*(1-oo.T@ao)
        log(f'Open-end movement locator {n}: {cost.shape}')
        D,path=librosa.sequence.dtw(C=cost,subseq=True,step_sizes_sigma=np.array([[1,1],[1,2],[2,1]]),weights_mul=np.array([2.,3.,3.]))
        path=path[::-1];a=float(path[0,1]/5);b=float(path[-1,1]/5)
        row={'movement':n,'start':a,'end':b,'search_window':[0,video['duration_seconds']],
            'method':'independent full-video subsequence chroma+DLNCO locator, 5 Hz',
            'locator_cost':float(D[-1,path[-1,1]]/len(path)),'human_signoff':None}
        rows.append(row);log(str(row))
        np.savez_compressed(CACHE/f'locator-{n}.npz',path=path,rate=5,video_sha256=video['sha256'],written_sha256=digest(WORK/'sync/reference/written.json'))
        del cost,D,path
    if any(b['start']<=a['end'] for a,b in zip(rows,rows[1:])):
        write(CACHE/'localized-draft.json',rows)
        # The first movement's free cadenza has much larger local tempo ratios
        # than the motoric inner movements. Re-search it before the independently
        # found Scherzo, retaining the failed unrestricted match for inspection.
        # This constraint uses musical order, never equal-duration allocation.
        if rows[0]['start']>rows[1]['start'] and rows[1]['end']<rows[2]['start']<rows[3]['start']:
            c,o,d=reference_features(1);limit=round(rows[1]['start']*5)
            cost=np.maximum(0,.7*(1-norm(shrink(c)).T@ac[:,:limit])+.3*(1-norm(shrink(o)).T@ao[:,:limit]))
            steps=np.array([[1,1],[1,2],[2,1],[1,3],[3,1],[1,4],[4,1]])
            D,path=librosa.sequence.dtw(C=cost,subseq=True,step_sizes_sigma=steps,weights_mul=steps.sum(axis=1).astype(float))
            path=path[::-1]
            rows[0]={'movement':1,'start':float(path[0,1]/5),'end':float(path[-1,1]/5),
                'search_window':[0,rows[1]['start']],
                'method':'order-constrained open-end chroma+DLNCO locator; flexible cadenza ratios up to 4:1',
                'locator_cost':float(D[-1,path[-1,1]]/len(path)),
                'constraint_evidence':'Scherzo independently located in full video; first movement precedes it',
                'human_signoff':None}
            np.savez_compressed(CACHE/'locator-1-ordered.npz',path=path,rate=5,video_sha256=video['sha256'],written_sha256=digest(WORK/'sync/reference/written.json'))
            log(str(rows[0]))
        if any(b['start']<=a['end'] for a,b in zip(rows,rows[1:])):
            raise ValueError('Independent searches still overlap; inspect before refinement')
    write(CACHE/'localized.json',rows)

def align():
    import numpy as np
    from synctoolbox.dtw.mrmsdtw import sync_via_mrmsdtw
    from align_recording import reduce_path
    doc=read(WORK/'sync/reference/written.json');media=read(WORK/'media-sync.json')
    audio=np.load(CACHE/f"audio-{media['video']['sha256'][:16]}.npz")
    localized=read(CACHE/'localized.json');maps=[];measures=[]
    review_path=WORK/'sync/boundary-review.json'
    if review_path.exists():
        review=read(review_path)
        if review['video_sha256']!=media['video']['sha256']:raise ValueError('Boundary review belongs to another video')
        localized=[{**r,**next(x for x in review['movements'] if x['movement']==r['movement'])} for r in localized]
    params=dict(input_feature_rate=50,step_weights=np.array([1.5,1.5,2.0]),threshold_rec=10**6,verbose=False)
    for mv,row in zip(doc['movements'],localized):
        n=mv['movement'];lo=row['start'];hi=row['end'];q0=F(mv['start_q'])
        c,o,d=reference_features(n)
        a=audio['chroma'][:,round(lo*50):round(hi*50)];ao=audio['onset'][:,round(lo*50):round(hi*50)]
        log(f'50-Hz DTW movement {n}: {lo} to {hi}')
        path=sync_via_mrmsdtw(f_chroma1=a,f_chroma2=c,f_onset1=ao,f_onset2=o,**params)
        baseline=sync_via_mrmsdtw(f_chroma1=a,f_chroma2=c,**params)
        s,t=reduce_path(path);bs,bt=reduce_path(baseline)
        np.savez_compressed(CACHE/f'refined-{n}.npz',path=path,baseline=baseline,rate=50,offset=lo,
            video_sha256=media['video']['sha256'],written_sha256=digest(WORK/'sync/reference/written.json'))
        points=[{'midi_seconds':float(q0)*.5+float(x/50),'audio_seconds':lo+float(y/50)} for x,y in zip(s[::5],t[::5])]
        points=[{'midi_seconds':float(q0)*.5,'audio_seconds':lo}]+points+[{'midi_seconds':float(F(mv['end_q']))*.5,'audio_seconds':hi}]
        points=sorted({p['midi_seconds']:p for p in points}.values(),key=lambda p:p['midi_seconds'])
        maps.append({'id':f'movement-{n}','movement':n,'start_seconds':lo,'end_seconds':hi,'time_map':points})
        for m in [m for m in doc['measures'] if m['movement']==n]:
            x=float(F(m['start_q'])-q0)*25;y=float(F(m['end_q'])-q0)*25
            a=lo+float(np.interp(x,s,t)/50);b=lo+float(np.interp(y,s,t)/50)
            delta=abs(float(np.interp(x,bs,bt)-np.interp(x,s,t))/50)
            flags=[]
            if delta>2:flags.append('feature_variant_disagreement_over_2s')
            if b<=a:flags.append('collapsed_or_reversed_interval')
            if m['timing_review'].startswith('large_'):flags.append('xml_piano_timing_quarantined')
            if b-a>30:flags.append('long_interval_check_cadenza_or_fermata')
            if m['sequence_index'] in [mv['first_sequence_index'],mv['last_sequence_index']]:flags.append('movement_boundary_requires_listening')
            measures.append({**m,'score_start_quarter':float(F(m['start_q'])),'score_end_quarter':float(F(m['end_q'])),
                'score_start_tick':float(F(m['start_q'])*960),'score_end_tick':float(F(m['end_q'])*960),
                'midi_start_seconds':float(F(m['start_q']))*.5,'midi_end_seconds':float(F(m['end_q']))*.5,
                'start_seconds':a,'end_seconds':b,'review_status':'needs_review' if flags else 'unreviewed',
                'source':'video_audio_independent_movement_chroma_dlnco_mrmsdtw','printed_measure_number':None,
                'numbering_status':'source_xml_sequence_not_scan_number','flags':flags,
                'quality_metrics':{'chroma_only_start_disagreement_seconds':delta}})
        log(f'Movement {n} flags: '+str(Counter(f for m in measures if m['movement']==n for f in m['flags'])))
    result={'format_version':'1.0.0','status':'automatic_movement_candidates_for_web_review',
        'audio':media['video'],'analysis_audio':media['analysisAudio'],'playback_clock':'video',
        'symbolic_reference':{**record(WORK/'sync/reference/derived.mid'),'duration_seconds':float(F(doc['quarter_duration']))*.5},
        'algorithm':{'name':'Sync Toolbox MrMsDTW','features':['chroma','DLNCO'],'feature_rate_hz':50,
            'boundary_method':'independent open-end searches across original video; local DTW in located intervals'},
        'score_time_coverage':{'start_seconds':maps[0]['start_seconds'],'end_seconds':maps[-1]['end_seconds']},
        'movements':[{**mv,'start_seconds':r['start'],'end_seconds':r['end']} for mv,r in zip(doc['movements'],localized)],
        'measures':measures,'time_maps':maps,'time_map':[p for r in maps for p in r['time_map']],
        'human_anchors':[],'quality':{'flag_counts':dict(Counter(f for m in measures for f in m['flags']))},
        'limitations':['Automatic times require user listening review; variant agreement is not accuracy.',
            'Movement pauses and applause are outside individual time-map segments.',
            'PDF geometry is separately checked; MIDI numbering is not copied onto the original scan.'],
        'human_signoff':None,'expert_review':None}
    write(WORK/'sync/alignment.raw.json',result)

def boundaries():
    """Check beginnings/endings using short, independent musical fingerprints."""
    import numpy as np,librosa
    media=read(WORK/'media-sync.json');video=media['video']
    audio=np.load(CACHE/f"audio-{video['sha256'][:16]}.npz")
    doc=read(WORK/'sync/reference/written.json');initial=read(CACHE/'localized.json');checks=[];updated=[]
    def shrink(v):
        count=v.shape[1]//10
        return v[:,:count*10].reshape(12,count,10).mean(axis=2)
    def norm(x):return x/np.maximum(np.linalg.norm(x,axis=0,keepdims=True),1e-9)
    steps=np.array([[1,1],[1,2],[2,1],[1,3],[3,1],[1,4],[4,1]])
    for mv,row in zip(doc['movements'],initial):
        n=mv['movement'];c,o,_=reference_features(n);ms=[m for m in doc['measures'] if m['movement']==n]
        spans=[('prefix',ms[:44] if n==1 else ms[:16]),('suffix',ms[-20:] if n==1 else ms[-16:])]
        bounds={}
        for kind,group in spans:
            ref_a=float(F(group[0]['start_q'])-F(mv['start_q']))*.5
            ref_b=float(F(group[-1]['end_q'])-F(mv['start_q']))*.5
            if n==1:lo,hi=(0,300) if kind=='prefix' else (max(300,row['end']-120),initial[1]['start'])
            else:
                center=row['start'] if kind=='prefix' else row['end']
                lo=max(0,center-(25 if kind=='prefix' else 100))
                hi=min(video['duration_seconds'],center+(100 if kind=='prefix' else 60))
                if kind=='suffix' and n<4:hi=min(hi,initial[n]['start'])
            ac=norm(shrink(audio['chroma'][:,round(lo*50):round(hi*50)]))
            ao=norm(shrink(audio['onset'][:,round(lo*50):round(hi*50)]))
            cc=norm(shrink(c[:,round(ref_a*50):round(ref_b*50)]))
            oo=norm(shrink(o[:,round(ref_a*50):round(ref_b*50)]))
            cost=np.maximum(0,.7*(1-cc.T@ac)+.3*(1-oo.T@ao))
            D,path=librosa.sequence.dtw(C=cost,subseq=True,step_sizes_sigma=steps,weights_mul=steps.sum(axis=1).astype(float))
            path=path[::-1]
            found={'movement':n,'kind':kind,'first_sequence':group[0]['sequence_index'],
                'last_sequence':group[-1]['sequence_index'],'start':lo+float(path[0,1]/5),
                'end':lo+float(path[-1,1]/5),'search_window':[lo,hi],
                'cost':float(D[-1,path[-1,1]]/len(path)),'human_signoff':None}
            checks.append(found);bounds[kind]=found;log(str(found))
        updated.append({**row,'start':bounds['prefix']['start'],'end':bounds['suffix']['end'],
            'boundary_method':'independent prefix/suffix musical fingerprint checks',
            'original_whole_movement_locator':row})
    write(CACHE/'boundary-checks.json',{'video_sha256':video['sha256'],'written_sha256':digest(WORK/'sync/reference/written.json'),'checks':checks})
    write(CACHE/'localized-before-boundary-checks.json',initial)
    if any(b['start']<=a['end'] for a,b in zip(updated,updated[1:])):
        write(CACHE/'localized-boundary-draft.json',updated);raise ValueError('Boundary checks overlap')
    write(CACHE/'localized.json',updated)

def scan_page_geometry(page,expected_systems):
    """Observed scan geometry, with Mahler's staff consensus plus gap rejection.

    Vertical lines must connect staves in sparse piano systems; parallel stems
    are insufficient. XML system count only detects missing systems and checks
    observations. It never supplies equal-width internal bar boundaries.
    """
    import numpy as np
    from scipy import ndimage as ndi
    from mahler4_score.geometry import extract,runs
    a=np.asarray(page.render(scale=2).to_pil().convert('L'));ink=a<150
    horizontal=ndi.binary_opening(ink,structure=np.ones((1,45)))
    projection=horizontal.sum(axis=1)
    ys=[int(g[np.argmax(projection[g])]) for g in runs(np.flatnonzero(projection>a.shape[1]*.35),2)]
    groups=[]
    for y in ys:
        if groups and y-groups[-1][-1]<13:groups[-1].append(y)
        else:groups.append([y])
    staffs=[g for g in groups if 4<=len(g)<=6]
    # Long beams in dense piano writing can merge adjacent staff-line peaks.
    # A second detector demands near-full staff width and tolerates scan tilt.
    strict_projection=ndi.maximum_filter(horizontal,size=(3,1)).sum(axis=1)
    strict_ys=[int(g[np.argmax(strict_projection[g])]) for g in runs(np.flatnonzero(strict_projection>a.shape[1]*.65),2)]
    strict_groups=[]
    for y in strict_ys:
        if strict_groups and y-strict_groups[-1][-1]<13:strict_groups[-1].append(y)
        else:strict_groups.append([y])
    strict_staffs=[g for g in strict_groups if 4<=len(g)<=6]
    if len(strict_staffs)>len(staffs):staffs=strict_staffs
    # Deduplicate overlapping seeds before numbering anything.
    seeds=[]
    for s in sorted(extract(page),key=lambda s:s['top']):
        if seeds and s['top']<=seeds[-1]['bottom']:
            seeds[-1]['bottom']=max(seeds[-1]['bottom'],s['bottom'])
        else:seeds.append({'top':s['top'],'bottom':s['bottom'],'method':'observed_left_brace_verticals'})
    if expected_systems==1 and staffs:
        # A break between instrument families must not turn a top woodwind
        # bracket into a complete full-orchestra system (e.g. scan page 104).
        seeds=[{'top':staffs[0][0],'bottom':staffs[-1][-1],
                'method':'all_observed_staffs_on_single_system_page'}]
    if len(seeds)<expected_systems:
        # Steeper scan tilt spreads each line over several image rows. The
        # observed full-width horizontal bands still locate the outer staff
        # extent, without inventing intermediate line or note positions.
        band_projection=ndi.maximum_filter(horizontal,size=(13,1)).sum(axis=1)
        bands=[g for g in runs(np.flatnonzero(band_projection>a.shape[1]*.6),5) if len(g)>12]
        band_extents=[[int(g[0])+6,int(g[-1])-6] for g in bands if g[-1]-g[0]>=20]
        if len(band_extents)>len(staffs):staffs=band_extents
    assigned=set()
    for s in seeds:
        s['staff_indices']=[i for i,g in enumerate(staffs) if s['top']-12<=sum(g)/len(g)<=s['bottom']+12]
        assigned.update(s['staff_indices'])
    missing=expected_systems-len(seeds)
    unused=[i for i in range(len(staffs)) if i not in assigned]
    if missing>0 and len(unused)>=2*missing:
        cuts=[]
        for j in range(len(unused)-1):
            cuts.append((staffs[unused[j+1]][0]-staffs[unused[j]][-1],j))
        divisions=sorted(j for gap,j in sorted(cuts,reverse=True)[:missing-1])
        starts=[0]+[j+1 for j in divisions]+[len(unused)]
        proposed=[unused[a:b] for a,b in zip(starts,starts[1:])]
        if all(len(g)>=2 for g in proposed):
            for indexes in proposed:
                seeds.append({'top':staffs[indexes[0]][0],'bottom':staffs[indexes[-1]][-1],
                    'staff_indices':indexes,'method':'uncovered_observed_staff_group; system_count_crosscheck'})
    seeds.sort(key=lambda s:s['top']);wide=ndi.maximum_filter(ink,size=(1,5))
    long_page=ndi.binary_opening(wide,structure=np.ones((55,1)))
    rows=[]
    for s in seeds:
        subset=[staffs[i] for i in s['staff_indices']]
        if len(subset)<2:continue
        top=min(s['top'],subset[0][0]);bottom=max(s['bottom'],subset[-1][-1])
        votes=np.zeros(a.shape[1]);lefts=[];rights=[]
        for g in subset:
            votes+=ndi.maximum_filter(wide[g[0]:g[-1]+1].mean(axis=0)>=.86,size=7)
            xx=np.flatnonzero(horizontal[g[0]:g[-1]+1].any(axis=0))
            if len(xx):lefts.append(xx[0]);rights.append(xx[-1])
        if not lefts:continue
        left=int(np.median(lefts));right=int(np.median(rights));support=votes/len(subset)
        good=support>=.83
        if len(subset)<=3:
            length=max(45,int((bottom-top)*.94))
            long=ndi.binary_opening(wide[top:bottom+1],structure=np.ones((length,1)))
            good&=ndi.maximum_filter(long.sum(axis=0),size=7)>=length
        else:
            good&=ndi.maximum_filter(long_page[top:bottom+1].sum(axis=0),size=13)>=max(90,(bottom-top)*.3)
        xs=[int(g[np.argmax(support[g])]) for g in runs(np.flatnonzero(good),18)]
        # Reject the initial clef/key column; it can vote across every staff.
        xs=[x for x in xs if left+105<x<=right+5]
        if not xs or right-xs[-1]>75:xs.append(right)
        rows.append({'top':int(top),'bottom':int(bottom),'left':left,'right':right,
            'boundaries':[left]+xs,'staff_count':len(subset),'system_detection':s['method'],
            'boundary_support':[round(float(support[x]),4) for x in [left]+xs],
            'coordinate_scale':2,'coordinate_origin':'top_left'})
    return rows

def geometry():
    import pypdfium2 as pdfium
    from PIL import ImageDraw
    doc=read(WORK/'sync/reference/written.json');layout=defaultdict(list)
    for m in doc['measures']:layout[m['layout_page'],m['layout_system']].append(m)
    results=[];issues=[];output=ROOT/'tmp/prokofiev2-sync/geometry-review';output.mkdir(parents=True,exist_ok=True)
    with pdfium.PdfDocument(PDF) as pdf:
        for n in range(1,len(pdf)+1):
            expected=[ms for (p,s),ms in layout.items() if p==n]
            page=pdf[n-1];ss=scan_page_geometry(page,len(expected));w,h=page.get_size()
            image=page.render(scale=1).to_pil().convert('RGB');draw=ImageDraw.Draw(image)
            page_ok=len(ss)==len(expected)
            if not page_ok:issues.append({'page':n,'kind':'system_count_mismatch','observed':len(ss),'reference':len(expected)})
            for i,s in enumerate(ss):
                ms=expected[i] if page_ok else []
                count=len(s['boundaries'])-1;ok=bool(ms) and count==len(ms)
                if not ok:issues.append({'page':n,'system':i,'kind':'bar_count_mismatch_or_unbound_system','observed':count,'reference':len(ms) if ms else None})
                s.update(page_number=n,system_index=i,page_width_pt=w,page_height_pt=h,
                    reference_sequences=[m['sequence_index'] for m in ms],
                    count_status='observed_and_reference_counts_agree' if ok else 'needs_review',
                    reference_local_numbers=[m['local_number'] for m in ms])
                results.append(s)
                xs=s['boundaries'] if ok else [s['left'],s['right']]
                for j,(a,b) in enumerate(zip(xs,xs[1:])):
                    draw.rectangle([a/2,s['top']/2,b/2,s['bottom']/2],outline='green' if ok else 'red',width=2)
                    draw.text((a/2+2,s['top']/2+1),f's{i} r{j+1}',fill='blue')
            image.save(output/f'{n:03d}.jpg')
            log(f'Scan {n}: systems {len(ss)}/{len(expected)}; bar counts '+str([(len(s['boundaries'])-1,len(s['reference_sequences'])) for s in ss]))
    result={'pdf':record(PDF),'source_xml':record(SOURCE),'systems':results,'issues':issues,
        'method':'observed scan staffs and cross-staff connected verticals; per-page XML layout comparison',
        'numbering_policy':'No printed measure numbers inferred from rehearsal figures; mismatches do not propagate across pages.',
        'human_signoff':None}
    write(CACHE/'geometry.raw.json',result)

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('stage',choices=['features','reference','locate','boundaries','align','geometry'])
    args=parser.parse_args()
    if args.stage=='features':features()
    elif args.stage=='reference':reference()
    elif args.stage=='locate':locate()
    elif args.stage=='align':align()
    elif args.stage=='geometry':geometry()
    elif args.stage=='boundaries':boundaries()
