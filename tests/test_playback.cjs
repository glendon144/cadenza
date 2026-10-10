const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

function harness() {
  const state = { audioEl: null, stemAudio: {}, audioContext: null };
  const dialog = { open: false, showModal() { this.open = true; }, close() { this.open = false; } };
  let click;
  const context = vm.createContext({
    state, window: {}, btnPlay: {}, setStatus(text) { context.status = text; },
    document: { getElementById(id) { return id === 'audio-permission-dialog' ? dialog : { addEventListener(_, fn) { click = fn; } }; } },
    setTimeout(fn) { context.timeout = fn; return 1; }, clearTimeout() {},
  });
  const source = fs.readFileSync('static/js/app.js', 'utf8');
  vm.runInContext(source.slice(source.indexOf('function unlockAudio()'), source.indexOf('function playAudio(url)')), context);
  return { context, state, dialog, click: () => click() };
}

test('starts all stems immediately, without waiting for context resume', async () => {
  const { context, state } = harness();
  let resume;
  let plays = 0;
  state.audioContext = { resume: () => new Promise(resolve => { resume = resolve; }) };
  state.stemAudio = { solo: { play() { plays++; return Promise.resolve(); } } };
  const pending = context.startPlayback();
  assert.equal(plays, 1);
  assert.equal(state.isPlaying, false);
  resume();
  await pending;
  assert.equal(state.isPlaying, true);
  assert.equal(context.status, 'Playing');
});

test('autoplay rejection pauses every stem and offers a working retry', async () => {
  const { context, state, dialog, click } = harness();
  let blocked = true;
  let pauses = 0;
  state.audioContext = { resume: () => Promise.resolve() };
  state.stemAudio = { solo: {
    play: () => blocked ? Promise.reject(Object.assign(new Error('blocked'), { name: 'NotAllowedError' })) : Promise.resolve(),
    pause() { pauses++; },
  } };
  await context.startPlayback();
  assert.equal(dialog.open, true);
  assert.equal(state.isPlaying, false);
  assert.equal(pauses, 1);
  blocked = false;
  click();
  await new Promise(setImmediate);
  assert.equal(dialog.open, false);
  assert.equal(state.isPlaying, true);
});

test('a suspended context cannot leave the app stuck rendering', async () => {
  const { context, state, dialog } = harness();
  state.audioContext = { state: 'suspended', resume: () => new Promise(() => {}) };
  state.stemAudio = { bass: { play: () => Promise.resolve(), pause() {} } };
  const pending = context.startPlayback();
  context.timeout();
  await pending;
  assert.equal(dialog.open, true);
  assert.equal(state.isPlaying, false);
  assert.match(context.status, /Audio ready/);
});

test('mixed MP3 failures restore the play button without a permission prompt', async () => {
  const { context, state, dialog } = harness();
  state.audioEl = { play: () => Promise.reject(new Error('Unsupported audio')), pause() {} };
  await context.startPlayback();
  assert.equal(state.isPlaying, false);
  assert.equal(context.btnPlay.textContent, '▶');
  assert.equal(dialog.open, false);
  assert.match(context.status, /Unsupported audio/);
});
