/**
 * ChordCraft — Front-end controller
 * Manages the chord grid, transport, and notation display.
 */

const state = {
  songId:      null,
  measures:    8,          // default grid size
  chords:      {},         // key: "m-b" (measure-beat), value: symbol string
  audioEl:     null,
  isPlaying:   false,
  mp3Url:      null,
  midiUrl:     null,
  pdfUrl:      null,
  invalidChords: {},
};

// ── DOM refs ────────────────────────────────────────────────────────────────
const grid            = document.getElementById("chord-grid");
const statusEl        = document.getElementById("playback-status");
const notationContainer = document.getElementById("notation-container");

const btnPlay    = document.getElementById("btn-play");
const btnStop    = document.getElementById("btn-stop");
const btnRewind  = document.getElementById("btn-rewind");
const btnForward = document.getElementById("btn-forward");

const btnNew    = document.getElementById("btn-new");
const btnSave   = document.getElementById("btn-save");
const btnAddM   = document.getElementById("btn-add-measure");
const btnRemM   = document.getElementById("btn-remove-measure");
const btnUpdateM = document.getElementById("btn-update-measures");
const btnRegenerate = document.getElementById("btn-regenerate");
const btnMixer = document.getElementById("btn-mixer");
const mixerPanel = document.getElementById("mixer-panel");
const mixerClose = document.getElementById("mixer-close");
const mixerStrips = document.getElementById("mixer-strips");

const btnExportMidi = document.getElementById("btn-export-midi");
const btnExportMp3  = document.getElementById("btn-export-mp3");
const btnExportPdf  = document.getElementById("btn-export-pdf");
const btnExportProject = document.getElementById("btn-export-project");
const btnExportAll = document.getElementById("btn-export-all");
const btnImportProject = document.getElementById("btn-import-project");
const importFile = document.getElementById("import-file");

function currentSongId() {
  return state.currentSongId || state.songId || state.id || null;
}

function csrfHeaders(extra = {}) {
  const match = document.cookie.match(/(?:^|; )csrf_token=([^;]+)/);
  const token = match ? decodeURIComponent(match[1]) : "";
  return {
    ...extra,
    "X-CSRF-Token": token,
  };
}

const songTitle  = document.getElementById("song-title");
const songTempo  = document.getElementById("song-tempo");
const songStyle  = document.getElementById("song-style");
const songKey    = document.getElementById("song-key");
const songGroove = document.getElementById("song-groove");
const scaleFocus = document.getElementById("scale-focus");
const rmsPhrasing = document.getElementById("rms-phrasing");
const chorusCount = document.getElementById("chorus-count");
const chorusCountLabel = document.getElementById("chorus-count-label");
const melodicTemperature = document.getElementById("melodic-temperature");
const melodicTemperatureLabel = document.getElementById("melodic-temperature-label");
const scoreView = document.getElementById("score-view");
const writtenFor = document.getElementById("written-for");
const measureCount = document.getElementById("measure-count");

const mixerDefaults = { solo: 1, bass: 1, rhythm: 1, drums: 1 };
state.settings = { groove: "auto", scale_focus: false, rms_phrasing: false,
  choruses: 1, melodic_temperature: 35, view: "full", transposition: "concert",
  mixer: { ...mixerDefaults } };


// ── Grid rendering ──────────────────────────────────────────────────────────

