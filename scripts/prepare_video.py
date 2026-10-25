"""Inspect a local video and extract analysis audio; never upload media."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess

from audio_io import find_ffmpeg

ROOT = Path(__file__).resolve().parents[1]


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def probe_video(path):
    probe = os.environ.get('FFPROBE_BINARY') or shutil.which('ffprobe')
    if probe:
        result = subprocess.run([probe, '-v', 'error', '-show_format', '-show_streams',
                                 '-of', 'json', str(path)], capture_output=True, timeout=90)
        if result.returncode:
            raise ValueError(result.stderr.decode('utf-8', errors='replace'))
        data = json.loads(result.stdout)
        return {'method': 'ffprobe', 'duration_seconds': float(data['format']['duration']),
                'streams': data['streams'], 'format': data['format']}
    # Portable imageio-ffmpeg ships FFmpeg only. Preserve its actual diagnostics
    # and report the fallback explicitly rather than claiming ffprobe was used.
    result = subprocess.run([find_ffmpeg(), '-hide_banner', '-i', str(path)],
                            capture_output=True, timeout=90)
    diagnostic = result.stderr.decode('utf-8', errors='replace')
    duration = re.search(r'Duration: (\d+):(\d+):(\d+\.\d+)', diagnostic)
    if not duration:
        raise ValueError('无法读取视频时长：' + diagnostic[-1000:])
    streams = [{'codec_type': kind.lower(), 'codec_name': codec, 'description': line.strip()}
               for line in diagnostic.splitlines()
               if (match := re.search(r'(Video|Audio): ([\w]+)', line))
               for kind, codec in [match.groups()]]
    return {'method': 'ffmpeg_diagnostic_fallback',
            'duration_seconds': sum(float(x)*factor for x, factor in zip(duration.groups(), [3600, 60, 1])),
            'streams': streams, 'diagnostic': diagnostic,
            'warning': 'ffprobe 未安装；当前轨道信息来自 FFmpeg，精细的轨道时间轴待 ffprobe 复核。'}


def prepare(video, output):
    video, output = Path(video).resolve(), Path(output).resolve()
    if not video.is_relative_to(ROOT / 'resource') or not output.is_relative_to(ROOT):
        raise ValueError('视频须位于 resource，输出须位于本地项目内')
    info = probe_video(video)
    if not any(s['codec_type'] == 'video' for s in info['streams']):
        raise ValueError('文件中没有视频轨道')
    output.mkdir(parents=True, exist_ok=True)
    fingerprint = digest(video)
    existing=output/'media-sync.json'
    if existing.exists():
        old=json.loads(existing.read_text(encoding='utf-8'))
        if old.get('video',{}).get('sha256')!=fingerprint:
            raise ValueError('当前目录绑定了其他视频，请使用新的输出目录')
        if old.get('anchors') or old.get('history'):
            return old
    source = {'path': video.relative_to(ROOT).as_posix(), 'sha256': fingerprint,
              'bytes': video.stat().st_size, **info}
    has_audio = any(s['codec_type'] == 'audio' for s in info['streams'])
    decoded = ROOT / '.tools/video-audio' / (fingerprint + '.wav')
    if has_audio and not decoded.exists():
        decoded.parent.mkdir(parents=True, exist_ok=True)
        pending = decoded.with_suffix('.pending.wav')
        result = subprocess.run([find_ffmpeg(), '-nostdin', '-hide_banner', '-loglevel', 'error',
            '-i', str(video), '-map', '0:a:0', '-vn', '-ac', '1', '-ar', '22050',
            '-c:a', 'pcm_s16le', '-y', str(pending)], capture_output=True, timeout=900)
        if result.returncode:
            pending.unlink(missing_ok=True)
            raise ValueError(result.stderr.decode('utf-8', errors='replace')[-1200:])
        pending.replace(decoded)
    warnings = []  # Probe implementation details stay in the audit metadata.
    if not has_audio:
        warnings.append('视频无音轨，不能自动音频匹配；仅支持人工锚点。')
    manifest = {'format_version': '1.0.0', 'masterMediaId': 'performance-video',
        'videoMediaId': 'performance-video', 'masterClock': 'video',
        'method': 'identity', 'matchStatus': 'same_file' if has_audio else 'manual_only',
        'video': source, 'hasAudio': has_audio, 'anchors': [],
        'qualityWarnings': warnings, 'history': [],
        'privacy': {'processing': 'local_only', 'media_uploaded': False},
        'analysisAudio': {'path': decoded.relative_to(ROOT).as_posix(),
                          'sha256': digest(decoded)} if has_audio else None}
    (output / 'media-sync.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    return manifest


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--video', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = prepare(args.video, args.output)
    print(json.dumps({'duration_seconds': result['video']['duration_seconds'],
                      'has_audio': result['hasAudio'], 'analysis_audio': result['analysisAudio']}, ensure_ascii=True))
