# ChordCraft upgraded v19

ChordCraft is a small Flask-based jazz chart generator.  It creates chord-grid based arrangements with MIDI/audio playback, LilyPond notation, PDF/SVG export, JSON project export/import, multiple styles, clave options, part views, generated solos, bass lines, comping, and drum-set parts.

## New in v19

- The saved bar count is now honored when rendering. A form with trailing
  rest bars keeps its full length, so later choruses start on the right bar.
- Suspended dominants such as `G7sus4`, `C9sus`, `Bb13sus4`, and `D7sus2`
  are accepted: the fourth (or second) replaces the third while the seventh
  and tensions stay.
- 6/9 chords are accepted: `C6/9`, `C69`, `Cm6/9`, including a slash bass
  after the color, as in `F6/9/A`.

## New in v18

- **Transposing instruments.**  A "Written for" dropdown next to the score
  view renders the notation as the player reads it: B♭ (trumpet, clarinet,
  soprano sax), B♭ tenor sax, E♭ alto sax, E♭ bari sax, or F horn.  When a
  student hears a concert C on an E♭ alto part, the staff shows an A — no
  transposing skill required.
- The written key signature and every chord symbol transpose with the
  notes (concert Dm7 appears as Bm7 on an alto part), and the part is
  labeled ("Solo Part — Written for E♭ — Alto Sax").  Tenor and bari use
  the conventional octave displacement so parts sit in staff range.
- Playback, MIDI, and MP3 always stay at concert pitch; only the displayed
  and exported notation (SVG/PDF, including Save All Formats) transposes.

## New in v17

- **Live mixing.**  Mixer moves (volume, ACT, SOLO, MUTE) now take effect
  immediately during playback — no re-render.  Each render produces
  per-part audio stems alongside the mixed MP3, and the browser plays the
  stems through Web Audio gain nodes, so the console works like a real
  mixing desk.
- Exported files (MIDI, MP3, Save All Formats) still have the mixer baked
  in server-side; they pick up console changes on the next render pass.
- Mixer changes made during playback are auto-saved with the song
  (debounced), so the mix you hear is the mix that's stored.
- If stem playback isn't available (older render, Web Audio failure), the
  transport falls back to the mixed MP3 and mixer changes queue a
  re-render as before.

## New in v16

- Added a **Mixer** panel, opened from the transport bar.  It floats above the
  page (drag it by its title bar) and stays open until closed, without
  blocking the staves.  Each part — Piano, Bass, Solo, Drums — has a channel
  strip with:
  - a volume fader (0-100, applied as MIDI channel volume),
  - **ACT**: channel on/off; an inactive part is left out of exported MIDI and audio entirely,
  - **SOLO**: silences every non-soloed part (multiple solos allowed),
  - **MUTE**: silences the part but keeps its notes in the exported MIDI.
- Mixer levels apply on the next render and to every exported file (MIDI,
  MP3, and the Save All Formats bundle).  Muting all parts renders a
  full-length silent file.
- Mixer settings are saved with the song and restored when it is loaded;
  New Song and Import reset the console to defaults.
- The dev server port can be overridden with the `PORT` environment variable.

## New in v15

- Added **Save All Formats**. This produces one zip bundle containing:
  - `.chordcraft.json` editable project file
  - `.mid` MIDI file
  - `.mp3` audio render
  - `.pdf` chart
  - `.svg` notation pages
- Added **RMS phrasing** checkbox.
  - This is adapted from Glen's ECM/RMS speech-timing idea.
  - It applies only to solo playback timing, not printed notation.
  - Phrases begin slightly relaxed, then catch up so phrase endpoints remain on time.
  - Bass, drums, and rhythm parts remain on the grid.
- Project JSON format is now version 3 and preserves `rms_phrasing`.

## Recent features retained

- Full drum-set track with style-aware Jazz, Bossa Nova, Samba, and Pop patterns.
- DrumStaff notation and Drums Only view.
- Full Score, Solo Only, Bass Only, Rhythm Only, and Drums Only views.
- Melodic temperature slider for motive development and enclosures.
- Scale focus option inspired by chord-scale teaching.
- Choruses slider up to 20.
- Two chord slots per bar: beat 1 and beat 3.
- 12-bar default form with manual bar-count update.
- Bossa/Samba clave options including Son and Rhumba 2-3 / 3-2.
- Key-aware transposition and major-key diatonic starter progressions.
- Export filenames based on `Title-style-clave_type` when applicable.

## Notes

The app uses external tools for rendering audio and notation. Install LilyPond, FluidSynth, ffmpeg, and a compatible soundfont for full rendering.

Run tests with:

```bash
pytest -q
```

The current pure-Python regression suite reports `32 passed, 6 skipped` in this container. The skipped tests require optional external packages/tools not present here.