function renderGrid() {
  grid.innerHTML = "";
  for (let m = 0; m < state.measures; m++) {
    const cell = document.createElement("div");
    cell.className = "chord-cell double-chord-cell";
    cell.dataset.measure = m;

    const numLabel = document.createElement("span");
    numLabel.className = "measure-num";
    numLabel.textContent = m + 1;
    cell.appendChild(numLabel);

    // Two chord slots per measure: beat 0 and beat 2
    for (const beat of [0, 2]) {
      const input = document.createElement("input");
      input.type        = "text";
      input.placeholder = "—";
      input.value       = state.chords[`${m}-${beat}`] || "";
      input.dataset.measure = m;
      input.dataset.beat    = beat;

      const invalid = state.invalidChords[`${m}-${beat}`];
      if (invalid) {
        cell.classList.add("invalid");
        input.classList.add("invalid");
        input.setAttribute("aria-invalid", "true");
        input.title = invalid.message;
      }

      input.addEventListener("input", e => {
        const key = `${m}-${beat}`;
        state.chords[key] = e.target.value.trim();
        if (state.invalidChords[key]) {
          delete state.invalidChords[key];
          cell.classList.remove("invalid");
          input.classList.remove("invalid");
          input.removeAttribute("aria-invalid");
          input.removeAttribute("title");
        }
      });
      input.addEventListener("keydown", e => {
        if (e.key === "Enter") {
          const nextBeat = beat === 0 ? 2 : 0;
          const nextMeasure = beat === 0 ? m : m + 1;
          const next = grid.querySelector(
            `input[data-measure="${nextMeasure}"][data-beat="${nextBeat}"]`
          );
          if (next) next.focus();
        }
      });

      cell.appendChild(input);
    }
    grid.appendChild(cell);
  }
}


// ── Chord serialisation ─────────────────────────────────────────────────────

function buildChordPayload() {
  const cells = [];
  for (let m = 0; m < state.measures; m++) {
    const a = state.chords[`${m}-0`];
    const b = state.chords[`${m}-2`];
    if (a && b) {
      cells.push({ measure: m, beat: 0, symbol: a, duration: 2.0 });
      cells.push({ measure: m, beat: 2, symbol: b, duration: 2.0 });
    } else if (a) {
      cells.push({ measure: m, beat: 0, symbol: a, duration: 4.0 });
    } else if (b) {
      cells.push({ measure: m, beat: 2, symbol: b, duration: 2.0 });
    }
  }
  return cells;
}

function showInvalidChords(invalidChords) {
  state.invalidChords = {};
  for (const item of invalidChords || []) {
    const measure = Number(item.measure);
    const beat = Number(item.beat || 0);
    state.invalidChords[`${measure}-${beat}`] = item;
  }

  renderGrid();

  const first = invalidChords && invalidChords[0];
  if (first) {
    const input = grid.querySelector(
      `input[data-measure="${first.measure}"][data-beat="${first.beat || 0}"]`
    );
    if (input) {
      input.focus();
      input.select();
    }

    const measureLabel = Number(first.measure) + 1;
    setStatus(`Fix measure ${measureLabel}: ${first.message}`);
  }
}


// ── API helpers ─────────────────────────────────────────────────────────────

async function apiPost(url, body) {
  const res = await fetch(url, {
    method:  "POST",
    headers: csrfHeaders({ "Content-Type": "application/json" }),
    body:    JSON.stringify(body),
  });
  return parseApiResponse(res);
}

async function apiPut(url, body) {
  const res = await fetch(url, {
    method:  "PUT",
    headers: csrfHeaders({ "Content-Type": "application/json" }),
    body:    JSON.stringify(body),
  });
  return parseApiResponse(res);
}

async function parseApiResponse(res) {
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || `Request failed (${res.status})`);
  return data;
}

async function apiGet(url) {
  const res = await fetch(url);
  return res.json();
}


// ── Song management ─────────────────────────────────────────────────────────

async function createNewSong({ resetGrid = true } = {}) {
  const data = await apiPost("/api/songs", {
    title:   songTitle.value || "Untitled",
    tempo:   parseInt(songTempo.value, 10) || 120,
    style:   songStyle.value,
    key_sig: songKey.value,
    groove: songGroove.value,
  });
  state.songId = data.id;
  if (resetGrid) {
    state.chords = {};
    state.invalidChords = {};
    state.measures = 8;
    renderGrid();
  }
  setStatus(`New song created (id ${state.songId})`);
}

