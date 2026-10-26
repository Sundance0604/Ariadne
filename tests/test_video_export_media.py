"""Real FFmpeg regression: variable frame times, nonzero seek, alpha, audio copy."""
from pathlib import Path
import shutil
import unittest
import uuid
from backend.video_export.content import read,write,digest
from backend.video_export.media import ffmpeg,run,inspect_frames
from backend.video_export.pipeline import prepare_score,compose,verify_video,validate_config
from backend.video_export.subtitles import analysis_ass

ROOT=Path(__file__).resolve().parents[1]


def tiny_pdf(path):
    objects=[b'<< /Type /Catalog /Pages 2 0 R >>',b'<< /Type /Pages /Count 1 /Kids [3 0 R] >>',
        b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 100 200] /Contents 4 0 R >>',
        b'<< /Length 24 >>\nstream\n10 20 70 140 re S\nendstream']
    data=b'%PDF-1.4\n';offsets=[]
    for i,obj in enumerate(objects,1):offsets.append(len(data));data+=f'{i} 0 obj\n'.encode()+obj+b'\nendobj\n'
    xref=len(data);data+=b'xref\n0 5\n0000000000 65535 f \n'+b''.join(f'{n:010} 00000 n \n'.encode() for n in offsets)
    data+=f'trailer\n<< /Size 5 /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n'.encode();path.write_bytes(data)


class RealExportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:cls.binary=ffmpeg(ROOT)
        except RuntimeError as e:raise unittest.SkipTest(str(e))

    def setUp(self):
        self.package=ROOT/'tmp'/('video-export-media-'+uuid.uuid4().hex);self.package.mkdir(parents=True)
        (self.package/'score').mkdir();tiny_pdf(self.package/'score/source.pdf')
        run([self.binary,'-v','error','-y','-f','lavfi','-i','testsrc2=size=320x180:rate=30:duration=5',
            '-f','lavfi','-i','sine=frequency=440:duration=5','-vf',"select='not(mod(n,2))+gte(t,4)'",
            '-fps_mode','vfr','-c:v','libx264','-bf','0','-preset','ultrafast','-c:a','aac','-shortest',self.package/'performance.mp4'])
        config=read(ROOT/'works/ravel-left-hand-video/video-export/sample-profile.json')
        config.update(width=320,height=180,music_start_video=3,segments=[{'video_start':3.5,'video_end':4.5}],preset='ultrafast',font_size=8)
        for v in config['layout'].values():
            for k in ['x','y','w','h','font_size']:
                if k in v:v[k]=max(1,round(v[k]/6))
        write(self.package/'export-config.json',config)
        mapping={'pdf_path':'score/source.pdf','pdf_sha256':digest(self.package/'score/source.pdf'),'measures':[
            {'measure_id':'a','page_number':1,'page_width_pt':100,'page_height_pt':200,'rect_pt':[10,20,70,140],'resolution':'bar'}]}
        alignment={'time_map':[{'audio_seconds':3,'midi_seconds':0},{'audio_seconds':5,'midi_seconds':2}],
            'score_time_coverage':{'start_seconds':3,'end_seconds':5},'measures':[
                {'measure_id':'a','start_seconds':3,'end_seconds':5,'midi_start_seconds':0,'midi_end_seconds':2}]}
        write(self.package/'project.json',{'alignment':alignment,'mapping':mapping})
        write(self.package/'annotations.json',{'events':[]})
        (self.package/'analysis.ass').write_text(analysis_ass([],config),encoding='utf-8-sig')
        write(self.package/'review-report.json',{'checks':{},'performance':{}})
        self.rebind()

    def rebind(self):
        write(self.package/'export-manifest.json',{'checksums':{n:digest(self.package/n) for n in ['performance.mp4','score/source.pdf','project.json','annotations.json','analysis.ass','export-config.json']}})

    def tearDown(self):
        target=self.package.resolve();self.assertTrue(target.is_relative_to((ROOT/'tmp').resolve()))
        self.assertTrue(target.name.startswith('video-export-media-'));shutil.rmtree(target)

    def test_variable_frame_timestamps_and_original_aac_survive_composition(self):
        prepare_score(ROOT,self.package);compose(ROOT,self.package)
        checks=verify_video(ROOT,self.package)
        probe=read(self.package/'source-frame-timestamps.json')[0]
        self.assertGreater(probe['max_frame_delta'],probe['min_frame_delta']*1.5)
        self.assertGreaterEqual(probe['first_pts'],3.5)
        self.assertTrue(checks['source_video_pts_preserved']);self.assertTrue(checks['audio_packets_unchanged'])

    def test_first_release_rejects_montage_cuts_instead_of_misaligning_copied_audio(self):
        config=read(self.package/'export-config.json');config['segments']=[{'video_start':3.5,'video_end':4},{'video_start':4.2,'video_end':4.7}]
        write(self.package/'export-config.json',config);self.rebind()
        with self.assertRaisesRegex(ValueError,'continuous source interval'):validate_config(config)


if __name__=='__main__':unittest.main()
