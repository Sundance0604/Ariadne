import unittest,copy,uuid,shutil
from pathlib import Path
from backend.video_export.visual_panels import part_registry,panel_layout,validate_settings,save_settings,load_settings,activity_payload

class VisualPanels(unittest.TestCase):
    def test_quartet_is_four_independent_parts_without_keyboard_or_solo_assumption(self):
        parts=part_registry([{'id':str(i),'name':name} for i,name in enumerate(['Violin I','Violin II','Viola','Cello'])])
        self.assertEqual([p['family'] for p in parts],['弦乐']*4)
        self.assertEqual(len({p['color'] for p in parts}),4)
        self.assertEqual(len({p['flow_group'] for p in parts}),4)
        self.assertFalse(any(p['role']=='solo' for p in parts))
        self.assertLess(panel_layout({},parts=parts)['panels']['orchestration']['height'],150)

    def test_violin_concerto_uses_explicit_solo_identity_not_piano_or_first_violins(self):
        parts=part_registry([{'id':'solo-vln','name':'Violin','role':'solo'},
            {'id':'orch-vln1','name':'Violin I'},{'id':'flute','name':'Flute'}])
        self.assertEqual([p['id'] for p in parts if p['role']=='solo'],['solo-vln'])
        self.assertEqual([p['id'] for p in parts],['solo-vln','orch-vln1','flute'])

    def test_whole_panel_sizes_round_trip_and_remain_inside_frame(self):
        value={'flow':{'scale':.75},'orchestration':{'scale':1.5}}
        folder=Path(__file__).resolve().parents[1]/'tmp'/('visual-panels-'+uuid.uuid4().hex);folder.mkdir(parents=True)
        try:
            path=folder/'settings.json';save_settings(value,path);settings=load_settings(path)
            layout=panel_layout(settings)
            self.assertEqual(layout['panels']['flow']['width'],300)
            self.assertEqual(layout['panels']['orchestration']['width'],780)
            for box in layout['panels'].values():self.assertLessEqual(box['x']+box['width'],1896)
        finally:
            self.assertTrue(folder.resolve().is_relative_to(Path(__file__).resolve().parents[1]/'tmp'));shutil.rmtree(folder)
        for bad in [0,float('nan'),True,2]:
            with self.assertRaises(ValueError):validate_settings({'flow':{'scale':bad}})

    def test_unpitched_activity_uses_original_dtw_and_never_receives_pitch_class(self):
        alignment={'time_map':[{'midi_seconds':0,'audio_seconds':10},{'midi_seconds':4,'audio_seconds':18}]}
        e={'id':'drum','kind':'unpitched','part_id':'dr','staff':'1','voice':'1','score_start_q':'2','score_end_q':'3','tie':[]}
        data=activity_payload({'notes':[],'coverage':{}},{'measures':{'m':{'events':[e]}}},
            {'quarantine':{'sequences':[]},'measures':[]},alignment,[],10,18)
        self.assertEqual((data['events'][0]['start_seconds'],data['events'][0]['end_seconds']),(12,13))
        self.assertNotIn('pc',data['events'][0]);self.assertNotIn('pitch',data['events'][0])

if __name__=='__main__':unittest.main()
