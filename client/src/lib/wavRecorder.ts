// Zia ASR validates the uploaded file by extension and rejects .webm with
// 400 INVALID_FILE_EXTENSION (verified live: identical bytes return 200 as
// .wav/.mp3/.ogg/.flac and 400 as .webm/.m4a). MediaRecorder cannot emit any
// of the accepted formats in Chrome -- it produces webm/opus -- so capture
// raw PCM through the Web Audio API and encode a WAV ourselves.
//
// Uses ScriptProcessorNode rather than AudioWorklet: it is deprecated but
// needs no separate worklet module (which would complicate the Vite build)
// and is supported everywhere this runs.

export interface WavRecorder {
  pause(): void;
  resume(): void;
  isPaused(): boolean;
  /** Returns the Web Audio AnalyserNode for visualizing audio data, if available. */
  getAnalyser(): AnalyserNode | null;
  /** Stops capture, releases the mic, and returns an audio/wav Blob. */
  stop(): Promise<Blob>;
}

// Zia returns 16 kHz audio and speech models expect roughly this; it also
// keeps the upload well under the backend's 5 MB cap.
const TARGET_SAMPLE_RATE = 16000;

export async function startWavRecording(): Promise<WavRecorder> {
  const AudioCtx: typeof AudioContext =
    window.AudioContext || (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext;
  const ctx = new AudioCtx();
  if (ctx.state === 'suspended') {
    await ctx.resume();
  }
  const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
  const source = ctx.createMediaStreamSource(stream);
  const processor = ctx.createScriptProcessor(4096, 1, 1);

  const chunks: Float32Array[] = [];
  let paused = false;

  const analyser = ctx.createAnalyser();
  analyser.fftSize = 256;
  source.connect(analyser);

  processor.onaudioprocess = (e) => {
    if (paused) return;
    // Copy: the underlying buffer is reused across callbacks.
    chunks.push(new Float32Array(e.inputBuffer.getChannelData(0)));
  };

  source.connect(processor);
  processor.connect(ctx.destination);

  return {
    pause() { paused = true; },
    resume() { paused = false; },
    isPaused() { return paused; },
    getAnalyser() { return analyser; },
    async stop() {
      processor.onaudioprocess = null;
      const inputRate = ctx.sampleRate;
      processor.disconnect();
      source.disconnect();
      stream.getTracks().forEach((t) => t.stop());
      try { await ctx.close(); } catch { /* already closed */ }
      return encodeWav(downsample(flatten(chunks), inputRate, TARGET_SAMPLE_RATE), TARGET_SAMPLE_RATE);
    },
  };
}

function flatten(chunks: Float32Array[]): Float32Array {
  let len = 0;
  for (const c of chunks) len += c.length;
  const out = new Float32Array(len);
  let offset = 0;
  for (const c of chunks) { out.set(c, offset); offset += c.length; }
  return out;
}

function downsample(samples: Float32Array, from: number, to: number): Float32Array {
  if (to >= from) return samples;
  const ratio = from / to;
  const outLen = Math.floor(samples.length / ratio);
  const out = new Float32Array(outLen);
  for (let i = 0; i < outLen; i++) {
    // Average across the source window rather than hard-decimating, which
    // would alias high frequencies down into the speech band.
    const start = Math.floor(i * ratio);
    const end = Math.min(Math.floor((i + 1) * ratio), samples.length);
    let sum = 0;
    for (let j = start; j < end; j++) sum += samples[j];
    out[i] = end > start ? sum / (end - start) : 0;
  }
  return out;
}

function encodeWav(samples: Float32Array, sampleRate: number): Blob {
  const dataLen = samples.length * 2; // 16-bit mono
  const buffer = new ArrayBuffer(44 + dataLen);
  const view = new DataView(buffer);
  const writeStr = (off: number, s: string) => {
    for (let i = 0; i < s.length; i++) view.setUint8(off + i, s.charCodeAt(i));
  };

  writeStr(0, 'RIFF');
  view.setUint32(4, 36 + dataLen, true);
  writeStr(8, 'WAVE');
  writeStr(12, 'fmt ');
  view.setUint32(16, 16, true);              // PCM header size
  view.setUint16(20, 1, true);               // format: PCM
  view.setUint16(22, 1, true);               // channels: mono
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, sampleRate * 2, true);  // byte rate
  view.setUint16(32, 2, true);               // block align
  view.setUint16(34, 16, true);              // bits per sample
  writeStr(36, 'data');
  view.setUint32(40, dataLen, true);

  let off = 44;
  for (let i = 0; i < samples.length; i++, off += 2) {
    const s = Math.max(-1, Math.min(1, samples[i]));
    view.setInt16(off, s < 0 ? s * 0x8000 : s * 0x7fff, true);
  }
  return new Blob([view], { type: 'audio/wav' });
}
