"""Record input provenance and final candidate processing state for the Lark."""
from pathlib import Path
import json
import hashlib
from datetime import datetime,timezone,timedelta
from collections import Counter

ROOT=Path(__file__).resolve().parents[1]
DATA=ROOT/'works/lark-ascending'


def main():
    alignment=json.loads((DATA/'alignment.json').read_text(encoding='utf8'))
    mapping=json.loads((DATA/'measure-map.json').read_text(encoding='utf8'))
    sources=[('mp3',alignment['audio']['path']),('midi',alignment['symbolic_reference']['path']),
             ('pdf',mapping['pdf_path']),('markdown','resource/Lark Ascending/Lark_Ascending_Full_Analysis.md')]
    inputs=[]
    for kind,path in sources:
        file=ROOT/path
        inputs.append(dict(kind=kind,path=path,bytes=file.stat().st_size,
                           sha256=hashlib.sha256(file.read_bytes()).hexdigest()))
    result=dict(format_version='1.0.0',project_id='lark-ascending-local-test',
        title='沃恩·威廉斯《云雀高飞》',
        created_at=datetime.now(timezone(timedelta(hours=8))).isoformat(),inputs=inputs,
        privacy=dict(processing='local_only',media_uploaded=False),
        files=dict(alignment='works/lark-ascending/alignment.json',measure_map='works/lark-ascending/measure-map.json',
                   recording_metadata='works/lark-ascending/metadata/recording.json',
                   analysis_annotations='works/lark-ascending/analysis/annotations.json'),
        processing_status=dict(input_audit='complete',midi_auxiliary_full_recording_alignment='candidate_ready',
            pdf_geometry_mapping='bar_and_shared_region_candidates',pdf_omr='not_run',
            human_listening_review='pending',musicological_analysis='editorially_revised_by_separate_workflow',
            m4a='suspended_by_user'),
        review_counts=dict(Counter(m['review_status'] for m in alignment['measures'])),
        pdf_resolution_counts=dict(Counter(m['resolution'] for m in mapping['measures'])),
        limitations=['Only supplied MIDI-assisted route completed; no full PDF OMR-only result.',
            '93 MIDI candidate intervals share cadenza/system rectangles; no invented barlines.',
            'Pages 27–28 have a contour-derived candidate page boundary requiring human review.',
            'Audio listening and browser playback not human-verified.'])
    (DATA/'project.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf8')


if __name__=='__main__':main()
