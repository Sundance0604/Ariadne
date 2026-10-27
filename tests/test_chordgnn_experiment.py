"""Source identity, explicit ties, real meters, and bounded clock projection."""
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from backend.chordgnn_experiment import (
    EXPERIMENT,interpolate,read,recording_time,resolve_meters,select_notes,
    source_keys,verify_protected,
)


def event(identity,start,end,ties=(),voice='1'):
    return {'id':identity,'movement':1,'part_id':'P1','voice':voice,'staff':1,
            'ps':60,'start_q':str(start),'end_q':str(end),'tie':list(ties)}


class ChordGNNExperiment(unittest.TestCase):
    def test_explicit_ties_only_with_voice_and_contiguity(self):
        doc={'measures':[{'movement':1,'local_number':1,'start_q':'0','end_q':'4'}],
             'events':[event('a',0,1,['start']),event('b',1,2,['stop']),
                       event('c',2,3),event('d',3,4),event('other',1,2,['stop'],voice='2')]}
        _,notes=select_notes(doc,1,1,1)
        self.assertEqual(len(notes),4)
        joined=next(n for n in notes if n['id']=='a')
        self.assertEqual(joined['end_q'],'2')
        self.assertEqual(joined['source_event_ids'],['a','b'])
        self.assertEqual(next(n for n in notes if n['id']=='other')['source_event_ids'],['other'])

    def test_clipping_retains_source_span(self):
        doc={'measures':[{'movement':1,'local_number':1,'start_q':'1','end_q':'3'}],
             'events':[event('a',0,4)]}
        _,notes=select_notes(doc,1,1,1)
        self.assertEqual((notes[0]['start_q'],notes[0]['end_q']),('1','3'))
        self.assertEqual((notes[0]['source_start_q'],notes[0]['source_end_q']),('0','4'))
        self.assertTrue(notes[0]['clipped_left'] and notes[0]['clipped_right'])

    def test_recording_uses_actual_knots_and_does_not_extrapolate(self):
        pts=[{'midi_seconds':0,'audio_seconds':10},{'midi_seconds':1,'audio_seconds':15},
             {'midi_seconds':4,'audio_seconds':18}]
        self.assertEqual(interpolate(pts,2),16)
        self.assertIsNone(interpolate(pts,-.01));self.assertIsNone(interpolate(pts,4.01))
        alignment={'measures':[{'movement':1,'start_q':'0','end_q':'8',
            'midi_start_seconds':0,'midi_end_seconds':4}],
            'time_maps':[{'movement':1,'time_map':pts}]}
        self.assertEqual(recording_time(alignment,4,1),16)
        self.assertEqual(recording_time(alignment,8,1),18)
        self.assertIsNone(recording_time(alignment,9,1))
        self.assertIsNone(recording_time(alignment,4,2))

    def test_poucet_meter_is_read_from_xml_not_guessed(self):
        case=read(EXPERIMENT/'inputs/poucet.json')
        resolved=resolve_meters(case['measures'])
        self.assertEqual([m['time_signature'] for m in resolved[:6]],['2/4','3/4','4/4','5/4','3/4','2/4'])
        self.assertTrue(all(m['meter_recovered_from_xml'] for m in resolved))
        inconsistent=[dict(resolved[0],time_signature='4/4')]
        with self.assertRaisesRegex(ValueError,'meter mismatch'):resolve_meters(inconsistent)

    def test_concert_key_is_transposed_once(self):
        keys=source_keys(str(ROOT/'resource/mother goose/ma-mere-loye-maurice-ravel.mxl'))
        self.assertEqual(keys[('P14',1)]['written_fifths'],1)
        self.assertEqual(keys[('P14',1)]['concert_fifths'],0)
        self.assertEqual(keys[('P1',1)]['concert_fifths'],0)

    def test_experiment_did_not_change_canonical_sources(self):
        manifest=read(EXPERIMENT/'manifest.json')
        verify_protected(manifest['protected_inputs'])
        self.assertIsNone(manifest['human_signoff'])

    def test_actual_successor_outputs_keep_incompatible_heads_undecoded(self):
        manifest=read(EXPERIMENT/'manifest.json')
        for case in manifest['cases']:
            result=read(EXPERIMENT/'analysisgnn'/f"{case['id']}.json")
            self.assertTrue(result['strict_checkpoint_load'])
            self.assertTrue(result['notes'])
            for onset in result['onsets']:
                for head in ('quality','romanNumeral'):
                    candidate=onset['candidates'].get(head)
                    if candidate:
                        self.assertIsNone(candidate['value'])
                        self.assertEqual(candidate['decode_status'],'disabled_vocabulary_mismatch')
                        self.assertLess(candidate['class_index'],result['decoder_mismatches'][head]['checkpoint_classes'])


if __name__=='__main__':unittest.main()