async function saveSong() {
  if (!state.songId) {
    await createNewSong({ resetGrid: false });
  }
  const payload = {
    title:   songTitle.value,
    tempo:   parseInt(songTempo.value, 10) || 120,
    style:   songStyle.value,
    key_sig: songKey.value,
    groove: songGroove.value,
    scale_focus: scaleFocus.checked,
    rms_phrasing: rmsPhrasing.checked,
    choruses: Number(chorusCount.value),
    melodic_temperature: Number(melodicTemperature.value),
    measures: state.measures,
    mixer: state.settings.mixer,
    chords:  buildChordPayload(),
  };
  try {
    await apiPut(`/api/songs/${state.songId}`, payload);
    const item = document.querySelector(`.song-item[data-id="${state.songId}"]`);
    if (item) item.querySelector(".song-title").textContent = payload.title || "Untitled";
    setStatus("Saved ✓");
  } catch (err) {
    setStatus(`Save failed: ${err.message}`);
    throw err;
  }
}

function currentProjectPayload() {
  return {
    title: songTitle.value,
    tempo: parseInt(songTempo.value, 10) || 120,
    style: songStyle.value,
    key_sig: songKey.value,
    groove: songGroove.value,
    scale_focus: scaleFocus.checked,
    rms_phrasing: rmsPhrasing.checked,
    choruses: Number(chorusCount.value),
    melodic_temperature: Number(melodicTemperature.value),
    measures: state.measures,
    mixer: state.settings.mixer,
    chords: buildChordPayload(),
    view: scoreView.value,
    transposition: writtenFor.value,
  };
}

async function createSongFromProject(project) {
  const song = project && project.song ? project.song : project;
  const chords = project && Array.isArray(project.chords) ? project.chords : [];
  if (!song || typeof song !== "object") throw new Error("Imported file has no song data.");

  songTitle.value = song.title || "Untitled";
  songTempo.value = song.tempo || 120;
  songStyle.value = song.style || "jazz";
  songKey.value = song.key_sig || "C";
  songGroove.value = song.groove || "auto";
  scaleFocus.checked = Boolean(song.scale_focus);
  rmsPhrasing.checked = Boolean(song.rms_phrasing);
  chorusCount.value = song.choruses || 1;
  chorusCountLabel.textContent = chorusCount.value;
  melodicTemperature.value = song.melodic_temperature ?? 35;
  melodicTemperatureLabel.textContent = melodicTemperature.value;
  state.measures = Number(song.measures) || 12;
  state.chords = {};
  state.invalidChords = {};
  state.settings.mixer = { ...mixerDefaults };
  for (const chord of chords) {
    state.chords[`${chord.measure}-${chord.beat}`] = chord.symbol;
  }
  renderGrid();

  const created = await apiPost("/api/songs", {
    title: songTitle.value,
    tempo: songTempo.value,
    style: songStyle.value,
    key_sig: songKey.value,
    groove: songGroove.value,
  });
  state.songId = created.id;
  await apiPut(`/api/songs/${state.songId}`, currentProjectPayload());
  setStatus(`Imported: ${songTitle.value}`);
}

async function loadSong(songId) {
  const data = await apiGet(`/api/songs/${songId}`);
  state.songId   = data.id;
  state.chords   = {};
  songTitle.value = data.title;
  songTempo.value = data.tempo;
  songStyle.value = data.style;
  songKey.value   = data.key_sig;
  songGroove.value = data.groove || "auto";
  scaleFocus.checked = Boolean(data.scale_focus);
  rmsPhrasing.checked = Boolean(data.rms_phrasing);
  chorusCount.value = data.choruses || 1;
  chorusCountLabel.textContent = chorusCount.value;
  melodicTemperature.value = data.melodic_temperature ?? 35;
  melodicTemperatureLabel.textContent = melodicTemperature.value;
  measureCount.value = data.measures || 12;
  state.settings.mixer = data.mixer || { ...mixerDefaults };

  // Determine grid size from chords
  const measures = data.chords.map(c => c.measure);
  state.measures = measures.length ? Math.max(...measures) + 1 : 8;

  for (const c of data.chords) {
    state.chords[`${c.measure}-${c.beat}`] = c.symbol;
  }
  renderGrid();
  setStatus(`Loaded: ${data.title}`);
}


