"""Source-specific complete-ballet preparation; original suite evidence is preserved.

Optional processing dependencies only. Playback consumes the frozen JSON files.
"""
from pathlib import Path
from fractions import Fraction as F
from collections import defaultdict, Counter
import argparse, hashlib, json, os, sys, time

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT/'scripts')]
os.environ.setdefault('NUMBA_CACHE_DIR', str(ROOT/'.tools/numba-cache'))
os.environ.setdefault('MPLCONFIGDIR', str(ROOT/'.tools/matplotlib'))
os.environ.setdefault('MPLBACKEND', 'Agg')
DATA = ROOT/'works/ravel-mother-goose-video'
BASE = ROOT/'resource/mother goose'
CACHE = ROOT/'.tools/mother-goose-video'
PDF = BASE/'ballet/ravel-ma-mere-loye-full-ballet-imslp62635.pdf'

def read(p): return json.loads(p.read_text(encoding='utf-8'))
def write(p,v):
    p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def digest(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def log(s):print(time.strftime('%H:%M:%S'),s,flush=True)

def features():
    import numpy as np, soundfile as sf, scipy.signal
    from synctoolbox.feature.pitch import audio_to_pitch_features
    from synctoolbox.feature.pitch_onset import audio_to_pitch_onset_features
    from synctoolbox.feature.utils import estimate_tuning
    from synctoolbox.feature.chroma import pitch_to_chroma, quantize_chroma
    from synctoolbox.feature.dlnco import pitch_onset_features_to_DLNCO
    media=read(DATA/'media-sync.json');source=ROOT/media['video']['path']
    if digest(source)!=media['video']['sha256']:raise ValueError('Video fingerprint changed')
    wav=ROOT/'.tools/video-audio'/f"{media['video']['sha256']}.wav"
    destination=CACHE/f"audio-{media['video']['sha256'][:16]}.npz"
    if destination.exists():log('Reusing fingerprint-bound audio features');return
    wave,fs=sf.read(wav,dtype='float32',always_2d=True);wave=wave.mean(axis=1)
    if fs!=22050:
        import math
        g=math.gcd(fs,22050);wave=scipy.signal.resample_poly(wave,22050//g,fs//g)
    tuning=int(estimate_tuning(np.concatenate([wave[int(t*22050):int((t+8)*22050)] for t in np.linspace(20,len(wave)/22050-30,8)]),22050))
    log(f'Audio tuning {tuning} cents; extracting pitch features')
    pitch=audio_to_pitch_features(wave,Fs=22050,feature_rate=50,tuning_offset=tuning)
    chroma=quantize_chroma(pitch_to_chroma(pitch));del pitch
    log('Extracting audio onset features')
    peaks=audio_to_pitch_onset_features(wave,Fs=22050,tuning_offset=tuning)
    onset=pitch_onset_features_to_DLNCO(peaks,feature_sequence_length=chroma.shape[1],feature_rate=50)
    CACHE.mkdir(parents=True,exist_ok=True)
    np.savez_compressed(destination,chroma=chroma,onset=onset,tuning=tuning,video_sha256=media['video']['sha256'])
    log(f'Audio features saved {chroma.shape}')

def render_pages(numbers,scale=1.6):
    import pypdfium2 as pdfium
    out=ROOT/'tmp/mother-goose/ballet-detail';out.mkdir(parents=True,exist_ok=True)
    with pdfium.PdfDocument(PDF) as doc:
        for n in numbers:doc[n-1].render(scale=scale).to_pil().save(out/f'{n:02d}.png')

def geometry():
    import pypdfium2 as pdfium
    import numpy as np
    from scipy import ndimage as ndi
    from mahler4_score.geometry import extract,runs
    from number_mahler4_pdf import observed_boundaries
    rows=[]
    with pdfium.PdfDocument(PDF) as doc:
        for n in range(3,99):
            p=doc[n-1];w,h=p.get_size()
            systems=extract(p)
            a=np.asarray(p.render(scale=2).to_pil().convert('L'));ink=a<150
            horizontal=ndi.binary_opening(ink,structure=np.ones((1,45)))
            lab,num=ndi.label(horizontal)
            lines=[(s[1].start,s[1].stop,s[0].start,s[0].stop) for s in ndi.find_objects(lab) if s and s[1].stop-s[1].start>a.shape[1]*.3]
            # Open cadenzas and an interrupted left brace do not necessarily
            # have two continuous vertical bars. These are visually inspected
            # staff extents, in pixels at render scale 2.
            manual={47:[(170,1430)],60:[(160,1430)],61:[(160,725),(803,1425)],69:[(160,1430)]}
            if n in manual:systems=[{'top':t,'bottom':b,'left':0,'boundaries':[]} for t,b in manual[n]]
            kept=[]
            for i,s in enumerate(systems):
                ls=[l for l in lines if s['top']-12<=l[2]<=s['bottom']+12]
                left=int(min(l[0] for l in ls));right=int(max(l[1] for l in ls))
                if right-left<200:raise ValueError(f'No staff extents page {n}')
                s['boundaries']=[left,right]
                b,v,staff_count,additions=observed_boundaries(a,s)
                # Original scan barlines tilt a few pixels across a tall
                # system. Aggregate staff votes in a 9px x-neighbourhood.
                wide=ndi.maximum_filter(ink,size=(1,7));r=horizontal[:,left:right].sum(axis=1)
                ys=np.flatnonzero(r>(right-left)*.3);ys=ys[(ys>=s['top']-12)&(ys<=s['bottom']+12)]
                ls2=[int(g[np.argmax(r[g])]) for g in runs(ys,2)];groups=[]
                for y in ls2:
                    if groups and y-groups[-1][-1]<13:groups[-1].append(y)
                    else:groups.append([y])
                staffs=[g for g in groups if 4<=len(g)<=6];votes=np.zeros(a.shape[1])
                for staff in staffs:
                    vertical=wide[staff[0]:staff[-1]+1].mean(axis=0)>=.8
                    votes+=ndi.maximum_filter(vertical,size=7)
                support=votes/max(1,len(staffs))
                long_vertical=ndi.binary_opening(ndi.maximum_filter(ink,size=(1,5)),structure=np.ones((65,1)))
                long_support=ndi.maximum_filter(long_vertical[s['top']:s['bottom']+1].sum(axis=0),size=9)
                eligible=(support>=.72)&(long_support>=min(90,(s['bottom']-s['top'])*.15))
                detected=[int(g[np.argmax(votes[g])]) for g in runs(np.flatnonzero(eligible),8)]
                detected=[x for x in detected if left+75<x<right-15]
                if detected and right-detected[-1]<55 and support[right]<.65:
                    # Cautionary next-system key/meter signatures extend the
                    # staff beyond its final bar. They are not another bar.
                    right=detected.pop()
                # A double bar remains one boundary.
                boundaries=[left]+detected+[right]
                s.update(left=left,boundaries=boundaries,staff_count=len(staffs),boundary_support=[float(support[x]) for x in boundaries],boundary_basis='cross-staff vertical votes and observed horizontal staff extents')
                kept.append(s);rows.append(dict(page=n,system=i,width=w,height=h,**s))
            systems=kept
            log(f"PDF {n}: {[(s['top'],s['bottom'],len(s['boundaries'])-1) for s in systems]}")
    write(CACHE/'geometry.raw.json',{'pdf_sha256':digest(PDF),'scale':2,'systems':rows})

def reference():
    """Canonical written bar clock; no recording seconds enter this stage."""
    from backend.musicxml_analysis.ingest import xml_root
    import xml.etree.ElementTree as ET
    import mido
    specifications=[(1,'前奏曲','i-qian',None,None),(2,'纺车舞与场景','danse-du',None,None),
                    (3,'睡美人的帕凡舞与间奏','iii-pavane',None,None),
                    (4,'美女与野兽的对话与间奏','iv-mei',None,None),
                    (5,'小拇指',None,21,99),(6,'丑姑娘，宝塔女皇',None,100,303),
                    (7,'仙境花园','di7qu',None,None)]
    all_events=[];all_measures=[];parts=[];movements=[];sources=[];q=F(0)
    original=read(ROOT/'tmp/mother-goose/ingest-cache.json')['data']
    for movement,title,needle,lo,hi in specifications:
        first=len(all_measures)+1;start=q
        if needle:
            source=next((BASE/'new').glob(f'*{needle}*.mxl'));root,_=xml_root(source)
            names={p.get('id'):p.findtext('part-name') for p in root.findall('part-list/score-part')}
            # The supplied spinning-wheel export omits every divisions element.
            # A separately retained repair declares 96: all explicit eighths=48,
            # quarters=96 and dotted halves=288; original bytes remain untouched.
            if movement==2:
                vals=Counter((n.findtext('type'),n.findtext('duration'),len(n.findall('dot')),n.findtext('time-modification/actual-notes','1'),n.findtext('time-modification/normal-notes','1')) for n in root.findall('.//note') if n.find('grace') is None)
                expected={'eighth':F(1,2),'quarter':F(1),'half':F(2),'whole':F(4),'16th':F(1,4)}
                support=[]
                for (typ,d,dots,actual,normal),count in vals.items():
                    if typ in expected and d and dots<=1:
                        ratio=F(d)/(expected[typ]*(F(3,2) if dots else 1)*F(int(normal),int(actual)))
                        support.append({'type':typ,'duration':d,'dots':dots,'count':count,'implied_divisions':str(ratio)})
                counts=Counter()
                for v in support:counts[v['implied_divisions']]+=v['count']
                if counts['96']<.99*sum(counts.values()):raise ValueError('96-unit repair no longer supported')
                for p in root.findall('part'):
                    a=p.find('measure/attributes')
                    if a is None:a=ET.Element('attributes');p.find('measure').insert(0,a)
                    ET.SubElement(a,'divisions').text='96'
                repair=DATA/'reference/spinning-divisions-repaired.musicxml'
                repair.parent.mkdir(parents=True,exist_ok=True);ET.ElementTree(root).write(repair,encoding='utf-8',xml_declaration=True)
                write(DATA/'reference/spinning-repair-audit.json',{'source_sha256':digest(source),'repair_sha256':digest(repair),'evidence':support,'division_ratio_counts':dict(counts),'human_signoff':None,'remaining_issue':'harp P18 measures 48–53 cursor underflow excluded from pitched analysis; 12 duration/type disagreements retained with encoded durations'})
            firstpart=root.find('part');lengths=[];meter=None
            for m in firstpart.findall('measure'):
                t=m.find('attributes/time')
                if t is not None:meter=(int(t.findtext('beats')),int(t.findtext('beat-type')))
                if not meter:raise ValueError('Initial meter missing')
                lengths.append((F(meter[0]*4,meter[1]),f'{meter[0]}/{meter[1]}'))
            if movement==1:
                # PDF 12 has the last three Prelude bars (48–50). The supplied
                # XML/MIDI also includes the following 6/8 opening tutti as
                # measure 51; it is already present in the next source.
                write(DATA/'reference/prelude-lookahead-audit.json',{'source_sha256':digest(source),'retained_source_measures':[1,50],'omitted_source_measure':51,'evidence':'complete ballet PDF 12 final bars and PDF 13 first 6/8 tutti; source MIDI independent locator overlaps the next movement','status':'agent_edition_boundary_check','human_signoff':None})
                lengths=lengths[:50]
            localstarts=[];local=F(0)
            for i,(length,meter) in enumerate(lengths,1):
                localstarts.append(local)
                all_measures.append({'measure_id':f'ballet-{movement}-m{i:03d}','sequence_index':len(all_measures)+1,'movement':movement,'local_number':i,'start_q':str(q+local),'end_q':str(q+local+length),'time_signature':meter,'source':source.relative_to(ROOT).as_posix(),'source_sequence':i})
                local+=length
            for p in root.findall('part'):
                pid=f'M{movement}-{p.get("id")}';parts.append({'id':pid,'name':names[p.get('id')]})
                div=None;trans={}
                for i,m in enumerate(p.findall('measure')[:len(lengths)],1):
                    cursor=F(0);previous=F(0);note_index=0
                    for child in m:
                        if child.tag=='attributes':
                            if child.find('divisions') is not None:div=int(child.findtext('divisions'))
                            for t in child.findall('transpose'):trans[t.get('number','all')]=int(t.findtext('chromatic','0'))+12*int(t.findtext('octave-change','0'))
                        elif child.tag in {'backup','forward'}:cursor+=(1 if child.tag=='forward' else -1)*F(child.findtext('duration','0'))/div
                        elif child.tag=='note':
                            note_index+=1
                            d=F(child.findtext('duration','0'))/div;on=previous if child.find('chord') is not None else cursor
                            if child.find('chord') is None:
                                previous=on
                                if child.find('grace') is None:cursor+=d
                            pitch=child.find('pitch')
                            if pitch is None or d<=0 or child.find('grace') is not None or child.get('print-object')=='no' or on<0:continue
                            if movement==2 and p.get('id')=='P18' and 48<=i<=53:continue
                            ps=(int(pitch.findtext('octave'))+1)*12+dict(C=0,D=2,E=4,F=5,G=7,A=9,B=11)[pitch.findtext('step')]+F(pitch.findtext('alter','0'))+trans.get(child.findtext('staff','1'),trans.get('all',0))
                            a=q+localstarts[i-1]+on;b=min(a+d,q+localstarts[i-1]+lengths[i-1][0])
                            if b<=a:continue
                            spelling=pitch.findtext('step')+{F(-2):'bb',F(-1):'b',F(0):'',F(1):'#',F(2):'##'}.get(F(pitch.findtext('alter','0')),'')+pitch.findtext('octave')
                            all_events.append({'id':f'{pid}-m{i:03d}-n{note_index:03d}','part_id':pid,'label':names[p.get('id')],'movement':movement,'local_number':i,'measure_id':f'ballet-{movement}-m{i:03d}','start_q':str(a),'end_q':str(b),'ps':float(ps),'encoded_name':spelling,'transpose':trans.get(child.findtext('staff','1'),trans.get('all',0)),'source_sequence':i,'harmonic':child.find('.//harmonic') is not None,'voice':child.findtext('voice','1'),'staff':child.findtext('staff','1'),'source_note_index':note_index,'source_event_id':f'{p.get("id")}-xml-m{i:04d}-n{note_index:04d}','instrument_ref':child.find('instrument').get('id') if child.find('instrument') is not None else None,'tie':[t.get('type') for t in child.findall('tie')],'articulations':[a.tag for a in child.findall('notations/articulations/*')],'notations_xml':[ET.tostring(a,encoding='unicode') for a in child.findall('notations')],'source_xml_path':source.relative_to(ROOT).as_posix()})
            q+=local
        else:
            source=BASE/'ma-mere-loye-maurice-ravel.mxl'
            base=F(original['measures'][lo-1]['start_q'])
            for i,m in enumerate(original['measures'][lo-1:hi],1):
                a=q+F(m['start_q'])-base;b=a+F(m['duration_q'])
                all_measures.append({'measure_id':f'ballet-{movement}-m{i:03d}','sequence_index':len(all_measures)+1,'movement':movement,'local_number':i,'start_q':str(a),'end_q':str(b),'time_signature':m.get('time_signature'),'source':source.relative_to(ROOT).as_posix(),'source_sequence':lo+i-1})
            for e in original['events']:
                if not e['analysis_eligible'] or not lo<=e['measure_sequence']<=hi:continue
                pid=f'M{movement}-{e["part_id"]}';name=next(p['name'] for p in original['parts'] if p['id']==e['part_id'])
                all_events.append({'id':f'M{movement}-{e["id"]}','part_id':pid,'label':name,'movement':movement,'local_number':e['measure_sequence']-lo+1,'measure_id':f'ballet-{movement}-m{e["measure_sequence"]-lo+1:03d}','start_q':str(q+F(e['score_start_q'])-base),'end_q':str(q+F(e['score_end_q'])-base),'ps':e['concert_pitch']['ps'],'encoded_name':e['concert_pitch']['name'],'transpose':0,'source_sequence':e['measure_sequence'],'harmonic':any('harmonic' in n for n in e['notations_xml'])})
            parts.extend({'id':f'M{movement}-{p["id"]}','name':p['name']} for p in original['parts'])
            q=F(all_measures[-1]['end_q'])
        movements.append({'movement':movement,'title':title,'first_sequence_index':first,'last_sequence_index':len(all_measures),'start_q':str(start),'end_q':str(q)})
        sources.append({'movement':movement,'path':source.relative_to(ROOT).as_posix(),'sha256':digest(source)})
    # Keep the already researched suite witness for the shared five scenes.
    # The added ballet material uses the new source, with its independent audit.
    for movement,lo,hi in [(3,1,20),(4,304,475),(7,476,531)]:
        row=next(m for m in movements if m['movement']==movement);start=F(row['start_q']);base=F(original['measures'][lo-1]['start_q']);count=hi-lo+1
        expected_end=start+F(original['measures'][hi-1]['start_q'])+F(original['measures'][hi-1]['duration_q'])-base
        current_end=F(next(m for m in all_measures if m['movement']==movement and m['local_number']==count)['end_q'])
        if expected_end!=current_end:raise ValueError('Common-scene duration differs; do not silently stretch the shared research')
        all_events=[e for e in all_events if not(e['movement']==movement and e['local_number']<=count)]
        source=BASE/'ma-mere-loye-maurice-ravel.mxl'
        for m in [m for m in all_measures if m['movement']==movement and m['local_number']<=count]:
            old=original['measures'][lo+m['local_number']-2]
            m.update(start_q=str(start+F(old['start_q'])-base),end_q=str(start+F(old['start_q'])+F(old['duration_q'])-base),source=source.relative_to(ROOT).as_posix(),source_sequence=old['sequence'])
        for e in original['events']:
            if not e['analysis_eligible'] or not lo<=e['measure_sequence']<=hi:continue
            pid=f'M{movement}-S-{e["part_id"]}';name=next(p['name'] for p in original['parts'] if p['id']==e['part_id'])
            all_events.append({'id':f'M{movement}-S-{e["id"]}','part_id':pid,'label':name,'movement':movement,'local_number':e['measure_sequence']-lo+1,'measure_id':f'ballet-{movement}-m{e["measure_sequence"]-lo+1:03d}','start_q':str(start+F(e['score_start_q'])-base),'end_q':str(start+F(e['score_end_q'])-base),'ps':e['concert_pitch']['ps'],'encoded_name':e['concert_pitch']['name'],'transpose':0,'source_sequence':e['measure_sequence'],'harmonic':any('harmonic' in n for n in e['notations_xml'])})
        parts.extend({'id':f'M{movement}-S-{p["id"]}','name':p['name']} for p in original['parts'])
        sources.append({'movement':movement,'path':source.relative_to(ROOT).as_posix(),'sha256':digest(source),'role':f'previously researched core {lo}–{hi}; new source retained for ballet extension'})
    document={'schema_version':'1.0','work_id':'ravel-mother-goose-ballet','sources':sources,'measures':all_measures,'events':all_events,'parts':parts,'movements':movements,'quarter_duration':str(q),'excluded_spans':['unreferenced interlude after Petit Poucet','unreferenced interlude after Laideronnette'],'clock_note':'Written quarters concatenate seven provided sources; absent interludes have no invented written duration. Recording projection is separately bounded.'}
    originals={e['id']:e for e in original['events']}
    for e in all_events:
        marker=e['id'].find('P')
        witness=originals.get(e['id'][marker:]) if marker>=0 and ('-S-' in e['id'] or e['movement'] in [5,6]) else None
        if witness:
            for field in ['voice','staff','source_note_index','instrument_ref','tie','articulations','notations_xml','encoded_pitch','written_pitch','concert_pitch']:e[field]=witness.get(field)
            e['source_event_id']=witness['id'];e['source_xml_path']=(BASE/'ma-mere-loye-maurice-ravel.mxl').relative_to(ROOT).as_posix()
    write(DATA/'reference/written.json',document)
    # A constant-tempo derived MIDI preserves exact XML bar offsets. Its seconds
    # are a reference coordinate, never the actual performance clock.
    midi=mido.MidiFile(ticks_per_beat=960);track=mido.MidiTrack();midi.tracks.append(track)
    track.append(mido.MetaMessage('set_tempo',tempo=500000,time=0));track.append(mido.MetaMessage('time_signature',numerator=4,denominator=4,time=0))
    intervals=defaultdict(list)
    for e in all_events:
        if not 21<=e['ps']<=108 or e['ps']%1:continue
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
    end=round(q*960);track.append(mido.MetaMessage('end_of_track',time=max(0,end-last)))
    midi.save(DATA/'reference/ballet-derived.mid')
    log(f'Reference: {len(all_measures)} bars, {len(all_events)} events; q={q}')

def align():
    import numpy as np
    from synctoolbox.feature.chroma import pitch_to_chroma,quantize_chroma
    from synctoolbox.feature.dlnco import pitch_onset_features_to_DLNCO
    from synctoolbox.dtw.mrmsdtw import sync_via_mrmsdtw
    from midi_score import read_midi,symbolic_features
    from align_recording import reduce_path
    media=read(DATA/'media-sync.json');video_hash=media['video']['sha256'];midi=DATA/'reference/ballet-derived.mid'
    audio=np.load(CACHE/f'audio-{video_hash[:16]}.npz');score=read_midi(midi)
    pitch,peaks,_=symbolic_features(score['notes'],score['duration'],50)
    chroma=quantize_chroma(pitch_to_chroma(pitch));onset=pitch_onset_features_to_DLNCO(peaks,feature_sequence_length=chroma.shape[1],feature_rate=50)
    del pitch,peaks
    log('Global ballet order / audio feature DTW')
    start,end=12.0,1634.0
    a=audio['chroma'][:,int(start*50):int(end*50)];o=audio['onset'][:,int(start*50):int(end*50)]
    params=dict(input_feature_rate=50,step_weights=np.array([1.5,1.5,2.0]),threshold_rec=10**6,verbose=False)
    path=sync_via_mrmsdtw(f_chroma1=a,f_chroma2=chroma,f_onset1=o,f_onset2=onset,**params)
    np.savez_compressed(CACHE/'global-path.npz',path=path,rate=50,offset=start,video_sha256=video_hash,midi_sha256=digest(midi))
    s,t=reduce_path(path);points=[{'midi_seconds':float(x/50),'audio_seconds':float(y/50+start)} for x,y in zip(s[::5],t[::5])]
    doc=read(DATA/'reference/written.json')
    def at(q):return float(np.interp(float(F(q))*.5*50,s,t)/50+start)
    for m in doc['measures']:m['start_seconds']=at(m['start_q']);m['end_seconds']=at(m['end_q'])
    write(CACHE/'global-measures.json',doc['measures'])
    write(CACHE/'global-time-map.json',points)
    for row in doc['movements']:
        log(f"{row['title']}: {at(row['start_q']):.2f}–{at(row['end_q']):.2f}")

def localize():
    """Independent open-end searches; no forced full-file movement endpoints."""
    import numpy as np, librosa
    from synctoolbox.feature.chroma import pitch_to_chroma,quantize_chroma
    from synctoolbox.feature.dlnco import pitch_onset_features_to_DLNCO
    from midi_score import read_midi,symbolic_features
    media=read(DATA/'media-sync.json');audio=np.load(CACHE/f"audio-{media['video']['sha256'][:16]}.npz")
    doc=read(DATA/'reference/written.json');out=[]
    searches={1:(0,250),2:(150,480),3:(350,700),4:(500,1000),5:(800,1250),6:(1050,1450),7:(1300,1640)}
    def norm(x):return x/np.maximum(np.linalg.norm(x,axis=0,keepdims=True),1e-9)
    for movement in doc['movements']:
        n=movement['movement'];s=next(s for s in doc['sources'] if s['movement']==n)
        if n not in [5,6]:
            midi=ROOT/Path(s['path']).with_suffix('.mid');score=read_midi(midi)
            notes=score['notes'];duration=score['duration'];basis='supplied MIDI with its own tempo map'
        else:
            q0=F(movement['start_q']);factor=1 if n==5 else .55
            notes=[{'pitch':round(e['ps']),'start':float(F(e['start_q'])-q0)*factor,'duration':float(F(e['end_q'])-F(e['start_q']))*factor,'velocity':80,'is_drum':False} for e in doc['events'] if e['movement']==n]
            duration=float(F(movement['end_q'])-q0)*factor;basis='XML-derived written intervals with reference tempo'
        p,peaks,_=symbolic_features(notes,duration,50);c=quantize_chroma(pitch_to_chroma(p));o=pitch_onset_features_to_DLNCO(peaks,feature_sequence_length=c.shape[1],feature_rate=50)
        np.savez_compressed(CACHE/f'reference-{n}.npz',chroma=c,onset=o,duration=duration)
        lo,hi=searches[n];step=10
        # Matrices use the same 50-Hz features, locally averaged to 5 Hz only
        # for the independent locator. Refined paths retain the 50-Hz data.
        def shrink(v):
            count=v.shape[1]//step
            return v[:,:count*step].reshape(12,count,step).mean(axis=2)
        a=shrink(audio['chroma'][:,lo*50:hi*50]);b=shrink(audio['onset'][:,lo*50:hi*50])
        cc=shrink(c);oo=shrink(o)
        cost=.7*(1-norm(cc).T@norm(a))+.3*(1-norm(oo).T@norm(b))
        D,path=librosa.sequence.dtw(C=cost,subseq=True,step_sizes_sigma=np.array([[1,1],[1,2],[2,1]]),weights_mul=np.array([2.,3.,3.]))
        path=path[::-1];start=lo+path[0,1]/5;end=lo+path[-1,1]/5
        row={'movement':n,'start':float(start),'end':float(end),'search_window':[lo,hi],'basis':basis,'locator_cost':float(D[-1,path[-1,1]]/len(path))}
        out.append(row);log(str(row))
        np.savez_compressed(CACHE/f'locator-{n}.npz',path=path,rate=5,offset=lo,cost=cost)
    write(CACHE/'localized.json',out)

def refine():
    import numpy as np
    from synctoolbox.feature.chroma import pitch_to_chroma,quantize_chroma
    from synctoolbox.feature.dlnco import pitch_onset_features_to_DLNCO
    from synctoolbox.dtw.mrmsdtw import sync_via_mrmsdtw
    from midi_score import symbolic_features
    from align_recording import reduce_path
    doc=read(DATA/'reference/written.json');media=read(DATA/'media-sync.json')
    audio=np.load(CACHE/f"audio-{media['video']['sha256'][:16]}.npz")
    localized=read(CACHE/'localized.json');maps=[];measures=[]
    params=dict(input_feature_rate=50,step_weights=np.array([1.5,1.5,2.0]),threshold_rec=10**6,verbose=False)
    for row in doc['movements']:
        n=row['movement'];q0=F(row['start_q']);duration=float(F(row['end_q'])-q0)*.5
        source=[e for e in doc['events'] if e['movement']==n]
        notes=[{'pitch':round(e['ps']),'start':float(F(e['start_q'])-q0)*.5,'duration':float(F(e['end_q'])-F(e['start_q']))*.5,'velocity':80,'is_drum':False} for e in source]
        pitch,peaks,_=symbolic_features(notes,duration,50);c=quantize_chroma(pitch_to_chroma(pitch));o=pitch_onset_features_to_DLNCO(peaks,feature_sequence_length=c.shape[1],feature_rate=50)
        lo=localized[n-1]['start'];hi=localized[n-1]['end']
        if n in [1,2,3,4]:hi=localized[n]['start']
        a=audio['chroma'][:,round(lo*50):round(hi*50)];ao=audio['onset'][:,round(lo*50):round(hi*50)]
        log(f'Refine {n}: {lo}–{hi}')
        path=sync_via_mrmsdtw(f_chroma1=a,f_chroma2=c,f_onset1=ao,f_onset2=o,**params)
        baseline=sync_via_mrmsdtw(f_chroma1=a,f_chroma2=c,**params)
        s,t=reduce_path(path);bs,bt=reduce_path(baseline)
        np.savez_compressed(CACHE/f'refined-path-{n}.npz',path=path,baseline=baseline,rate=50,offset=lo,video_sha256=media['video']['sha256'],written_sha256=digest(DATA/'reference/written.json'))
        points=[{'midi_seconds':float(q0)*.5+float(x/50),'audio_seconds':lo+float(y/50)} for x,y in zip(s[::5],t[::5])]
        points=[{'midi_seconds':float(q0)*.5,'audio_seconds':lo}]+points+[{'midi_seconds':float(F(row['end_q']))*.5,'audio_seconds':hi}]
        points=sorted({p['midi_seconds']:p for p in points}.values(),key=lambda p:p['midi_seconds'])
        maps.append({'id':f'movement-{n}','movement':n,'start_seconds':lo,'end_seconds':hi,'time_map':points})
        for m in [m for m in doc['measures'] if m['movement']==n]:
            ref=(float(F(m['start_q'])-q0)*25,float(F(m['end_q'])-q0)*25)
            start=lo+float(np.interp(ref[0],s,t)/50);end=lo+float(np.interp(ref[1],s,t)/50)
            delta=abs(float(np.interp(ref[0],bs,bt)-np.interp(ref[0],s,t))/50)
            measures.append({**m,'score_start_quarter':float(F(m['start_q'])),'score_end_quarter':float(F(m['end_q'])),'score_start_tick':float(F(m['start_q'])*960),'score_end_tick':float(F(m['end_q'])*960),'midi_start_seconds':float(F(m['start_q']))*.5,'midi_end_seconds':float(F(m['end_q']))*.5,'start_seconds':start,'end_seconds':end,'review_status':'unreviewed','source':'independent_movement_chroma_dlnco_mrmsdtw','printed_measure_number':None,'numbering_status':'source_xml_local_sequence','flags':(['feature_variant_disagreement_over_2s'] if delta>2 else [])+(['collapsed_or_reversed_interval'] if end<=start else []),'quality_metrics':{'chroma_only_start_disagreement_seconds':delta}})
        log(f'Movement {n}: variant >2s: {sum(m["quality_metrics"]["chroma_only_start_disagreement_seconds"]>2 for m in measures if m["movement"]==n)}')
    output={'format_version':'1.0.0','status':'independent_movement_alignment_agent_review_pending','audio':media['video'],'symbolic_reference':{'path':(DATA/'reference/ballet-derived.mid').relative_to(ROOT).as_posix(),'sha256':digest(DATA/'reference/ballet-derived.mid'),'duration_seconds':float(F(doc['quarter_duration']))*.5,'basis':'derived source-XML clock; absent interludes excluded'},'algorithm':{'name':'Sync Toolbox MrMsDTW','feature_rate_hz':50,'features':['chroma','DLNCO'],'source_audio':'same video audio; 12-cent tuning estimate','boundary_method':'independent open-end searches, then local 50-Hz DTW; no full-file forced movement boundaries'},'score_time_coverage':{'start_seconds':maps[0]['start_seconds'],'end_seconds':maps[-1]['end_seconds']},'measures':measures,'time_maps':maps,'time_map':sorted([p for r in maps for p in r['time_map']],key=lambda p:p['audio_seconds']),'human_anchors':[],'quality':{'flag_counts':dict(Counter(f for m in measures for f in m['flags']))},'limitations':['Automatic movement boundaries and internal times require listening review; variant disagreement is not an accuracy probability.','Two unreferenced ballet interludes have separate observed page landmarks; no XML note clock or instantaneous harmony is fabricated there.'],'human_signoff':None}
    write(DATA/'alignment.json',output)

def geometry_contact():
    import pypdfium2 as pdfium
    from PIL import Image,ImageDraw
    systems=read(CACHE/'geometry.raw.json')['systems'];out=ROOT/'tmp/mother-goose/bar-review';out.mkdir(parents=True,exist_ok=True)
    with pdfium.PdfDocument(PDF) as pdf:
        images=[];cached={}
        for s in systems:
            if s['page'] not in cached:cached[s['page']]=pdf[s['page']-1].render(scale=1.6).to_pil().convert('RGB')
            a=cached[s['page']];y=round(s['top']*.8)
            crop=a.crop((0,max(0,y-40),a.width,min(a.height,y+100)))
            canvas=Image.new('RGB',(1000,185),'white');canvas.paste(crop,(0,25));d=ImageDraw.Draw(canvas)
            d.text((5,4),f"PDF {s['page']} / system {s['system']} / detected {len(s['boundaries'])-1}",fill='black')
            for i,x in enumerate(s['boundaries']):
                x=round(x*.8);d.line((x,45,x,160),fill='red');d.text((x+1,25),str(i),fill='red')
            images.append(canvas)
        for k in range(0,len(images),10):
            contact=Image.new('RGB',(2000,185*5),'#cccccc')
            for j,a in enumerate(images[k:k+10]):contact.paste(a,(j%2*1000,j//2*185))
            contact.save(out/f'contact-{k//10+1:02d}.jpg',quality=94)

def bridge_frames():
    import subprocess
    from PIL import Image,ImageDraw
    from backend.video_export.media import ffmpeg
    video=ROOT/read(DATA/'media-sync.json')['video']['path'];out=ROOT/'tmp/mother-goose/bridge-frames';out.mkdir(parents=True,exist_ok=True)
    times=[*range(1044,1149,4),*range(1360,1453,4)]
    for t in times:
        name=out/f'{t}.jpg'
        if not name.exists():subprocess.run([ffmpeg(ROOT),'-v','error','-ss',str(t),'-i',str(video),'-frames:v','1','-vf','scale=384:-2','-y',str(name)],check=True)
    for k in range(0,len(times),24):
        sheet=Image.new('RGB',(384*6,242*4),'#ddd');d=ImageDraw.Draw(sheet)
        for j,t in enumerate(times[k:k+24]):
            a=Image.open(out/f'{t}.jpg');x=j%6*384;y=j//6*242;sheet.paste(a,(x,y+20));d.text((x+5,y+2),str(t),fill='black')
        sheet.save(out/f'contact-{k//24+1}.jpg',quality=92)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('stage');args=parser.parse_args()
    if args.stage=='features':features()
    elif args.stage=='pages':render_pages([3,12,13,30,31,33,34,37,38,50,51,53,54,59,60,61,62,63,64,86,87,88,89,90,91,98])
    elif args.stage=='geometry':geometry()
    elif args.stage=='reference':reference()
    elif args.stage=='align':align()
    elif args.stage=='localize':localize()
    elif args.stage=='refine':refine()
    elif args.stage=='geometry-contact':geometry_contact()
    elif args.stage=='bridge-frames':bridge_frames()
