"""Loss-aware MIDI note and metrical timeline extraction (MIDI is auxiliary).

Keep track/port/channel identities; do not use MIDI playback seconds as recording seconds.
"""
from bisect import bisect_right
from collections import defaultdict, deque
from fractions import Fraction

import mido
import numpy as np


class TempoMap:
    def __init__(self, events, ppq):
        self.ppq = ppq
        by_tick = {0: 500000}
        for tick, tempo in events:
            if tick in by_tick and tick != 0 and by_tick[tick] != tempo:
                raise ValueError(f'Conflicting tempo events at tick {tick}')
            by_tick[tick] = tempo
        self.ticks = sorted(by_tick)
        self.tempos = [by_tick[t] for t in self.ticks]
        self.seconds = [0.0]
        for i in range(1, len(self.ticks)):
            self.seconds.append(self.seconds[-1] +
                (self.ticks[i] - self.ticks[i-1]) * self.tempos[i-1] / ppq / 1e6)

    def at(self, tick):
        i = bisect_right(self.ticks, tick) - 1
        return self.seconds[i] + (float(tick) - self.ticks[i]) * self.tempos[i] / self.ppq / 1e6


def build_measures(meters, end_tick, ppq, tempo):
    meters = sorted(set(meters))
    if not meters or meters[0][0] != 0:
        raise ValueError('Explicit initial meter required; do not guess weak pickup duration')
    if len({t for t, _, _ in meters}) != len(meters):
        raise ValueError('Conflicting meters at the same tick')
    measures = []
    for i, (tick, numerator, denominator) in enumerate(meters):
        boundary = Fraction(meters[i+1][0] if i+1 < len(meters) else end_tick)
        length = Fraction(ppq * 4 * numerator, denominator)
        start = Fraction(tick)
        while start < boundary:
            stop = min(start + length, boundary)
            flags = []
            if stop < start + length:
                flags.append('partial_final_bar' if i == len(meters)-1 else 'meter_change_inside_bar')
            index = len(measures) + 1
            measures.append({'measure_id': f'midi-m{index:04d}',
                'sequence_index': index, 'printed_measure_number': None,
                'score_start_tick': float(start), 'score_end_tick': float(stop),
                'score_start_quarter': float(start / ppq), 'score_end_quarter': float(stop / ppq),
                'midi_start_seconds': tempo.at(start), 'midi_end_seconds': tempo.at(stop),
                'time_signature': f'{numerator}/{denominator}', 'flags': flags,
                'numbering_status': 'midi_inferred_unverified'})
            start = stop
    return measures


def read_midi(path):
    midi = mido.MidiFile(file=path) if hasattr(path,'read') else mido.MidiFile(path)
    if midi.type == 2 or midi.ticks_per_beat <= 0:
        raise ValueError('Only simultaneous PPQ MIDI type 0/1 is supported')
    tempo_events, meters, markers, raw_notes, anomalies = [], [], [], [], []
    end_tick, count_on = 0, 0
    for track_index, track in enumerate(midi.tracks):
        tick, port = 0, 0
        active = defaultdict(deque)
        for event in track:
            tick += event.time
            if event.type == 'set_tempo':
                tempo_events.append((tick, event.tempo))
            elif event.type == 'time_signature':
                meters.append((tick, event.numerator, event.denominator))
            elif event.type == 'marker':
                markers.append({'tick': tick, 'text': event.text, 'track_index': track_index})
            elif event.type == 'midi_port':
                port = event.port
            elif event.type in {'note_on', 'note_off'}:
                key = (port, event.channel, event.note)
                if event.type == 'note_on' and event.velocity > 0:
                    count_on += 1
                    active[key].append((tick, event.velocity))
                elif active[key]:
                    start, velocity = active[key].popleft()
                    if tick > start:
                        raw_notes.append({'start_tick': start, 'end_tick': tick,
                            'pitch': event.note, 'velocity': velocity, 'track_index': track_index,
                            'track_name': track.name, 'port': port, 'channel': event.channel,
                            'is_drum': event.channel == 9})
                    else:
                        anomalies.append({'type': 'zero_duration_note', 'track': track_index, 'tick': tick})
                else:
                    anomalies.append({'type': 'unmatched_note_off', 'track': track_index,
                                      'tick': tick, 'pitch': event.note, 'port': port})
        for key, queue in active.items():
            for start, _ in queue:
                anomalies.append({'type': 'unclosed_note_on', 'track': track_index,
                                  'tick': start, 'pitch': key[2], 'port': key[0]})
        end_tick = max(end_tick, tick)
    tempo = TempoMap(sorted(tempo_events), midi.ticks_per_beat)
    for note in raw_notes:
        note['start'] = tempo.at(note['start_tick'])
        note['duration'] = tempo.at(note['end_tick']) - note['start']
    measures = build_measures(meters, end_tick, midi.ticks_per_beat, tempo)
    for marker in markers:
        marker['midi_seconds'] = tempo.at(marker['tick'])
    return {'ppq': midi.ticks_per_beat, 'notes': raw_notes, 'measures': measures,
            'markers': markers, 'duration': tempo.at(end_tick), 'tempo_events': len(tempo_events),
            'note_on_count': count_on, 'anomalies': anomalies, 'track_count': len(midi.tracks)}


def symbolic_features(notes, duration, rate=50, minimum=21, maximum=108):
    """Create pitch activation and exact onset peaks; unpitched drums excluded."""
    pitch = np.zeros((128, int(np.ceil(duration * rate)) + 1))
    peaks = defaultdict(list)
    selected = []
    for note in notes:
        if note['is_drum'] or not minimum <= note['pitch'] <= maximum:
            continue
        p = note['pitch']
        first = int(np.floor(note['start'] * rate))
        last = min(pitch.shape[1], int(np.ceil((note['start'] + note['duration']) * rate)) + 1)
        pitch[p, first:last] += note['velocity'] / 127
        peaks[p].append((note['start'] * 1000, note['velocity'] / 1e6))
        selected.append(note)
    return pitch, {p: np.asarray(values, dtype=float).T for p, values in peaks.items()}, selected
