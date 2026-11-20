# Studio editor (part 2): design

Status: approved by Haos on 2026-11-20 ("делай сразу всё", in the desk, no React) and built on feat/studio-recording. Part 1 (recording projects) is in
`2026-11-19-studio-recording-design.md`; this is the "Edit" tab it left disabled.

## 1. Intent

Haos records with `ul capture` / the desk Studio and wants to finish the video in
the same place: cut out mistakes and silences, add subtitles, text, music and a
voice-over, and export for YouTube and vertical formats. Models: OpenCut (the
web editor, `opencut-classic`, MIT) for the data model and the simple flow, and
DaVinci Resolve for the timeline feel (blade, ripple, J/K/L, snapping, a page
with media, viewer, inspector and timeline).

## 2. Goals, non-goals, anti-goals

Goals
- An Edit tab in `ul desk` that opens any recording project and shows its tracks
  on a timeline: video (the composed scenes), mic, Mac sound, plus new tracks.
- Cuts that never touch the recorded files: the edit is a list in `project.json`.
- Subtitles from local speech recognition (`ul lm transcribe`), editable, styled,
  burned into the export and saved as `.srt`.
- Export through the existing ffmpeg pipeline, every canvas (16:9, 9:16, 1:1, 4:5).

Non-goals (now)
- Effects, colour grading, keyframes, masks, speed ramps, transitions other than
  a crossfade, multi-project timelines, plugins.

Anti-goals
- Anything that changes or deletes recorded media.
- A cloud service of any kind (transcription stays on the Mac).
- A framework or a build step in the page (it stays vanilla JS, nodes built with
  textContent only, like the rest of the desk).

## 3. Approaches

A. **Edit tab in the desk page (chosen if Haos agrees).** The page draws the
timeline and plays a preview by syncing the project's own media elements to one
clock (the project page already plays a project this way). The edit is JSON in
`project.json`; Python validates it and the export applies it. Reuses the
server, the project model, the export, `ul lm`.

B. Native editor (Rust GUI, like the OpenCut rewrite). Best performance, but a
second UI toolkit, months of work, and the desk would still need the same model.

C. A separate web app with a framework (like `opencut-classic`: React, wasm
compositor, transformers.js). Fast to copy ideas, but breaks the project rule of
no build step and no dependencies, and would download speech models in the
browser instead of using `ul lm`.

## 4. The edit model (`project.json` → `edit`, version 1)

Borrowed from OpenCut's timeline types: tracks hold elements with
`start` (timeline seconds), `in`/`out` (seconds inside the source), so trimming
is just changing `in`/`out`.

```
edit: {
  version: 1,
  tracks: [
    {id: "v1", kind: "video", name: "Video", clips: [...]},      // the recording, composed by scenes
    {id: "o1", kind: "overlay", name: "Text & images", clips: [...]},
    {id: "s1", kind: "subtitles", name: "Subtitles", clips: [...], style: {...}},
    {id: "a1", kind: "audio", source: "mic", name: "Mic", clips: [...], volume: 1, muted: false},
    {id: "a2", kind: "audio", source: "system", name: "Mac sound", ...},
    {id: "a3", kind: "audio", name: "Music / voice-over", clips: [...]}
  ],
  marks: [...]   // copied from the recording's marks
}
clip: {id, start, in, out, ref}
  ref = {recording: true}          // a stretch of the recording's own timeline (video and its audio)
      | {asset: "assets/x.m4a"}    // imported music, voice-over (recorded with `ul capture record audio`)
      | {text, ...style}           // overlay text (drawn to a PNG like Studio text sources)
      | {caption: "words"}         // a subtitle line
```

A new project gets one clip per track covering the whole recording, so an
untouched edit exports exactly like today. Cutting the recording = several
`{recording: true}` clips on v1 with gaps closed (ripple). The mic and Mac
sound tracks follow v1's cuts unless unlinked (Resolve's "link"), so a cut never
puts sound out of sync.

## 5. The Edit tab

Resolve's layout, desk tokens: media/assets on the left (recording, imported
files, "Record voice-over"), viewer in the middle (the composed canvas, same
stage code as Record), inspector on the right (clip, text, subtitle style),
timeline across the bottom (resizable, like the Record panels).

Timeline behaviour (Resolve keys; letters read by `event.code`):
- Playhead click/drag, ruler, zoom (⌘= / ⌘−, pinch), fit (⇧Z).
- Space play/pause, J/K/L shuttle, ←/→ one frame, ↑/↓ previous/next cut, I/O in/out.
- B or ⌘B blade at the playhead; Delete = ripple delete (closes the gap),
  ⇧Delete leaves a gap; drag a clip edge to trim, ⌥ for roll.
- Snapping to the playhead, clip edges and marks (OpenCut's snap sources), N toggles.
- Waveforms on audio tracks (peaks computed once by ffmpeg, cached in
  `cache/peaks-*.json`, like OpenCut's waveform summary), a thumbnail strip on v1.
- Undo/redo for every edit (the Studio history).
- "Remove silences": cut where the mic stays below a level for N seconds, as a
  suggestion the user can undo.

## 6. Subtitles

- "Transcribe" runs `ul lm transcribe <mic file> --json -l <lang>` per segment
  (the desk calls ul, like everything else); the model is any speech model
  `ul lm` has (Whisper, Parakeet), chosen in a menu, last choice remembered.
- Segments become caption clips on s1, mapped through the cuts (a caption whose
  speech was cut is dropped or shortened).
- Edit text inline in a list next to the timeline; split/merge lines; drag edges.
- Style per canvas (16:9 and vertical differ): font, size, colour, outline or
  box, position (bottom, middle, top), max line width; preview in the viewer.
- Export burns them in as PNG overlays (the ffmpeg here has no libass/drawtext,
  see part 1) and writes `<name>.srt` next to the video.

## 7. Export

`capture_export` gets a planner from the edit: the timeline is cut into pieces
where any clip starts or ends; each piece is one ffmpeg run as today (scene
layout + overlays + current subtitle PNGs), audio tracks mixed with their
volumes and offsets, then the same concat, loudness and publish steps. A project
without `edit` exports exactly as now.

## 8. Phases

1. Edit model, validation, timeline UI with play, blade, ripple delete, trim,
   move, snapping, zoom, undo, waveforms; export applies cuts.
2. Subtitles: transcribe, edit, style, burn-in, `.srt`.
3. Overlay text/images, music and voice-over tracks, volume per clip, fades,
   crossfade between v1 clips, remove silences.

## 9. Calls made while building

- Edit model as built: `clips` and `captions` on the recording clock, `texts` and `audio` on the output
  clock (section 4's `tracks` list became these four lists: simpler to validate, same meaning).
- No crossfade between clips and no unlinked sound yet: the recording's picture and sound always cut together.
- The voice-over comes from an audio-only project recorded on the Record tab (copied into assets/).
- Caption PNGs are drawn at 2x for a 1080-line frame, so 4K exports stay sharp.

## 10. Left to the builder

Peak/thumbnail sizes, exact keyboard map beyond §5, caching details, how the
preview handles a gap (black), the test split (Python model + export, cjs page).
