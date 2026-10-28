"""Portable, fingerprint-bound review snapshots without processing dependencies."""
from functools import lru_cache
import hashlib
import json
from pathlib import Path


@lru_cache(maxsize=128)
def _verify(path, size, modified, expected):
    with Path(path).open('rb') as stream:
        if hashlib.file_digest(stream,'sha256').hexdigest()!=expected:
            raise ValueError('曲目资料指纹不匹配，请保留结果并核对源材料')


def bundle(root,directory):
    root,directory=Path(root).resolve(),Path(directory).resolve()
    if not directory.is_relative_to(root):raise ValueError('曲目目录越界')
    def bounded(value):
        p=(root/value).resolve()
        if not p.is_relative_to(root):raise ValueError('研究资料路径越界')
        return p
    pointer=json.loads((directory/'playback/current.json').read_text(encoding='utf8'))
    folder=bounded(pointer['path'])
    if not folder.is_relative_to(directory/'playback'):raise ValueError('快照目录越界')
    path=folder/'manifest.json';stat=path.stat()
    _verify(str(path),stat.st_size,stat.st_mtime_ns,pointer['manifest_sha256'])
    manifest=json.loads(path.read_text(encoding='utf8'))
    for row in [*manifest['inputs'], *[{'path':(folder/name).relative_to(root).as_posix(),**meta}
                                     for name,meta in manifest['files'].items()]]:
        p=bounded(row['path']);stat=p.stat()
        if row.get('bytes') is not None and row['bytes']!=stat.st_size:raise ValueError('曲目资料大小发生变化')
        _verify(str(p),stat.st_size,stat.st_mtime_ns,row['sha256'])
    return folder,manifest


def endpoint(root,directory,route,query):
    folder,manifest=bundle(root,directory)
    def read(name):return json.loads((folder/name).read_text(encoding='utf8'))
    names={'/api/analysis':'analysis.json','/api/research':'research.json',
           '/api/musicxml-live':'live.json','/api/visual-panels':'visual-panels.json'}
    if route in names:return read(names[route])
    if route=='/api/musicxml':return {'available':True,'manifest':manifest,**read('research.json')['musicxml']}
    if route=='/api/musicxml-evidence':
        identity=query.get('measure_id',[''])[0];table=read('evidence.json')['measures']
        if identity not in table:raise ValueError('未知曲目小节经过')
        return table[identity]
    if route=='/api/musicxml-artifact':
        name=query.get('name',[''])[0]
        if name not in manifest['files']:raise ValueError('未知研究资料')
        return read(name)
    raise ValueError('未知研究接口')
