"""Read the Prokofiev II web-review snapshot with playback-only dependencies."""
from functools import lru_cache
import hashlib,json
from pathlib import Path

@lru_cache(maxsize=96)
def _verify(path,size,modified,expected):
    with Path(path).open('rb') as stream:
        if hashlib.file_digest(stream,'sha256').hexdigest()!=expected:
            raise ValueError('普罗第二钢协资料指纹不匹配，请保留已有结果并核对素材')
    return True

def bundle(root,directory):
    root,directory=Path(root).resolve(),Path(directory).resolve()
    if not directory.is_relative_to(root):raise ValueError('曲目目录越界')
    def bounded(value):
        p=(root/value).resolve()
        if not p.is_relative_to(root):raise ValueError('研究资料路径越界')
        return p
    pointer=json.loads((directory/'playback/current.json').read_text(encoding='utf8'))
    folder=bounded(pointer['path'])
    if not folder.is_relative_to(directory/'playback'):raise ValueError('研究快照目录越界')
    manifest_path=folder/'manifest.json';stat=manifest_path.stat()
    _verify(str(manifest_path),stat.st_size,stat.st_mtime_ns,pointer['manifest_sha256'])
    manifest=json.loads(manifest_path.read_text(encoding='utf8'))
    records=manifest['inputs']+[{'path':(folder/name).relative_to(root).as_posix(),**meta} for name,meta in manifest['files'].items()]
    for entry in records:
        path=bounded(entry['path']);stat=path.stat()
        if entry.get('bytes') is not None and entry['bytes']!=stat.st_size:raise ValueError('普罗第二钢协资料大小已变化')
        _verify(str(path),stat.st_size,stat.st_mtime_ns,entry['sha256'])
    return folder,manifest

def endpoint(root,directory,route,query):
    folder,manifest=bundle(root,directory)
    names={'/api/analysis':'analysis.json','/api/research':'research.json'}
    if 'live.json' in manifest['files']:names['/api/musicxml-live']='live.json'
    if route in names:return json.loads((folder/names[route]).read_text(encoding='utf8'))
    if route=='/api/musicxml' and 'live.json' in manifest['files']:
        research=json.loads((folder/'research.json').read_text(encoding='utf8'))
        return {'available':True,'manifest':manifest,**research['musicxml']}
    if route=='/api/musicxml-evidence' and 'evidence.json' in manifest['files']:
        identity=query.get('measure_id',[''])[0]
        table=json.loads((folder/'evidence.json').read_text(encoding='utf8'))['measures']
        if identity not in table:raise ValueError('未知普罗第二钢协小节')
        return table[identity]
    # Older score-review snapshots remain readable without invented live data.
    if route in {'/api/musicxml','/api/musicxml-live'}:
        return {'available':False,'reason':'当前为曲谱同步核查；四维谱面分析与全文在研究区展示。'}
    if route=='/api/musicxml-artifact':
        name=query.get('name',[''])[0]
        if name not in manifest['files']:raise ValueError('未知研究资料')
        return json.loads((folder/name).read_text(encoding='utf8'))
    raise ValueError('当前同步版本未提供该逐音证据接口')
