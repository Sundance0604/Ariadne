"""Coverage is measured from actual captions; music supplies scheduling bounds."""
import copy,unittest
from backend.video_export.coverage import merge_intervals,blank_intervals,caption_coverage,schedule_entries
from backend.video_export.presentation import presentation_config


class Coverage(unittest.TestCase):
    def setUp(self):
        self.config=presentation_config({'width':1920,'height':1080,'font':'KaiTi','font_size':32,
            'yellow':'#FFDF42','web_video_layout':True,'segments':[{'video_start':0,'video_end':120}],
            'layout':{'guide':{'x':40,'y':320,'w':600,'h':168,'font_size':32},
                      'interpretation':{'x':220,'y':336,'w':1480,'h':720,'font_size':44}}},
            {'分析':{},'诠释':{}})
        self.plan={'gaps':[{'rank':1,'start_seconds':15,'end_seconds':70}],
            'entries':[{'id':'follow','gap_rank':1,'start_sequence':2,'last_sequence':2,
                'column':'导聆','text':'声音交接以后，继续追踪较慢的旋律。'}]}
        self.alignment={'measures':[{'sequence_index':1,'movement':1,'local_number':'1','start_seconds':10,'end_seconds':14,'pdf_page':1},
            {'sequence_index':2,'movement':1,'local_number':'2','start_seconds':23,'end_seconds':70,'pdf_page':1}],
            'score_time_coverage':{'segments':[{'start_seconds':10,'end_seconds':80}]}}
    def test_complement_respects_disjoint_music_scopes_and_touching_captions(self):
        intervals=merge_intervals([[20,30],[10,20],[50,60],[45,47]])
        self.assertEqual(intervals,[[10,30],[45,47],[50,60]])
        self.assertEqual(blank_intervals(intervals,[[0,35],[40,65]]),[[0,10],[30,35],[40,45],[47,50],[60,65]])
    def test_coverage_uses_auto_expiry_and_long_interpretation_not_source_hold(self):
        events=[{'slot':'guide','text':'读完就退场。','output_start':0,'output_end':120},
                {'slot':'interpretation','text':'这里是一段完整的诠释。','output_start':30,'output_end':65}]
        self.assertEqual(caption_coverage(events,self.config),[[0,10],[30,65]])
    def test_schedule_follows_actual_nonuniform_score_time_not_fraction_of_gap(self):
        first=schedule_entries(self.plan,self.alignment,self.config)[0]
        self.assertEqual(first['start_seconds'],23)
        shifted=copy.deepcopy(self.alignment);shifted['measures'][1]['start_seconds']=36
        self.assertEqual(schedule_entries(self.plan,shifted,self.config)[0]['start_seconds'],36)
    def test_music_pause_and_insufficient_reading_window_are_rejected(self):
        for change in ('pause','short'):
            data=copy.deepcopy(self.alignment)
            if change=='pause':data['measures'][1].update(start_seconds=90,end_seconds=100)
            else:data['measures'][1]['end_seconds']=26
            with self.subTest(change=change),self.assertRaises(ValueError):schedule_entries(self.plan,data,self.config)
