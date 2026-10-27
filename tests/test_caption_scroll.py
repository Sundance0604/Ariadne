"""At-rest captions must contain complete rows, independently of ASS metrics."""
import re,unittest
from backend.video_export.subtitles import web_analysis_ass,reading_window

class ScrollRest(unittest.TestCase):
    def setUp(self):
        self.box={'x':50,'y':730,'w':180,'h':140,'font_size':36,'scroll':True}
        self.config={'width':1920,'height':1080,'font':'KaiTi','font_size':36,'yellow':'#FFDF42',
            'web_video_layout':True,'layout':{'guide':self.box}}
    def event(self,text):return {'slot':'guide','text':text,'output_start':0,'output_end':12}
    def test_short_caption_that_fits_stays_whole_even_in_scrolling_slot(self):
        ass=web_analysis_ass([self.event('短句完整显示')],self.config)
        self.assertNotIn(r'\move',ass)
    def test_stopped_tail_contains_only_complete_rows_with_padding(self):
        event=self.event('甲乙丙丁戊己庚辛壬癸子丑寅卯辰巳午未申酉戌亥')
        ass=web_analysis_ass([event],self.config);rows=[r for r in ass.splitlines() if r.startswith('Dialogue:')]
        moving=[r for r in rows if r'\move' in r];self.assertTrue(moving)
        stops={r.split(',')[2] for r in moving};self.assertEqual(len(stops),1)
        held=[r for r in rows if r.split(',')[1] in stops];window=reading_window(self.box,36,5)
        self.assertEqual(len(held),window['visible_lines'])
        for i,row in enumerate(held):
            y=float(re.search(r'\\pos\([^,]+,([^\)]+)\)',row)[1])
            self.assertAlmostEqual(y,window['initial_y']+i*window['line_height'],places=2)
            self.assertGreater(y,window['top']);self.assertLessEqual(y+window['line_height'],window['bottom']-window['padding']+.01)
    def test_invalid_tiny_window_fails_instead_of_cutting_glyphs(self):
        with self.assertRaises(ValueError):reading_window({**self.box,'h':65},36,3)

if __name__=='__main__':unittest.main()
