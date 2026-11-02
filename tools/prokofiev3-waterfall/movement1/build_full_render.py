"""Build a reproducible visual score for the aligned first movement.

The source alignment remains untouched. Colour, density and photographic
backdrop envelopes live here so a passage can be rerendered independently.
"""
from __future__ import annotations

import copy
import json
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OPENING = ROOT / "prokofiev3-opening180.timeline.json"
ALIGNMENT = ROOT / "prokofiev3-full-alignment.json"
OUTPUT = ROOT / "prokofiev3-full-render.timeline.json"
REVIEWED_NOTES = ROOT / "prokofiev3-reviewed-note-corrections.json"
DURATION = 580.0
INTRO_LEAD = 5.0
# The supplied recording has about seven seconds of room sound after the
# final aligned score event. Keep it for a gradual visual fade.
RECORDING_END = 587.08
VIDEO_DURATION = 592.1
PLATE_BRIGHTNESS_GAIN = 1.78
RHYTHM_FLASH_GAIN = 1.56
RHYTHM_FLASH_TIME_SCALE = 1 / 2


def section(start, name, transition, previous, *, low, high, lead, chord,
            neutral, strike, keyboard, background, veil, material,
            density, life, glow, strength, crystal=0.025, metal=0.015,
            ember=0.0):
    look = copy.deepcopy(previous)
    look["colors"].update(piano_low=low, piano_high=high, strike=strike)
    look["appearance"].update(
        material=material, orchestra_lead_color=lead,
        orchestra_chord_color=chord, orchestra_neutral_color=neutral,
        keyboard_tint=keyboard, horizon_tint=strike,
        background_tint=background, veil_tint=veil,
        keyboard_crystal_amount=crystal, keyboard_metal_amount=metal,
        keyboard_ember_amount=ember, particle_life_scale=life,
        material_amount=1.1 if material != "gilded" else 1.27,
    )
    for key in ("ember_per_second", "streak_per_second", "smoke_per_second",
                "light_per_second", "glint_per_second", "filament_per_second"):
        look["density"][key] = round(previous["density"][key] * density, 4)
    look["density"]["ember_attack_count"] = min(500, round(
        previous["density"]["ember_attack_count"] * density))
    look["brightness"]["note_glow"] = glow
    look["brightness"]["strike_flash"] = strength
    return {"name": name, "start_seconds": start,
            "end_seconds": DURATION, "transition_seconds": transition,
            "preset": look}


def apply_reviewed_note_corrections(notes):
    """Keep small score/audio corrections separate from the global matcher.

    The render timeline is rebuilt from the original alignment plus this
    auditable overlay; regenerating the global alignment cannot silently undo
    the manually checked local notes.
    """
    fixes = json.loads(REVIEWED_NOTES.read_text())
    by_id = {note["score_id"]: note for note in notes}
    missing = (set(fixes["remove_score_ids"]) |
               set(fixes["retime_audio_start"]) |
               set(fixes["promote_score_ids"]) |
               {entry["template_score_id"] for entry in fixes["restore_notes"]}) - set(by_id)
    if missing:
        raise ValueError(f"Reviewed score events are missing: {sorted(missing)}")
    for score_id, new_start in fixes["retime_audio_start"].items():
        note = by_id[score_id]
        shift = new_start - note["audio_start"]
        note["audio_start"] = round(new_start, 4)
        note["audio_end"] = round(max(new_start + .07, note["audio_end"] + shift), 4)
        note["onset_source"] = "reviewed_orchestra_pitch_attack"
        note["release_source"] = "reviewed_duration_shift"
    for score_id in fixes["promote_score_ids"]:
        note = by_id[score_id]
        note["visual_role"] = "lead"
        note["musical_role"] = "orchestra_melody"
        note.update(accent_color="#e2c78e", accent_emitter_scale=.72,
                    accent_filament_attack_count=2,
                    accent_filament_per_second=1.3,
                    accent_light_per_second=1.6)
    for entry in fixes["restore_notes"]:
        score_id = entry["score_id"]
        if score_id in by_id:
            raise ValueError(f"Reviewed note already exists: {score_id}")
        note = copy.deepcopy(by_id[entry["template_score_id"]])
        note.update(score_id=score_id, event_id=entry["event_id"],
                    midi_pitch=entry["midi_pitch"],
                    score_start_beat=entry["score_start_beat"],
                    audio_start=entry["audio_start"],
                    audio_end=entry["audio_end"],
                    visual_role="lead", musical_role="orchestra_melody",
                    onset_source="reviewed_score_and_audio",
                    release_source="reviewed_score_bounded")
        notes.append(note)
    return sorted((note for note in notes
                   if note["score_id"] not in fixes["remove_score_ids"]),
                  key=lambda note: (note["audio_start"], note["midi_pitch"]))


