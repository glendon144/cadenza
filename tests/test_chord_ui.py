"""Exercise the browser response handler without audio/browser dependencies."""
import shutil
import subprocess
from pathlib import Path

import pytest


def test_api_errors_highlight_and_success_updates_chords():
    if not shutil.which("node"):
        pytest.skip("Node is needed for the JavaScript regression test")
    source = Path("static/js/app.js").read_text()
    handler = source.split("async function parseApiResponse(res) {", 1)[1].split("async function apiGet", 1)[0]
    script = """
const assert = require('node:assert/strict');
let highlighted, rendered = 0, status;
const state = {chords: {'0-0': 'Cma7'}, invalidChords: {'0-0': {}}};
function showInvalidChords(items) { highlighted = items; }
function renderGrid() { rendered++; }
function setStatus(message) { status = message; }
async function parseApiResponse(res) {
""" + handler + """
(async () => {
  const invalid = [{measure: 0, beat: 0, message: 'Bad position'}];
  await assert.rejects(parseApiResponse({ok: false, json: async () => ({error: 'Invalid', invalid_chords: invalid})}));
  assert.deepEqual(highlighted, invalid);
  await parseApiResponse({ok: true, json: async () => ({chords: [{measure: 0, beat: 0, symbol: 'Cmaj7'}]})});
  assert.equal(state.chords['0-0'], 'Cmaj7');
  assert.deepEqual(state.invalidChords, {});
  assert.equal(rendered, 1);
  assert.match(status, /Cma7 → Cmaj7/);
})().catch(error => { console.error(error); process.exit(1); });
"""
    subprocess.run(["node", "-e", script], check=True, capture_output=True, text=True)
