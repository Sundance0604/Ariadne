---
name: concerto-waterfall
description: Align a concerto MusicXML score with a specific recording and produce or revise a multi-instrument piano-roll waterfall video, including piano separation, orchestral lead roles, note releases, and section-aware visuals.
---

# Concerto waterfall

Use this skill for a requested concerto score/audio alignment, waterfall preview, full render, or local correction. The user's requested scope and approved visual choices control the work. From the project repository root, read `docs/workflows/concerto-waterfall.md` and, for the Prokofiev 3 examples, `tools/prokofiev3-waterfall/README.md` before modifying a pipeline. If the skill is installed outside the repository, locate the checkout first; these guides and the runnable scripts live in the repository.

## Establish source identity and score structure

- Check the exact score edition, recording, movement boundary, source hashes, instrument IDs, transpositions, ties, repeats, duplicate keys and malformed measure lengths. Keep the original files untouched. A new recording or score gets new evidence caches and a fresh role review.
- Derive a broad score/audio clock from chroma and onset features, but treat it as a search prior. Record each final note's pitch, part, onset/release source and confidence.

## Align piano from the performance

- Separate the piano in overlapping bounded crops and use the midpoint of overlaps. Transcribe attacks, measure pitch-specific energy, and delete large scratch WAVs after saving compact evidence. Confirm that source hashes match before reusing cached MIDI or spectral arrays.
- Match normal passages by score pitch and order to the separated-piano attacks. Refine conspicuous bass/chord attacks from the stem's energy rise. Never force unmatched notes onto an XML beat simply to fill gaps.
- When the XML timing or voice order is demonstrably malformed, prefer score-validated performance detections for that passage; log dropped or ambiguous events. Check repeated keys, decay, realistic hand capacity, and audibly different note lengths. Mark constrained key-off estimates rather than claiming they are measured.

## Align and style orchestra deliberately

- Classify foreground melody, foreground harmony/chords, and support from instrument part, register, score texture, dynamics, phrase continuity and pitch-specific recorded evidence. Handle string section handoffs, octave doubling, and unisons explicitly; do not promote an entire loud orchestra to melody color.
- In loud polyphony, a stronger later peak can occur after a pitch has begun. Compare pre/post spectral energy for the score pitch, use concordant entrances of independent parts as anchors, guard against octave harmonics of notes already sounding, and preserve each part's note order. Leave ambiguous masked inner voices for review instead of guessing a global offset.
- Foreground orchestra must light the matching key and receive its own particles/trails. Keep support legible without competing with piano or foreground melody. Preserve the user's approved geometry and keyboard style while changing timing or scene effects.

## Verify and render

- Audit the exposed and difficult passages against audio, including quiet bass, fast strings, role handoffs, releases and chunk boundaries. Report which evidence was checked and which events remain uncertain; automated feature proximity is not listening proof.
- Build an absolute-time visual timeline with stable random seeds. Change colors, materials, density and backgrounds with musical structure. For a local edit, rerender affected windows plus any effect tail, and reuse unchanged frames only after checking the source signature and boundary frames.
- Verify the actual final video decodes, has the requested dimensions/frame rate/duration/audio, and has no abnormal seam jump before saying export is complete. Clean only confirmed disposable outputs. Keep final media local unless the user separately requests publication and repository rules allow it.
