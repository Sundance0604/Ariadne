import sys
from pathlib import Path
from io import BytesIO
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import mido
from midi_score import TempoMap,build_measures,read_midi


class MidiTimelineTests(unittest.TestCase):
    def test_tempo_changes_are_integrated_before_new_tempo(self):
        tempo=TempoMap([(0,500000),(480,1000000)],480)
        self.assertAlmostEqual(tempo.at(480),.5)
        self.assertAlmostEqual(tempo.at(960),1.5)

    def test_changing_meters_and_partial_final_bar(self):
        bars=build_measures([(0,3,4),(1440,2,4)],2500,480,TempoMap([],480))
        self.assertEqual([b['score_start_tick'] for b in bars],[0,1440,2400])
        self.assertEqual(bars[-1]['flags'],['partial_final_bar'])

    def test_midbar_change_is_not_silently_rounded(self):
        bars=build_measures([(0,3,4),(1000,2,4)],1960,480,TempoMap([],480))
        self.assertIn('meter_change_inside_bar',bars[0]['flags'])
        self.assertEqual(bars[1]['score_start_tick'],1000)

    def test_port_switches_do_not_pair_different_instruments(self):
        midi=mido.MidiFile(ticks_per_beat=480)
        midi.tracks.append(mido.MidiTrack([
            mido.MetaMessage('time_signature',numerator=4,denominator=4),
            mido.Message('note_on',note=60,velocity=80,time=0),
            mido.MetaMessage('midi_port',port=1,time=120),
            mido.Message('note_on',note=60,velocity=90,time=0),
            mido.Message('note_off',note=60,time=120),
            mido.MetaMessage('midi_port',port=0,time=0),
            mido.Message('note_off',note=60,time=120)]))
        stream=BytesIO();midi.save(file=stream);stream.seek(0)
        result=read_midi(stream)
        by_port={n['port']:n for n in result['notes']}
        self.assertEqual((by_port[0]['start_tick'],by_port[0]['end_tick']),(0,360))
        self.assertEqual((by_port[1]['start_tick'],by_port[1]['end_tick']),(120,240))
        self.assertFalse(result['anomalies'])

    def test_missing_initial_meter_requires_review(self):
        with self.assertRaises(ValueError):
            build_measures([(480,3,4)],1920,480,TempoMap([],480))


if __name__=='__main__': unittest.main()