// ── Render & playback ────────────────────────────────────────────────────────

async function renderAndPlay() {
  if (!state.songId) await createNewSong({ resetGrid: false });

  setStatus("Rendering… (this may take a few seconds)");
  btnPlay.disabled = true;

  const payload = {
    title: songTitle.value,
    tempo: parseInt(songTempo.value, 10) || 120,
    style: songStyle.value,
    key_sig: songKey.value,
    chords: buildChordPayload(),
    groove: songGroove.value,
    scale_focus: scaleFocus.checked,
    rms_phrasing: rmsPhrasing.checked,
    choruses: Number(chorusCount.value),
    melodic_temperature: Number(melodicTemperature.value),
    measures: state.measures,
    view: scoreView.value,
    transposition: writtenFor.value,
    mixer: state.settings.mixer,
  };

  try {
    const result = await apiPost(`/api/songs/${state.songId}/render`, payload);

    if (result.error) {
      if (result.invalid_chords) {
        showInvalidChords(result.invalid_chords);
      } else {
        setStatus(`Error: ${result.error}`);
      }
      btnPlay.disabled = false;
      return;
    }

    state.mp3Url  = result.mp3_url  + "?t=" + Date.now();
    state.midiUrl = result.midi_url + "?t=" + Date.now();
    state.pdfUrl  = result.pdf_url  + "?t=" + Date.now();

    // LilyPond can produce one SVG per page.  `svg_url` is retained by the
    // API for backwards compatibility, but using it here would silently
    // truncate every multi-page score to page one.
    const scorePages = Array.isArray(result.svg_urls) && result.svg_urls.length
      ? result.svg_urls
      : result.svg_url;
    displaySVG(scorePages);

    // Play audio
    playAudio(state.mp3Url);

  } catch (err) {
    setStatus(`Network error: ${err.message}`);
  } finally {
    btnPlay.disabled = false;
  }
}

function playAudio(url) {
  if (state.audioEl) {
    state.audioEl.pause();
  }
  state.audioEl     = new Audio(url);
  state.isPlaying   = true;
  btnPlay.textContent = "⏸";

  state.audioEl.play().catch(e => setStatus(`Playback error: ${e.message}`));

  state.audioEl.addEventListener("ended", () => {
    state.isPlaying = false;
    btnPlay.textContent = "▶";
    setStatus("Playback finished");
  });

  state.audioEl.addEventListener("timeupdate", () => {
    if (state.audioEl.duration) {
      const pct = (state.audioEl.currentTime / state.audioEl.duration * 100).toFixed(1);
      setStatus(`▶ ${formatTime(state.audioEl.currentTime)} / ${formatTime(state.audioEl.duration)}`);
    }
  });
}

function formatTime(secs) {
  const m = Math.floor(secs / 60).toString().padStart(2, "0");
  const s = Math.floor(secs % 60).toString().padStart(2, "0");
  return `${m}:${s}`;
}

function displaySVG(urls) {
  const pages = Array.isArray(urls) ? urls : [urls];
  const cacheBust = Date.now();

  notationContainer.innerHTML = pages
    .filter(Boolean)
    .map((url, index) => {
      const separator = url.includes("?") ? "&" : "?";
      return `<img class="score-page" src="${url}${separator}t=${cacheBust}" alt="Score notation, page ${index + 1}">`;
    })
    .join("");
}


// ── Transport controls ───────────────────────────────────────────────────────

btnPlay.addEventListener("click", () => {
  if (!state.audioEl || state.audioEl.ended || state.audioEl.src === "") {
    renderAndPlay();
    return;
  }
  if (state.isPlaying) {
    state.audioEl.pause();
    state.isPlaying = false;
    btnPlay.textContent = "▶";
    setStatus("Paused");
  } else {
    state.audioEl.play();
    state.isPlaying = true;
    btnPlay.textContent = "⏸";
  }
});

btnStop.addEventListener("click", () => {
  if (state.audioEl) {
    state.audioEl.pause();
    state.audioEl.currentTime = 0;
    state.isPlaying = false;
    btnPlay.textContent = "▶";
    setStatus("Stopped");
  }
});

