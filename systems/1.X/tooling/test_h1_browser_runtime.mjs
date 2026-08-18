import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import path from 'node:path';

const edge = process.argv[2] || 'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe';
const pageUrl = process.argv[3] || 'http://127.0.0.1:8793/';
const port = Number(process.argv[4] || 9225);
const profile = path.resolve('work/emulator/edge-cdp-profile');
const browser = spawn(edge, [
  '--headless=new',
  '--no-first-run',
  '--disable-background-networking',
  '--autoplay-policy=no-user-gesture-required',
  `--remote-debugging-port=${port}`,
  `--user-data-dir=${profile}`,
  pageUrl
], { stdio: 'ignore', windowsHide: true });

const delay = milliseconds => new Promise(resolve => setTimeout(resolve, milliseconds));

async function findPage() {
  let lastError = null;
  for (let attempt = 0; attempt < 80; attempt++) {
    try {
      const response = await fetch(`http://127.0.0.1:${port}/json/list`);
      const targets = await response.json();
      const target = targets.find(item => item.type === 'page' && item.url.startsWith(pageUrl));
      if (target) return target;
    } catch (error) {
      lastError = error;
    }
    await delay(100);
  }
  throw new Error(`Edge page did not expose DevTools: ${lastError || 'target missing'}`);
}

async function connectCdp(url) {
  const socket = new WebSocket(url);
  await new Promise((resolve, reject) => {
    socket.addEventListener('open', resolve, { once: true });
    socket.addEventListener('error', reject, { once: true });
  });
  let nextId = 1;
  const pending = new Map();
  const errors = [];
  socket.addEventListener('message', event => {
    const message = JSON.parse(event.data);
    if (message.id && pending.has(message.id)) {
      const { resolve, reject } = pending.get(message.id);
      pending.delete(message.id);
      if (message.error) reject(new Error(message.error.message));
      else resolve(message.result);
      return;
    }
    if (message.method === 'Runtime.exceptionThrown') {
      errors.push(message.params.exceptionDetails.text);
    } else if (message.method === 'Log.entryAdded' && message.params.entry.level === 'error') {
      errors.push(message.params.entry.text);
    }
  });
  const send = (method, params = {}) => new Promise((resolve, reject) => {
    const id = nextId++;
    pending.set(id, { resolve, reject });
    socket.send(JSON.stringify({ id, method, params }));
  });
  return { socket, send, errors };
}

async function evaluate(send, expression) {
  const result = await send('Runtime.evaluate', {
    expression,
    awaitPromise: true,
    returnByValue: true
  });
  if (result.exceptionDetails) throw new Error(result.exceptionDetails.text);
  return result.result.value;
}

try {
  const target = await findPage();
  const cdp = await connectCdp(target.webSocketDebuggerUrl);
  await cdp.send('Runtime.enable');
  await cdp.send('Log.enable');
  let pageReady = false;
  for (let attempt = 0; attempt < 80; attempt++) {
    pageReady = await evaluate(
      cdp.send,
      'document.readyState === "complete" && typeof ensureAudio === "function"'
    );
    if (pageReady) break;
    await delay(100);
  }
  assert(pageReady, 'browser page script did not become ready');
  await evaluate(cdp.send, '(async()=>{ensureAudio();await audioContext.resume();if(audioInitPromise)await audioInitPromise;return true})()');
  await delay(12000);
  const state = await evaluate(cdp.send, `({
    renderer: canvas.dataset.frameRenderer || null,
    audioMode: canvas.dataset.audioMode || null,
    audioContext: audioContext?.state || null,
    frameMessages: Number(canvas.dataset.frameArrivalCount || 0),
    frameMaxGapMs: Number(canvas.dataset.frameMaxArrivalGapMs || 0),
    audioMessages: Number(canvas.dataset.audioArrivalCount || 0),
    audioMaxGapMs: Number(canvas.dataset.audioMaxArrivalGapMs || 0),
    audioPackets: window.__h1AudioDebug.packets,
    audioFrames: window.__h1AudioDebug.frames,
    audioUnderruns: window.__h1AudioDebug.underruns,
    audioDroppedFrames: Number(canvas.dataset.audioDroppedFrames || 0),
    audioQueuedFrames: Number(canvas.dataset.audioQueuedFrames || 0),
    audioLeadSeconds: Number(canvas.dataset.audioLastLeadSeconds || 0),
    audioRateCorrection: Number(canvas.dataset.audioRateCorrection || 0),
    audioOutputRate: Number(canvas.dataset.audioOutputRate || 0)
  })`);
  assert.equal(state.renderer, 'webgl');
  assert.equal(state.audioMode, 'worklet');
  assert.equal(state.audioContext, 'running');
  assert(state.frameMessages > 0, 'no framebuffer messages reached the page');
  assert(state.audioPackets > 0, 'no PCM packets reached AudioWorklet');
  assert.equal(state.audioUnderruns, 0, 'AudioWorklet underrun detected');
  assert.equal(state.audioDroppedFrames, 0, 'AudioWorklet overflow detected');
  assert.deepEqual(cdp.errors, []);
  process.stdout.write(`${JSON.stringify(state, null, 2)}\n`);
  cdp.socket.close();
} finally {
  if (browser.exitCode === null) browser.kill();
}
