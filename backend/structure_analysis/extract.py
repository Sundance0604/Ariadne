"""Supplied-vector-edition adapter, not a general PDF-to-MusicXML system.

PDF observations, decoded written pitches, MIDI durations and their proposed
correspondence remain separate. Unmatched notes are retained, never silently
promoted to score facts. No recordings, papers or existing analysis are inputs.
"""
from collections import Counter, defaultdict, deque
from statistics import median

from .common import bounded_path, digest, pitch_name
from .notation import octave_assignment,octave_for_head,barline_positions,tremolo_bridges,alternating_runs,single_tremolo_marks

HEADS = {0xE0A0:'breve',0xE0A2:'whole',0xE0A3:'half',0xE0A4:'black'}
CLEFS = {0xE050:32,0xE05C:28,0xE062:24}  # diatonic G4, C4, F3 at glyph anchor
ACCIDENTALS = {0xE260:-1,0xE261:0,0xE262:1,0xE263:2,0xE264:-2}
DYNAMICS = {0xE520:'p',0xE521:'m',0xE522:'f',0xE52A:'ppp',0xE52B:'pp',
            0xE52C:'mp',0xE52D:'mf',0xE52F:'ff',0xE530:'fff'}
ARTICULATIONS = {0xE4A0:'accent',0xE4A1:'accent',0xE4A2:'staccato',0xE4A3:'staccato',
                 0xE4A4:'tenuto',0xE4A5:'tenuto',0xE4AC:'marcato',0xE4AD:'marcato'}


def staff_groups(page):
    horizontal = [l for l in page.lines if l['height'] < .05 and l['width'] > 100]
    if not horizontal:
        raise ValueError('No supported native staff lines; scanned score requires a different adapter')
    stroke = Counter(round(l['linewidth'],3) for l in horizontal).most_common(1)[0][0]
    ys = sorted({round(l['top'],3) for l in horizontal if abs(l['linewidth']-stroke)<.002})
    result, i = [], 0
    while i+4 < len(ys):
        differences = [ys[i+j+1]-ys[i+j] for j in range(4)]
        if max(differences)-min(differences)<.02 and 1<differences[0]<8:
            result.append(ys[i:i+5]);i += 5
        else:
            i += 1
    return result