btnRewind.addEventListener("click", () => {
  if (state.audioEl) {
    state.audioEl.currentTime = Math.max(0, state.audioEl.currentTime - 10);
  }
});

btnForward.addEventListener("click", () => {
  if (state.audioEl) {
    state.audioEl.currentTime = Math.min(
      state.audioEl.duration || 0,
      state.audioEl.currentTime + 10
    );
  }
});


// ── Grid size controls ───────────────────────────────────────────────────────

btnAddM.addEventListener("click", () => {
  state.measures = Math.min(state.measures + 1, 64);
  renderGrid();
});

btnRemM.addEventListener("click", () => {
  if (state.measures > 1) {
    state.measures--;
    delete state.chords[`${state.measures}-0`];
    delete state.chords[`${state.measures}-2`];
    renderGrid();
  }
});

btnUpdateM.addEventListener("click", () => {
  const requested = Math.max(1, Math.min(64, Number(measureCount.value) || state.measures));
  if (requested < state.measures) {
    for (const key of Object.keys(state.chords)) {
      if (Number(key.split("-")[0]) >= requested) delete state.chords[key];
    }
  }
  state.measures = requested;
  measureCount.value = requested;
  renderGrid();
});

function bindRange(input, label, setting, clamp) {
  input.addEventListener("input", () => {
    const value = clamp(Number(input.value));
    input.value = value;
    label.textContent = value;
    state.settings[setting] = value;
  });
}

bindRange(chorusCount, chorusCountLabel, "choruses", value => Math.max(1, Math.min(20, value || 1)));
bindRange(melodicTemperature, melodicTemperatureLabel, "melodic_temperature", value => Math.max(0, Math.min(100, value || 0)));

scaleFocus.addEventListener("change", () => { state.settings.scale_focus = scaleFocus.checked; });
rmsPhrasing.addEventListener("change", () => { state.settings.rms_phrasing = rmsPhrasing.checked; });
songGroove.addEventListener("change", () => { state.settings.groove = songGroove.value; });

btnRegenerate.addEventListener("click", renderAndPlay);
scoreView.addEventListener("change", () => { if (state.songId && state.audioEl) renderAndPlay(); });
writtenFor.addEventListener("change", () => { if (state.songId && state.audioEl) renderAndPlay(); });

function renderMixer() {
  const names = { solo: "Solo", bass: "Bass", rhythm: "Rhythm", drums: "Drums" };
  mixerStrips.innerHTML = "";
  for (const [part, name] of Object.entries(names)) {
    const row = document.createElement("label");
    row.className = "mixer-strip";
    row.innerHTML = `<span>${name}</span><input type="range" min="0" max="1" step="0.01" value="${state.settings.mixer[part] ?? 1}" aria-label="${name} level">`;
    row.querySelector("input").addEventListener("input", event => {
      state.settings.mixer[part] = Number(event.target.value);
      scheduleMixerSave();
    });
    mixerStrips.appendChild(row);
  }
}

let mixerSaveTimer = null;
function scheduleMixerSave() {
  if (!state.songId) return;
  clearTimeout(mixerSaveTimer);
  mixerSaveTimer = setTimeout(async () => {
    try {
      await apiPut(`/api/songs/${state.songId}`, { mixer: state.settings.mixer });
    } catch (err) {
      setStatus(`Mixer save failed: ${err.message}`);
    }
  }, 500);
}

btnMixer.addEventListener("click", () => { renderMixer(); mixerPanel.classList.toggle("hidden"); });
mixerClose.addEventListener("click", () => mixerPanel.classList.add("hidden"));


// ── Song management controls ─────────────────────────────────────────────────

btnNew.addEventListener("click",  createNewSong);
btnSave.addEventListener("click", saveSong);


// ── Export controls ──────────────────────────────────────────────────────────

btnExportMidi.addEventListener("click", () => {
  if (state.midiUrl) downloadFile(state.midiUrl, "chordcraft.mid");
  else alert("Render the song first (press Play).");
});

