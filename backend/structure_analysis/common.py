import hashlib
import json
from pathlib import Path

PITCH_NAMES = ('C','C#','D','Eb','E','F','F#','G','Ab','A','Bb','B')


def pitch_name(pitch):
    return PITCH_NAMES[pitch % 12] + str(pitch // 12 - 1)


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8', newline='\n')


def bounded_path(root, relative):
    from pathlib import PureWindowsPath
    if not isinstance(relative, str) or Path(relative).is_absolute() or PureWindowsPath(relative).drive:
        raise ValueError('Engine paths must be project relative')
    path = (Path(root) / relative).resolve()
    if not path.is_relative_to(Path(root).resolve()):
        raise ValueError('Engine path escapes project')
    return path


def overlap(note, start, end):
    return note['start_tick'] < end and note['sounding_end_tick'] > start


def located(notes):
    return [n for n in notes if n.get('score_locations') and n['correspondence']['pitch_class_agrees']]


def evidence_ids(notes):
    return sorted({n['id'] for n in notes})
