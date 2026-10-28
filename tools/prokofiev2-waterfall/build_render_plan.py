"""Compile one small render timeline from the aligned movement and visual cues.

The musical cue sheet is the only hand-edited parameter file. No WAV copy,
model download or frame cache is created. Run with --scene full later to build
the complete movement timeline from exactly the same settings.
"""

from __future__ import annotations

import argparse
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
PLAN = HERE / "render-plan.json"
PROFILES = HERE / "gpu-vfx-flow" / "profiles"
RENDERER = HERE / "gpu-vfx-flow"
MEASURE = re.compile(r"-m(\d+)-")
COUNT_KEYS = ("ember_attack_count", "streak_attack_count", "filament_attack_count")
EFFECT_DENSITY_KEYS = ("ember_attack_count", "streak_attack_count",
                       "filament_attack_count", "ember_per_second",
                       "streak_per_second", "filament_per_second",
                       "glint_per_second", "light_per_second")


def revision_at_least(plan, minimum):
    """Keep approved cue fixes active when a later render revision is named."""
    value = str((plan or {}).get("local_review_revision", ""))
    return value.startswith("v") and value[1:].isdigit() and int(value[1:]) >= minimum


def digest(path):
    h = sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def compile_look(cue, particle_trail_density_scale=1.0,
                 filament_visibility_scale=1.0, filament_min_per_second=0.0):
    if not .1 <= particle_trail_density_scale <= 3:
        raise ValueError("Particle/trail density scale must be between 0.1 and 3")
    look = deepcopy(json.loads((PROFILES / f"{cue['look']}.json").read_text()))
    last_fire = json.loads((PROFILES / "crimson_real_fire_slow.json").read_text())
    target = last_fire["density"]["ember_per_second"] * cue["density"]
    ratio = target / max(.001, look["density"]["ember_per_second"])
    for key, value in look["density"].items():
        look["density"][key] = (round(value * ratio) if key in COUNT_KEYS
                                  else round(value * ratio, 4))
    for key in EFFECT_DENSITY_KEYS:
        value = look["density"][key] * particle_trail_density_scale
        look["density"][key] = (round(value) if key in COUNT_KEYS
                                  else round(value, 4))
    filament_visibility_scale *= cue.get("filament_scale", 1.0)
    look["density"]["filament_per_second"] = round(max(
        filament_min_per_second,
        look["density"]["filament_per_second"] * filament_visibility_scale), 4)
    if cue["density"] >= .2:
        look["density"]["filament_attack_count"] = max(
            1, round(look["density"]["filament_attack_count"] *
                     filament_visibility_scale))
    for key in ("flight_speed_scale", "launch_speed_scale"):
        look["motion"][key] = round(look["motion"][key] * cue["speed"], 4)
    look["colors"].update(piano_low=cue["piano_low"],
                          piano_high=cue["piano_high"], strike=cue["piano_high"])
    look["appearance"].update(
        keyboard_tint=cue["keyboard"], horizon_tint=cue["horizon"],
        background_tint=cue["piano_low"], background_atmosphere=.23,
        keyboard_crystal_amount=(.15 if cue["look"] == "crystal" else .025),
        keyboard_metal_amount=(.12 if cue["look"] == "metal" else
                               .085 if cue["look"] == "gilded" else .015),
        keyboard_ember_amount=(.13 if cue["look"] == "crimson_real_fire_slow" else 0.),
        orchestra_neutral_color="#a9afb4",
        orchestra_base_alpha=.43 if cue["look"] == "crimson_real_fire_slow" else .44,
        orchestra_lead_color=cue.get("lead_color", "#a9cbd8"),
        orchestra_lead_alpha=cue.get("lead_alpha", .91),
        orchestra_lead_start=0, orchestra_lead_end=0,
        orchestra_emitter_scale=.24 if cue["look"] == "crimson_real_fire_slow" else .13,
        fire_mix=cue.get("fire_mix", 0),
    )
    # Fine controls can be changed per musical cue without editing renderer
    # source or copying a new profile for every section.
    look["brightness"].update(cue.get("brightness_overrides", {}))
    look["appearance"].update(cue.get("appearance_overrides", {}))
    return look


def measure_of(note):
    match = MEASURE.search(note["score_id"])
    return int(match.group(1)) if match else 0


