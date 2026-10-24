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
