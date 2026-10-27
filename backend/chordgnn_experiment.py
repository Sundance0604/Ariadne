"""Read-only score adapter for optional ChordGNN probes, with source witnesses."""
from bisect import bisect_right
from collections import defaultdict
from fractions import Fraction as F
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET
import zipfile
from functools import lru_cache

ROOT=Path(__file__).resolve().parents[1]
DATA=ROOT/'works/ravel-mother-goose-video'
EXPERIMENT=DATA/'experiments/chordgnn-20261027'
CASES=[
    ('prelude',1,1,12,'前奏：三和弦与半音织体'),
    ('spinning',2,1,16,'纺车舞：快速运动'),
    ('pavane',3,1,12,'帕凡舞：旋律与持续背景'),
    ('beauty',4,1,16,'美女与野兽：声部与和声'),
    ('poucet',5,1,16,'小拇指：流动弦乐'),
    ('pagodes',6,1,16,'宝塔女皇：五声音响'),
    ('garden',7,1,16,'花园：慢速和声'),
    ('garden-climax',7,41,56,'花园结尾：密集配器'),
]

def read(path):return json.loads(Path(path).read_text(encoding='utf-8-sig'))

def write(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

def fingerprint(path):
    path=Path(path)
    with path.open('rb') as f:sha=hashlib.file_digest(f,'sha256').hexdigest()
    return {'path':path.resolve().relative_to(ROOT).as_posix(),'sha256':sha,'bytes':path.stat().st_size}

def protected_files():
    pointer=read(DATA/'playback/current.json')
    folder=ROOT/pointer['path']
    paths=[DATA/'reference/written.json',DATA/'alignment.json',DATA/'measure-map.json',
           DATA/'media-sync.json',DATA/'playback/current.json',
           DATA/'video-export/captions-optimized.json',DATA/'video-export/captions-reviewed.json',
           DATA/'video-export/full-profile.json',folder/'manifest.json',folder/'live.json',
           folder/'analysis.json',folder/'research.json',folder/'evidence.json']
    paths.extend(ROOT/s['path'] for s in read(DATA/'reference/written.json')['sources'])
    return [fingerprint(p) for p in sorted(set(paths))]

def verify_protected(records):
    for record in records:
        if fingerprint(ROOT/record['path'])!=record:raise ValueError('Protected source changed: '+record['path'])


def source_root(path):
    path=Path(path)
    if zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as archive:
            container=ET.fromstring(archive.read('META-INF/container.xml'))
            entry=next(e.attrib['full-path'] for e in container.iter() if e.tag.endswith('rootfile'))
            root=ET.fromstring(archive.read(entry))
    else:root=ET.parse(path).getroot()
    for element in root.iter():element.tag=element.tag.rsplit('}',1)[-1]
    return root


@lru_cache(maxsize=16)
def source_meters(path):
    """Read explicit/inherited meters from every XML part; never guess by length."""
    root=source_root(path)
    votes=defaultdict(list)
    for part in root.findall('part'):
        current=None;declared=None
        for sequence,measure in enumerate(part.findall('measure'),1):
            times=measure.findall('attributes/time')
            if times:
                values=[]
                for time in times:
                    beats=time.findall('beats');types=time.findall('beat-type')
                    if len(beats)!=1 or len(types)!=1:
                        raise ValueError('Composite/free meter needs a separate adapter')
                    values.append(f'{beats[0].text}/{types[0].text}')
                if len(set(values))!=1:raise ValueError('Staff-specific meters disagree')
                current=values[0];declared=sequence
            if current:votes[sequence].append({'part_id':part.attrib['id'],'meter':current,'declared_sequence':declared})
    result={}
    for sequence,entries in votes.items():
        values={v['meter'] for v in entries}
        result[sequence]={'meter':values.pop() if len(values)==1 else None,
                          'xml_part_evidence':entries}
    return result


@lru_cache(maxsize=16)
def source_keys(path):
    result={}
    for part in source_root(path).findall('part'):
        fifths=None;mode=None;diatonic=0;chromatic=0
        for sequence,measure in enumerate(part.findall('measure'),1):
            for attrs in measure.findall('attributes'):
                key=attrs.find('key')
                if key is not None:
                    if key.find('fifths') is None:raise ValueError('Non-traditional signature requires a separate adapter')
                    fifths=int(key.findtext('fifths'));mode=key.findtext('mode')
                transpose=attrs.find('transpose')
                if transpose is not None:
                    diatonic=int(transpose.findtext('diatonic','0'))
                    chromatic=int(transpose.findtext('chromatic','0'))
            # Octave-only transposition leaves the key signature unchanged.
            result[(part.attrib['id'],sequence)]={'written_fifths':fifths,'mode':mode,
                'transpose_diatonic':diatonic,'transpose_chromatic':chromatic,
                'concert_fifths':None if fifths is None else fifths+7*chromatic-12*diatonic}
    return result


def resolve_meters(measures):
    result=[]
    for measure in measures:
        source=source_meters(str(ROOT/measure['source']))[measure['source_sequence']]
        if source['meter'] is None:raise ValueError('Source part meters disagree: '+measure['measure_id'])
        existing=measure.get('time_signature')
        if existing is not None and existing!=source['meter']:
            raise ValueError('Canonical/XML meter mismatch: '+measure['measure_id'])
        result.append({**measure,'time_signature':source['meter'],
            'meter_recovered_from_xml':existing is None,'meter_evidence':source})
    return result

def select_notes(document,movement,first,last):
    """Join only explicit contiguous ties; clip crossing notes with witnesses."""
    measures=[m for m in document['measures'] if m['movement']==movement and first<=m['local_number']<=last]
    if len(measures)!=last-first+1:raise ValueError('Incomplete measure selection')
    start,end=F(measures[0]['start_q']),F(measures[-1]['end_q'])
    groups=defaultdict(list)
    for event in document['events']:
        if event['movement']==movement:
            groups[(event['part_id'],event.get('voice'),event.get('staff'),event['ps'])].append(event)
    notes=[]
    for values in groups.values():
        previous=None
        for event in sorted(values,key=lambda e:(F(e['start_q']),e['id'])):
            a,b=F(event['start_q']),F(event['end_q'])
            if previous and 'stop' in (event.get('tie') or []) and previous['_tie_start'] and F(previous['source_end_q'])==a:
                previous['source_end_q']=str(b)
                previous['source_event_ids'].append(event['id'])
                previous['_tie_start']='start' in (event.get('tie') or [])
            else:
                previous={**event,'source_start_q':str(a),'source_end_q':str(b),
                          'source_event_ids':[event['id']], '_tie_start':'start' in (event.get('tie') or [])}
                notes.append(previous)
    kept=[]
    for note in notes:
        a,b=F(note['source_start_q']),F(note['source_end_q'])
        if b<=start or a>=end:continue
        if float(note['ps'])%1:raise ValueError('Microtonal note requires a separate model adapter')
        kept.append({k:v for k,v in note.items() if k!='_tie_start'} |
                    {'start_q':str(max(a,start)), 'end_q':str(min(b,end)),
                     'clipped_left':a<start,'clipped_right':b>end})
    kept.sort(key=lambda e:(F(e['start_q']),e['ps'],e['id']))
    return measures,kept

def interpolate(points,value,x='midi_seconds',y='audio_seconds'):
    if not points or value<points[0][x] or value>points[-1][x]:return None
    i=max(0,min(len(points)-2,bisect_right([p[x] for p in points],value)-1))
    if len(points)==1:return points[0][y] if value==points[0][x] else None
    a,b=points[i:i+2]
    if b[x]<=a[x]:raise ValueError('Non-increasing reference time')
    return a[y]+(value-a[x])/(b[x]-a[x])*(b[y]-a[y])

def recording_time(alignment,q,movement):
    q=F(q)
    ms=[m for m in alignment['measures'] if m['movement']==movement]
    measure=next((m for m in ms if F(m['start_q'])<=q<F(m['end_q'])),None)
    if measure is None and ms and q==F(ms[-1]['end_q']):measure=ms[-1]
    if measure is None:return None
    # Map the existing symbolic reference coordinate, then use actual DTW knots.
    proportion=float((q-F(measure['start_q']))/(F(measure['end_q'])-F(measure['start_q'])))
    reference=measure['midi_start_seconds']+proportion*(measure['midi_end_seconds']-measure['midi_start_seconds'])
    segment=next((s for s in alignment['time_maps'] if s['movement']==movement),None)
    return interpolate(segment['time_map'],reference) if segment else None

def prepare(output=EXPERIMENT):
    output=Path(output)
    if (output/'manifest.json').exists():raise FileExistsError('Use a new experiment directory; existing evidence is retained')
    document=read(DATA/'reference/written.json');alignment=read(DATA/'alignment.json')
    protected=protected_files();cases=[]
    for identity,movement,first,last,title in CASES:
        # Four bars of score context around the evaluated passage, where present.
        max_bar=max(m['local_number'] for m in document['measures'] if m['movement']==movement)
        lo,hi=max(1,first-4),min(max_bar,last+4)
        measures,notes=select_notes(document,movement,lo,hi)
        target=[m for m in measures if first<=m['local_number']<=last]
        case={'id':identity,'title':title,'movement':movement,'bars':[first,last], 'context_bars':[lo,hi],
              'start_q':target[0]['start_q'],'end_q':target[-1]['end_q'],
              'context_start_q':measures[0]['start_q'],'context_end_q':measures[-1]['end_q'],
              'recording_start_seconds':recording_time(alignment,target[0]['start_q'],movement),
              'recording_end_seconds':recording_time(alignment,target[-1]['end_q'],movement),
              'measures':measures,'notes':notes,'note_count':len(notes),
              'input_basis':'Derived concert-pitch note intervals from current canonical ballet reference, not raw re-parsed alternate XML; explicit ties joined and clipping recorded.'}
        write(output/'inputs'/f'{identity}.json',case)
        cases.append({k:v for k,v in case.items() if k not in ('notes','measures')})
    manifest={'schema_version':1,'date':'2026-10-27','status':'prepared_not_inferred','cases':cases,
              'protected_inputs':protected,'human_signoff':None,'expert_review':None,
              'activation':'No player pointers, alignment, captions or original scores changed.',
              'limitations':['No unreferenced interludes are inferred.','Model candidates and pitch support checks are not harmonic truth or an accuracy rate.']}
    write(output/'manifest.json',manifest);verify_protected(protected)
    return manifest
