import copy
import hashlib
import json
from pathlib import Path
import sys
import threading
import unittest
from unittest.mock import patch
from urllib.request import urlopen
from urllib.error import HTTPError
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from research_data import load_research, harmonic_fields
import serve_review


class ResearchDataTests(unittest.TestCase):
    def setUp(self):
        self.root = ROOT / 'tmp' / f'research-test-{uuid.uuid4().hex}'
        for folder in ['analysis', 'metadata', 'resource']:
            (self.root / folder).mkdir(parents=True, exist_ok=True)
        self.pdf = self.root / 'resource/score.pdf'
        self.pdf.write_bytes(b'explicit test fixture, not a production score')
        self.hash = hashlib.sha256(self.pdf.read_bytes()).hexdigest()
        self.save('measure-map.json', {'pdf_path': 'resource/score.pdf', 'pdf_sha256': self.hash,
                  'page_count': 4, 'measures': [{'measure_id': 'candidate-a', 'page_number': 1}]})
        self.save('metadata/recording.json', {'work': {'work_id': 'test-work'},
                  'recording': {'recording_id': 'recording-a'}})
        self.mock = patch('research_data.load_analysis', return_value={'audio_sha256': 'audio-a',
                          'references': [{'source_id': 'source-a', 'reading_status': 'abstract_checked'}]})
        self.mock.start()
        self.addCleanup(self.mock.stop)
        self.edition = {'edition_id': 'test-edition', 'pdf_sha256': self.hash}
        self.event = {'id': 'a', 'dimension': 'harmony', 'claim_level': 'theoretical_analysis',
                      'short_label': 'fixture-only hypothesis', 'detail_markdown': '<script>x</script>',
                      'score_spans': [{'pdf_page_start': 1, 'pdf_page_end': 1, 'precision': 'page_range'}],
                      'sources': [{'source_id': 'source-a', 'locator': 'abstract', 'claim_attribution': 'authors'}],
                      'verification': {'score': 'pending', 'literature': 'abstract_checked',
                                       'location': 'page_range', 'timing': 'candidate_alignment'}}
        self.struct = {'schema_version': '1.0.0', 'work_id': 'test-work', 'edition': self.edition, 'events': [self.event]}

    def save(self, path, value):
        (self.root / path).write_text(json.dumps(value), encoding='utf-8')

    def load(self):
        self.save('analysis/structural-events.json', self.struct)
        return load_research(self.root)

    def test_missing_research_is_a_valid_empty_result(self):
        self.assertFalse(load_research(self.root)['available'])

    def test_safe_html_and_noncontinuous_persistent_essay(self):
        essay = {**self.event, 'id': 'essay', 'title': 'persistent essay', 'reading_mode': 'persistent',
                 'claim_level': 'hermeneutic_interpretation', 'markdown': 'body',
                 'score_spans': [self.event['score_spans'][0],
                                {'pdf_page_start': 3, 'pdf_page_end': 4, 'precision': 'page_range'}],
                 'related_event_ids': ['a']}
        self.save('analysis/hermeneutic-essays.json', {**self.struct, 'essays': [essay]})
        data = self.load()
        self.assertNotIn('<script>', data['events'][0]['html'])
        self.assertEqual(len(data['essays'][0]['score_spans']), 2)
        self.assertEqual(data['sources'][0]['reading_status'], 'abstract_checked')

    def test_wrong_work_edition_and_actual_pdf_content_are_rejected(self):
        for field, bad in [('work_id', 'wrong-work'), ('edition', {**self.edition, 'pdf_sha256': 'wrong'})]:
            old = self.struct[field]
            self.struct[field] = bad
            with self.assertRaises(ValueError): self.load()
            self.struct[field] = old
        self.pdf.write_bytes(b'changed score')
        with self.assertRaisesRegex(ValueError, 'PDF'): self.load()

    def test_unsafe_paths_and_unknown_sources_are_rejected(self):
        self.event['markdown_path'] = '../outside.md'
        self.event['detail_markdown'] = ''
        with self.assertRaisesRegex(ValueError, '路径越界'): self.load()
        del self.event['markdown_path']
        self.event['detail_markdown'] = 'body'
        self.event['sources'][0]['source_id'] = 'made-up-source'
        with self.assertRaisesRegex(ValueError, '来源'): self.load()

    def test_reference_score_fingerprint_cannot_be_silently_replaced(self):
        self.save('analysis/sources.json', {'sources': [{'source_id':'comparison-score',
            'path':'resource/score.pdf','sha256':'wrong-fingerprint','urls':[]}]})
        with self.assertRaisesRegex(ValueError, '参考谱'): self.load()

    def test_granularity_status_and_authority_cannot_be_invented(self):
        cases = [('score_spans', [{'precision': 'unlocated', 'pdf_page_start': 1}]),
                 ('score_spans', [{'precision': 'page_range', 'pdf_page_start': 1, 'pdf_page_end': 2, 'start_seconds': 8}]),
                 ('score_spans', [{'precision': 'score_segment_candidate', 'pdf_page_start': 1, 'pdf_page_end': 1, 'region_ids': ['wrong']}]),
                 ('confidence', .99), ('verification', {**self.event['verification'], 'score': 'verified'}),
                 ('verification', {**self.event['verification'], 'score': 'automatically_true'})]
        for key, value in cases:
            with self.subTest(key=key, value=value):
                old = copy.deepcopy(self.event)
                self.event[key] = value
                with self.assertRaises(ValueError): self.load()
                self.event.clear(); self.event.update(old)

    def test_abstract_reading_cannot_be_promoted_and_recording_binding_is_checked(self):
        self.event['verification']['literature'] = 'full_text_checked'
        with self.assertRaisesRegex(ValueError, '全文'): self.load()
        self.event['verification']['literature'] = 'relevant_sections_checked'
        with self.assertRaisesRegex(ValueError, '相关章节'): self.load()
        self.event['verification']['literature'] = 'abstract_checked'
        self.event['recording'] = {'recording_id': 'other', 'audio_sha256': 'audio-a'}
        with self.assertRaisesRegex(ValueError, '录音'): self.load()

    def test_actual_audio_fingerprint_is_checked_for_recording_specific_claim(self):
        audio = self.root / 'resource/recording.mp3'
        audio.write_bytes(b'test bytes, not a real performance')
        fingerprint = hashlib.sha256(audio.read_bytes()).hexdigest()
        self.mock.stop()
        self.mock = patch('research_data.load_analysis', return_value={'audio_sha256': fingerprint,
                          'references': [{'source_id': 'source-a', 'reading_status': 'abstract_checked'}]})
        self.mock.start(); self.addCleanup(self.mock.stop)
        self.save('alignment.json', {'audio': {'path': 'resource/recording.mp3'}})
        self.event['recording'] = {'recording_id': 'recording-a', 'audio_sha256': fingerprint}
        self.load()
        audio.write_bytes(b'changed test recording')
        with self.assertRaisesRegex(ValueError, '录音内容'): self.load()

    def test_http_empty_unknown_track_and_invalid_data(self):
        self.save('library.json', {'default_track': 'test', 'tracks': [{'id': 'test', 'data_root': '.', 'title': 'fixture'}]})
        old = serve_review.ROOT
        serve_review.ROOT = self.root
        server = serve_review.ReviewServer(('127.0.0.1', 0), serve_review.Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        try:
            url = f'http://127.0.0.1:{server.server_port}/api/research'
            with urlopen(url + '?track=test') as response:
                self.assertFalse(json.load(response)['available'])
            with self.assertRaises(HTTPError) as caught: urlopen(url + '?track=../../')
            self.assertEqual(caught.exception.code, 404); caught.exception.close()
            self.struct['edition']['pdf_sha256'] = 'wrong'
            self.save('analysis/structural-events.json', self.struct)
            with self.assertRaises(HTTPError) as caught: urlopen(url + '?track=test')
            self.assertEqual(caught.exception.code, 422); caught.exception.close()
        finally:
            server.shutdown(); server.server_close(); thread.join(); serve_review.ROOT = old


class RavelResearchTests(unittest.TestCase):
    def test_invalid_optional_engine_is_rejected_without_hiding_existing_essays(self):
        with patch('backend.structure_analysis.store.load_bundle',side_effect=ValueError('fingerprint mismatch')):
            data=load_research(ROOT)
        self.assertEqual(len(data['essays']),5);self.assertEqual(len([e for e in data['events'] if e.get('analysis_origin') not in {'score_study','musicxml_analysis'}]),35)
        self.assertTrue(data['score_study'])
        self.assertIn('fingerprint mismatch',data['engine_error']);self.assertNotIn('reference_clock',data)

    def test_real_pilot_is_conservative_and_legacy_guides_unchanged(self):
        data = load_research(ROOT)
        self.assertEqual(len([e for e in data['events'] if e.get('analysis_origin') not in {'engine_candidate','score_study','musicxml_analysis'}]), 35)
        self.assertEqual(len(data['essays']), 5)
        self.assertGreaterEqual(len(data['essays'][0]['score_spans']), 3)
        self.assertTrue(all(e['verification']['timing'] == 'candidate_alignment' for e in data['events']))
        self.assertTrue(any(e['score_spans'][0]['precision'] == 'score_segment' for e in data['events']))
        self.assertEqual(len(json.loads((ROOT/'analysis/annotations.json').read_text(encoding='utf-8'))['annotations']), 15)
        self.assertFalse(load_research(ROOT, ROOT/'works/lark-ascending')['available'])
        self.assertFalse(load_research(ROOT, ROOT/'works/mahler-4')['available'])

    def test_actual_ravel_harmonic_claims_keep_bass_collection_and_scope(self):
        data = load_research(ROOT)
        events = {e['id']: e for e in data['events']}
        harmonic = [e for e in data['events'] if 'harmonic_analysis' in e]
        self.assertEqual(len(harmonic), 8)
        arrival = events['return-tonic-second-inversion']['harmonic_analysis']
        self.assertEqual((arrival['root'],arrival['bass'],arrival['inversion']), ('D','A3','second'))
        self.assertEqual(arrival['pitch_collection'], ['D','F#','A'])
        self.assertEqual(events['cadenza-c-over-e']['harmonic_analysis']['inversion'], 'first')
        self.assertIsNone(events['tonal-perspective']['harmonic_analysis']['roman_numeral'])
        self.assertEqual(events['cadenza-dominant']['harmonic_analysis']['omitted_tones'], ['E'])
        sources = {s['source_id']:s for s in data['sources']}
        self.assertIn('Clare Hammond',sources['analysis-ref-11-6']['citation_label'])
        self.assertEqual(sources['analysis-ref-11-6']['reading_status'], 'relevant_sections_checked')
        self.assertEqual(sources['ravel-russ-2000']['reading_status'], 'publisher_metadata_checked')

    def test_harmony_rejects_written_pitch_and_inversion_without_bass_evidence(self):
        event = next(e for e in load_research(ROOT)['events'] if e['id']=='return-tonic-second-inversion')
        for field, value in [('pitch_basis','written'),('bass','D2'),('root','A'),
                             ('voices',[]),('omitted_tones',['A']),('system','automatically_verified')]:
            bad = copy.deepcopy(event);bad['harmonic_analysis'][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError): harmonic_fields(bad)
        bad = copy.deepcopy(event);bad['dimension']='form'
        with self.assertRaises(ValueError):harmonic_fields(bad)


if __name__ == '__main__': unittest.main()