def review_lead_role(note, plan=None):
    """Score-part selections checked against the v9 performed timeline."""
    t, part, pitch = note["audio_start"], note["part_id"], note["midi_pitch"]
    # The scherzo's opposing violin runs are part of the foreground phrase,
    # not grey accompaniment. They lead into the three octave statements.
    if (plan and revision_at_least(plan, 13) and
            (229.58 <= t < 230.04 or 232.88 <= t < 233.42) and
            part in ("P16", "P17")):
        return "lead"
    # Video 1:43–2:01: flute/clarinet octaves, followed by oboe single notes.
    if 98.8 <= t < 105.3 and part in ("P1", "P3"):
        return "lead"
    if 107.8 <= t < 115.2 and part == "P2":
        return "lead"
    # Video 3:55 and 3:58: two doubled high entries.  At 4:02 the
    # octave line moves to flute and clarinet; exclude the short ornaments.
    if (plan and revision_at_least(plan, 13) and
            231.60 <= t < 232.96 and part == "P1"):
        return "lead"
    if (plan and revision_at_least(plan, 13) and
            233.65 <= t < 234.45 and part in ("P1", "P2")):
        return "lead"
    if 230.35 <= t < 235.0 and part in ("P1", "P2") and (
        (part == "P1" and pitch in (82, 83, 87)) or
        (part == "P2" and pitch in (70, 71, 75))):
        return "lead"
    if 236.8 <= t < 240 and part in ("P1", "P3"):
        return "lead"
    if (plan and revision_at_least(plan, 13) and
            240 <= t < 243 and part in ("P1", "P3") and pitch >= 70):
        return "lead"
    # The low brass theme begins in measure 181.  Its five quicker octave
    # attacks in measure 184 must not be lost to a minimum-duration filter.
    if 590.4 <= t < 591.4 and part == "P7" and pitch in (41, 53):
        return "lead"
    if 591.4 <= t < 606.5 and part == "P7" and pitch != 39:
        return "lead"
    if 602.8 <= t < 603.1 and part == "P8" and pitch == 36:
        return "lead"
    if 607.5 <= t < 617.4 and part == "P6":
        return "lead"
    return None


def tutti_color(pitch):
    """Hot red basses rise into bright gold in the final orchestral chords."""
    blend = min(1., max(0., (pitch - 36) / 60))
    low, high = (255, 54, 47), (255, 205, 100)
    rgb = [round(a + (b - a) * blend) for a, b in zip(low, high)]
    return "#" + "".join(f"{channel:02x}" for channel in rgb)


def lead_role(note, plan=None):
    if note["family"] == "piano":
        return None
    if (plan and revision_at_least(plan, 11) and
            619.35 <= note["audio_start"] < 621.05):
        return "lead"
    if plan and plan.get("local_review_revision"):
        role = review_lead_role(note, plan)
        if role:
            return role
    t = note["audio_start"]
    measure = measure_of(note)
    length = note["audio_end"] - t
    part = note["part_id"]
    if 190 <= t < 216 and (
        (part == "P1" and note["midi_pitch"] >= 70) or
        (part == "P3" and note["midi_pitch"] >= 64) or
        (part == "P4" and note["midi_pitch"] >= 55 and t < 200)):
        return "lead"
    if 216.35 <= t < 230 and part == "P1" and note["midi_pitch"] >= 76:
        return "lead"
    if 252 <= t < 256 and part in ("P5", "P6", "P7"):
        return "lead"
    if 3.5 <= t < 10 and part == "P16" and note["midi_pitch"] >= 55:
        return "lead"
    if 136 <= t < 174.8 and part == "P16" and note["midi_pitch"] >= 62:
        return "lead"
    if 174.8 <= t < 198 and (
        (part == "P1" and note["midi_pitch"] >= 70) or
        (part == "P4" and note["midi_pitch"] >= 55 and length >= .25)):
        return "lead"
    if not (plan and plan.get("local_review_revision")) and 590 <= t < 616 and length >= 1.7 and (
        (part == "P7" and 182 <= measure <= 185) or
        (part == "P6" and 186 <= measure <= 187)):
        return "lead"
    return "support"


