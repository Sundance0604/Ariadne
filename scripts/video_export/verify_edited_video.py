"""Verify an edited continuous film against its source clock and saved document."""
import argparse,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from backend.video_export.content import read,write,digest,FORBIDDEN,normalized
from backend.video_export.editor import prepare
from backend.video_export.media import ffmpeg,run,inspect_frames,audio_hash,subtitle_font_report
from backend.video_export.subtitles import analysis_ass


def verify(package,revision):
    package=Path(package).resolve();revision=Path(revision).resolve()
    report=read(revision/'review-report.json');output=revision/report['output']['video']
    config=read(revision/'config.json');events=read(revision/'annotations.json')['events']
    document=read(revision/'editing.json')
    rebuilt,expected_events,_=prepare(document,package)
    duration=config['segments'][0]['video_end']-config['segments'][0]['video_start']
    binary=ffmpeg(ROOT)
    actual=inspect_frames(binary,output,0,duration+.1,revision/'verified-pts.log')
    source=read(package/'source-frame-timestamps.json')[0]
    offset=config['segments'][0]['video_start']
    expected=[t-offset for t in source['frame_pts']]
    errors=[abs(a-b) for a,b in zip(expected,actual['frame_pts'])]
    audio_source=audio_hash(binary,package/'performance.mp4',offset,duration)
    audio_output=audio_hash(binary,output,duration=duration)
    ass=(revision/'analysis.ass').read_text(encoding='utf-8-sig')
    canonical=analysis_ass(expected_events,rebuilt)
    font_report=subtitle_font_report((revision/'export.log').read_text(encoding='utf-8'))
    run([binary,'-v','error','-nostdin','-i',output,'-map','0:v:0','-map','0:a:0','-f','null','-'],revision/'verified-decode.log')
    metadata=run([binary,'-v','error','-i',output,'-f','ffmetadata','-']).stdout
    (revision/'verified-chapters.ffmetadata').write_text(metadata,encoding='utf-8')
    chapters=config.get('chapters',[])
    chapter_matches=metadata.count('[CHAPTER]')==len(chapters)
    for chapter,block in zip(chapters,metadata.split('[CHAPTER]')[1:]):
        values=dict(line.split('=',1) for line in block.splitlines() if '=' in line)
        numerator,denominator=map(int,values['TIMEBASE'].split('/'))
        chapter_matches &= abs(int(values['START'])*numerator/denominator-chapter['start'])<.002
        chapter_matches &= values.get('title')==chapter['title']
    intros=[e for e in events if e.get('phase')=='intro']
    first_clear=[next((t for t in actual['frame_pts'] if t>=e['output_end']-1e-6),duration) for e in intros]
    checks={'all_frames_decode':True,'source_pts_preserved':len(expected)==actual['frame_count'] and max(errors,default=1)<.002,
        'original_aac_unchanged':audio_source==audio_output,'captions_match_editing_document':events==expected_events and ass==canonical,
        'config_matches_document':config==rebuilt,'no_research_placeholders':not FORBIDDEN.search(normalized(ass)),
        'no_unresolved_glyphs':not font_report['unresolved_glyphs'],'chapter_titles_and_starts_match':bool(chapter_matches),
        'intro_three_seconds_clear':bool(intros) and all(t<=config['music_start_video']-offset-3+1e-6 for t in first_clear)}
    result={'status':'automated_checks_passed_visual_review_required' if all(checks.values()) else 'verification_failed',
        'checks':checks,'video':str(output.relative_to(ROOT)),'sha256':digest(output),'bytes':output.stat().st_size,
        'frames':actual['frame_count'],'max_pts_error_seconds':max(errors,default=None),'caption_count':len(events),
        'chapter_count':len(chapters),'audio_sha256':audio_output,'fonts':font_report,
        'editing_sha256':digest(revision/'editing.json'),'config_sha256':digest(revision/'config.json'),
        'ass_sha256':digest(revision/'analysis.ass'),'human_signoff':None,'expert_review':None}
    write(revision/'verification.json',result)
    if not all(checks.values()):raise ValueError('Edited video verification failed; see verification.json')
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--package',required=True,type=Path);parser.add_argument('--revision',required=True,type=Path)
    args=parser.parse_args();print(json.dumps(verify(args.package,args.revision),ensure_ascii=False))
