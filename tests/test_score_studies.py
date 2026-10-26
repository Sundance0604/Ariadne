import copy
from fractions import Fraction
from pathlib import Path
import sys
import unittest
import threading
from urllib.request import urlopen
from urllib.error import HTTPError
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'scripts'))
from backend.score_studies import load_studies,derive,validate_document,pitch_number
from backend.structure_analysis.common import read
from scripts.classify_score_diagnostics import classify
from research_data import load_research


class ScoreStudies(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.study=load_studies(ROOT,ROOT);cls.doc=cls.study['document']
        cls.windows={w['id']:w for w in cls.doc['windows']}

    def test_score_only_loader_has_no_automatic_engine_dependency(self):
        with patch('backend.structure_analysis.store.load_bundle',side_effect=RuntimeError('Engine must not be called')):
            self.assertEqual(len(load_studies(ROOT,ROOT)['document']['windows']),3)

    def test_first_bar_sextuplets_fill_three_quarters_and_keep_fourth_collection(self):
        w=self.windows['opening-bar-1'];moving=next(v for v in w['voices'] if v['id']=='db-moving')
        self.assertEqual(len(moving['notes']),18)
        self.assertEqual(sum(Fraction(n['duration_q']) for n in moving['notes']),3)
        d=derive(w);self.assertTrue(all(v['pitch_classes']==[2,4,7,9] and v['bass']==28 for v in d['verticals']))
        self.assertTrue(all(pitch_number(n['concert'])==pitch_number(n['written'])-12 for n in moving['notes']))

    def test_octave_doubling_and_parallel_sixths_are_not_four_independent_lines(self):
        pairs=derive(self.windows['horn-bassoon-bars-10-11'])['voice_pairs']
        horn=next(p for p in pairs if p['voices']==['horn-upper','horn-lower'])
        bassoon=next(p for p in pairs if p['voices']==['bassoon-upper','bassoon-lower'])
        self.assertEqual({p['semitones'] for p in horn['samples']},{12})
        self.assertEqual({p['semitones'] for p in bassoon['samples']},{8,9})

    def test_passing_dissonance_is_local_while_E_is_structural_in_other_layer(self):
        pairs=derive(self.windows['horn-bassoon-bars-10-11'])['voice_pairs']
        p=next(p for p in pairs if p['voices']==['horn-upper','bassoon-upper'])
        selected=[s for s in p['samples'] if s['onset_q'] in ['4','9/2','5']]
        self.assertEqual([(s['a'],s['semitones']) for s in selected],[('F4',19),('E4',18),('D4',16)])
        pedal=next(p for p in pairs if p['voices']==['horn-upper','contra-pedal'])
        self.assertEqual(next(s['semitones'] for s in pedal['samples'] if s['onset_q']=='9/2'),36)

    def test_I64_shape_does_not_prove_cadential_resolution(self):
        d=derive(self.windows['strings-return-two-attacks'])
        self.assertEqual(d['attacks'][0]['pitch_classes'],[2,6,9]);self.assertEqual(d['attacks'][0]['bass'],57)
        self.assertEqual(d['attacks'][1]['pitch_classes'],[4,8,9,11])
        self.assertEqual({m['semitones'] for m in d['motion']},{0,2})
        self.assertFalse(any(m['from']=='D4' and m['to']=='C#4' for m in d['motion']))

    def test_timing_and_transposition_errors_cannot_be_hidden_by_a_readable_paragraph(self):
        for change in ['duration','pitch','human']:
            bad=copy.deepcopy(self.doc)
            if change=='duration':bad['windows'][0]['voices'][0]['notes'][0]['duration_q']='2'
            if change=='pitch':bad['windows'][1]['voices'][0]['notes'][0]['concert']='E4'
            if change=='human':bad['windows'][0]['review']['human_status']='verified'
            with self.subTest(change=change),self.assertRaises(ValueError):validate_document(bad,ROOT)

    def test_source_edition_and_hierarchy_are_bound_without_forcing_a_sonata(self):
        bad=copy.deepcopy(self.doc);bad['form']['units'][1]['parent_id']='missing'
        with self.assertRaises(ValueError):validate_document(bad,ROOT)
        self.assertEqual({u['level'] for u in self.doc['form']['units']},{'work','section','subsection','phrase'})
        self.assertFalse(self.doc['research_policy']['global_match_clearance_required'])
        self.assertEqual(self.doc['research_policy']['human_review_count'],0)
        self.assertTrue(any(e['dimension']=='orchestration' and e['pages']==[51,51] and not e['window_ids'] for e in self.doc['events']))

    def test_studies_still_reach_player_when_optional_engine_is_rejected(self):
        with patch('backend.structure_analysis.store.load_bundle',side_effect=ValueError('source changed')):
            data=load_research(ROOT)
        self.assertEqual(len([e for e in data['events'] if e.get('analysis_origin')=='score_study']),15)
        self.assertEqual(len(data['essays']),5)
        self.assertTrue(all(e['verification']['score']=='agent_score_checked' for e in data['events'] if e.get('analysis_origin')=='score_study'))

    def test_diagnostic_buckets_cover_records_but_do_not_claim_they_are_all_errors(self):
        pointer=read(ROOT/'analysis/engine/current.json');data=classify(ROOT/pointer['run_path'])
        self.assertEqual(len(data['records']),439)
        self.assertEqual(sum(data['counts'].values()),439)
        self.assertEqual(data['counts']['confirmed_error'],0)
        self.assertEqual(data['automatic_corrections'],0)
        self.assertEqual(len({r['id'] for r in data['records']}),439)
        self.assertTrue(all(r['automatic_action']=='none' for r in data['records']))

    def test_actual_study_HTTP_and_bound_image_without_engine_dependency(self):
        import serve_review
        import json
        server=serve_review.ReviewServer(('127.0.0.1',0),serve_review.Handler)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        url=f'http://127.0.0.1:{server.server_port}'
        try:
            with patch('backend.structure_analysis.store.load_bundle',side_effect=RuntimeError('not a study dependency')):
                with urlopen(url+'/api/score-studies?track=ravel-left-hand') as response:
                    data=json.load(response);self.assertTrue(data['available']);self.assertEqual(len(data['document']['windows']),3)
                with urlopen(url+'/api/score-study-image?track=ravel-left-hand&window_id=opening-bar-1') as response:
                    self.assertEqual(response.headers['Content-Type'],'image/png');self.assertEqual(response.read(8),b'\x89PNG\r\n\x1a\n')
            with self.assertRaises(HTTPError) as error:urlopen(url+'/api/score-study-image?track=ravel-left-hand&window_id=../../secret')
            self.assertEqual(error.exception.code,404);error.exception.close()
            with urlopen(url+'/api/score-studies?track=lark-ascending') as response:self.assertFalse(json.load(response)['available'])
        finally:server.shutdown();server.server_close();thread.join()


if __name__=='__main__':unittest.main()
