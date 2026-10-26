import copy
import json
from pathlib import Path
import sys
import unittest
import uuid
import shutil
import threading
from urllib.request import urlopen
from urllib.error import HTTPError

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
sys.path.insert(0,str(ROOT/'scripts'))
from backend.structure_analysis.harmony import sonority,analyze as harmony
from backend.structure_analysis.counterpoint import analyze as counterpoint,streams
from backend.structure_analysis.motif import MotifAnalyzer
from backend.structure_analysis.form import analyze as form_analysis
from backend.structure_analysis.store import load_bundle,validate_run,event_evidence
from backend.structure_analysis.common import read,digest
from backend.structure_analysis.comparison import record_comparison


def note(id,pitch,start,end,part='a',sustain=None):
    return {'id':id,'pitch':pitch,'start_tick':start,'key_end_tick':end,'sounding_end_tick':sustain or end,
        'part_id':part,'is_drum':False,'score_locations':[],
        'correspondence':{'octave_agrees':False,'pitch_class_agrees':False}}


class StructureAlgorithms(unittest.TestCase):
    def test_bass_defines_inversion_and_quartal_is_not_forced_to_ii(self):
        chord=sonority([57,62,66])['candidates'][0]
        self.assertEqual((chord['root_pc'],chord['quality'],chord['inversion_index']),(2,'major',2))
        self.assertEqual(sonority([40,45,50,55])['structures'],['stacked_fourths'])
        self.assertEqual(sonority([45,49,55])['candidates'][0]['omitted_pcs'],[4])

    def test_sounding_overlap_is_not_arpeggiated_union_and_CC64_is_separate(self):
        excerpt=[{'id':'x','start_tick':0,'end_tick':1440}]
        notes=[note('c',60,0,480),note('e',64,480,960),note('g',67,960,1440)]
        result=harmony(notes,excerpt,480)
        self.assertTrue(all(len(w['sonority']['pitch_classes'])==1 for w in result['windows']))
        self.assertEqual(result['arpeggiated_reductions'][0]['collection']['pitch_classes'],[0,4,7])
        self.assertFalse(result['arpeggiated_reductions'][0]['simultaneous'])
        notes=[note('residue',21,0,120,sustain=1440),note('a',57,480,960),note('d',62,480,960),note('f',66,480,960)]
        window=next(w for w in harmony(notes,excerpt,480)['windows'] if w['start_tick']==480)
        self.assertEqual(window['sonority']['bass'],21)
        self.assertEqual(window['key_held_sonority']['bass'],57)
        self.assertEqual(window['pedal_residue_note_ids'],['residue'])
        self.assertTrue(any(w['start_tick']==120 for w in harmony(notes,excerpt,480)['windows']))

    def test_exact_doubling_and_rhythmic_independence_are_not_fugues(self):
        notes=[note(f'a{i}',p,i*480,(i+1)*480,'a') for i,p in enumerate([60,62,65,64])]
        notes += [note(f'b{i}',p+12,i*480,(i+1)*480,'b') for i,p in enumerate([60,62,65,64])]
        result=counterpoint(notes,[{'id':'x','start_tick':0,'end_tick':1920}],480)
        self.assertTrue(any(r['kind']=='unison_or_octave_doubling' for r in result['relations']))
        self.assertFalse(any('fugue'==r['kind'] or 'canon'==r['kind'] for r in result['relations']))

    def test_imitation_requires_interval_and_rhythm_witnesses(self):
        notes=[note(f'a{i}',p,t,t+100,'a') for i,(p,t) in enumerate(zip([60,62,65,64,67],[0,100,200,400,500]))]
        notes += [note(f'b{i}',p+7,t+1000,t+1100,'b') for i,(p,t) in enumerate(zip([60,62,65,64,67],[0,100,200,400,500]))]
        excerpts=[{'id':'x','start_tick':0,'end_tick':2000}]
        result=MotifAnalyzer().analyze([{**s,'notes':[n['id'] for n in s['notes']]} for s in streams(notes)],notes,excerpts)
        witness=result['imitation_candidates'][0]
        self.assertEqual(witness['transposition_semitones'],7)
        self.assertEqual(witness['prototype']['intervals_semitones'],[2,3,-1,3])
        self.assertEqual(witness['answer']['ioi_ratios'],['1','1','2','1'])
        changed=copy.deepcopy(notes);changed[-2]['start_tick']+=13
        altered=MotifAnalyzer().analyze([{**s,'notes':[n['id'] for n in s['notes']]} for s in streams(changed)],changed,excerpts)
        self.assertFalse(altered['imitation_candidates'])

    def test_meter_change_alone_is_not_a_formal_boundary(self):
        result=form_analysis([], [{'id':'x','start_tick':0,'end_tick':3000}],480,[[1440,2,4]],
            {'activity_edges':[]},{'windows':[]},{'motifs':[]})
        self.assertEqual(result['boundaries'][0]['status'],'single_signal_insufficient')
        self.assertEqual(result['formal_model'],'unassigned_pending_independent_evidence')

    def test_held_bass_and_moving_line_need_overlap_not_two_joint_attacks(self):
        notes=[note('bass',40,0,1440,'bass')]+[note('melody'+str(i),p,i*480,(i+1)*480,'line') for i,p in enumerate([60,62,64])]
        relationships=counterpoint(notes,[{'id':'x','start_tick':0,'end_tick':1440}],480)['relations']
        self.assertTrue(any(r['comparison_basis']=='held_key_overlap_samples' and any(m['type']=='oblique' for m in r['motions']) for r in relationships))

    def test_separate_midi_staves_do_not_become_an_alternating_melody(self):
        notes=[{**note('upper',84,0,240,'piano'),'track_index':23},{**note('lower',24,240,480,'piano'),'track_index':24}]
        values=streams(notes)
        self.assertEqual(len(values),2);self.assertTrue(all(len(s['notes'])==1 for s in values))


