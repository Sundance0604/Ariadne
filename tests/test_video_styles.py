"""Editable styling must reach ASS without changing clocks or chapter intent."""
import copy,re,uuid,shutil,unittest
from pathlib import Path
from backend.video_export.content import read,write
from backend.video_export.editor import prepare,package_config,ROOT
from backend.video_export.subtitles import analysis_ass


class CaptionStyles(unittest.TestCase):
    def test_column_and_row_styles_reach_ass_without_retiming(self):
        config=read(ROOT/'works/ravel-mother-goose-video/video-export/full-profile.json')
        document=read(ROOT/'works/ravel-mother-goose-video/video-export/captions-optimized.json')
        document=copy.deepcopy(document)
        document['字幕样式']={'诠释':{'滚动倍速':1,'字体':'Microsoft YaHei','横坐标':240}}
        row=next(r for r in document['字幕'] if r['栏目']=='诠释')
        row['样式']={'横坐标':260,'字号':42,'字体':'KaiTi','滚动倍速':2}
        before=[(r['编号'],r['开始秒'],r['结束秒']) for r in document['字幕']]
        package=ROOT/'tmp'/('caption-styles-'+uuid.uuid4().hex);package.mkdir()
        try:
            write(package/'export-config.json',config)
            self.assertEqual(package_config(package),config)
            active,events,_=prepare(document,package)
        finally:
            self.assertTrue(package.resolve().is_relative_to((ROOT/'tmp').resolve()))
            shutil.rmtree(package)
        event=next(e for e in events if e['id']==row['编号'])
        self.assertEqual((event['output_start'],event['output_end']),(row['开始秒'],row['结束秒']))
        text=analysis_ass([event],active)
        self.assertIn(r'\fnKaiTi\fs42',text)
        self.assertIn('Style: interpretation,Microsoft YaHei',text)
        end2=int(re.search(r'\\move\([^,]+,[^,]+,[^,]+,[^,]+,650,(\d+)\)',text)[1])
        event['render_style']['scroll_speed']=1
        end1=int(re.search(r'\\move\([^,]+,[^,]+,[^,]+,[^,]+,650,(\d+)\)',analysis_ass([event],active))[1])
        self.assertLess(end2,end1)
        self.assertEqual(before,[(r['编号'],r['开始秒'],r['结束秒']) for r in document['字幕']])
        self.assertEqual(len(active['chapters']),7)

    def test_invalid_styles_fail_before_export(self):
        from backend.video_export.editor import validate_style
        config=read(ROOT/'works/ravel-mother-goose-video/video-export/full-profile.json')
        for style in [{'滚动倍速':0},{'滚动倍速':float('nan')},{'横坐标':1900},{'字号':True},{'字体':r'KaiTi\pos(0,0)'}]:
            with self.subTest(style=style),self.assertRaises(ValueError):
                validate_style(style,config['layout']['interpretation'],config)

    def test_font_fallback_requires_a_successful_selection(self):
        from backend.video_export.media import subtitle_font_report
        request='[Parsed_ass_5 @ 123] Glyph 0x266F not found, selecting one more font for (KaiTi, 700, 0)'
        chosen='[Parsed_ass_5 @ 123] fontselect: (KaiTi, 700, 0) -> Arial-BoldMT, 0, Arial-BoldMT'
        self.assertTrue(subtitle_font_report(request)['unresolved_glyphs'])
        report=subtitle_font_report(request+'\n'+chosen)
        self.assertFalse(report['unresolved_glyphs']);self.assertEqual(len(report['resolved_fallbacks']),1)
