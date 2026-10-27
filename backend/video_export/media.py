"""FFmpeg discovery and source-PTS inspection; no assumed constant frame rate."""
import os
from pathlib import Path
import re
import shutil
import subprocess
import json
import hashlib


def ffmpeg(root):
    candidates=[os.environ.get('FFMPEG_BINARY'),shutil.which('ffmpeg')]
    candidates += [str(p) for p in (Path(root)/'.tools/media-runtime/imageio_ffmpeg/binaries').glob('ffmpeg*') if p.suffix in {'.exe',''}]
    try:
        import imageio_ffmpeg
        candidates.append(imageio_ffmpeg.get_ffmpeg_exe())
    except (ImportError,RuntimeError):pass
    for value in candidates:
        if value and Path(value).is_file():return str(Path(value).resolve())
    raise RuntimeError('Install requirements-media.txt or set FFMPEG_BINARY')


def run(command,log=None,cwd=None):
    result=subprocess.run([str(c) for c in command],cwd=cwd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,encoding='utf-8',errors='replace')
    if log:Path(log).write_text(result.stdout+'\n'+result.stderr,encoding='utf-8')
    if result.returncode:raise RuntimeError('Media command failed: '+result.stderr[-3500:])
    return result


def subtitle_font_report(log):
    """A successful libass fallback is not a missing final glyph."""
    pending={};resolved=[];failures=[]
    for line in log.splitlines():
        match=re.search(r'\[([^]]+)\]',line);context=match[1] if match else ''
        if 'Glyph ' in line and 'not found, selecting one more font' in line:
            if context in pending:failures.append(pending[context])
            pending[context]=line
        elif re.search(r'failed to find|fontselect:.*failed',line,re.I):
            failures.append(line)
        elif 'fontselect:' in line and ' -> ' in line and context in pending:
            resolved.append({'request':pending.pop(context),'selected':line})
    return {'resolved_fallbacks':resolved,'unresolved_glyphs':failures+list(pending.values())}


def inspect_frames(binary,path,start,duration,log=None):
    probe=os.environ.get('FFPROBE_BINARY') or shutil.which('ffprobe')
    if probe:
        command=[probe,'-v','error','-select_streams','v:0','-read_intervals',f'{start}%{start+duration}',
            '-show_streams','-show_frames','-show_entries','stream=width,height,time_base,r_frame_rate,avg_frame_rate:frame=best_effort_timestamp_time,duration_time', '-of','json',path]
        data=json.loads(run(command,log).stdout);stream=data['streams'][0]
        frames=[(float(f['best_effort_timestamp_time']),float(f.get('duration_time',f.get('pkt_duration_time',0)))) for f in data['frames'] if 'best_effort_timestamp_time' in f]
        method='ffprobe_frame_timestamps'
    else:
        # Decode this interval only. copyts retains original presentation times;
        # showinfo observes actual frames, including variable-rate sources.
        result=run([binary,'-hide_banner','-nostdin','-copyts','-ss',str(start),'-i',path,'-t',str(start+duration),
            '-map','0:v:0','-vf','showinfo','-an','-fps_mode','passthrough','-f','null','-'],log)
        time_base=re.search(r'config in time_base:\s*(\d+)/(\d+)',result.stderr)
        if time_base:
            unit=int(time_base[1])/int(time_base[2])
            frames=[(int(p)*unit,int(d)*unit) for p,d in re.findall(r'\bn:\s*\d+\s+pts:\s*(-?\d+)\s+pts_time:[\d.eE+\-]+\s+duration:\s*(-?\d+)',result.stderr)]
        else:frames=[(float(p),float(d)) for p,d in re.findall(r'\bn:\s*\d+\s+pts:\s*-?\d+\s+pts_time:([\d.eE+\-]+)\s+duration:\s*-?\d+\s+duration_time:([\d.eE+\-]+)',result.stderr)]
        sizes=re.findall(r'\bs:(\d+)x(\d+)\b',result.stderr)
        if not frames or not sizes:raise ValueError('No decoded video timestamps')
        width,height=map(int,sizes[0]);stream={'width':width,'height':height}
        if time_base:stream['time_base']=f'{time_base[1]}/{time_base[2]}'
        method='ffmpeg_decoded_showinfo'
    frames=[f for f in frames if start-1e-6<=f[0]<start+duration-1e-6]
    pts=[f[0] for f in frames]
    if not pts or any(b<=a for a,b in zip(pts,pts[1:])):raise ValueError('Missing/non-monotonic source presentation timestamps')
    differences=[b-a for a,b in zip(pts,pts[1:])]
    return {'method':method,'stream':stream,'frame_count':len(pts),'first_pts':pts[0],'last_pts':pts[-1],
        'min_frame_delta':min(differences,default=None),'max_frame_delta':max(differences,default=None),
        'frame_pts':pts,'frame_durations':[f[1] for f in frames],
        'timing_policy':'preserve_source_pts_no_fps_filter_no_output_r'}


def audio_hash(binary,path,start=None,duration=None):
    args=[binary,'-v','error','-nostdin']
    if start is not None:args+=['-ss',str(start)]
    args+=['-i',path]
    if duration is not None:args+=['-t',str(duration)]
    args+=['-map','0:a:0','-c:a','copy','-f','framehash','-hash','sha256','-']
    text=run(args).stdout;time_base=re.search(r'#tb 0:\s*(\d+)/(\d+)',text)
    if not time_base:raise ValueError('Missing audio packet time base')
    unit=int(time_base[1])/int(time_base[2]);packets=[]
    for line in text.splitlines():
        if not line.startswith('0,'):continue
        row=[v.strip() for v in line.split(',')];pts=float(row[2])*unit;length=float(row[3])*unit
        # Stream-copy seeks can include decoder preroll from an earlier video
        # keyframe. Compare all packets intersecting the audible output range,
        # including the partial AAC packet crossing zero, not hidden preroll.
        if pts+length>1e-6 and (duration is None or pts<duration-1e-6):packets.append(row[5])
    return 'SHA256='+hashlib.sha256('\n'.join(packets).encode()).hexdigest()