def build():
    original = json.loads(OPENING.read_text())
    aligned = json.loads(ALIGNMENT.read_text())
    if aligned["alignment_interval_seconds"] != [0, DURATION]:
        raise ValueError("Full alignment has changed")
    timeline = {key: original[key] for key in
                ("format_version", "orchestra_pressed_keys", "sources")}
    timeline["title"] = "Prokofiev Piano Concerto No. 3, movement I — full"
    timeline["render_interval"] = dict(start_seconds=0,
                                       duration_seconds=VIDEO_DURATION,
                                       lookahead_seconds=5)
    timeline["intro"] = dict(
        lead_in_seconds=INTRO_LEAD,
        title="PIANO CONCERTO",
        subtitle="NO. 3 IN C MAJOR  ·  OP. 26  ·  I. ANDANTE – ALLEGRO",
        composer="PROKOFIEV",
        credit="LANG LANG  ·  SIR SIMON RATTLE  ·  BERLINER PHILHARMONIKER",
        title_fade_in_seconds=.85,
        title_fade_out_start_seconds=3.35,
        title_fade_out_end_seconds=5.55,
        keyboard_fade_start_seconds=4.25,
        keyboard_fade_end_seconds=6.5,
    )
    timeline["outro"] = dict(fade_start_seconds=580.2,
                             fade_end_seconds=RECORDING_END)
    timeline["visual_sections"] = copy.deepcopy(original["visual_sections"])
    for s in timeline["visual_sections"]:
        s["end_seconds"] = DURATION
    last = timeline["visual_sections"][-1]["preset"]
    base_density = copy.deepcopy(last["density"])
    # Times are seconds in the supplied Lang Lang / Rattle recording.
    moments = [
        (195, "Piano and orchestra in shadow", 9, "#dac9b4", "#8ac6d4", "#a5d6dd", "#d0ab78", "#aeb8bf", "#8ac6d4", "#aeb6bf", "#20374b", "#8cbaca", "crystal", .83, .91, 1.13, 1.0),
        (224, "Pressure before the burst", 6, "#e2c4a2", "#96c8d5", "#e8b98c", "#d69465", "#abb2b8", "#c5d0d0", "#aaa5a8", "#3c323b", "#b49ba8", "metal", 1.16, 1.0, 1.22, 1.1),
        (230, "Glass and gold detonation", 1.8, "#f2c26f", "#a9ddeb", "#e8cb96", "#f3aa62", "#adb8c2", "#f4d590", "#aeb2bb", "#423a3b", "#d5b7a1", "gilded", 1.31, 1.13, 1.33, 1.2),
        (246, "Dancing crossfire", 4, "#e2b785", "#8ed0de", "#e0bd91", "#d88865", "#aeb8be", "#c4d5d8", "#aab2bd", "#293644", "#a5bbc6", "crystal", .86, .90, 1.18, 1.03),
        (257, "Autumn orchestral crest", 3, "#f3bb70", "#dfd2b5", "#f5d497", "#b87a5b", "#b6b8bb", "#efc186", "#b7aa9d", "#49342b", "#d4a771", "gilded", 1.42, 1.25, 1.39, 1.25),
        (278, "Amber receding", 9, "#e5bc8c", "#bfd3d6", "#dec9ab", "#aa866e", "#afb8bd", "#d7c4aa", "#b4aaa2", "#2e3339", "#bdad9a", "glass", .74, 1.02, 1.14, 1.01),
        (292, "Piano autumn afterglow", 3, "#e4cdab", "#9bd0df", "#c9d2ca", "#afad96", "#a8b7bd", "#a9cdd3", "#b8b0aa", "#263d4b", "#a3bbbf", "glass", .82, 1.15, 1.13, .98),
        (323, "Piano study", 12, "#d7ceba", "#a1c4d7", "#aac5d0", "#a2b2b2", "#a8b6bb", "#a1c4d7", "#b6b1b2", "#203845", "#92b5c4", "crystal", .82, .96, 1.12, 1.0),
        (365, "Hushed orchestral swell", 12, "#dfcbad", "#a6d2df", "#b6d6de", "#c4b8a9", "#adb7bd", "#a6d2df", "#b8b5b3", "#2a4252", "#a6c5d7", "glass", 1.08, 1.12, 1.22, 1.08),
        (390, "Restless return", 8, "#e7c29c", "#8ed3d5", "#edc29d", "#b69ca4", "#aeb5be", "#e0c4b1", "#b6adad", "#333944", "#b6b1c0", "metal", 1.13, 1.02, 1.24, 1.12),
        (430, "Orchestral surge", 11, "#ebc889", "#b8d6d9", "#f0c597", "#cb8c74", "#adb8bf", "#e3cfac", "#b6aba5", "#3b393c", "#c7b2a3", "gilded", 1.21, 1.10, 1.3, 1.15),
        (468, "Warmth over shadow", 13, "#ddc5a2", "#9bbfd4", "#d2d1c3", "#b3a2a0", "#a9b6bf", "#adc9d1", "#b0adae", "#27384a", "#a7b6ca", "glass", .82, .96, 1.14, 1.0),
        (511, "Final ascent", 12, "#e8c48d", "#8bcbd7", "#e5c390", "#bb9f92", "#afb7bd", "#d8c5a6", "#b7b2ab", "#303c46", "#b7b7b5", "crystal", 1.23, 1.10, 1.25, 1.13),
        (552, "Golden sprint", 9, "#f2c47d", "#c6dfe0", "#f0d7a4", "#d4a07e", "#aeb6bc", "#f1d5a5", "#b8aeaa", "#3d3939", "#d4bcaa", "gilded", 1.35, 1.16, 1.37, 1.2),
        (574, "Closing glow", 4, "#efcf9c", "#bfd6dc", "#e5d1b2", "#c6a48a", "#b1b9be", "#e5d2b8", "#b5b3b2", "#323a42", "#c8c3be", "glass", .73, 1.05, 1.16, 1.04),
    ]
    for m in moments:
        s = section(*m[:3], last, low=m[3], high=m[4], lead=m[5],
                    chord=m[6], neutral=m[7], strike=m[8], keyboard=m[9],
                    background=m[10], veil=m[11], material=m[12],
                    density=m[13], life=m[14], glow=m[15], strength=m[16])
        for key in ("ember_per_second", "streak_per_second", "smoke_per_second",
                    "light_per_second", "glint_per_second", "filament_per_second"):
            s["preset"]["density"][key] = round(base_density[key] * m[13], 4)
        s["preset"]["density"]["ember_attack_count"] = round(
            base_density["ember_attack_count"] * m[13])
        timeline["visual_sections"].append(s)
        last = s["preset"]
    # Ordinary key-triggered emitters follow the notes, not the rhythmic
    # backdrop pulses. These profiles give each musical passage its own plume
    # speed, wind, trail density and afterglow without changing note timing.
    emitter_profiles = {
        0: dict(filament=1.0, streak=1.0, speed=.91, wind=.90, life=1.12),
        40: dict(filament=2.0, streak=1.18, speed=1.10, wind=1.15,
                 life=.90, attacks=2),
        49: dict(filament=2.0, streak=1.12, speed=1.06, wind=1.08,
                 life=1.02, attacks=2),
        90: dict(filament=1.55, streak=1.05, speed=.98, wind=1.04),
        122: dict(filament=1.12, streak=.92, speed=.88, wind=.91,
                  life=1.14),
        139: dict(filament=2.25, streak=1.17, speed=1.04, wind=1.19,
                  attacks=2),
        156: dict(filament=2.1, streak=1.15, speed=1.08, wind=1.12,
                  attacks=2),
        173: dict(filament=2.45, streak=1.26, speed=1.15, wind=1.23,
                  life=.90, attacks=2),
        195: dict(filament=1.35, streak=.96, speed=.92, wind=1.05,
                  life=1.11),
        224: dict(filament=2.35, streak=1.22, speed=1.09, wind=1.20,
                  attacks=2),
        230: dict(filament=2.75, streak=1.34, speed=1.16, wind=1.32,
                  life=1.08, attacks=3),
        246: dict(filament=2.15, streak=1.20, speed=1.15, wind=1.29,
                  life=.87, attacks=2),
        257: dict(filament=2.15, streak=1.13, speed=.91, wind=1.25,
                  life=1.20, attacks=2),
        278: dict(filament=1.35, streak=.93, speed=.86, wind=1.08,
                  life=1.17),
        292: dict(filament=1.55, streak=1.0, speed=.89, wind=1.10,
                  life=1.13),
        323: dict(filament=1.12, streak=.95, speed=.92, wind=.91,
                  life=1.08),
        365: dict(filament=1.8, streak=1.08, speed=.93, wind=1.15,
                  life=1.18, attacks=2),
        390: dict(filament=2.3, streak=1.23, speed=1.12, wind=1.25,
                  life=.95, attacks=2),
        430: dict(filament=2.75, streak=1.30, speed=1.14, wind=1.32,
                  life=1.08, attacks=3),
        468: dict(filament=1.45, streak=.96, speed=.89, wind=1.04,
                  life=1.15),
        511: dict(filament=2.5, streak=1.25, speed=1.11, wind=1.24,
                  life=1.05, attacks=2),
        552: dict(filament=2.9, streak=1.33, speed=1.17, wind=1.30,
                  life=1.07, attacks=3),
        574: dict(filament=.85, streak=.82, speed=.75, wind=1.12,
                  life=1.27),
    }
    for passage in timeline["visual_sections"]:
        profile = emitter_profiles[passage["start_seconds"]]
        preset = passage["preset"]
        density = preset["density"]
        for key, factor in (("filament_per_second", profile["filament"]),
                            ("streak_per_second", profile["streak"]),
                            ("light_per_second", 1 + .16 * (profile["filament"]-1)),
                            ("glint_per_second", 1 + .10 * (profile["filament"]-1))):
            density[key] = round(density[key] * factor, 4)
        density["filament_attack_count"] = profile.get("attacks", 1)
        motion = preset["motion"]
        for key in ("flight_speed_scale", "launch_speed_scale"):
            motion[key] = round(motion[key] * profile["speed"], 4)
        for key in ("horizontal_wind_scale", "vertical_wind_scale"):
            motion[key] = round(motion[key] * profile["wind"], 4)
        motion["launch_angle_sweep_rate"] = round(
            motion["launch_angle_sweep_rate"] *
            (profile["speed"] * .8 + .2), 4)
        preset["appearance"]["particle_life_scale"] = round(
            preset["appearance"]["particle_life_scale"] *
            profile.get("life", 1), 4)
        preset["brightness"]["filament"] = round(
            min(1.4, 1 + .12 * (profile["filament"]-1)), 4)
    # Plate weights are independent of note brightness. These envelopes are
    # intentionally authored in absolute recording time for local rerenders.
    def b(time, a=0, c=0, d=0, e=0, first="#9bc8d8", second="#d8b989"):
        # The plates remain visible between rhythmic waves. Raise their
        # ordinary luminance without touching note/key exposure.
        gain = PLATE_BRIGHTNESS_GAIN
        return dict(time=time, plate_a=min(.82, a * gain), plate_b=0,
                    plate_c=min(.82, c * gain),
                    plate_d=min(.82, d * gain), plate_e=min(.82, e * gain),
                    backdrop_light_tint=first, backdrop_second_tint=second)
    timeline["backdrop_sections"] = [
        b(0), b(126),
        # Show the warm reflection already at video 2:12 and carry the same
        # plate continuously through the original 2:28 entrance.
        b(127, e=.34, first="#e9c594", second="#a9c7d2"),
        b(130, e=.34, first="#e9c594", second="#a9c7d2"),
        b(138, e=.35, first="#e9c594", second="#a9c7d2"),
        b(142, e=.35, first="#e9c594", second="#a9c7d2"),
        b(146, e=.34, first="#e9c594", second="#a9c7d2"),
        b(188, e=.34), b(202, e=.30), b(206),
        b(229.98), b(230.22, c=.40, first="#e4d2ad", second="#a9d8ed"),
        b(239, c=.43), b(248, c=.40), b(254),
        b(258, a=.40, first="#efbd70", second="#c4b8a5"),
        b(292, a=.43), b(338, a=.37), b(344),
        b(367), b(378, a=.08), b(384, a=.34),
        b(402, a=.40), b(417, a=.47), b(430, a=.43), b(438),
        b(487), b(489, c=.37), b(501, c=.41), b(513, c=.42), b(520),
        b(555), b(560, c=.09), b(568, c=.24),
        b(575, c=.40), b(579, c=.50), b(580, c=.48),
    ]
    timeline["backdrop_cues"] = [
        dict(time=230.0, attack=.055, decay=.75, strength=.27,
             x=.09, y=.38, radius=.24, color="#efbf80"),
        dict(time=230.06, attack=.06, decay=.78, strength=.23,
             x=.92, y=.32, radius=.25, color="#a8d8e5"),
        dict(time=257, attack=.45, decay=2.2, strength=.20,
             x=.16, y=.25, radius=.30, color="#edb76a"),
    ]
    timeline["edge_reveal"] = dict(time=230.0, duration=.28,
                                    plate_index=2)
    timeline["autumn_falls"] = [
        dict(start=254.4, end=338, count=110, opacity=.36),
    ]
    # Opening annotations are already reviewed; full-alignment annotations
    # after 180 s come from the reproducible alignment workflow.
    notes = apply_reviewed_note_corrections(copy.deepcopy(aligned["notes"]))
    for note in notes:
        note.setdefault("event_id", note["score_id"])
        t = note["audio_start"]
        if note["family"] == "piano" and 48 <= t < 73:
            note["accent_emitter_scale"] = max(1.4, note.get("accent_emitter_scale", 1))
        if note["family"] != "piano" and 24 <= t < 40 and note.get("visual_role") == "lead":
            note["accent_filament_attack_count"] = 6
            note["accent_filament_per_second"] = 3.4
            note["accent_color"] = "#eec38e"
        # Two terminal clarinet notes after the rapid downward figure were
        # present in the aligned score but had been classed as support.
        if note["score_id"] in {"p3-m73-P4-4111", "p3-m74-P4-4126"}:
            note["visual_role"] = "lead"
            note["musical_role"] = "orchestra_melody"
        if note["audio_start"] < 180 or note["family"] == "piano":
            continue
        role = note.get("musical_role")
        if role == "orchestra_melody":
            note["visual_role"] = "lead"
            note["accent_emitter_scale"] = .56
            note["accent_filament_attack_count"] = 2
            note["accent_filament_per_second"] = 1.2
            note["accent_light_per_second"] = 1.4
        elif role == "orchestra_chord":
            note["visual_role"] = "lead"
            note["accent_emitter_scale"] = .42
            note["accent_filament_attack_count"] = 1
            note["accent_filament_per_second"] = .7
            note["accent_light_per_second"] = 1.0
        else:
            note["visual_role"] = "support"
    # Recluster by actual rests within each melodic part. A new instrumental
    # phrase gets a different stream profile instead of changing mid-phrase at
    # an arbitrary wall-clock boundary.
    melodic_parts = defaultdict(list)
    for note in notes:
        if (142 <= note["audio_start"] < 202 and
                note["family"] != "piano" and note["visual_role"] == "lead"):
            melodic_parts[note["part_id"]].append(note)
    for part_index, (_, melody) in enumerate(sorted(melodic_parts.items())):
        phrase = -1
        last_end = -1e9
        for note in sorted(melody, key=lambda n: n["audio_start"]):
            if note["audio_start"] > last_end + .65:
                phrase += 1
            last_end = max(last_end, note["audio_end"])
            profile = (phrase + part_index) % 4
            note["accent_emitter_scale"] = [1.6, .55, 1.25, .85][profile]
            note["accent_filament_attack_count"] = [7, 1, 5, 2][profile]
            note["accent_filament_per_second"] = [3.2, .55, 2.1, .9][profile]
            note["accent_light_per_second"] = [2.8, .7, 1.9, 1.2][profile]
            note["accent_particle_life_scale"] = [.62, 1.28, .78, 1.08][profile]
    # Keep the deliberately varied orchestral phrase profiles, while allowing
    # the larger passage to raise or lower their curved light trails slightly.
    passage_starts = sorted(emitter_profiles)
    for note in notes:
        if note["family"] == "piano" or note.get("visual_role") != "lead":
            continue
        start = max(t for t in passage_starts if t <= note["audio_start"])
        trail_scale = 1 + .27 * (emitter_profiles[start]["filament"] - 1)
        for key in ("accent_filament_per_second", "accent_light_per_second"):
            if key in note:
                note[key] = round(note[key] * trail_scale, 4)
    # Use the aligned piano onset of each two-beat score group. In these
    # passages that group consists of eight quick notes; following the actual
    # onsets preserves the recording's rubato and local accelerations.
    def rhythmic_pulses(start, end, plate, initial, final):
        grouped = defaultdict(list)
        for note in notes:
            t = note["audio_start"]
            beat = note.get("score_start_beat")
            if note["family"] == "piano" and beat is not None and start <= t < end:
                grouped[int(beat // 2)].append(note)
        result = []
        for group, members in sorted(grouped.items()):
            first = min(members, key=lambda n: n["audio_start"])
            t = first["audio_start"]
            progress = max(0, min(1, (t - start) / max(.001, end - start)))
            result.append(dict(time=round(t, 4), plate_index=plate,
                               strength=round((initial + (final-initial)*progress)*RHYTHM_FLASH_GAIN, 4),
                               attack=round(.08 * RHYTHM_FLASH_TIME_SCALE, 4),
                               travel=round(.32 * RHYTHM_FLASH_TIME_SCALE, 4),
                               duration=round(.63 * RHYTHM_FLASH_TIME_SCALE, 3),
                               echo_duration=.43, echo_strength=.46,
                               spark_count=26,
                               score_beat=group*2, measure=first["measure"],
                               score_id=first["score_id"]))
        return result
    timeline["backdrop_pulses"] = (
        [dict(time=230, plate_index=2, strength=round(.45 * RHYTHM_FLASH_GAIN, 4),
              attack=.018, travel=.20, duration=.34,
              echo_duration=.43, echo_strength=.46, spark_count=26,
              score_beat=None, measure=None),
         dict(time=239, plate_index=2, strength=round(.34 * RHYTHM_FLASH_GAIN, 4),
              attack=round(.09 * RHYTHM_FLASH_TIME_SCALE, 4),
              travel=round(.39 * RHYTHM_FLASH_TIME_SCALE, 4),
              duration=round(.82 * RHYTHM_FLASH_TIME_SCALE, 3),
              echo_duration=.43, echo_strength=.46, spark_count=26,
              score_beat=None, measure=None)]
        + rhythmic_pulses(384, 417, 0, .20, .40)
        + rhythmic_pulses(487, 513, 2, .23, .35)
        + rhythmic_pulses(555, 579.6, 2, .09, .44)
    )
    # Source-image UV coordinates of actual caustic tips and line endings.
    # Directions follow the photographed/painted strands, so a pulse sheds
    # light at the artwork's features rather than at a generic screen center.
    timeline["backdrop_emitters"] = [
        dict(plate_index=0, name="left cyan prism tip", u=.245, v=.285,
             dx=.82, dy=.45, color="#9bdff1", weight=1.0, count=8),
        dict(plate_index=0, name="left low crossing", u=.086, v=.400,
             dx=.94, dy=-.18, color="#75d7ec", weight=.83, count=7),
        dict(plate_index=0, name="left upper angle", u=.329, v=.190,
             dx=.72, dy=.50, color="#a9dbe9", weight=.65, count=5),
        dict(plate_index=0, name="right gold tip", u=.949, v=.170,
             dx=-.76, dy=.48, color="#f6d5a0", weight=1.0, count=8),
        dict(plate_index=0, name="right blue ribbon end", u=.814, v=.325,
             dx=-.87, dy=.26, color="#b4ddec", weight=.77, count=6),
        dict(plate_index=0, name="right lower glint", u=.941, v=.494,
             dx=-.80, dy=-.30, color="#f0bf81", weight=.70, count=6),
        dict(plate_index=2, name="gold upper burst", u=.145, v=.105,
             dx=.65, dy=.63, color="#ffe2af", weight=1.0, count=8),
        dict(plate_index=2, name="gold left lower facet", u=.164, v=.626,
             dx=.70, dy=-.51, color="#d6dfea", weight=.72, count=6),
        dict(plate_index=2, name="gold right upper edge", u=.959, v=.105,
             dx=-.57, dy=.63, color="#f9d7a0", weight=.94, count=7),
        dict(plate_index=2, name="gold right crossing", u=.878, v=.390,
             dx=-.78, dy=.30, color="#f7d19c", weight=.85, count=7),
        dict(plate_index=2, name="gold right low shard", u=.922, v=.642,
             dx=-.76, dy=-.32, color="#b7d2ec", weight=.74, count=6),
    ]
    timeline["upward_motes"] = [
        dict(start=99, end=126, family="piano", color="#e8c99d", count=7),
        dict(start=156, end=202, family="piano", color="#a9ddf3", count=7),
    ]
    timeline["notes"] = notes
    OUTPUT.write_text(json.dumps(timeline, ensure_ascii=False,
                                 separators=(",", ":")))
    print(f"{OUTPUT}: {len(notes)} notes, {len(timeline['visual_sections'])} styles")


if __name__ == "__main__":
    build()
