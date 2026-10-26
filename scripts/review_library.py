"""Resolve only locally configured tracks; query values never become paths."""
import json
from pathlib import Path


def library(root):
    path = root / 'library.json'
    return json.loads(path.read_text(encoding='utf-8')) if path.exists() else {
        'default_track': 'ravel-left-hand',
        'tracks': [{'id': 'ravel-left-hand', 'title': '拉威尔 · 左手钢琴协奏曲', 'data_root': '.'}]}


def track_context(root, track_id=None):
    root = root.resolve()
    catalog = library(root)
    track_id = track_id or catalog['default_track']
    track = next((item for item in catalog['tracks'] if item['id'] == track_id), None)
    if track is None:
        raise ValueError('未知曲目')
    directory = (root / track['data_root']).resolve()
    if not directory.is_relative_to(root):
        raise ValueError('曲目目录必须位于当前项目内')
    return track, directory


def page_count(mapping):
    return int(mapping.get('page_count') or max(m['page_number'] for m in mapping['measures']))


def score_directory(root, directory):
    """Share score research explicitly; performance timelines remain separate."""
    root, directory = Path(root).resolve(), Path(directory).resolve()
    if not directory.is_relative_to(root):
        raise ValueError('曲目目录必须位于当前项目内')
    catalog = library(root)
    track = next((t for t in catalog['tracks'] if (root/t['data_root']).resolve()==directory),None)
    if not track or not track.get('score_source'):
        return directory
    source, shared = track_context(root,track['score_source'])
    if shared==directory or source.get('score_source'):
        raise ValueError('共享谱面来源不能循环或多级转接')
    def read(folder,name):
        return json.loads((folder/name).read_text(encoding='utf-8'))
    for name,field in [('measure-map.json','pdf_sha256'),('alignment.json','symbolic_reference')]:
        actual, expected = read(directory,name)[field], read(shared,name)[field]
        if field=='symbolic_reference':actual,expected=actual['sha256'],expected['sha256']
        if actual!=expected:
            raise ValueError('共享谱面与当前PDF或符号参考不匹配')
    if read(directory,'metadata/recording.json')['work']['work_id']!=read(shared,'metadata/recording.json')['work']['work_id']:
        raise ValueError('共享谱面属于其他作品')
    return shared