def accent_for(note, plan=None):
    if note["family"] == "piano":
        return {}
    t, part, pitch = note["audio_start"], note["part_id"], note["midi_pitch"]
    if plan and plan.get("local_review_revision"):
        if (revision_at_least(plan, 11) and
                619.35 <= t < 621.05):
            return {"accent_color": tutti_color(pitch),
                    "accent_fire": True, "accent_tutti": True,
                    "accent_emitter_scale": .62,
                    "accent_filament_attack_count": 8,
                    "accent_filament_per_second": 10.,
                    "accent_smoke_per_second": 10.,
                    "accent_light_per_second": 9.}
        if (revision_at_least(plan, 13) and
                190 <= t < 243 and lead_role(note, plan) == "lead"):
            # Keep this concertante line visibly alive at the keyboard.
            # The strings' fast notes use fewer particles than the held wind
            # octaves, but both receive continuous embers and curved traces.
            fast_strings = part in ("P16", "P17")
            return {"accent_color": "#bc3044" if t < 216 else "#ffd56b",
                    "accent_emitter_scale": .34 if fast_strings else .55,
                    "accent_particle_life_scale": .48 if fast_strings else .62,
                    "accent_filament_attack_count": 2 if fast_strings else 4,
                    "accent_filament_per_second": 2.2 if fast_strings else 3.6,
                    "accent_light_per_second": 2.1 if fast_strings else 3.1}
        if review_lead_role(note, plan) == "lead" and (
            98.8 <= t < 115.2 or 230.35 <= t < 240):
            return {"accent_color": "#ffd56b"}
        if 252 <= t < 256 and part in ("P5", "P6", "P7"):
            if revision_at_least(plan, 11):
                return {"accent_color": "#d91632", "accent_fire": True,
                        "accent_emitter_scale": 1.82,
                        "accent_filament_attack_count": 7,
                        "accent_filament_per_second": 7.2,
                        "accent_smoke_per_second": 9.1,
                        "accent_light_per_second": 6.5}
            return {"accent_color": "#d91632", "accent_fire": True,
                    "accent_emitter_scale": 1.4,
                    "accent_filament_attack_count": 12,
                    "accent_filament_per_second": 12.0}
    if 190 <= t < 216 and (
        (part == "P1" and pitch >= 70) or
        (part == "P3" and pitch >= 64) or
        (part == "P4" and pitch >= 55 and t < 200)):
        return {"accent_color": "#bc3044"}
    if 216.35 <= t < 230 and part == "P1" and pitch >= 76:
        return {"accent_color": "#ffd66b"}
    if 252 <= t < 256 and part in ("P5", "P6", "P7"):
        return {"accent_color": "#b3132c", "accent_fire": True}
    return {}


def piano_review_for(note, plan):
    if note["family"] != "piano" or not plan.get("local_review_revision"):
        return {}
    # Smooth at the ends in note-onset space.  Both hands use one colour and
    # black/white notes approach the same physical width in this short phrase.
    t = note["audio_start"]
    weight = min(1., max(0., (t - 139.5) / 2), max(0., (148.5 - t) / 2))
    if weight <= 0:
        return {}
    return {"piano_unify_strength": round(weight, 4),
            "piano_unify_color": "#dce8eb"}


def sections_for(plan, start, end):
    cues = plan["sections"]
    if any(b["at"] <= a["at"] for a, b in zip(cues, cues[1:])):
        raise ValueError("Musical cues must have strictly increasing times")
    first = max(i for i, cue in enumerate(cues) if cue["at"] <= max(0, start - 5))
    # A preview may begin mid-transition.  Keep its predecessor so the
    # colour/material interpolation matches the full movement exactly.
    first = max(0, first - 1)
    selected = [cue for cue in cues[first:] if cue["at"] <= end + 5]
    result = []
    for i, cue in enumerate(selected):
        next_at = selected[i + 1]["at"] if i + 1 < len(selected) else end + 5.001
        result.append({"name": cue["label"], "start_seconds": cue["at"],
                       "end_seconds": next_at,
                       "transition_seconds": cue["blend"],
                       "preset": compile_look(
                           cue, plan.get("particle_trail_density_scale", 1.0),
                           plan.get("filament_visibility_scale", 1.0),
                           plan.get("filament_min_per_second", 0.0))})
    return result


