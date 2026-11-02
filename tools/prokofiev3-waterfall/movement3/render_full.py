"""Restartable 4K60 export, with identical absolute-time effects at joins."""
from __future__ import annotations

import json
import os
import shutil
from hashlib import sha256
from math import ceil
from pathlib import Path
import subprocess

HERE=Path(__file__).resolve().parent
RENDERER=HERE.parents[1]/'prokofiev2-waterfall/gpu-vfx-flow'
PARTS=HERE/'render-parts'
NODE=Path(os.environ.get('PROK3_NODE') or shutil.which('node') or 'node')
FFMPEG=Path(os.environ.get('PROK3_FFMPEG') or shutil.which('ffmpeg') or 'ffmpeg')
TIMELINE=HERE/'prokofiev3-movement3-full.timeline.json'
FINAL=HERE/'prokofiev3-movement3-full-4k60.mp4'


def run(command,env=None):
    subprocess.run(command,cwd=RENDERER,env=env,check=True)


def main():
    timeline=json.loads(TIMELINE.read_text())
    audio=Path(os.environ.get('PROK3_M3_AUDIO_PATH', timeline['sources']['audio']['path']))
    if not audio.is_absolute():
        audio=HERE/audio
    duration=float(timeline['render_interval']['duration_seconds'])
    lead=float(timeline['intro']['lead_in_seconds'])
    PARTS.mkdir(exist_ok=True)
    signature=sha256()
    for path in [TIMELINE,RENDERER/'dist/waterfall.js',
                 RENDERER/'visual-preset.json',RENDERER/'visual-style.json']:
        signature.update(path.read_bytes())
    signature.update(b'3840x2160/60fps/crf16/ultrafast')
    old=PARTS/'signature.sha256'
    digest=signature.hexdigest()
    if old.exists() and old.read_text()!=digest:
        raise RuntimeError('Scene changed since partial export; remove old parts first')
    old.write_text(digest)
    env=os.environ.copy()
    env.update(WATERFALL_WIDTH='3840',WATERFALL_HEIGHT='2160',
               WATERFALL_VIDEO_ONLY='1',WATERFALL_CRF='16',
               WATERFALL_ENCODING_PRESET='ultrafast',
               WATERFALL_ENCODER_THREADS='4',
               WATERFALL_VERIFIED_AUDIO_SHA256=timeline['sources']['audio']['sha256'],
               FFMPEG_BINARY=str(FFMPEG))
    outputs=[]
    for start in range(0,ceil(duration),20):
        end=min(start+20,duration)
        output=PARTS/f'part-{start:03d}.mp4'
        outputs.append(output)
        if output.exists() and output.stat().st_size>100_000:
            print(f'skip {output.name}',flush=True)
            continue
        print(f'render {start:03d}-{end:06.1f}',flush=True)
        env['WATERFALL_START']=str(start)
        env['WATERFALL_DURATION']=str(end-start)
        temp=output.with_suffix('.incomplete.mp4')
        try:
            run([str(NODE),'export.mjs',str(PARTS/f'part-{start:03d}.json'),
                 str(audio),str(temp),'60'],env)
            temp.replace(output)
        finally:
            temp.unlink(missing_ok=True)
    concat=PARTS/'concat.txt'
    concat.write_text(''.join(f"file '{p.resolve()}'\n" for p in outputs))
    temp=PARTS/'final.incomplete.mp4'
    run([str(FFMPEG),'-hide_banner','-loglevel','error','-nostdin','-y',
         '-f','concat','-safe','0','-i',str(concat),'-i',str(audio),
         '-filter_complex',f'[1:a]adelay={round(lead*1000)}:all=1,apad=whole_dur={duration}[a]',
         '-map','0:v:0','-map','[a]','-c:v','copy','-c:a','aac','-b:a','256k',
         '-t',str(duration),'-movflags','+faststart',str(temp)])
    temp.replace(FINAL)
    print(f'Complete: {FINAL}',flush=True)


if __name__=='__main__':main()