class RealRavelContent(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bundle=load_bundle(ROOT,ROOT)
        if cls.bundle is None:raise unittest.SkipTest('Precomputed Ravel engine not activated')
        cls.run_path=ROOT/cls.bundle['run_path']
        cls.notes=read(cls.run_path/'notes.json')['notes']
        cls.harmony=read(cls.run_path/'harmony.json')
        cls.pdf=read(cls.run_path/'pdf-observations.json')

    def window(self,tick):
        return next(w for w in self.harmony['windows'] if w['start_tick']<=tick<w['end_tick'])

    def test_opening_is_actual_fourth_collection_in_three_low_string_layers(self):
        window=self.window(0)
        self.assertEqual(window['sonority']['pitch_classes'],[2,4,7,9])
        self.assertEqual(window['sonority']['bass'],28)
        self.assertIn('stacked_fourths',window['sonority']['structures'])
        selected=[n for n in self.notes if n['id'] in window['note_ids']]
        self.assertEqual({n['part_id'] for n in selected},{'cello','double-bass'})
        self.assertTrue(all(any(p['page']==1 and p['notation_role']=='onset_correspondence_candidate' for p in n['score_locations']) for n in selected))

    def test_contrabassoon_entry_has_native_written_pitch_and_octave_transposition(self):
        first=min((n for n in self.notes if n['part_id']=='contrabassoon'),key=lambda n:n['start_tick'])
        self.assertEqual((first['start_tick'],first['pitch']),(2760,28))
        observed=next(h for h in self.pdf['notes'] if h['id']==first['score_locations'][0]['id'])
        self.assertEqual((observed['written_pitch_candidate'],observed['transpose_semitones']),(40,-12))

    def test_return_orchestral_attack_and_piano_pedal_are_different_sonorities(self):
        window=self.window(90120)
        attack=window['key_held_sonority'];candidate=attack['candidates'][0]
        self.assertEqual((attack['pitch_classes'],attack['bass']),([2,6,9],57))
        self.assertEqual(candidate['inversion_index'],2)
        self.assertEqual(window['sonority']['bass'],21)
        self.assertTrue(window['pedal_residue_note_ids'])
        self.assertNotEqual(window['sonority']['pitch_classes'],attack['pitch_classes'])
        residue=[n for n in self.notes if n['id'] in window['pedal_residue_note_ids']]
        self.assertEqual({n['part_id'] for n in residue},{'piano'})

    def test_orchestra_return_is_entered_by_real_parts_while_low_strings_wait(self):
        activity=read(self.run_path/'instrument-activity.json')
        edge=next(e for e in activity['activity_edges'] if e['tick']==90120)
        self.assertTrue({'flute','horn','violin-1','violin-2'}<=set(edge['entered']))
        self.assertNotIn('cello',edge['active_parts'])
        self.assertTrue(any(m['kind']=='dynamic' and m['page']==15 and m['value']=='ff' for m in self.pdf['marks']))
        self.assertTrue(any(e['tick']==90720 and 'double-bass' in e['active_parts'] for e in activity['activity_edges']))

    def test_literal_real_score_patterns_have_checkable_pitch_and_rhythm_correspondence(self):
        motifs=read(self.run_path/'theme-identities.json')['motifs']
        self.assertTrue(motifs)
        for motif in motifs[:12]:
            for occurrence in motif['occurrences']:
                pitches=occurrence['pitches'];ticks=occurrence['onset_ticks']
                self.assertEqual([b-a for a,b in zip(pitches,pitches[1:])],motif['intervals_semitones'])
                self.assertEqual(len(ticks),5)
            self.assertEqual(motif['theme_identity'],'unassigned')

    def test_contrabassoon_to_piano_correspondence_is_recall_candidate_not_concurrent_imitation(self):
        motif=next(m for m in read(self.run_path/'theme-identities.json')['motifs'] if any(o['pitches']==[43,40,35,33,31] for o in m['occurrences']))
        witness=next(w for w in motif['witnesses'] if w['answer']['pitches']==[74,71,66,64,62])
        self.assertEqual(motif['intervals_semitones'],[-3,-5,-2,-2])
        self.assertEqual(motif['ioi_ratios'],['1','3','1','7'])
        self.assertEqual(witness['transposition_semitones'],31)
        self.assertEqual(witness['temporal_relation'],'nonoverlapping_transfer_or_recall')
        byid={n['id']:n for n in self.notes}
        self.assertTrue(all(byid[id]['correspondence']['octave_agrees'] for o in motif['occurrences'] for id in o['note_ids']))

    def test_real_bassoon_cello_doubling_and_solo_entry_are_not_independent_voice_claims(self):
        relations=read(self.run_path/'counterpoint.json')['relations']
        self.assertTrue(any(r['kind']=='unison_or_octave_doubling' and r['stream_ids']==['bassoon:track7:upper','cello:track33:upper'] and set(r['simultaneous_intervals_semitones'])=={0} for r in relations))
        edges=read(self.run_path/'instrument-activity.json')['activity_edges']
        self.assertEqual(next(e for e in edges if e['tick']==38658)['active_parts'],['piano'])
        boundary=next(b for b in read(self.run_path/'form.json')['boundaries'] if b['tick']==90120)
        self.assertEqual(boundary['status'],'multi_signal_candidate')
        self.assertIn('not_automatic',boundary['function'])

    def test_hierarchy_and_expansion_gate_keep_unknowns_visible(self):
        f=read(self.run_path/'form.json')
        self.assertEqual({u['level'] for u in f['units']},{'work','movement','section','phrase','motif'})
        self.assertTrue(any(b['status']=='single_signal_insufficient' for b in f['boundaries']))
        self.assertFalse(self.bundle['summary']['expansion_gate']['C_D_enabled'])
        self.assertEqual(self.bundle['summary']['human_review_count'],0)
        self.assertEqual(self.bundle['summary']['expert_review_count'],0)

    def test_evidence_endpoint_payload_resolves_real_notes_and_preserves_immutable_round(self):
        event=next(e for e in self.bundle['events'] if e['dimension']=='harmony')
        payload=event_evidence(ROOT,ROOT,event['id'])
        self.assertEqual({n['id'] for n in payload['facts']['notes']},set(event['raw_evidence_ids']))
        validate_run(self.run_path,ROOT)
        self.assertIn('literature text',self.bundle['manifest']['excluded_inputs'])
        self.assertTrue(payload['native_noteheads'])
        form_event=next(e for e in self.bundle['events'] if e['dimension']=='form')
        form_payload=event_evidence(ROOT,ROOT,form_event['id'])
        self.assertTrue(form_payload['hierarchy'])
        self.assertTrue(form_payload['motif_patterns'])

    def test_frozen_artifact_change_and_comparison_overwrite_are_rejected(self):
        folder=ROOT/'tmp'/('engine-test-'+uuid.uuid4().hex);folder.mkdir(parents=True)
        try:
            copy=folder/'round1';shutil.copytree(self.run_path,copy)
            (copy/'harmony.json').write_text('{}',encoding='utf-8')
            with self.assertRaisesRegex(ValueError,'fingerprint'):validate_run(copy,ROOT,check_sources=False)
            document={k:[] for k in ['agreement','disagreement','independent_unvalidated','unresolved']}
            document['prior_exposure_statement']='Earlier literature exposure disclosed.'
            source=folder/'comparison-input.json';source.write_text(json.dumps(document),encoding='utf-8')
            output=folder/'round2.json';record_comparison(ROOT,self.run_path,source,output)
            with self.assertRaisesRegex(ValueError,'Preserve'):record_comparison(ROOT,self.run_path,source,output)
        finally:shutil.rmtree(folder)


    def test_notehead_box_contains_observed_anchor_not_displaced_font_metrics(self):
        for n in self.pdf['notes']:
            x,y,w,h=n['rect_pt']
            self.assertLessEqual(y,n['y_pt']);self.assertGreaterEqual(y+h,n['y_pt'])
            self.assertIn('font_bbox_pt',n)

    def test_piano_first_octave_sign_belongs_to_piano_and_corrects_A0_A1(self):
        first=[n for n in self.notes if n['part_id']=='piano' and n['start_tick']==38640]
        byid={h['id']:h for h in self.pdf['notes']}
        self.assertEqual({n['pitch'] for n in first},{21,33})
        for n in first:
            h=byid[n['score_locations'][0]['id']]
            self.assertEqual(h['octave_line_shift'],-12)
            self.assertEqual(h['concert_pitch_candidate'],n['pitch'])

    def test_bar55_C_and_F_naturals_survive_intervening_stems(self):
        notes=[h for h in self.pdf['notes'] if h['staff_id']=='pdf-p012-staff07' and 94<=h['x_pt']<=296.5]
        self.assertGreater(len(notes),12)
        self.assertEqual({h['concert_pitch_candidate']%12 for h in notes},{0,5})

    def test_F_minor_seventh_reduction_retains_upper_chord_and_pedal_bass_distinction(self):
        window=self.window(74200)
        chord=window['sonority']['candidates'][0]
        self.assertEqual((chord['root_pc'],chord['quality'],chord['inversion_index']),(5,'minor7',0))
        self.assertEqual(window['key_held_sonority']['bass'],41)
        self.assertEqual(window['sonority']['bass'],29)
        self.assertTrue(window['pdf_input_complete'])

    def test_score_review_cannot_be_presented_as_human_or_expert_acceptance(self):
        window=self.window(74200)
        payload=event_evidence(ROOT,ROOT,'engine-'+window['id'])
        review=next(c for c in payload['case_reviews'] if c['id']=='AB-H2')
        self.assertIn('not_human_or_expert',review['review_status'])
        self.assertTrue(any('Fm7' in finding for finding in review['findings']))
        self.assertIsNone(payload['review_warning'])

    def test_notated_double_tremolo_is_traced_without_inventing_onset_heads(self):
        marks=[m for m in self.pdf['marks'] if m['kind']=='two_note_tremolo_candidate']
        self.assertEqual(len(marks),2)
        self.assertTrue(all(len(m['beam_polygons_pt'])==3 and m['page']==14 for m in marks))
        realized=[n for n in self.notes if any(l['notation_role']=='two_note_tremolo_realization_candidate' for l in n['score_locations'])]
        self.assertGreaterEqual(len(realized),35)
        byid={h['id']:h for h in self.pdf['notes']}
        for n in realized:
            self.assertTrue(n['correspondence']['octave_agrees'])
            self.assertEqual(byid[n['score_locations'][0]['id']]['concert_pitch_candidate'],n['pitch'])

    def test_cello_tremolo_without_extracted_Trem_text_uses_actual_cross_stem_slashes(self):
        marks=[m for m in self.pdf['marks'] if m['kind']=='single_chord_tremolo_candidate' and m['part_id']=='cello' and m['page']==10]
        self.assertEqual(len(marks),2)
        self.assertTrue(all(len(m['beam_polygons_pt'])==3 for m in marks))
        realized=[n for n in self.notes if n['part_id']=='cello' and any(l['notation_role']=='single_chord_tremolo_realization_candidate' for l in n['score_locations'])]
        self.assertEqual(len(realized),60)

    def test_continuation_only_correspondence_has_correct_independent_status(self):
        n=next(n for n in self.notes if n['part_id']=='flute' and n['start_tick']==37440 and n['pitch']==81)
        self.assertEqual(n['correspondence']['status'],'continuation_only_candidate')
        self.assertTrue(n['correspondence']['onset_not_located'])

    def test_actual_structure_http_evidence_and_invalid_identifiers(self):
        from scripts import serve_review
        server=serve_review.ReviewServer(('127.0.0.1',0),serve_review.Handler)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        base=f'http://127.0.0.1:{server.server_port}'
        try:
            with urlopen(base+'/api/structure?track=ravel-left-hand') as response:self.assertTrue(json.load(response)['available'])
            event=self.bundle['events'][0]
            with urlopen(base+'/api/structure-evidence?track=ravel-left-hand&event_id='+event['id']) as response:
                self.assertEqual(json.load(response)['event_id'],event['id'])
            for path,code in [('/api/structure?track=../../',404),('/api/structure-evidence?track=ravel-left-hand&event_id=../notes.json',422)]:
                with self.assertRaises(HTTPError) as error:urlopen(base+path)
                self.assertEqual(error.exception.code,code);error.exception.close()
            with urlopen(base+'/api/structure?track=lark-ascending') as response:self.assertFalse(json.load(response)['available'])
        finally:server.shutdown();server.server_close();thread.join()


if __name__=='__main__':unittest.main()