def native_pdf(root, profile):
    import pdfplumber
    source = bounded_path(root, profile['pdf']['path'])
    if digest(source) != profile['pdf']['sha256']:
        raise ValueError('Pilot adapter is bound to a different PDF edition')
    observations, staves, marks, issues = [], [], [], []
    parts = {p['id']:p for p in profile['parts']}
    with pdfplumber.open(source) as document:
        for topology in profile['pages']:
            number = topology['page'];page = document.pages[number-1]
            groups = staff_groups(page)
            if len(groups) != len(topology['staves']):
                raise ValueError(f'Page {number}: staff topology changed ({len(groups)})')
            characters=[]
            for c in page.chars:
                if len(c['text']) != 1:
                    continue
                characters.append({'code':ord(c['text']),'text':c['text'], 'x':c['x0'],
                    'y':page.height-c['matrix'][5], 'size':c['size'],
                    'rect_pt':[round(c['x0'],3),round(c['top'],3),round(c['width'],3),round(c['height'],3)]})
            staff_records=[]
            for index,(lines,assignment) in enumerate(zip(groups,topology['staves'])):
                part_id, system = assignment
                staff={'id':f'pdf-p{number:03d}-staff{index:02d}','part_id':part_id,'page':number,
                    'physical_system_index':system,'staff_index':index,'lines_pt':lines,
                    'page_width_pt':page.width,'page_height_pt':page.height}
                staff_records.append(staff);staves.append(staff)
            from scripts.map_pdf import extract_page
            geometries,_ = extract_page(page,number)
            # Horizontal location is observed; no equal-width slicing of cadenzas.
            for c in characters:
                if c['code'] in DYNAMICS or c['code'] in ARTICULATIONS or 0xE510<=c['code']<=0xE51F or 0xE650<=c['code']<=0xE65F:
                    staff=min(staff_records,key=lambda s:abs(c['y']-sum(s['lines_pt'][::4])/2))
                    kind = 'dynamic' if c['code'] in DYNAMICS else 'articulation' if c['code'] in ARTICULATIONS else 'octave_sign' if c['code']<0xE650 else 'pedal_mark'
                    octave=octave_assignment(c,characters,staff_records) if kind=='octave_sign' else None
                    if octave:staff=octave['staff']
                    marks.append({'id':f'pdf-mark-{number}-{len(marks):04d}','kind':kind,
                        'value':DYNAMICS.get(c['code'],ARTICULATIONS.get(c['code'],f'U+{c["code"]:04X}')),
                        'page':number,'staff_id':staff['id'],'part_id':staff['part_id'],
                        'physical_system_index':staff['physical_system_index'],'x_pt':round(c['x'],3),'y_pt':round(c['y'],3),
                        'assignment_status':'nearest_staff_candidate','raw_glyph':f'U+{c["code"]:04X}'})
                    if octave:marks[-1].update({k:v for k,v in octave.items() if k!='staff'})
            for word in page.extract_words():
                text=word['text']
                if any(t in text.lower() for t in ['pizz','arco','sord','trem','gliss','legato','lento','vivo','tempo','acceler','rall','strep','riten']):
                    staff=min(staff_records,key=lambda s:abs(word['top']-s['lines_pt'][0]))
                    marks.append({'id':f'pdf-text-{number}-{len(marks):04d}','kind':'written_text','value':text,
                        'page':number,'staff_id':staff['id'],'part_id':staff['part_id'],'physical_system_index':staff['physical_system_index'],
                        'x_pt':round(word['x0'],3),'y_pt':round(word['top'],3),'assignment_status':'nearest_staff_candidate'})
            # Vector hairpins are observations, not synthesized dynamics from velocity.
            for curve in page.curves:
                if not curve.get('fill') and 12 < curve['width'] < 700 and 1 < curve['height'] < 12 and len(curve.get('pts',[])) in {3,4}:
                    staff=min(staff_records,key=lambda s:abs(curve['top']-s['lines_pt'][-1]))
                    marks.append({'id':f'pdf-hairpin-{number}-{len(marks):04d}','kind':'hairpin_candidate',
                        'value':'direction_unreviewed','page':number,'staff_id':staff['id'],'part_id':staff['part_id'],
                        'physical_system_index':staff['physical_system_index'],'x_pt':round(curve['x0'],3),
                        'y_pt':round(curve['top'],3),'rect_pt':[curve['x0'],curve['top'],curve['width'],curve['height']],
                        'assignment_status':'shape_candidate'})
            for index,staff in enumerate(staff_records):
                lines=staff['lines_pt'];spacing=(lines[-1]-lines[0])/4;part=parts[staff['part_id']]
                lower=(groups[index-1][-1]+lines[0])/2 if index else lines[0]-80
                upper=(lines[-1]+groups[index+1][0])/2 if index+1<len(groups) else lines[-1]+80
                # Characters can extend over adjacent staves; pitch anchors use glyph baselines.
                chars=[c for c in characters if lower<c['y']<upper]
                clefs=sorted([c for c in chars if c['code'] in CLEFS],key=lambda c:c['x'])
                if not clefs:
                    issues.append({'staff_id':staff['id'],'reason':'clef_not_decoded'});continue
                heads=sorted([c for c in chars if c['code'] in HEADS],key=lambda c:(c['x'],-c['y']))
                prefix_end=min(clefs[0]['x']+29,min((h['x'] for h in heads),default=clefs[0]['x']+40)-spacing*1.5)
                signatures={}
                for c in chars:
                    if c['code'] in ACCIDENTALS and clefs[0]['x']<c['x']<prefix_end:
                        ref=clefs[0];dia=CLEFS[ref['code']]+round((ref['y']-c['y'])/(spacing/2))
                        signatures[dia%7]=ACCIDENTALS[c['code']]
                # Some empty/courtesy staves omit a signature. Edition adapter supplies
                # its visually checked written signature; local accidentals still win.
                signature={**{int(k):v for k,v in part.get('written_key',{}).items()},**signatures}
                bars=barline_positions(page.lines,lines)
                local={};last_bar=None
                for head in heads:
                    clef=max((c for c in clefs if c['x']<=head['x']),key=lambda c:c['x'],default=clefs[0])
                    diatonic=CLEFS[clef['code']]+round((clef['y']-head['y'])/(spacing/2))
                    residual=abs((clef['y']-head['y'])/(spacing/2)-round((clef['y']-head['y'])/(spacing/2)))
                    bar=sum(x<=head['x'] for x in bars)
                    if bar!=last_bar:local={};last_bar=bar
                    accidentals=[c for c in chars if c['code'] in ACCIDENTALS and prefix_end<c['x']<head['x']
                        and head['x']-c['x']<spacing*4 and abs(c['y']-head['y'])<spacing*.18]
                    accidental=max(accidentals,key=lambda c:c['x'],default=None)
                    if accidental:local[diatonic]=ACCIDENTALS[accidental['code']]
                    alter=local.get(diatonic,signature.get(diatonic%7,0))
                    octave,letter=divmod(diatonic,7)
                    written=12*(octave+1)+(0,2,4,5,7,9,11)[letter]+alter
                    # Ottava extents require a matching dashed line, not proximity alone.
                    octave_shift,octave_refs,octave_basis=octave_for_head(head,staff,[m for m in marks if m['page']==number],page.lines,spacing)
                    geometry=next((g for g in geometries if g['top']-1<=lines[0]<=g['bottom']+1),None)
                    measure_candidates=[]
                    if geometry and geometry['printed_start_measure'] is not None:
                        bounds=geometry['boundaries'];offset=max(0,sum(x<=head['x'] for x in bounds)-1)
                        measure_candidates=[geometry['printed_start_measure']+offset]
                    elif number==11 and staff['physical_system_index']==0:measure_candidates=[34]
                    elif number==11 and staff['physical_system_index']==1:measure_candidates=[35,36]
                    observations.append({'id':f'{staff["id"]}-head{len(observations):05d}',
                        'part_id':staff['part_id'],'staff_id':staff['id'],'page':number,
                        'physical_system_index':staff['physical_system_index'],'x_pt':round(head['x'],3),'y_pt':round(head['y'],3),
                        # PDF font boxes include the font's vertical metrics, which
                        # can be far below the actual head. Keep those as provenance;
                        # the display region is estimated around the observed anchor.
                        'rect_pt':[round(head['x'],3),round(head['y']-spacing*.55,3),
                            round(head['rect_pt'][2],3),round(spacing*1.1,3)],
                        'font_bbox_pt':head['rect_pt'],
                        'geometry_status':'native_glyph_anchor_staff_scaled_box_candidate',
                        'glyph':f'U+{head["code"]:04X}','head_class':HEADS[head['code']],
                        'written_pitch_candidate':written,'written_spelling_candidate':'CDEFGAB'[letter]+({-2:'bb',-1:'b',0:'',1:'#',2:'##'}[alter])+str(octave),
                        'concert_pitch_candidate':written+part['transpose_semitones']+octave_shift,
                        'transpose_semitones':part['transpose_semitones'],'octave_line_shift':octave_shift,'octave_mark_ids':octave_refs,
                        'octave_scope_basis':octave_basis,
                        'midi_measure_candidates':measure_candidates,
                        'accidental_glyph':None if not accidental else f'U+{accidental["code"]:04X}',
                        'clef_glyph':f'U+{clef["code"]:04X}','staff_step_residual':round(residual,5),
                        'observation_status':'native_vector_glyph','pitch_status':'decoded_candidate',
                        'duration_status':'head_shape_only_not_rhythm_transcription','voice_identity_status':'staff_observed_voice_undetermined'})
            marks.extend(tremolo_bridges(number,[h for h in observations if h['page']==number],staff_records,page.lines,page.curves))
            marks.extend(single_tremolo_marks(number,[h for h in observations if h['page']==number],staff_records,page.lines,page.curves))
    return {'notes':observations,'staves':staves,'marks':marks,'issues':issues,
        'method':'native_SMUFL_glyph_staff_clef_accidental_decoder', 'limitations':[
        'Adapter covers only the fingerprint-bound vector edition and explicit page/staff topology.',
        'Tuplets, beams, ties, slur extents and complete score rhythm are not reconstructed.',
        'Native notehead location is observed; pitch decoding, staff assignments and MIDI matching are separate candidates.']}


