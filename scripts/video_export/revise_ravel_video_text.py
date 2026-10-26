"""Revise the existing 95-second sample's text only; reuse its PDF and source PTS."""
from pathlib import Path
import re
import sys
import subprocess
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from backend.video_export.content import read,write
from backend.video_export.subtitles import analysis_ass
from backend.video_export.media import ffmpeg,run


def build(package):
    package=Path(package).resolve();config=read(package/'export-config-kaiti.json')
    data=read(package/'web-captions.json');events=data['events']
    document=(ROOT/'resource/ravel left hand piano concerto/analysis/Ravel_Left_Hand_Concerto_Full_Analysis.md').read_text(encoding='utf-8')
    overview=re.search(r'## 1\.[^\n]*\n(.*?)(?=\n## 2\.)',document,re.S)[1].strip()
    essay=(ROOT/'analysis/essays/ravel-tonal-emergence.md').read_text(encoding='utf-8')
    interpretation=essay.split('\n\n')[1].strip()
    extra=[
        {'id':'web-intro','slot':'interpretation','phase':'intro','video_start':.8,'video_end':24.48,
         'text':'拉威尔《左手钢琴协奏曲》\n'+overview,'display_title':'一只手如何形成完整的音乐空间','source':'web full-analysis section 1'},
        {'id':'web-interpretation','slot':'interpretation','phase':'performance','video_start':59,'video_end':69,
         'text':interpretation,'display_title':'诠释：从模糊的支点到主调','source':'web essay first complete paragraph'},
    ]
    for e in events+extra:e.update(output_start=e['video_start'],output_end=e['video_end'])
    (package/'analysis-kaiti.ass').write_text(analysis_ass(events+extra,config),encoding='utf-8-sig')
    write(package/'annotations-kaiti.json',{'events':events+extra,'omitted_research_status_lines':data['omitted']})
    # Reuse the existing fixed PDF viewport, page events, highlight and playhead.
    graph=(package/'compose-000.ffgraph').read_text(encoding='utf8').replace("filename='analysis.ass'","filename='analysis-kaiti.ass'")
    (package/'compose-kaiti.ffgraph').write_text(graph,encoding='utf8')
    pts=read(package/'source-frame-timestamps.json')[0]
    last_duration=pts['frame_durations'][-1] or pts['min_frame_delta']
    bsf=f'setts=duration=if(eq(N\\,{pts["frame_count"]-1})\\,{last_duration:.9f}/TB\\,DURATION)'
    binary=ffmpeg(ROOT)
    command=[binary,'-hide_banner','-nostdin','-y','-i','performance.mp4','-safe','0','-f','concat','-i','score/pages.ffconcat',
        '-filter_complex_script','compose-kaiti.ffgraph','-map','[out]','-map','0:a:0','-t','95',
        '-c:v','libx264','-crf','18','-preset','fast','-bf','0','-fps_mode:v','passthrough',
        '-enc_time_base:v','demux','-bsf:v',bsf,'-c:a','copy','-map_metadata','-1','-movflags','+faststart','guided-performance-kaiti.mp4']
    print('Rendering the same 0-95 second performance with full web captions and bold KaiTi.',flush=True)
    run(command,package/'compose-kaiti.log',package)
    print(package/'guided-performance-kaiti.mp4')


if __name__=='__main__':build(sys.argv[1] if len(sys.argv)>1 else ROOT/'output/video-export/ravel-demo')
