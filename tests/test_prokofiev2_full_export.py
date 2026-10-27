"""Prepared full-video resources are complete without encoding a finished film."""
from pathlib import Path
from collections import Counter
from unittest.mock import patch
import json,unittest
from backend.video_export.editor import prepare
from backend.video_export.content import read,FORBIDDEN
from backend.video_export.pipeline import validate_config,verify_bindings
from backend.video_export.visual_full import full_layout,stage_visuals,composition_command
from backend.video_export.visual_panels import load_settings

ROOT=Path(__file__).resolve().parents[1];DATA=ROOT/'works/prokofiev-piano-concerto-2/video-export';PACKAGE=ROOT/'output/video-export/prokofiev2-full-001'

@unittest.skipUnless((PACKAGE/'source-frame-timestamps.json').exists(),'local full export package not prepared')
class FullExport(unittest.TestCase):
    def test_all_sections_and_performer_paragraphs_have_editable_source_bound_captions(self):
        document=read(DATA/'captions-editable.json');config,events,excluded=prepare(document,PACKAGE)
        self.assertFalse(excluded)
        base=[r for r in document['字幕'] if not r.get('接续分析')]
        self.assertEqual(len(base),200)
        self.assertEqual(Counter(r['栏目'] for r in base),{'和弦':38,'配器':38,'声部关系与复调':38,'曲式与主题发展':38,'导聆':38,'诠释':9,'片头':1})
        if document.get('空白补充'):
            self.assertEqual(len(events),218)
            self.assertEqual({r['接续分析']['原空白排名'] for r in document['字幕'] if r.get('接续分析')},set(range(1,11)))
        self.assertTrue(all(not FORBIDDEN.search(e['text']) for e in events));validate_config(config)
        self.assertTrue(config['interpretation_hides_score'])
        self.assertEqual(set(config['interpretation_suppresses_slots']),{'harmony','orchestration','counterpoint','form','guide'})

    def test_pdf_and_original_score_renderer_are_prepared_without_fabricated_cadenza_lines(self):
        self.assertEqual(len(list((PACKAGE/'score').glob('page-*.png'))),168)
        plan=read(PACKAGE/'score/plan.json')
        cadenza=[e for e in plan['events'] if 1639<e['videoTime']<1645]
        self.assertTrue(cadenza);self.assertTrue(all(e['playhead'] is None for e in cadenza))
        self.assertTrue(any(e['highlight'] for e in cadenza))
        self.assertTrue(all(not e['visible'] for e in plan['events'] if 710<e['videoTime']<726))

    def test_size_adjustments_reflow_pdf_and_subtitles_without_overlaps(self):
        config=read(PACKAGE/'export-config.json');registry=read(PACKAGE/'visuals/registry.json')
        for scale in [.6,1,1.5]:
            settings=load_settings();settings['flow']['scale']=scale;settings['orchestration']['scale']=scale
            actual=full_layout(config,settings,registry);validate_config(actual)
            top=max(p['y']+p['height'] for p in actual['visual_layout']['panels'].values())
            self.assertGreater(actual['layout']['score']['y'],top)
            self.assertEqual(actual['layout']['score']['x']+actual['layout']['score']['w'],config['width'])
            self.assertLessEqual(actual['layout']['counterpoint']['y']-actual['layout']['harmony']['y'],176)

    def test_renderer_and_payload_bindings_are_complete_but_no_finished_video_is_created(self):
        manifest=verify_bindings(PACKAGE);self.assertFalse(manifest['video_encoding_performed'])
        self.assertTrue((PACKAGE/'visuals/renderer/stream.mjs').is_file())
        self.assertEqual(len(read(PACKAGE/'visuals/activity.json')['flow_groups']),5)
        self.assertEqual(len(read(PACKAGE/'visuals/activity.json')['parts']),19)
        self.assertEqual(len(read(PACKAGE/'export-config.json')['chapters']),4)
        # A later user-initiated render is allowed; package preparation itself
        # remains separate from the rendering entry point.
        config=read(PACKAGE/'export-config.json')
        visual={**config['visual_layout'],'fps':30,'duration':1948.2,'frame_count':58446,'last_duration_seconds':.032}
        with patch.object(Path,'write_text'):
            command=composition_command(PACKAGE,PACKAGE/'command-test-only',config,visual)
        self.assertEqual(command[command.index('-c:a')+1],'copy')
        self.assertEqual(command[command.index('-fps_mode:v')+1],'passthrough')
        self.assertEqual(command[command.index('-enc_time_base:v')+1],'demux')

if __name__=='__main__':unittest.main()
