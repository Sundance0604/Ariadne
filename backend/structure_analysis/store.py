"""Read-only, standard-library playback adapter and evidence integrity checks."""
from pathlib import Path
from .common import read,digest,bounded_path

DATA_FILES={'profile.json','pdf-observations.json','notes.json','correspondence.json','harmony.json',
            'counterpoint.json','instrument-activity.json','theme-identities.json','form.json','hud-events.json','validation.json'}


def validate_run(run,root,check_sources=True):
    run=Path(run);root=Path(root).resolve();manifest=read(run/'manifest.json')
    if set(manifest.get('files',{}))!=DATA_FILES:raise ValueError('Engine artifact set incomplete or unexpected')
    for name,sha in manifest['files'].items():
        if digest(run/name)!=sha:raise ValueError('Frozen engine artifact fingerprint mismatch: '+name)
    if check_sources:
        for source in manifest['sources'].values():
            if digest(bounded_path(root,source['path']))!=source['sha256']:raise ValueError('Engine source fingerprint mismatch')
    notes=read(run/'notes.json')['notes'];byid={n['id']:n for n in notes}
    heads={n['id']:n for n in read(run/'pdf-observations.json')['notes']}
    if len(byid)!=len(notes):raise ValueError('Duplicate engine note IDs')
    for n in notes:
        if not n['start_tick']<n['key_end_tick']<=n['sounding_end_tick']:raise ValueError('Invalid note interval')
        for loc in n['score_locations']:
            if loc['id'] not in heads:raise ValueError('Unknown native PDF notehead')
            if heads[loc['id']]['part_id']!=n['part_id']:raise ValueError('Cross-instrument note attribution')
        if n['correspondence']['octave_agrees'] and not any(heads[l['id']]['concert_pitch_candidate']==n['pitch'] for l in n['score_locations']):
            raise ValueError('Octave agreement lacks matching native decoded pitch')
    records={}
    for name in DATA_FILES:
        data=read(run/name);index={}
        for values in data.values():
            if isinstance(values,list):
                for row in values:
                    if isinstance(row,dict) and 'id' in row:
                        if row['id'] in index:raise ValueError('Duplicate intermediate evidence ID')
                        index[row['id']]=row
                        if 'note_ids' in row and not set(row['note_ids'])<=byid.keys():raise ValueError('Intermediate record has orphan notes')
        records[name[:-5]]=index
    events=read(run/'hud-events.json')['events'];seen=set()
    for e in events:
        if e['id'] in seen:raise ValueError('Duplicate engine events')
        seen.add(e['id'])
        if not set(e['raw_evidence_ids'])<=byid.keys():raise ValueError('Engine event cites nonexistent notes')
        for ref in e['evidence_records']:
            if ref['file'] not in records or ref['id'] not in records[ref['file']]:raise ValueError('Unknown intermediate evidence reference')
        if not set(e['related_structure_ids'])<=records['form'].keys():raise ValueError('Unknown related structure')
        if e['verification']['score']=='verified' or e['verification']['timing']=='verified':raise ValueError('Generated candidates cannot self-certify')
        for span in e['score_spans']:
            if not span['reference_start_tick']<span['reference_end_tick']:raise ValueError('Invalid reference interval')
            if span['reference_sha256']!=manifest['sources']['midi']['sha256']:raise ValueError('Event/reference identity mismatch')
    units=read(run/'form.json')['units'];ids={u['id'] for u in units}
    for u in units:
        if u['parent_id'] is not None and u['parent_id'] not in ids:raise ValueError('Orphan formal unit')
        visited=set();p=u
        while p['parent_id'] is not None:
            if p['id'] in visited:raise ValueError('Formal hierarchy cycle')
            visited.add(p['id']);p=next(x for x in units if x['id']==p['parent_id'])
    return manifest