btnExportMp3.addEventListener("click", () => {
  if (state.mp3Url)  downloadFile(state.mp3Url,  "chordcraft.mp3");
  else alert("Render the song first (press Play).");
});

btnExportPdf.addEventListener("click", () => {
  if (state.pdfUrl)  downloadFile(state.pdfUrl,  "chordcraft.pdf");
  else alert("Render the song first (press Play).");
});

function downloadFile(url, filename) {
  const a    = document.createElement("a");
  a.href     = url;
  a.download = filename;
  a.click();
}


// ── Song library ─────────────────────────────────────────────────────────────

document.querySelectorAll(".btn-load").forEach(btn => {
  btn.addEventListener("click", () => loadSong(parseInt(btn.dataset.id, 10)));
});

document.querySelectorAll(".btn-delete").forEach(btn => {
  btn.addEventListener("click", async () => {
    if (!confirm("Delete this song?")) return;
    try {
      await parseApiResponse(await fetch(`/api/songs/${btn.dataset.id}`, { method: "DELETE", headers: csrfHeaders() }));
      btn.closest(".song-item").remove();
    } catch (err) { setStatus(`Delete failed: ${err.message}`); }
  });
});


// ── Utilities ────────────────────────────────────────────────────────────────

function setStatus(msg) {
  statusEl.textContent = msg;
}


// ── Init ──────────────────────────────────────────────────────────────────────

renderGrid();
setStatus("Ready — enter chords and press Play");

// ── Project import/export buttons ───────────────────────────────────────────

function downloadBlob(blob, filename) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename || "chordcraft-project.json";
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

function filenameFromDisposition(header, fallback) {
  if (!header) return fallback;
  const match = header.match(/filename="?([^"]+)"?/i);
  return match ? match[1] : fallback;
}

if (btnExportProject) {
  btnExportProject.addEventListener("click", async () => {
    try {
      await saveSong();
      const res = await fetch("/api/project/export", {
        method: "POST",
        headers: csrfHeaders({ "Content-Type": "application/json" }),
        body: JSON.stringify(currentProjectPayload()),
      });
      if (!res.ok) throw new Error((await res.json().catch(() => ({}))).error || "Could not export project.");
      downloadBlob(await res.blob(), filenameFromDisposition(res.headers.get("Content-Disposition"), "chordcraft-project.chordcraft.json"));
    } catch (err) { setStatus(`Export failed: ${err.message}`); }
  });
}

if (btnExportAll) {
  btnExportAll.addEventListener("click", async () => {
    try {
      await saveSong();
      const res = await fetch("/api/project/export-all", {
        method: "POST",
        headers: csrfHeaders({ "Content-Type": "application/json" }),
        body: JSON.stringify(currentProjectPayload()),
      });
      if (!res.ok) throw new Error((await res.json().catch(() => ({}))).error || "Could not export all formats.");
      downloadBlob(await res.blob(), filenameFromDisposition(res.headers.get("Content-Disposition"), "chordcraft-all-formats.zip"));
    } catch (err) { setStatus(`Export failed: ${err.message}`); }
  });
}

if (btnImportProject && importFile) {
  btnImportProject.addEventListener("click", () => {
    importFile.value = "";
    importFile.click();
  });

  importFile.addEventListener("change", async () => {
    const file = importFile.files && importFile.files[0];
    if (!file) return;

    const isMidi = /\.(mid|midi)$/i.test(file.name);
    const endpoint = isMidi ? "/api/project/import-midi" : "/api/project/import";

    const form = new FormData();
    form.append("file", file);
    form.append("style", songStyle ? songStyle.value : "jazz");
    form.append("key_sig", songKey ? songKey.value : "C");

    const res = await fetch(endpoint, {
      method: "POST",
      headers: csrfHeaders(),
      body: form,
    });

    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      alert(err.error || "Could not import project.");
      return;
    }

    const data = await res.json();
    try {
      await createSongFromProject(data);
    } catch (err) {
      setStatus(`Import failed: ${err.message}`);
    }
  });
}
