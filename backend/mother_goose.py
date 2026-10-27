"""Read the separate, fingerprint-bound Mother Goose ballet playback edition.

No optional music-analysis packages are imported by the HTTP playback process.
The suite research and the other performance editions remain independent.
"""
from functools import lru_cache
import hashlib
import json
from pathlib import Path


@lru_cache(maxsize=96)
def _verified(path, size, modified, expected):
    with Path(path).open('rb') as stream:
        if hashlib.file_digest(stream, 'sha256').hexdigest() != expected:
            raise ValueError('鹅妈妈资料指纹不匹配，请保留旧结果并重新生成对应版本')
    return True


def bundle(root, directory):
    root, directory = Path(root).resolve(), Path(directory).resolve()
    if not directory.is_relative_to(root):
        raise ValueError('研究目录越界')
    pointer = json.loads((directory/'playback/current.json').read_text(encoding='utf-8'))
    folder = (root/pointer['path']).resolve()
    if not folder.is_relative_to(directory/'playback'):
        raise ValueError('鹅妈妈快照目录越界')
    manifest_path = folder/'manifest.json'
    stat = manifest_path.stat()
    _verified(str(manifest_path), stat.st_size, stat.st_mtime_ns, pointer['manifest_sha256'])
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    for item in [*manifest['inputs'], *[{'path':str((folder/name).relative_to(root)).replace('\\','/'), **meta} for name,meta in manifest['files'].items()]]:
        path = (root/item['path']).resolve()
        if not path.is_relative_to(root):raise ValueError('研究来源路径越界')
        stat = path.stat()
        if item.get('bytes') is not None and item['bytes'] != stat.st_size:raise ValueError('鹅妈妈资料大小发生变化')
        _verified(str(path), stat.st_size, stat.st_mtime_ns, item['sha256'])
    return folder, manifest


def endpoint(root, directory, route, query):
    folder, manifest = bundle(root, directory)
    def read(name):return json.loads((folder/name).read_text(encoding='utf-8'))
    names = {'/api/analysis':'analysis.json', '/api/research':'research.json', '/api/musicxml-live':'live.json'}
    if route in names:return read(names[route])
    if route == '/api/musicxml':
        d=read('research.json')
        return {'available':True,'manifest':manifest, **d['musicxml']}
    if route == '/api/musicxml-evidence':
        identity=query.get('measure_id',[''])[0]
        table=read('evidence.json')
        if identity not in table['measures']:raise ValueError('未知鹅妈妈小节')
        return table['measures'][identity]
    if route == '/api/musicxml-artifact':
        name=query.get('name',[''])[0]
        if name not in manifest['files']:raise ValueError('未知研究文件')
        return read(name)
    raise ValueError('未知鹅妈妈研究接口')
