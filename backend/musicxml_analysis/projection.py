"""Reuse score-time evidence while binding a separate performance clock."""
from fractions import Fraction
from functools import lru_cache
from pathlib import Path
import json
from backend.structure_analysis.common import read,digest,bounded_path


def rebind_projection(root,alignment_path,base,template):
    alignment=read(alignment_path)
    reference=alignment['symbolic_reference']
    if reference['sha256']!=template['midi_sha256'] or digest(bounded_path(root,reference['path']))!=reference['sha256']:
        raise ValueError('Shared score requires the same verified reference MIDI')
    measures=base['tables']['measures']['measures']
    if len(alignment['measures'])!=len(measures):raise ValueError('Performance/XML measure structure differs')
    checks=[]
    for index,(old,m) in enumerate(zip(alignment['measures'],measures),1):
        start=abs(old['score_start_quarter']-float(Fraction(m['start_q'])))<1e-7
        duration=abs(old['score_end_quarter']-old['score_start_quarter']-float(Fraction(m['duration_q'])))<1e-7
        if old['sequence_index']!=index or not start or (not duration and index!=len(measures)):
            raise ValueError('Unresolved performance/XML structural clock mismatch')
        checks.append({'measure_id':m['measure_id'],'start_agrees':start,'duration_agrees':duration})
    # Keep the shared conservative end cap. The original DTW metadata rounds
    # MIDI seconds by a few hundredths; never extend its XML coverage from that.
    if reference['duration_seconds']+1e-7<template['reference_end_seconds'] or alignment['measures'][-1]['score_end_quarter']!=template['reference_end_quarter']:
        raise ValueError('Reference clock extent differs')
    return {**template,'audio_sha256':alignment['audio']['sha256'],
        'alignment_sha256':digest(alignment_path),'measure_checks':checks,
        'base_manifest_sha256':digest(bounded_path(root,base['run_path'])/'manifest.json'),
        'status':'separate_performance_DTW_projection_estimated_not_per_note_calibrated',
        'basis':'Independent alignment of this performance audio to the same MIDI; shared XML analysis and tempo clock only.'}


@lru_cache(maxsize=2)
def _load(root_text,work_text,binding_text,base_hash,template_text,token):
    root,work=Path(root_text),Path(work_text)
    binding=json.loads(binding_text);template=json.loads(template_text)
    path=bounded_path(root,binding['path'])
    if not path.is_relative_to(work):raise ValueError('Performance projection outside work')
    if digest(path)!=binding['sha256']:raise ValueError('Performance projection fingerprint mismatch')
    projection=read(path);alignment=read(work/'alignment.json')
    if projection['base_manifest_sha256']!=base_hash or projection['xml_sha256']!=template['xml_sha256']:
        raise ValueError('Performance projection belongs to another XML snapshot')
    if digest(work/'alignment.json')!=projection['alignment_sha256']:
        raise ValueError('Performance projection needs rebuilding for changed alignment')
    for field in ['midi_sha256','ppq','reference_clock','reference_end_seconds','reference_end_quarter','measure_checks']:
        if projection[field]!=template[field]:raise ValueError('Shared symbolic clock differs: '+field)
    for kind,field in [('audio','audio_sha256'),('symbolic_reference','midi_sha256')]:
        if alignment[kind]['sha256']!=projection[field] or digest(bounded_path(root,alignment[kind]['path']))!=projection[field]:
            raise ValueError('Performance projection media/reference fingerprint mismatch')
    return projection


def load_projection(root,work,base,template):
    root,work=Path(root).resolve(),Path(work).resolve()
    binding=read(work/'project.json')['files']['musicxml_recording_projection']
    path=bounded_path(root,binding['path']);alignment=read(work/'alignment.json')
    paths=[path,work/'alignment.json',*[bounded_path(root,alignment[k]['path']) for k in ['audio','symbolic_reference']]]
    token=tuple((p.stat().st_size,p.stat().st_mtime_ns) for p in paths)
    base_hash=digest(bounded_path(root,base['run_path'])/'manifest.json')
    return _load(str(root),str(work),json.dumps(binding,sort_keys=True),base_hash,json.dumps(template,sort_keys=True),token)