def midi_reference(root, profile):
    import mido
    source=bounded_path(root,profile['midi']['path'])
    if digest(source)!=profile['midi']['sha256']:raise ValueError('MIDI input fingerprint changed')
    midi=mido.MidiFile(source);notes=[];pedals=[];meters=[];tempos=[];issues=[]
    mapping={track:part for part in profile['parts'] for track in part['tracks']}
    for ti,track in enumerate(midi.tracks):
        tick=0;port=0;active=defaultdict(deque);pending=defaultdict(list);down=defaultdict(bool)
        for event in track:
            tick+=event.time
            if event.type=='midi_port':port=event.port
            elif event.type=='set_tempo':tempos.append((tick,event.tempo))
            elif event.type=='time_signature':meters.append((tick,event.numerator,event.denominator))
            elif event.type=='control_change' and event.control==64:
                key=(port,event.channel);pedals.append({'tick':tick,'track':ti,'port':port,'channel':event.channel,'value':event.value})
                down[key]=event.value>=64
                if not down[key]:
                    for note in pending.pop(key,[]):note['sounding_end_tick']=tick
            elif event.type in {'note_on','note_off'}:
                key=(port,event.channel,event.note)
                if event.type=='note_on' and event.velocity:
                    active[key].append((tick,event.velocity))
                elif active[key]:
                    start,velocity=active[key].popleft()
                    note={'id':f'midi-t{ti:02d}-{start:07d}-{event.note:03d}-{len(notes):05d}',
                        'part_id':mapping.get(ti,{'id':f'unassigned-track-{ti}'})['id'],'track_index':ti,
                        'port':port,'channel':event.channel,'pitch':event.note,'pitch_name':pitch_name(event.note),
                        'start_tick':start,'key_end_tick':tick,'sounding_end_tick':tick,
                        'velocity':velocity,'is_drum':event.channel==9,'source':'midi_bytes',
                        'duration_status':'auxiliary_MIDI_duration_not_PDF_rhythm_verified','score_locations':[]}
                    if tick>start:
                        notes.append(note)
                        if down[(port,event.channel)]:pending[(port,event.channel)].append(note)
                else:issues.append({'track':ti,'tick':tick,'type':'unmatched_note_off'})
        for key,queue in active.items():
            if queue:issues.append({'track':ti,'key':list(key),'type':'unclosed_note_on'})
        for values in pending.values():
            for note in values:
                note['sounding_end_tick']=tick;note['pedal_end_status']='file_end_unreleased_candidate'
    ppq=midi.ticks_per_beat
    if midi.type==2 or ppq<=0:raise ValueError('Simultaneous PPQ MIDI required')
    clock=[];seconds=0;previous_tick=0;tempo=500000
    for tick,newtempo in sorted(dict(tempos).items()):
        seconds+=(tick-previous_tick)*tempo/ppq/1e6
        clock.append({'tick':tick,'midi_seconds':seconds,'seconds_per_tick':newtempo/ppq/1e6})
        previous_tick=tick;tempo=newtempo
    if not clock or clock[0]['tick']!=0:clock.insert(0,{'tick':0,'midi_seconds':0,'seconds_per_tick':.5/ppq})
    from fractions import Fraction
    metrical=[];meters=sorted(set(meters));last=max(n['sounding_end_tick'] for n in notes)
    for i,(tick,num,den) in enumerate(meters):
        end=meters[i+1][0] if i+1<len(meters) else last;step=Fraction(ppq*4*num,den)
        start=Fraction(tick)
        while start<end:
            stop=min(start+step,end)
            metrical.append({'number':len(metrical)+1,'start_tick':int(start),'end_tick':int(stop),'meter':[num,den]});start=stop
    for n in notes:
        bar=next((b for b in metrical if b['start_tick']<=n['start_tick']<b['end_tick']),None)
        n['midi_measure_candidate']=None if not bar else bar['number']
    return {'notes':notes,'pedal_controls':pedals,'meters':[list(t) for t in sorted(set(meters))],
            'metrical_reference':metrical,'reference_clock':clock,'ppq':ppq,'issues':issues}


