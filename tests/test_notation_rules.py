import unittest
from backend.structure_analysis.notation import octave_assignment,octave_for_head,barline_positions,alternating_runs,tremolo_bridges
from backend.structure_analysis.orchestration import notation_activity_bridges


class NotationRules(unittest.TestCase):
    def test_bassa_suffix_selects_staff_above_even_if_next_staff_is_nearer(self):
        staves=[{'id':'piano','lines_pt':[100,104,108,112,116]}, {'id':'violin','lines_pt':[136,140,144,148,152]}]
        glyph={'code':0xE510,'text':'8','x':200,'y':132}
        suffix={'code':98,'text':'b','x':205,'y':132}
        chosen=octave_assignment(glyph,[glyph,suffix],staves)
        self.assertEqual(chosen['staff']['id'],'piano');self.assertEqual(chosen['direction'],-1)

    def test_bare_ottava_is_local_and_dashed_line_allows_small_anchor_offset(self):
        staff={'id':'s','lines_pt':[100,104,108,112,116]}
        mark={'id':'oct','kind':'octave_sign','staff_id':'s','x_pt':200,'y_pt':130,'direction':-1,'octave_count':1}
        self.assertEqual(octave_for_head({'x':199.8},staff,[mark],[],4)[0],-12)
        self.assertEqual(octave_for_head({'x':230},staff,[mark],[],4)[0],0)
        line={'x0':210,'x1':300,'top':130,'height':0,'dash':([2,2],0)}
        self.assertEqual(octave_for_head({'x':199.8},staff,[mark],[line],4)[0],-12)
        self.assertEqual(octave_for_head({'x':301},staff,[mark],[line],4)[0],0)

    def test_long_stem_cannot_reset_local_accidentals(self):
        shared={'width':0,'height':30,'top':95,'bottom':125}
        stem={**shared,'x0':110,'linewidth':.405};bar={**shared,'x0':180,'linewidth':.8}
        self.assertEqual(barline_positions([stem,bar],[100,104,108,112,116]),[180])

    def test_tremolo_realization_requires_repeated_alternation_of_complete_chords(self):
        notes=[{'id':str(i),'start_tick':i*60,'pitch':p} for i,p in enumerate([21,22,21,22,21])]
        found=alternating_runs(notes,[21],[22]);self.assertEqual(len(found),1)
        self.assertFalse(alternating_runs(notes[:3],[21],[22]))
        self.assertFalse(alternating_runs(notes,[21],[22,34]))

    def test_ordinary_black_beamed_notes_are_not_half_note_tremolo(self):
        head={'staff_id':'s','head_class':'black'}
        self.assertEqual(tremolo_bridges(1,[head],[{'id':'s','lines_pt':[100,104,108,112,116]}],[],[]),[])

    def test_only_notation_supported_tremolo_gaps_are_bridged_without_changing_notes(self):
        notes=[{'id':str(i),'part_id':'cello','start_tick':i*60,'sounding_end_tick':i*60+58,
                'midi_measure_candidate':1,'score_locations':[{'id':'head'}]} for i in range(3)]
        self.assertFalse(notation_activity_bridges(notes,[],480))
        mark={'id':'trem','kind':'single_chord_tremolo_candidate','head_ids':['head'],'part_id':'cello','midi_measure_candidates':[1]}
        bridges=notation_activity_bridges(notes,[mark],480)
        self.assertEqual([(b['start_tick'],b['end_tick']) for b in bridges],[(58,60),(118,120)])
        self.assertEqual(notes[0]['sounding_end_tick'],58)


if __name__=='__main__':unittest.main()
