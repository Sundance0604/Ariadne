"""Reading windows stop on content; interpretation is a separate long-text mode."""
import copy,re,unittest
from unittest.mock import patch
from backend.video_export.presentation import presentation_config,display_events
from backend.video_export.subtitles import web_analysis_ass,balanced_lines,reading_window


class Presentation(unittest.TestCase):
    def setUp(self):
        box={'x':40,'y':320,'w':600,'h':168,'font_size':32}
        self.config=presentation_config({'width':1920,'height':1080,'font':'KaiTi','font_size':32,
            'yellow':'#FFDF42','web_video_layout':True,'scroll_speed':1,
            'layout':{'guide':box,'interpretation':{'x':220,'y':336,'w':1480,'h':720,'font_size':44}}},
            {'分析':{},'诠释':{}})
    def event(self,text,slot='guide',start=0,end=120):
        return {'slot':slot,'text':text,'output_start':start,'output_end':end}
    def test_static_analysis_expires_without_changing_its_source_interval(self):
        e=self.event('这是一段需要阅读，然后把画面还给音乐的分析。');original=copy.deepcopy(e)
        shown=display_events([e],self.config)[0]
        self.assertLess(shown['output_end'],20);self.assertEqual(e,original)
        self.assertIn(r'\fad(450,1600)',web_analysis_ass([e],self.config))
    def test_same_contiguous_analysis_does_not_restart_its_reading_clock(self):
        a=self.event('不变的分析',end=60);b=self.event('不变的分析',start=60)
        events=display_events([a,b],self.config)
        self.assertEqual(len(events),1);self.assertEqual(events[0]['output_end'],10)
    def test_ordinary_scroll_distance_and_stop_do_not_depend_on_long_source_hold(self):
        e=self.event('甲乙丙丁戊己庚辛壬癸'*9)
        a=web_analysis_ass([e],self.config)
        b=web_analysis_ass([{**e,'output_end':1000}],self.config)
        moves=re.findall(r'\\move\(([^)]+)\)',a)
        self.assertTrue(moves);self.assertEqual(moves,re.findall(r'\\move\(([^)]+)\)',b))
        window=reading_window(self.config['layout']['guide'],32,5)
        first=list(map(float,moves[0].split(',')))
        self.assertAlmostEqual(first[1]-first[3],2*window['line_height'],places=2)
        self.assertLess(first[-1],5000)
    def test_tiny_tail_is_rebalanced_and_latin_words_are_kept_whole(self):
        lines=balanced_lines('甲乙丙丁戊己庚辛壬癸角。',180,30)
        self.assertTrue(all(len(s)>=4 for s in lines))
        lines=balanced_lines('钢琴 caloroso con gran espressione 的声音。',300,32)
        self.assertTrue(any('caloroso' in s for s in lines))
        self.assertTrue(all(s[0] not in '，。！？' for s in lines))
    def test_cinematic_rows_travel_together_and_fade_without_empty_tail_hold(self):
        e=self.event('让音乐保留自己的呼吸，把记忆交还给旋律。'*10,'interpretation',20,65)
        ass=web_analysis_ass([e],self.config)
        body=[r for r in ass.splitlines() if r'\move' in r];self.assertTrue(body)
        deltas=[]
        for row in body:
            a=list(map(float,re.search(r'\\move\(([^)]+)\)',row)[1].split(',')))
            self.assertEqual(a[-2:],[0,45000]);deltas.append(round(a[1]-a[3],2))
            self.assertIn(r'\fad(1400,4000)',row)
            self.assertEqual(row.split(',')[1:3],['0:00:20.00','0:01:05.00'])
        self.assertEqual(len(set(deltas)),1);self.assertLessEqual(deltas[0],100)
        self.assertNotIn(r'\frx',ass)
    def test_old_projects_without_rules_keep_their_display_intervals(self):
        e=self.event('原来显示时长');config=copy.deepcopy(self.config);config.pop('caption_presentation')
        self.assertEqual(display_events([e],config),[e])
    def test_invalid_presentation_rules_fail_before_generation(self):
        for rules in [{'分析':{'滚动像素每秒':0}},{'诠释':{'上移像素':float('nan')}},{'诠释时隐藏乐谱':'yes'}]:
            with self.subTest(rules=rules),self.assertRaises(ValueError):presentation_config(self.config,rules)

    def test_same_slot_followup_may_start_after_fade_inside_old_source_section(self):
        from backend.video_export.editor import prepare
        slots={'和弦':'harmony','配器':'orchestration','声部关系与复调':'counterpoint',
               '曲式与主题发展':'form','导聆':'guide','诠释':'interpretation','片头':'intro'}
        config=copy.deepcopy(self.config)
        config.update(segments=[{'video_start':0,'video_end':200}],music_start_video=20,intro_clear_video=17)
        for slot in slots.values():config['layout'].setdefault(slot,copy.deepcopy(config['layout']['guide']))
        rows=[{'编号':'old','栏目':'和弦','文字':'第一段已经读完的分析。','开始秒':20,'结束秒':120},
              {'编号':'new','栏目':'和弦','文字':'后来的音乐变化。','开始秒':40,'结束秒':55}]
        doc={'字号':{s:32 for s in slots},'字幕':rows}
        with patch('backend.video_export.editor.package_config',return_value=config):
            _,events,_=prepare(doc)
            self.assertEqual(events[0]['output_end'],120)
            doc['字幕'][1]['开始秒']=25
            with self.assertRaisesRegex(ValueError,'时间重叠'):prepare(doc)
            doc['字幕'][1]['开始秒']=40
            config['caption_presentation']['analysis']['enabled']=False
            with self.assertRaisesRegex(ValueError,'时间重叠'):prepare(doc)