def sequence_pairs(pdf, midi):
    """Global ordered correspondence with explicit gaps; pitches not overwritten."""
    from array import array
    n,m=len(pdf),len(midi)
    previous=[j*.8 for j in range(m+1)];trace=[bytearray(m+1) for _ in range(n+1)]
    for i in range(1,n+1):
        current=[i*.8]+[0.]*m;trace[i][0]=1
        for j in range(1,m+1):
            a,b=pdf[i-1]['concert_pitch_candidate'],midi[j-1]['pitch']
            candidates=pdf[i-1]['midi_measure_candidates']
            in_bar=not candidates or midi[j-1]['midi_measure_candidate'] in candidates
            cost=(0 if a==b else .3 if (a-b)%12==0 else 2.) if in_bar else 2.
            values=(previous[j-1]+cost,previous[j]+.8,current[j-1]+.8)
            choice=min(range(3),key=values.__getitem__);current[j]=values[choice];trace[i][j]=choice
        previous=current
    pairs=[];i,j=n,m
    while i and j:
        choice=trace[i][j]
        if choice==0:
            candidates=pdf[i-1]['midi_measure_candidates']
            if (pdf[i-1]['concert_pitch_candidate']-midi[j-1]['pitch'])%12==0 and (not candidates or midi[j-1]['midi_measure_candidate'] in candidates):pairs.append((i-1,j-1))
            i-=1;j-=1
        elif choice==1:i-=1
        else:j-=1
    return list(reversed(pairs))


