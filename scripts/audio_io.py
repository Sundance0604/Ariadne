"""Local audio input. Decode M4A/MP4 with FFmpeg, keeping source fingerprints."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import uuid

import soundfile as sf

ROOT=Path(__file__).resolve().parents[1]
SUPPORTED={'.mp3','.m4a','.mp4','.wav','.flac','.aif','.aiff','.ogg'}


def find_ffmpeg():
    configured=os.environ.get('FFMPEG_BINARY')
    candidates=[configured,shutil.which('ffmpeg')]
    candidates.extend(str(p) for p in (ROOT/'.tools/media-runtime/imageio_ffmpeg/binaries').glob('ffmpeg*.exe'))
    for candidate in candidates:
        if candidate and Path(candidate).is_file(): return str(Path(candidate).resolve())
    try:
        import imageio_ffmpeg
        candidate=imageio_ffmpeg.get_ffmpeg_exe()
        if Path(candidate).is_file(): return candidate
    except (ImportError,AttributeError,RuntimeError):
        pass
    raise RuntimeError('M4A 解码需要本地 FFmpeg。请配置 FFMPEG_BINARY 或安装项目的媒体解码组件。')


def readable_audio(path):
    path=Path(path).resolve()
    if path.suffix.lower() not in SUPPORTED: raise ValueError(f'不支持的音频格式：{path.suffix}')
    if path.suffix.lower() not in {'.m4a','.mp4'}:
        try:
            sf.info(path)
            return path
        except (RuntimeError,sf.LibsndfileError):
            pass
    with path.open('rb') as stream: key=hashlib.file_digest(stream,'sha256').hexdigest()
    directory=ROOT/'.tools/decoded-audio';directory.mkdir(parents=True,exist_ok=True)
    decoded=directory/f'{key}.wav'
    if decoded.exists():
        sf.info(decoded)
        return decoded
    ffmpeg=find_ffmpeg()
    pending=directory/f'{key}-{uuid.uuid4().hex}.wav'
    command=[ffmpeg,'-nostdin','-hide_banner','-loglevel','error','-i',str(path),
             '-map','0:a:0','-vn','-c:a','pcm_f32le','-y',str(pending)]
    result=subprocess.run(command,capture_output=True,timeout=600)
    if result.returncode:
        pending.unlink(missing_ok=True)
        raise ValueError('本地音频解码失败：'+result.stderr.decode('utf-8',errors='replace')[-1200:])
    info=sf.info(pending)
    if not info.frames: raise ValueError('音频文件没有可解码的采样')
    pending.replace(decoded)
    decoded.with_suffix('.json').write_text(json.dumps({'source_sha256':key,
        'source_suffix':path.suffix.lower(),'decoder':'FFmpeg','ffmpeg_executable':ffmpeg,
        'sample_rate':info.samplerate,'channels':info.channels,'frames':info.frames,
        'duration_seconds':info.duration,'output':'32-bit float PCM WAV; no lossy re-encoding'},indent=2),encoding='utf-8')
    return decoded


def audio_info(path): return sf.info(readable_audio(path))


def read_audio(path,**kwargs): return sf.read(readable_audio(path),**kwargs)


def playback_audio(path):
    path=Path(path)
    # WAV playback also covers ALAC-in-M4A in browsers without an ALAC decoder.
    if path.suffix.lower() in {'.m4a','.mp4'}: return readable_audio(path),'audio/wav'
    mime={'.mp3':'audio/mpeg','.wav':'audio/wav','.flac':'audio/flac',
          '.ogg':'audio/ogg','.aif':'audio/aiff','.aiff':'audio/aiff'}
    return path,mime.get(path.suffix.lower(),'application/octet-stream')
