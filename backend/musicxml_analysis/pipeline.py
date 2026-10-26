"""Reproducible MusicXML-first build; never edits media or alignment."""
import argparse
from collections import Counter,defaultdict
from datetime import datetime,timezone
from pathlib import Path
import json
from backend.structure_analysis.common import read,write,digest,bounded_path
from .ingest import ingest,refresh_written_octaves,enrich_source_notation
from .mapping import build_mapping
from .analyze import harmony,orchestration,counterpoint
from .form import analyze_form


def save(path,document):
    # Compact large evidence tables; stable IDs, source fields and all records remain.
    path.write_text(json.dumps(document,ensure_ascii=False,separators=(',',':'))+'\n',encoding='utf-8')


def build(root,source,output,reuse_ingest=None):
    root=Path(root).resolve();source=bounded_path(root,source);out=bounded_path(root,output)
    if out.exists():raise ValueError('Preserve prior output; choose a new run directory')
    mapping=read(root/'measure-map.json');study=read(root/'analysis/score-studies/ravel-study-20261026.json')
    pdf=bounded_path(root,mapping['pdf_path'])
    if digest(pdf)!=mapping['pdf_sha256']:raise ValueError('PDF fingerprint mismatch')
    protected=['alignment.json','measure-map.json','metadata/recording.json','analysis/hermeneutic-essays.json',
               'analysis/score-studies/current.json','analysis/engine/current.json']
    before={p:digest(root/p) for p in protected}
    print('Parsing MusicXML with music21; retaining notation and source events.',flush=True)
    if reuse_ingest:
        previous=bounded_path(root,reuse_ingest);manifest=read(previous/'manifest.json')
        if manifest['source']['sha256']!=digest(source):raise ValueError('Ingest reuse source mismatch')
        data={}
        for name,key in [('events','events'),('parts','parts'),('measures','measures'),('notation','notation')]:
            if digest(previous/(name+'.json'))!=manifest['files'][name+'.json']['sha256']:raise ValueError('Ingest reuse fingerprint mismatch')
            data[key]=read(previous/(name+'.json'))[key]
        if digest(previous/'parse-audit.json')!=manifest['files']['parse-audit.json']['sha256']:raise ValueError('Ingest audit fingerprint mismatch')
        data['audit']=read(previous/'parse-audit.json')
        refresh_written_octaves(data['events'])
        enrich_source_notation(data['events'],source)
    else:data=ingest(source)
    links=build_mapping(data,mapping,digest(source),digest(pdf),study,root)
    audit=links['edition_audit']
    if audit['layout_difference_count'] or any(s['status']!='agrees' for s in audit['score_window_checks']):
        # Keep reviewable intake, but refuse main-flow activation on mismatched versions.
        out.mkdir(parents=True);save(out/'intake-rejected.json',{'mapping':links,'parse_audit':data['audit']})
        raise ValueError('MusicXML/PDF sample or layout mismatch; intake retained, no activation')
    print('Layout and key score samples agree. Building harmony and voice evidence.',flush=True)
    h=harmony(data);print('Harmony windows:',len(h['windows']),flush=True)
    o=orchestration(data);cp=counterpoint(data);print('Voice-pair intervals:',len(cp['intervals']),flush=True)
    form=analyze_form(data,h,o,study)
    out.mkdir(parents=True)
    outputs={'events.json':{'events':data['events']},'parts.json':{'parts':data['parts']},
        'measures.json':{'measures':data['measures']},'notation.json':{'notation':data['notation']},
        'parse-audit.json':data['audit'],'pdf-map.json':links,'harmony.json':h,
        'orchestration.json':o,'counterpoint.json':cp,'form.json':form}
    for name,document in outputs.items():save(out/name,document)
    summary={'parts':len(data['parts']),'measures':len(data['measures']),'events':len(data['events']),
        'event_kinds':dict(Counter(e['kind'] for e in data['events'])),
        'eligible_pitched_events':sum(e['analysis_eligible'] for e in data['events']),
        'invisible_events_quarantined':len(data['audit']['invisible_events_quarantined']),
        'harmony_windows':len(h['windows']),'complete_chord_identity_windows':sum(bool(w['sonority']['chord']) for w in h['windows']),
        'inversions':dict(Counter(str(w['sonority']['chord']['inversion']) for w in h['windows'] if w['sonority']['chord'])),
        'orchestration_measures':len(o['measures']),'voice_pair_intervals':len(cp['intervals']),
        'voice_motions':len(cp['motions']),'chordal_interval_attacks':len(cp['chordal_intervals']),
        'motif_comparisons':len(form['motif_comparisons']),'cadence_candidates':len(form['cadence_candidates']),
        'human_signoffs':0,'expert_reviews':0}
    write(out/'summary.json',summary)
    if any(digest(root/p)!=before[p] for p in protected):raise ValueError('Protected playback or research inputs changed')
    manifest={'schema_version':'1.0.0','track_id':'ravel-left-hand','work_id':study['work_id'],
        'source':{'path':source.relative_to(root).as_posix(),'sha256':digest(source),'bytes':source.stat().st_size},
        'pdf':{'path':mapping['pdf_path'],'sha256':digest(pdf)},'geometry_sha256':digest(root/'measure-map.json'),
        'music21_version':data['audit']['music21_version'],'method_version':'musicxml-first-1',
        'code_files':{str(Path(__file__).with_name(name).relative_to(root)).replace('\\','/'):digest(Path(__file__).with_name(name)) for name in ['ingest.py','analyze.py','mapping.py','form.py','pipeline.py']},
        'ingest_reused_from':reuse_ingest,
        'created_at':datetime.now(timezone.utc).isoformat(),
        'files':{name:{'sha256':digest(out/name),'bytes':(out/name).stat().st_size} for name in [*outputs,'summary.json']},
        'protected_inputs':before,'analysis_basis':'MusicXML score events; no MIDI note correspondence required',
        'review_status':'computed_full_score_with_agent_sample_checks_human_signoff_pending'}
    write(out/'manifest.json',manifest)
    # Publish the pointer last; an interrupted build never becomes the main source.
    write(root/'analysis/musicxml/current.json',{'path':out.relative_to(root).as_posix(),'manifest_sha256':digest(out/'manifest.json')})
    print(json.dumps(summary,ensure_ascii=True),flush=True)
    return summary


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--source',required=True);parser.add_argument('--output',required=True)
    parser.add_argument('--reuse-ingest',help='Fingerprint-checked prior run; only parsing is reused, analyses are recomputed')
    args=parser.parse_args();build(Path(__file__).resolve().parents[2],args.source,args.output,args.reuse_ingest)


if __name__=='__main__':main()
