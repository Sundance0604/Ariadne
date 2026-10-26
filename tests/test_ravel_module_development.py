"""Use actual Ravel XML and original Motif records; no media fingerprints."""
import copy
from pathlib import Path
import unittest
from backend.video_export.content import read
from backend.musicxml_analysis.ravel_development import load_profile

ROOT=Path(__file__).resolve().parents[1]


class RavelDevelopment(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path=read(ROOT/'analysis/musicxml/current.json')['path']
        cls.bundle={'manifest':read(ROOT/path/'manifest.json'),'run_path':path,
                    'tables':{name:read(ROOT/path/f'{name}.json') for name in ['events','form']}}

    def test_actual_xml_supports_local_correspondence_but_no_theme_identity(self):
        profile=load_profile(ROOT,ROOT,self.bundle)
        relation=profile['relations'][0]
        self.assertEqual(relation['intervals'],[0,-5,4,-2])
        self.assertEqual(relation['duration_ratios'],['1','1','6','2','16'])
        self.assertEqual(relation['transposition_semitones'],24)
        self.assertEqual(relation['theme_identity'],'unassigned')
        self.assertIsNone(relation['human_signoff'])
        self.assertGreater(len(relation['simultaneous_doublings']),1)

    def test_other_work_and_changed_note_evidence_do_not_activate_profile(self):
        self.assertIsNone(load_profile(ROOT,ROOT/'works/lark-ascending',self.bundle))
        broken=copy.deepcopy(self.bundle)
        note=next(e for e in broken['tables']['events']['events'] if e['id']=='P1-xml-m0067-n0006')
        note['concert_pitch']['ps']+=1
        with self.assertRaises(ValueError):load_profile(ROOT,ROOT,broken)


if __name__=='__main__':unittest.main()
