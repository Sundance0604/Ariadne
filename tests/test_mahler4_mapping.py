"""Validate the real scan candidate data without asserting unreviewed accuracy."""
import hashlib
import json
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]


class MahlerMappingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mapping=json.loads((ROOT/'works/mahler-4/measure-map.json').read_text(encoding='utf-8'))
        cls.alignment=json.loads((ROOT/'works/mahler-4/alignment.json').read_text(encoding='utf-8'))

    def test_real_geometry_spans_all_score_pages_and_is_fingerprint_bound(self):
        with (ROOT/self.mapping['pdf_path']).open('rb') as stream:
            self.assertEqual(hashlib.file_digest(stream,'sha256').hexdigest(),self.mapping['pdf_sha256'])
        self.assertEqual(self.mapping['symbolic_reference_sha256'],self.alignment['symbolic_reference']['sha256'])
        regions=self.mapping['score_regions']
        self.assertEqual({r['page_number'] for r in regions},set(range(5,128)))
        self.assertEqual(len({r['region_id'] for r in regions}),len(regions))
        for region in regions+self.mapping['bar_regions']:
            x,y,w,h=region['rect_pt']
            self.assertTrue(0<=x<x+w<=region['page_width_pt']+1)
            self.assertTrue(0<=y<y+h<=region['page_height_pt']+1)
            self.assertLess(region['midi_start_seconds'],region['midi_end_seconds'])
            self.assertIsNone(region['printed_measure_number'])

    def test_finer_candidates_have_observed_parent_geometry_and_stricter_evidence(self):
        parents={r['region_id']:r for r in self.mapping['score_regions']}
        self.assertGreater(len(self.mapping['bar_regions']),100)
        for region in self.mapping['bar_regions']:
            parent=parents[region['parent_region_id']]
            self.assertEqual(region['page_number'],parent['page_number'])
            x,y,w,h=region['rect_pt'];px,py,pw,ph=parent['rect_pt']
            self.assertTrue(px<=x<x+w<=px+pw+1)
            self.assertEqual((y,h),(py,ph))
            self.assertGreaterEqual(region['quality_metrics']['diatonic_histogram_cosine'],.65)
            self.assertLessEqual(region['quality_metrics']['reference_boundary_variant_spread_seconds'],1)

    def test_unreviewed_results_do_not_become_confirmed_measure_numbers(self):
        regions=self.mapping['score_regions']
        self.assertTrue(any(r['review_status']=='needs_review' for r in regions))
        self.assertTrue(any(r['stable_candidate'] for r in regions))
        self.assertEqual(self.mapping['algorithm']['human_verified_regions'],0)
        self.assertTrue(all(r['resolution']=='system_candidate' for r in regions))


if __name__=='__main__':unittest.main()