def build_scene(name, clip, plan, source, audio, output_dir, audio_sha256=None):
    start, duration = clip["start_seconds"], clip["duration_seconds"]
    end = start + duration
    lookahead = plan["lookahead_seconds"]
    particle_lookback = (max(lookahead, 12.0)
                         if "tail_particle_bloom" in plan and
                         end >= plan["tail_particle_bloom"]["start_seconds"]
                         else lookahead)
    sections = sections_for(plan, start, end)
    notes = [{**note, **({"visual_role": lead_role(note, plan),
                         **accent_for(note, plan)}
                        if note["family"] != "piano" else
                        piano_review_for(note, plan))}
             for note in source["notes"]
             if note["audio_end"] >= start - particle_lookback and
                note["audio_start"] <= end + lookahead]
    if revision_at_least(plan, 14):
        for note in notes:
            attack = note["audio_start"]
            if any(lo <= attack < hi for lo, hi in
                   plan.get("filament_silence_intervals", [])):
                note["suppress_filament"] = True
            if "accent_filament_per_second" in note:
                # The scherzo's foreground orchestra is quieter than the
                # general 15% lift; leave its particles and colours intact.
                scale = (.4 if 190 <= attack < 286 and
                         note["family"] != "piano" else 1.15)
                note["accent_filament_per_second"] = round(
                    note["accent_filament_per_second"] * scale, 4)
                note["accent_filament_attack_count"] = max(0, round(
                    note["accent_filament_attack_count"] * scale))
    # Duplicate orchestral unisons over the selected lead add visual noise.
    leads = [note for note in notes if note.get("visual_role") == "lead"]
    notes = [note for note in notes if not (
        note.get("visual_role") == "support" and note["family"] == "brass" and
        any(lead["midi_pitch"] == note["midi_pitch"] and
            abs(lead["audio_start"] - note["audio_start"]) < .055
            for lead in leads))]
    if plan.get("local_review_revision"):
        # The score doubles these selected melodies in strings and winds.
        # Keep the selected part and avoid a grey unison obscuring its face.
        notes = [note for note in notes if not (
            note.get("visual_role") == "support" and
            (98.8 <= note["audio_start"] < 115.2 or
             230.35 <= note["audio_start"] < 240) and
            any(lead["midi_pitch"] == note["midi_pitch"] and
                abs(lead["audio_start"] - note["audio_start"]) < .075
                for lead in leads))]
    if revision_at_least(plan, 13):
        # Separate players may double one physical pitch. Keep their score
        # notes, but release just one particle plume per matched attack.
        emitted = []
        for note in sorted(notes, key=lambda item: item["audio_start"]):
            if not (note.get("visual_role") == "lead" and
                    229.5 <= note["audio_start"] < 243):
                continue
            pitch, attack = note["midi_pitch"], note["audio_start"]
            if any(old_pitch == pitch and abs(old_attack - attack) < .045
                   for old_pitch, old_attack in emitted):
                note["accent_emitter_scale"] = 0
            else:
                emitted.append((pitch, attack))
    if revision_at_least(plan, 11):
        # Many instruments double the same pitch in the tutti.  Keep every
        # note bright, but emit only one plume per physical key and attack.
        emitted = []
        for note in notes:
            if not note.get("accent_tutti"):
                continue
            if any(pitch == note["midi_pitch"] and
                   abs(attack - note["audio_start"]) < .13
                   for pitch, attack in emitted):
                note["accent_emitter_scale"] = 0
            else:
                emitted.append((note["midi_pitch"], note["audio_start"]))
    document = {
        **source, "title": f"Prokofiev 2/I — {name}",
        "sources": {"audio": {"path": str(audio.resolve()),
                              "sha256": audio_sha256 or digest(audio)}},
        "render_interval": {"start_seconds": start, "duration_seconds": duration,
                            "lookahead_seconds": lookahead},
        "fire_entry_seconds": plan["fire_entry_seconds"],
        **({"outro": plan["outro"]} if "outro" in plan else {}),
        **({"eclipse_fade": plan["eclipse_fade"]} if "eclipse_fade" in plan else {}),
        **({"eclipse_lane_cleanup_start_seconds":
            plan["eclipse_lane_cleanup_start_seconds"]}
           if "eclipse_lane_cleanup_start_seconds" in plan else {}),
        **({"tail_particle_bloom": plan["tail_particle_bloom"]}
           if "tail_particle_bloom" in plan else {}),
        "note_palette_cuts": plan.get("note_palette_cuts", []),
        **({"intro": clip["intro"]} if "intro" in clip else {}),
        "visual_sections": sections,
        "notes": notes,
    }
    match = re.search(r"-v(\d+)(?:\.|$)", plan["source_timeline"])
    version = plan.get("local_review_revision") or (f"v{match.group(1)}" if match else "v4")
    path = output_dir / f"prokofiev2-{name}-{version}.timeline.json"
    path.write_text(json.dumps(document, ensure_ascii=False, separators=(",", ":")) + "\n")
    print(json.dumps({"scene": name, "start": start, "duration": duration,
                      "notes": len(notes), "lead_orchestra": len(leads),
                      "sections": [s["name"] for s in sections],
                      "timeline": str(path)}, ensure_ascii=False))
    return path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, default=PLAN)
    parser.add_argument("--audio", type=Path)
    parser.add_argument("--scene", default="all")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "outputs")
    args = parser.parse_args()
    plan = json.loads(args.plan.read_text())
    if plan["schema_version"] != 1:
        raise ValueError("Unknown render plan schema")
    if args.scene not in ("all", "full", *plan["clips"]):
        raise ValueError(f"Unknown scene {args.scene}")
    source = json.loads((ROOT / plan["source_timeline"]).read_text())
    audio = args.audio or ROOT / plan["source_audio"]
    if not audio.is_file():
        raise FileNotFoundError(audio)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    scenes = (plan["clips"] if args.scene == "all" else
              {"full": {"start_seconds": 0,
                         "duration_seconds": source["render_interval"]["duration_seconds"]}}
              if args.scene == "full" else {args.scene: plan["clips"][args.scene]})
    audio_sha256 = digest(audio)
    expected_audio = plan.get("source_audio_sha256")
    if expected_audio and audio_sha256 != expected_audio:
        raise ValueError("Recording SHA-256 differs from this performance-specific render plan")
    for name, clip in scenes.items():
        build_scene(name, clip, plan, source, audio, args.output_dir,
                    audio_sha256=audio_sha256)


if __name__ == "__main__":
    main()