def correlate(pdf, midi, excerpts):
    notes=midi['notes'];matched=set();comparisons=[]
    bars={b['number']:b for b in midi['metrical_reference']}
    def location(observed, role):
        candidates=[bars[b] for b in observed['midi_measure_candidates'] if b in bars]
        return {**{k:observed[k] for k in ['id','page','physical_system_index','staff_id','x_pt','y_pt','rect_pt','written_spelling_candidate']},
                'notation_role':role,'bar_start_tick':min((b['start_tick'] for b in candidates),default=None),
                'bar_end_tick':max((b['end_tick'] for b in candidates),default=None)}
    for excerpt in excerpts:
        pages=set(excerpt['pages']);start,end=excerpt['start_tick'],excerpt['end_tick']
        part_ids={n['part_id'] for n in pdf['notes'] if n['page'] in pages}
        for part in sorted(part_ids):
            a=sorted([n for n in pdf['notes'] if n['page'] in pages and n['part_id']==part],
                key=lambda n:(n['page'],n['physical_system_index'],round(n['x_pt']/2),-n['concert_pitch_candidate']))
            b=sorted([n for n in notes if n['part_id']==part and start<=n['start_tick']<end and not n['is_drum']],
                key=lambda n:(n['start_tick'],-n['pitch'],n['track_index']))
            pairs=sequence_pairs(a,b)
            for pi,mi in pairs:
                observed,reference=a[pi],b[mi];matched.add(observed['id'])
                exact=observed['concert_pitch_candidate']==reference['pitch']
                reference['score_locations'].append(location(observed,'onset_correspondence_candidate'))
                reference['correspondence']={'method':'ordered_pitch_sequence_with_gaps','pitch_class_agrees':True,
                    'octave_agrees':exact,'status':'pitch_agrees_candidate' if exact else 'octave_discrepancy',
                    'decoded_concert_pitch':observed['concert_pitch_candidate'],'not_human_verified':True}
            comparisons.append({'excerpt':excerpt['id'],'part_id':part,'pdf_heads':len(a),'midi_onsets':len(b),
                'paired_pitch_classes':len(pairs),'octave_agreements':sum(a[i]['concert_pitch_candidate']==b[j]['pitch'] for i,j in pairs)})
            # One notated sustained pitch can have tied continuation heads. Conversely
            # a written Trem. can yield repeated MIDI attacks. Neither invents PDF rhythm.
            for observed in a:
                if observed['id'] in matched:continue
                for reference in b:
                    spans=[bars[i] for i in observed['midi_measure_candidates'] if i in bars]
                    if observed['concert_pitch_candidate']!=reference['pitch']:continue
                    if any(reference['start_tick']<bar['start_tick']<reference['key_end_tick'] for bar in spans):
                        reference['score_locations'].append(location(observed,'sustain_or_tie_continuation_candidate'))
                        reference.setdefault('correspondence',{'method':'written_pitch_and_sustained_reference_overlap',
                            'pitch_class_agrees':True,'octave_agrees':True,'status':'continuation_only_candidate',
                            'onset_not_located':True,'not_human_verified':True})
                        matched.add(observed['id']);break
            tremolo=[m for m in pdf['marks'] if m['part_id']==part and m['kind']=='written_text' and 'trem' in m['value'].lower()]
            for reference in b:
                if reference['score_locations']:continue
                observed=next((h for h in a if h['concert_pitch_candidate']==reference['pitch'] and reference['midi_measure_candidate'] in h['midi_measure_candidates']
                    and any(t['page']==h['page'] and t['physical_system_index']==h['physical_system_index'] and abs(t['x_pt']-h['x_pt'])<30 for t in tremolo)),None)
                if observed:
                    reference['score_locations'].append(location(observed,'tremolo_realization_candidate'))
                    reference['correspondence']={'method':'written_tremolo_plus_reference_repetition','pitch_class_agrees':True,
                        'octave_agrees':True,'status':'tremolo_realization_candidate','not_human_verified':True}
            for mark in pdf['marks']:
                if mark['kind']=='single_chord_tremolo_candidate' and mark['part_id']==part and mark['page'] in pages:
                    candidates=[n for n in b if n['midi_measure_candidate'] in mark['midi_measure_candidates']
                        and n['pitch'] in mark['pitches'] and n['key_end_tick']-n['start_tick']<=midi['ppq']/4]
                    repeated={pitch for pitch in mark['pitches'] if len({n['start_tick'] for n in candidates if n['pitch']==pitch})>=3}
                    for reference in candidates:
                        if reference['score_locations'] or reference['pitch'] not in repeated:continue
                        observed=next(h for h in a if h['id'] in mark['head_ids'] and h['concert_pitch_candidate']==reference['pitch'])
                        reference['score_locations'].append({**location(observed,'single_chord_tremolo_realization_candidate'),'realization_mark_id':mark['id']})
                        reference['correspondence']={'method':'native_cross_stem_slashes_and_repeated_reference',
                            'pitch_class_agrees':True,'octave_agrees':True,'status':'tremolo_realization_candidate','not_human_verified':True}
                if mark['kind']!='two_note_tremolo_candidate' or mark['part_id']!=part or mark['page'] not in pages:continue
                candidates=[n for n in b if n['midi_measure_candidate'] in mark['midi_measure_candidates']]
                for run in alternating_runs(candidates,mark['left_pitches'],mark['right_pitches']):
                    for reference in run:
                        if reference['score_locations']:continue
                        observed=next((h for h in a if h['id'] in mark['left_head_ids']+mark['right_head_ids'] and h['concert_pitch_candidate']==reference['pitch']),None)
                        if observed:
                            reference['score_locations'].append({**location(observed,'two_note_tremolo_realization_candidate'),'realization_mark_id':mark['id']})
                            reference['correspondence']={'method':'native_half_heads_beam_bridge_and_alternating_reference',
                                'pitch_class_agrees':True,'octave_agrees':True,'status':'tremolo_realization_candidate','not_human_verified':True}
    for n in notes:
        n.setdefault('correspondence',{'status':'reference_only_unlocated','pitch_class_agrees':False,'octave_agrees':False})
    return {'parts':comparisons,'unmatched_pdf_head_ids':[n['id'] for n in pdf['notes'] if n['id'] not in matched]}
