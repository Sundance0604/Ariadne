"""Validate precomputed interpretations/projection without processing libraries."""
from pathlib import Path
from functools import lru_cache
from backend.structure_analysis.common import read,digest,bounded_path


@lru_cache(maxsize=1)
def _load(root_text,work_text,pointer_text,base_hash,token):
    import json
    root=Path(root_text);work=Path(work_text);pointer=json.loads(pointer_text);run=bounded_path(root,pointer['path'])
    if not run.is_relative_to(work/'analysis/musicxml'):raise ValueError('Interpretation outside work')
    if digest(run/'manifest.json')!=pointer['manifest_sha256']:raise ValueError('Interpretation manifest changed')
    manifest=read(run/'manifest.json')
    if manifest['base_manifest_sha256']!=base_hash:raise ValueError('Interpretation belongs to another XML snapshot')
    tables={}
    for name,binding in manifest['files'].items():
        path=bounded_path(run,name)
        if digest(path)!=binding['sha256']:raise ValueError('Interpretation evidence changed')
        tables[name.removesuffix('.json')]=read(path)
    projection=tables['recording-projection'];alignment=read(work/'alignment.json')
    if digest(work/'alignment.json')!=projection['alignment_sha256']:raise ValueError('Recording projection needs rebuilding for changed alignment')
    for kind,binding in [('audio','audio_sha256'),('symbolic_reference','midi_sha256')]:
        if digest(bounded_path(root,alignment[kind]['path']))!=projection[binding]:raise ValueError('Projection media/reference fingerprint mismatch')
    return {'manifest':manifest,'tables':tables,'path':pointer['path']}


def load_live(root,work,base):
    root=Path(root).resolve();work=Path(work).resolve();path=work/'analysis/musicxml/interpretation-current.json'
    if not path.exists():return None
    pointer=read(path);run=bounded_path(root,pointer['path']);manifest=read(run/'manifest.json')
    alignment=read(work/'alignment.json')
    paths=[path,run/'manifest.json',work/'alignment.json',*[bounded_path(run,n) for n in manifest['files']],
        bounded_path(root,alignment['audio']['path']),bounded_path(root,alignment['symbolic_reference']['path'])]
    token=tuple((p.stat().st_size,p.stat().st_mtime_ns) for p in paths)
    base_hash=digest(bounded_path(root,base['run_path'])/'manifest.json')
    return _load(str(root),str(work),path.read_text(encoding='utf-8'),base_hash,token)
