"""Source-faithful MusicXML events, with music21 semantics and rational clocks."""
from collections import Counter, defaultdict, deque
from fractions import Fraction as F
from pathlib import Path
import warnings
import zipfile
import xml.etree.ElementTree as ET


def fraction(value):
    return F(str(value)).limit_denominator(1000000)


def pitch_record(p):
    return {'name':p.name.replace('-', 'b')+str(p.octave), 'step':p.step,
            'alter':p.accidental.alter if p.accidental else 0, 'octave':p.octave,
            'ps':p.ps, 'pc':p.pitchClass}


def refresh_written_octaves(events):
    """Restore engraving octave without enharmonically respelling D# as Eb."""
    import music21 as m21
    for e in events:
        encoded=e['encoded_pitch']
        if not encoded:e['written_pitch']=None;continue
        delta=sum((1 if s['type']=='up' else -1)*12*((int(s.get('size','8'))-1)//7) for s in e['octave_shift_notation'])
        p=m21.pitch.Pitch();p.step=encoded['step'];p.octave=encoded['octave'];p.accidental=encoded['alter']
        shift=m21.interval.Interval('P'+('-' if delta<0 else '')+str(7*(abs(delta)//12)+1)) if delta else None
        e['written_pitch']=pitch_record(p.transpose(shift)) if shift else encoded


def note_metadata(element):
    return {'instrument_ref':element.find('instrument').get('id') if element.find('instrument') is not None else None,
        'stem':element.findtext('stem'),'beams':[{'number':x.get('number'),'value':x.text} for x in element.findall('beam')],
        'accidental_display':{'value':element.findtext('accidental'),'attributes':element.find('accidental').attrib} if element.find('accidental') is not None else None,
        'chord_member':element.find('chord') is not None,'cue':element.find('cue') is not None,
        'note_attributes':dict(element.attrib)}


def enrich_source_notation(events,path):
    """Refresh display/instrument fields when reusing a fingerprint-checked parse."""
    root,_=xml_root(path);by_id={e['id']:e for e in events};count=0
    for part in root.findall('part'):
        for sequence,measure in enumerate(part.findall('measure'),1):
            for index,note in enumerate(measure.findall('note'),1):
                id=f'{part.get("id")}-xml-m{sequence:04d}-n{index:04d}'
                by_id[id].update(note_metadata(note));count+=1
    if count!=len(events):raise ValueError('Notation enrichment event count differs from source')


def xml_root(path):
    if zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as archive:
            container=ET.fromstring(archive.read('META-INF/container.xml'))
            name=next(e.get('full-path') for e in container.iter() if e.tag.endswith('rootfile'))
            info=archive.getinfo(name)
            if info.file_size>100*1024*1024:raise ValueError('Oversized MusicXML')
            content=archive.read(name)
    else:content=Path(path).read_bytes()
    if b'<!ENTITY' in content:raise ValueError('Entity definitions are not supported')
    root=ET.fromstring(content)
    if root.tag!='score-partwise':raise ValueError('Expected partwise MusicXML')
    return root,content


def ingest(path):
    import music21 as m21
    from music21.musicxml.xmlToM21 import MeasureParser
    root,content=xml_root(path)
    with warnings.catch_warnings(record=True) as caught:
        score=m21.converter.parseData(content.decode('utf-8'),format='musicxml')
    parser=MeasureParser()
    specifications={p.get('id'):p for p in root.findall('part-list/score-part')}
    events=[];directions=[];parts=[];part_measures=[];audit=[];layout=[]
    # music21 separates multi-staff parts. Match by source part/staff order, not names.
    stream_cursor=0
    for part in root.findall('part'):
        pid=part.get('id');spec=specifications[pid]
        staves=max([int(x.text) for x in part.findall('.//staves')]+[1])
        parsed_parts=list(score.parts)[stream_cursor:stream_cursor+staves];stream_cursor+=staves
        parts.append({'id':pid,'name':' '.join((spec.findtext('part-name') or pid).split()),
            'abbreviation':' '.join((spec.findtext('part-abbreviation') or '').split()),'staves':staves,
            'score_instruments':[{'id':x.get('id'),'name':x.findtext('instrument-name'),'sound':x.findtext('instrument-sound')} for x in spec.findall('score-instrument')],
            'music21_parts':[{'id':str(p.id),'class':type(p).__name__,
                'instruments':[{'class':type(i).__name__,'name':i.instrumentName,
                    'transposition':str(i.transposition) if i.transposition else None} for i in p.recurse().getElementsByClass(m21.instrument.Instrument)]} for p in parsed_parts]})
        divisions=1;transposes={};clefs={};keys={};meter=None;page=1;system=0;techniques={}
        for seq,measure in enumerate(part.findall('measure'),1):
            mid=f'xml-m{seq:04d}';cursor=F(0);last_onset=F(0);end=F(0);ni=0
            print_element=measure.find('print')
            if print_element is not None:
                if print_element.get('new-page')=='yes':page+=1;system=0
                elif print_element.get('new-system')=='yes':system+=1
            if pid==next(iter(specifications)):
                layout.append({'measure_id':mid,'sequence':seq,'number':measure.get('number'),
                    'page':page,'system_index':system,'xml_width_tenths':float(measure.get('width','0')),
                    'implicit':measure.get('implicit')=='yes'})
            # Reparse the source at note level to preserve XML voice/staff identities.
            # Whole-score music21 objects provide an independent duration/pitch audit.
            pools=defaultdict(deque)
            for staff,p in enumerate(parsed_parts,1):
                pm=list(p.getElementsByClass(m21.stream.Measure))[seq-1]
                for obj in pm.recurse().notesAndRests:
                    offset=fraction(obj.getOffsetInHierarchy(pm))
                    components=obj.notes if isinstance(obj,m21.chord.ChordBase) else [obj]
                    for component in components:
                        key=(staff,offset,'rest' if component.isRest else
                             component.pitch.nameWithOctave if isinstance(component,m21.note.Note) else 'unpitched')
                        pools[key].append((component,obj))
            for child in measure:
                tag=child.tag
                if tag=='attributes':
                    divisions=int(child.findtext('divisions',str(divisions)))
                    for x in child.findall('transpose'):transposes[x.get('number','all')]=parser.xmlTransposeToInterval(x)
                    for x in child.findall('clef'):clefs[x.get('number','1')]={c.tag:c.text for c in x}
                    for x in child.findall('key'):keys[x.get('number','all')]={c.tag:c.text for c in x}
                    if child.find('time') is not None:meter={c.tag:c.text for c in child.find('time')}
                    directions.append({'id':f'{pid}-{mid}-attr-{len(directions)}','part_id':pid,'measure_id':mid,
                        'offset_q':str(cursor),'kind':'attributes','xml':ET.tostring(child,encoding='unicode')})
                elif tag in {'backup','forward'}:
                    duration=F(child.findtext('duration','0'))/divisions
                    cursor+=duration if tag=='forward' else -duration
                    end=max(end,cursor)
                    if cursor<0:audit.append({'kind':'negative_xml_cursor','part_id':pid,'measure_id':mid,'cursor_q':str(cursor)})
                elif tag=='direction':
                    staff=child.findtext('staff','1');offset=cursor+F(child.findtext('offset','0'))/divisions
                    words=[x.text or '' for x in child.findall('direction-type/words')]
                    for word in words:
                        if any(t in word.lower() for t in ['pizz','arco','sord','div.','unis','trem']):techniques[staff]=word.strip()
                    directions.append({'id':f'{pid}-{mid}-direction-{len(directions)}','part_id':pid,'measure_id':mid,
                        'offset_q':str(offset),'staff':staff,'kind':'direction','words':words,
                        'rehearsal':[x.text for x in child.findall('direction-type/rehearsal')],
                        'octave_shifts':[dict(x.attrib) for x in child.findall('direction-type/octave-shift')],
                        'xml':ET.tostring(child,encoding='unicode')})
                elif tag=='barline':
                    directions.append({'id':f'{pid}-{mid}-barline-{len(directions)}','part_id':pid,'measure_id':mid,
                        'offset_q':str(cursor),'kind':'barline','xml':ET.tostring(child,encoding='unicode')})
                elif tag=='note':
                    ni+=1;staff=child.findtext('staff','1');voice=child.findtext('voice','1')
                    grace=child.find('grace') is not None
                    duration=F(child.findtext('duration','0'))/divisions
                    onset=last_onset if child.find('chord') is not None else cursor
                    if child.find('chord') is None:
                        last_onset=onset
                        if not grace:cursor+=duration
                    end=max(end,onset+duration)
                    parser.divisions=divisions
                    # Music21's own pitch/duration/notation parser, with the original
                    # XML fields retained. No MIDI source is opened here.
                    if child.find('rest') is not None:
                        obj=m21.note.Rest();kind='rest';encoded=None
                    else:
                        obj=parser.xmlToSimpleNote(child,freeSpanners=False)
                        kind='pitched' if isinstance(obj,m21.note.Note) else 'unpitched'
                        encoded=obj.pitch if kind=='pitched' else None
                    transpose=transposes.get(staff,transposes.get('all'))
                    concert=encoded.transpose(transpose) if encoded and transpose else encoded
                    source_key=(int(staff),onset,'rest' if kind=='rest' else encoded.nameWithOctave if encoded else 'unpitched')
                    parsed=pools[source_key].popleft() if pools[source_key] else None
                    if not parsed:audit.append({'kind':'music21_stream_note_not_paired','part_id':pid,'measure_id':mid,'source_note_index':ni,'key':str(source_key)})
                    elif fraction(parsed[0].duration.quarterLength)!=duration:
                        audit.append({'kind':'music21_duration_difference','part_id':pid,'measure_id':mid,'source_note_index':ni,
                            'xml_q':str(duration),'music21_q':str(parsed[0].duration.quarterLength)})
                    hidden=child.findtext('notehead')=='none' or child.get('print-object')=='no'
                    events.append({'id':f'{pid}-{mid}-n{ni:04d}','part_id':pid,'measure_id':mid,'measure_sequence':seq,
                        'source_note_index':ni,'xml_note_id':child.get('id'),'voice_id':f'{pid}:v{voice}',**note_metadata(child),
                        'voice':voice,'staff':int(staff),'kind':kind,'onset_q':str(onset),'duration_q':str(duration),
                        'encoded_pitch':pitch_record(encoded) if encoded else None,'concert_pitch':pitch_record(concert) if concert else None,
                        'transpose':{'semitones':transpose.chromatic.semitones,'diatonic':transpose.diatonic.generic.directed} if transpose else {'semitones':0,'diatonic':1},
                        'tie':[x.get('type') for x in child.findall('tie')],'grace':grace,
                        'type':child.findtext('type'),'dots':len(child.findall('dot')),
                        'time_modification':{x.tag:x.text for x in child.find('time-modification')} if child.find('time-modification') is not None else None,
                        'clef':clefs.get(staff),'key_signature':keys.get(staff,keys.get('all')),'meter':meter,
                        'articulations':[x.tag for x in child.findall('notations/articulations/*')],
                        'notations_xml':[ET.tostring(x,encoding='unicode') for x in child.findall('notations')],
                        'technique_context':techniques.get(staff),'notehead':child.findtext('notehead'),
                        'print_object':child.get('print-object','yes'),'analysis_eligible':kind=='pitched' and not hidden and not grace and duration>0,
                        'exclusion_reason':'invisible_notehead_or_print_object_quarantined' if hidden else 'grace_no_fixed_duration' if grace else None,
                        'xml_position':{k:child.get(k) for k in ['default-x','default-y','relative-x','relative-y'] if child.get(k) is not None},
                        'music21_stream_audit':'paired' if parsed else 'unpaired',
                        'music21_expressions':[type(x).__name__ for x in parsed[1].expressions] if parsed else [],
                        'music21_articulations':[type(x).__name__ for x in parsed[1].articulations] if parsed else []})
            pm=list(parsed_parts[0].getElementsByClass(m21.stream.Measure))[seq-1]
            part_measures.append({'part_id':pid,'measure_id':mid,'duration_q':str(end),
                'music21_part_offset_q':str(fraction(pm.offset)),'meter':meter})
    # Use the maximum explicitly encoded extent for the shared paper sequence.
    # Never concatenate the independently accumulated music21 part offsets.
    lengths=defaultdict(list)
    for pm in part_measures:lengths[pm['measure_id']].append(F(pm['duration_q']))
    measures=[];start=F(0)
    for row in layout:
        duration=max(lengths[row['measure_id']]);values=Counter(map(str,lengths[row['measure_id']]))
        measures.append({**row,'start_q':str(start),'duration_q':str(duration),'part_duration_counts':dict(values)})
        if len(values)>1:audit.append({'kind':'part_measure_duration_difference','measure_id':row['measure_id'],'durations':dict(values)})
        start+=duration
    starts={m['measure_id']:F(m['start_q']) for m in measures}
    for event in events:
        event['score_start_q']=str(starts[event['measure_id']]+F(event['onset_q']))
        event['score_end_q']=str(F(event['score_start_q'])+F(event['duration_q']))
    shifts=defaultdict(list)
    for d in directions:
        if d.get('octave_shifts'):
            for shift in d['octave_shifts']:
                shifts[(d['part_id'],int(d['staff']))].append((starts[d['measure_id']]+F(d['offset_q']),shift))
    for key,values in shifts.items():values.sort(key=lambda pair:pair[0])
    for event in events:
        active_shifts={}
        for at,shift in shifts[(event['part_id'],event['staff'])]:
            if at>F(event['score_start_q']):break
            number=shift.get('number','1')
            if shift['type']=='stop':active_shifts.pop(number,None)
            elif shift['type'] in {'up','down'}:active_shifts[number]=shift
        event['octave_shift_notation']=list(active_shifts.values())
    refresh_written_octaves(events)
    for pm in part_measures:
        if F(pm['music21_part_offset_q'])!=starts[pm['measure_id']]:
            audit.append({'kind':'music21_part_clock_difference',**pm,'canonical_start_q':str(starts[pm['measure_id']])})
    return {'events':events,'parts':parts,'measures':measures,'notation':directions,
        'audit':{'records':audit,'counts':dict(Counter(x['kind'] for x in audit)),
            'music21_warnings':[str(w.message) for w in caught],
            'invisible_events_quarantined':[e['id'] for e in events if e['exclusion_reason']=='invisible_notehead_or_print_object_quarantined'],
            'music21_version':m21.__version__,'source_metadata':{'creator':[x.text for x in root.findall('identification/creator')],
                'source':root.findtext('identification/source'),'software':[x.text for x in root.findall('identification/encoding/software')],
                'encoding_date':root.findtext('identification/encoding/encoding-date')},
            'clock_policy':'shared XML measure sequence and maximum encoded local duration; not music21 per-part global offsets',
            'pitch_policy':'MusicXML pitch data already includes ottava; apply explicit XML transpose exactly once; printed octave stored separately in notation',
            'pedal_policy':'preserve written pedal; no acoustic or MIDI pedal extension invented'}}
