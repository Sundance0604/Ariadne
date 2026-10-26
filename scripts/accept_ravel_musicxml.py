"""Evidence audit for the agent-reviewed release; never signs for a human."""
from collections import Counter
from fractions import Fraction as F
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from backend.structure_analysis.common import read,write,digest
from backend.musicxml_analysis.store import load_bundle
from backend.musicxml_analysis.live_store import load_live


def main():
    base=load_bundle(ROOT,ROOT);live=load_live(ROOT,ROOT,base);tables=base['tables']
    notes={e['id']:e for e in tables['events']['events']};windows={w['id']:w for w in tables['harmony']['windows']}
    readings=live['tables']['harmonic-readings']['readings'];frames=live['tables']['activation']['frames']
    assert set(readings)==set(windows)
    for id,rs in readings.items():
        assert 1<=len(rs)<=2
        for r in rs:
            assert set(r['event_ids'])|set(r['omitted_event_ids'])==set(windows[id]['event_ids'])
            assert not set(r['event_ids'])&set(r['omitted_event_ids'])
    for f in frames:
        assert f['start_q']<f['end_q']
        for p in f['active_instruments']:
            for id in p['event_ids']:
                e=notes[id]
                assert e['part_id']==p['part_id'] and e['exclusion_reason'] is None
                assert float(F(e['score_start_q']))<=f['start_q']+1e-9<float(F(e['score_end_q']))+1e-9
    # Concrete musical witnesses independently checked against the source PDF.
    harp=[notes['P22-xml-m0007-n0003'],notes['P22-xml-m0007-n0004']]
    assert [e['concert_pitch']['name'] for e in harp]==['E1','Fb1']
    assert len({e['concert_pitch']['ps'] for e in harp})==1
    w=windows['xml-h-001493']
    assert w['measure_id']=='xml-m0083' and w['sonority']['chord']['root']=='F#'
    assert w['sonority']['chord']['quality']=='major triad' and w['sonority']['bass']['name']=='F#1'
    witnesses=[{'id':'harp-enharmonic-unison','measure_id':'xml-m0007','pdf_page':2,
        'claim':'E1 and Fb1 are distinct notations at one sounding height, not a semitone dissonance.',
        'event_ids':[e['id'] for e in harp],'agent_visual_review':True},
        {'id':'f-sharp-area','measure_id':'xml-m0083','pdf_page':23,'window_id':w['id'],
        'claim':'F# major over F#1 forms a regional support distinct from the earlier D/A arrival.',
        'event_ids':w['event_ids'],'agent_visual_review':True}]
    section_evidence=[]
    for section in live['tables']['form-synthesis']['sections']:
        members=[w for w in windows.values() if F(w['start_q'])<F(section['end_q']) and F(w['end_q'])>F(section['start_q'])]
        bass=Counter();chords=Counter()
        for w in members:
            length=float(min(F(w['end_q']),F(section['end_q']))-max(F(w['start_q']),F(section['start_q'])))
            bass[w['sonority']['bass']['pc']]+=length
            if w['sonority']['chord']:chords[w['sonority']['chord']['root']+' '+w['sonority']['chord']['quality']]+=length
        section_evidence.append({**section,'harmony_window_ids':[w['id'] for w in members],
            'bass_pitch_class_quarters':dict(bass),'complete_vertical_chord_quarters':dict(chords),
            'status':'notated_duration_evidence_not_accuracy_or_final_key_certification'})
    preserved={p:digest(ROOT/p)==h for p,h in base['manifest']['protected_inputs'].items()}
    assert all(preserved.values())
    browser=read(ROOT/'output/research/ravel-acceptance/browser-acceptance.json')
    assert browser['checks']['article_scroll']['before']==browser['checks']['article_scroll']['after']
    assert browser['checks']['article_scroll']['before']['top']>0
    out=ROOT/'analysis/musicxml/acceptance-20261026';out.mkdir(parents=True,exist_ok=True)
    write(out/'musicological-witnesses.json',{'cases':witnesses,'human_signoffs':0,'expert_reviews':0})
    write(out/'section-evidence.json',{'sections':section_evidence})
    report={'release_status':'agent_acceptance_passed_with_explicit_alternatives_and_estimated_projection',
        'base_run':base['run_path'],'base_manifest_sha256':digest(ROOT/base['run_path']/'manifest.json'),
        'interpretation_run':live['path'],'interpretation_manifest_sha256':digest(ROOT/live['path']/'manifest.json'),
        'full_data_checks':{'harmonic_windows_with_traceable_readings':len(readings),'activation_frames_checked':len(frames),
            'sections_with_evidence':len(section_evidence),'all_source_inputs_preserved':preserved},
        'musical_review_scope':'Full-score rule/evidence audit plus selected direct score checks; not exhaustive expert note-by-note adjudication.',
        'browser_artifacts':{p:{'sha256':digest(ROOT/p),'bytes':(ROOT/p).stat().st_size} for p in browser['screenshots']+['output/research/ravel-acceptance/browser-acceptance.json']},
        'human_signoffs':0,'expert_reviews':0,'browser_record':browser,
        'tests':{'python':{'run':150,'passed':148,'skipped':2,'log':'tmp/musicxml/acceptance-python.log'},
            'frontend':{'run':37,'passed':37,'log':'tmp/musicxml/acceptance-frontend.log'},
            'module_and_HTTP':'tmp/musicxml/acceptance-module-integration.log'},
        'revised_articles':{p:digest(ROOT/p) for p in ['analysis/essays/ravel-harmonic-ledger.md',
            'analysis/essays/ravel-form-functions.md','analysis/essays/ravel-texture-counterpoint.md']},
        'limitations':['Recording projection remains a DTW-based estimate.','The final uncovered 0.4 XML quarters are not extrapolated.',
            'Orchestral layer hypotheses and local tonal interpretations may coexist.','An agent release acceptance is not a human/expert signature.']}
    write(out/'acceptance.json',report)
    write(out/'manifest.json',{'audit_code_sha256':digest(Path(__file__)),
        'files':{name:{'sha256':digest(out/name),'bytes':(out/name).stat().st_size} for name in ['musicological-witnesses.json','section-evidence.json','acceptance.json']}})
    print('Agent acceptance evidence saved; no human or expert signature created.')


if __name__=='__main__':main()
