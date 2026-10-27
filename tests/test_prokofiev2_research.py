"""Editorial coverage, source witnesses, local harmony and playback isolation."""
from fractions import Fraction as F
import hashlib,json
from pathlib import Path
import sys,unittest
ROOT=Path(__file__).resolve().parents[1]
DATA=ROOT/'works/prokofiev-piano-concerto-2/analysis'
sys.path.insert(0,str(ROOT))


def read(name):return json.loads((DATA/name).read_text(encoding='utf8'))


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream,'sha256').hexdigest()


class ProkofievResearch(unittest.TestCase):
    def test_38_reading_sections_cover_source_sequence_including_continuation(self):
        sections=read('sections.json')['sections'];ms=read('measure-index.json')['measures']
        self.assertEqual(len(sections),38)
        self.assertEqual([m for s in sections for m in s['measure_ids']],[m['measure_id'] for m in ms])
        self.assertEqual(sum(n=='X1' for s in sections for n in s['local_measure_labels']),1)
        self.assertEqual([sum(s['movement']==i for s in sections) for i in range(1,5)],[12,7,8,11])

    def test_all_local_witnesses_are_eligible_and_active(self):
        windows=read('score-studies.json')['windows'];self.assertEqual(len(windows),22)
        quarantine=set(read('symbolic-source-summary.json')['large_timing_quarantine_sequences'])
        for w in windows:
            self.assertNotIn(w['sequence'],quarantine)
            q=F(w['offset_q'])
            for e in w['selected_events']+w['other_active_events']:
                self.assertTrue(e['eligible']);self.assertNotEqual(e['part_id'],'P14')
                self.assertEqual(e['sequence'],w['sequence'])
                self.assertLessEqual(F(e['onset_q']),q)
                self.assertLess(q,F(e['onset_q'])+F(e['duration_q']))
                self.assertEqual(F(e['concert_ps']),F(str(e['concert_pitch']['ps'])))

    def test_open_intervals_and_real_triads_remain_distinct(self):
        ws={w['id']:w for w in read('score-studies.json')['windows']}
        self.assertEqual(ws['I-initial-rest']['sonority']['label'],'silence')
        self.assertIsNone(ws['I-piano-accompaniment-entry']['sonority']['chord'])
        self.assertEqual(ws['IV-lullaby-solo-entry']['sonority']['chord']['root'],'D')
        self.assertEqual(ws['IV-flat-side-chord']['sonority']['chord']['root'],'Eb')
        self.assertEqual(ws['IV-last-full-ensemble-bar']['sonority']['pitch_classes'],[0,7])
        self.assertEqual(ws['IV-last-bar']['sonority']['pitch_classes'],[7])
        self.assertIsNone(ws['IV-last-bar']['sonority']['chord'])

    def test_source_and_protected_playback_fingerprints(self):
        manifest=read('manifest.json');audit=read('build-audit.json')
        records=[audit['source']]+audit['protected_files']+audit['code']+list(manifest['files'].values())
        records.append(manifest['editorial_packager'])
        if manifest.get('performance_metadata'):records.append(manifest['performance_metadata'])
        if manifest.get('previous_recording_metadata'):records.append(manifest['previous_recording_metadata'])
        for r in records:
            p=ROOT/r['path']
            if r['path']=='library.json' and (DATA.parent/'playback/current.json').exists():
                p=DATA.parent/'sync/history/library-before-sync.json'
                old=json.loads(p.read_text(encoding='utf8'))
                current=json.loads((ROOT/'library.json').read_text(encoding='utf8'))
                current['tracks']=[t for t in current['tracks'] if t['id']!='prokofiev-piano-concerto-2']
                self.assertEqual(old,current)
            self.assertEqual(digest(p),r['sha256'],r['path'])
        for s in read('sources.json')['sources']:
            if 'sha256' in s:self.assertEqual(digest(ROOT/s['path']),s['sha256'])

    def test_performer_target_preserves_pending_file_and_previous_version(self):
        context=read('performance-context.json')
        metadata=json.loads((DATA.parent/'metadata/recording.json').read_text(encoding='utf8'))
        recording=metadata['recording']
        previous=json.loads((ROOT/metadata['previous_recording_metadata']).read_text(encoding='utf8'))['recording']
        project=json.loads((DATA.parent/'project.json').read_text(encoding='utf8'))
        sections={s['id']:s for s in read('sections.json')['sections']}
        sources={s['id']:s for s in read('sources.json')['sources']}
        self.assertIsNone(context['same_performance'])
        activated=(DATA.parent/'playback/current.json').exists()
        if activated:self.assertEqual(context['local_recording_id'],recording['id'])
        else:self.assertIsNone(context['local_recording_id'])
        self.assertTrue(context['target_matches_literature_by_user_selection'])
        self.assertEqual(context['target_recording_id'],recording['id'])
        self.assertEqual(context['target_recording_id'],context['literature_recording_id'])
        self.assertEqual(context['literature_recording_id'],sources['G']['recording_discussed']['id'])
        self.assertEqual(context['previous_local_recording_id'],previous['id'])
        self.assertEqual(sources['V']['sha256'],previous['media']['sha256'])
        self.assertNotEqual(previous['id'],recording['id'])
        if activated:
            self.assertEqual(recording['media']['sha256'],project['video']['sha256'])
            self.assertNotEqual(recording['media']['sha256'],previous['media']['sha256'])
            self.assertEqual(sources['VT']['local_media']['sha256'],recording['media']['sha256'])
        else:
            self.assertIsNone(recording['media']);self.assertIsNone(project['video'])
        self.assertEqual(project['performance_target_recording_id'],recording['id'])
        self.assertEqual(sources['VT']['local_file_verified'],activated)
        self.assertEqual(recording['auditory_review']['status'],'not_performed')
        self.assertEqual(recording['auditory_review']['reviewed_intervals'],[])
        self.assertEqual({c['section_id'] for c in context['cases']},
                         {s['id'] for s in sections.values() if s.get('performance_interpretation')})
        for case in context['cases']:
            section=sections[case['section_id']]
            self.assertEqual(case['movement'],section['movement'])
            self.assertEqual(str(case['first_local_measure']),section['local_measure_labels'][0])
            self.assertIsNone(case['local_recording_observation'])
            self.assertIsNone(case['audio_projection'])
            self.assertIsNone(case['human_signoff'])
            self.assertEqual(case['target_recording_id'],recording['id'])
            for sid in case['literature_source_ids']:self.assertIn(sid,sources)

    def test_no_recording_clock_activation_or_fabricated_signoff(self):
        manifest=read('manifest.json');project=json.loads((DATA.parent/'project.json').read_text(encoding='utf8'))
        # The original musical research remains measure-local. A later,
        # separately fingerprinted web synchronization is explicitly allowed.
        self.assertFalse(manifest['player_activation'])
        self.assertIsNone(project['audio'])
        if project.get('recording_projection'):
            # Later, separately authorized written-activity projection; the
            # original analytical snapshot below still has no recording clock.
            self.assertEqual(project['recording_projection']['status'],'existing_DTW_candidate')
            self.assertTrue((ROOT/project['recording_projection']['path']).is_file())
        else:self.assertIsNone(project['recording_projection'])
        if project['player_registration']:
            self.assertTrue((DATA.parent/'playback/current.json').exists())
            self.assertTrue((ROOT/project['alignment']).exists())
        else:self.assertIsNone(project['alignment'])
        self.assertIsNone(manifest['human_signoff']);self.assertIsNone(manifest['expert_review'])
        self.assertIsNone(read('symbolic-source-summary.json')['global_score_time'])
        self.assertNotIn('gnn',read('score-studies.json')['method'].lower())
        for s in read('sections.json')['sections']:
            self.assertIsNone(s['audio_projection']);self.assertIsNone(s['human_signoff'])


if __name__=='__main__':unittest.main()