def load_bundle(root,directory,mapping=None):
    pointer=Path(directory)/'analysis/engine/current.json'
    if not pointer.exists():return None
    current=read(pointer);run=bounded_path(root,current['run_path'])
    if not run.is_relative_to(Path(directory).resolve()/'analysis'/'engine'):raise ValueError('Engine run outside this work')
    if digest(run/'manifest.json')!=current['manifest_sha256']:raise ValueError('Engine manifest mismatch')
    manifest=validate_run(run,root)
    if mapping and manifest['sources']['pdf']['sha256']!=mapping['pdf_sha256']:raise ValueError('Engine/PDF edition mismatch')
    return {'manifest':manifest,'run_path':run.relative_to(Path(root).resolve()).as_posix(),
        'events':read(run/'hud-events.json')['events'],'reference_clock':read(run/'notes.json')['reference_clock'],
        'summary':read(run/'validation.json')}


def event_evidence(root,directory,event_id):
    bundle=load_bundle(root,directory)
    if not bundle:raise ValueError('No score-analysis engine run for this work')
    event=next((e for e in bundle['events'] if e['id']==event_id),None)
    if not event:raise ValueError('Unknown engine event')
    run=bounded_path(root,bundle['run_path']);note_ids=set(event['raw_evidence_ids'])
    note_document=read(run/'notes.json')
    notes=sorted([n for n in note_document['notes'] if n['id'] in note_ids],key=lambda n:(n['start_tick'],n['pitch'],n['part_id']))
    records=[]
    for ref in event['evidence_records']:
        data=read(run/(ref['file']+'.json'))
        for values in data.values():
            if isinstance(values,list):records.extend(v for v in values if isinstance(v,dict) and v.get('id')==ref['id'])
    note_parts={n['part_id'] for n in notes};pages={l['page'] for n in notes for l in n['score_locations']}
    marks=[m for m in read(run/'pdf-observations.json')['marks'] if m['part_id'] in note_parts and m['page'] in pages]
    head_ids={loc['id'] for n in notes for loc in n['score_locations']}
    heads=[h for h in read(run/'pdf-observations.json')['notes'] if h['id'] in head_ids]
    hierarchy=[];patterns=[]
    if event['dimension']=='form':
        units=read(run/'form.json')['units'];wanted={r['id'] for r in records if r.get('level')}
        while True:
            expanded=wanted|{u['id'] for u in units if u['parent_id'] in wanted}
            if expanded==wanted:break
            wanted=expanded
        hierarchy=[u for u in units if u['id'] in wanted]
        motif_ids={u['motif_id'] for u in hierarchy if u.get('motif_id')}
        patterns=[m for m in read(run/'theme-identities.json')['motifs'] if m['id'] in motif_ids]
    reviews=[];review_warning=None
    pointer=Path(directory)/'analysis/engine/reviews/current.json'
    if pointer.exists():
        try:
            binding=read(pointer);casebook=bounded_path(root,binding['path'])
            if not casebook.is_relative_to(Path(directory).resolve()/'analysis/engine/reviews'):raise ValueError('Review outside work review directory')
            if digest(casebook)!=binding['sha256']:raise ValueError('Score-review fingerprint mismatch')
            document=read(casebook)
            if document['run_manifest_sha256']!=digest(run/'manifest.json'):raise ValueError('Score review belongs to a different frozen round')
            for source in document.get('additional_score_sources',[]):
                if digest(bounded_path(root,source['path']))!=source['sha256']:raise ValueError('Comparison-score fingerprint mismatch')
            reviews=[c for c in document['cases'] if event_id in c['event_ids']]
        except (OSError,KeyError,TypeError,ValueError) as error:review_warning=str(error)
    return {'event_id':event_id,'run_id':bundle['manifest']['run_id'],'ppq':note_document['ppq'],'facts':{'notes':notes,'written_marks':marks},
        'native_noteheads':heads,'instrument_definitions':[p for p in read(run/'profile.json')['parts'] if p['id'] in note_parts],
        'hierarchy':hierarchy,'motif_patterns':patterns,
        'case_reviews':reviews,'review_warning':review_warning,
        'derivations':records,'uncertainties':event['uncertainties'],'related_structure_ids':event['related_structure_ids'],
        'status':'algorithm_candidates_with_traceable_observations_not_expert_verified'}
