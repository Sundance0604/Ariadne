import copy
from pathlib import Path
import uuid
import shutil
import unittest
from backend.video_export.content import content_hash,digest,review_events,output_events,read,write
from backend.video_export.pipeline import validate_config,import_ass_text
from backend.video_export.subtitles import analysis_ass,escape

ROOT=Path(__file__).resolve().parents[1]


class PublicationTests(unittest.TestCase):
    def setUp(self):
        self.root=ROOT/'tmp'/('video-export-test-'+uuid.uuid4().hex);self.root.mkdir(parents=True)
        (self.root/'evidence.txt').write_text('checked source',encoding='utf-8')
        self.config={'width':1920,'height':1080,'music_start_video':27.5,'font':'Microsoft YaHei','font_size':32,'yellow':'#FFDF42',
            'layout':{'harmony':{'x':70,'y':60,'w':800,'h':160},'intro':{'x':100,'y':200,'w':1600,'h':700}},
            'segments':[{'video_start':0,'video_end':40}]}
        self.event={'id':'ok','slot':'harmony','text':'持续低音与分解音型','video_start':28,'video_end':36,'phase':'performance','timing_precision':'score_segment'}
        self.event['review']={'status':'approved','reviewer':'source checker','scope':'limited score check',
            'sources':[{'path':'evidence.txt','sha256':digest(self.root/'evidence.txt')}],'content_sha256':content_hash(self.event)}

    def tearDown(self):
        target=self.root.resolve();self.assertTrue(target.is_relative_to((ROOT/'tmp').resolve()))
        self.assertTrue(target.name.startswith('video-export-test-'));shutil.rmtree(target)

    def audit(self,event):return review_events({'events':[event]},self.config,self.root)

    def test_review_hash_binds_text_slot_and_timing(self):
        self.assertEqual(len(self.audit(self.event)[0]),1)
        for key,value in [('text','新结论'),('video_start',29),('slot','form')]:
            row=copy.deepcopy(self.event);row[key]=value
            self.assertIn('changed_since_review',self.audit(row)[1][0]['reasons'])

    def test_source_change_and_ass_injection_are_not_silently_accepted(self):
        (self.root/'evidence.txt').write_text('changed',encoding='utf-8')
        self.assertEqual(self.audit(self.event)[0],[])
        self.assertNotIn('{',escape(r'{\pos(0,0)}'))
        self.assertNotIn('\\pos',escape(r'{\pos(0,0)}'))

    def test_research_words_rejected_as_whole_event_even_with_review(self):
        for text in ['和声待核查','TODO 补充','估计位置','尚未人工复核','未验证的推断']:
            row=copy.deepcopy(self.event);row['text']=text;row['review']['content_sha256']=content_hash(row)
            self.assertEqual(self.audit(row)[0],[])

    def test_intro_is_completely_gone_three_seconds_before_entry(self):
        row=copy.deepcopy(self.event);row.update(slot='interpretation',phase='intro',video_start=1,video_end=24.5)
        row['review']['content_sha256']=content_hash(row);self.assertEqual(len(self.audit(row)[0]),1)
        row['video_end']=24.51;row['review']['content_sha256']=content_hash(row)
        self.assertIn('intro_three_second_violation',self.audit(row)[1][0]['reasons'])

    def test_fast_text_and_conflicting_same_slot_fail_closed(self):
        row=copy.deepcopy(self.event);row['video_end']=28.5;row['review']['content_sha256']=content_hash(row)
        self.assertIn('insufficient_reading_time',self.audit(row)[1][0]['reasons'])
        row=copy.deepcopy(self.event);row['id']='other';row['review']['content_sha256']=content_hash(row)
        ok,bad=review_events({'events':[row,self.event]},self.config,self.root)
        self.assertEqual(ok,[]);self.assertEqual(len(bad),2)

    def test_ass_is_one_yellow_track_with_fixed_positions_and_zero_shadow(self):
        text=analysis_ass(output_events([self.event],self.config),self.config)
        self.assertIn('&H0042DFFF',text);self.assertIn(r'\pos(70,60)',text)
        self.assertIn('0,1,0,0,7,0,0,0,1',text)
        self.assertNotIn(r'\fad',text)

    def test_clip_does_not_turn_reviewed_long_caption_into_a_flash(self):
        self.config['segments']=[{'video_start':35.5,'video_end':40}];excluded=[]
        self.assertEqual(output_events([self.event],self.config,excluded),[])
        self.assertEqual(excluded[0]['reasons'],['clip_leaves_insufficient_reading_time'])

    def test_intro_ass_end_is_quantized_to_a_clear_source_frame_before_deadline(self):
        row={**self.event,'slot':'interpretation','phase':'intro','video_start':1,'video_end':24.5}
        self.config['intro_clear_video']=24.48
        self.assertEqual(output_events([row],self.config)[0]['output_end'],24.48)

    def test_independent_ass_text_edit_reimports_with_explicit_review_and_fixed_layout(self):
        package=self.root/'package';(package/'evidence').mkdir(parents=True)
        shutil.copy2(self.root/'evidence.txt',package/'evidence/evidence.txt')
        config=read(ROOT/'works/ravel-left-hand-video/video-export/sample-profile.json')
        write(package/'export-config.json',config);write(package/'annotations.json',{'events':[self.event]})
        write(package/'review-report.json',{});write(package/'export-manifest.json',{'checksums':{}})
        original=analysis_ass(output_events([self.event],config),config)
        edited=self.root/'edited.ass';edited.write_text(original.replace(self.event['text'],'低音保持，分解音型流动。'),encoding='utf-8-sig')
        changed=import_ass_text(package,edited,'test fixture reviewer','synthetic source check')
        self.assertEqual(changed,['ok']);self.assertIn('低音保持',read(package/'annotations.json')['events'][0]['text'])
        modified=(package/'analysis.ass').read_text(encoding='utf-8-sig').replace(r'\pos(70,60)',r'\pos(0,0)')
        edited.write_text(modified,encoding='utf-8-sig')
        with self.assertRaisesRegex(ValueError,'position'):import_ass_text(package,edited,'test fixture reviewer','synthetic source check')


class HTTPImportTests(unittest.TestCase):
    def test_actual_player_import_graph_includes_shared_score_display_module(self):
        import sys,threading,re
        from urllib.parse import urljoin,urlparse
        from urllib.request import urlopen
        sys.path.insert(0,str(ROOT/'scripts'))
        import serve_review
        class Quiet(serve_review.Handler):
            def log_message(self,*args):pass
        server=serve_review.ReviewServer(('127.0.0.1',0),Quiet)
        worker=threading.Thread(target=server.serve_forever,daemon=True);worker.start()
        origin=f'http://127.0.0.1:{server.server_port}';pending=[origin+'/app.mjs'];seen=set()
        try:
            while pending:
                url=pending.pop()
                if url in seen:continue
                seen.add(url)
                with urlopen(url,timeout=5) as response:
                    self.assertEqual(response.status,200);code=response.read().decode('utf-8')
                for dependency in re.findall(r"from\s+['\"]([^'\"]+\.mjs)['\"]",code):
                    target=urljoin(url,dependency);self.assertEqual(urlparse(target).netloc,urlparse(origin).netloc);pending.append(target)
            self.assertIn(origin+'/score-display.mjs',seen);self.assertGreater(len(seen),10)
        finally:server.shutdown();server.server_close();worker.join()


if __name__=='__main__':unittest.main()
