// WebAudio Audio Recorder with Voice Activity Detection (VAD) & 16kHz PCM WAV encoding

export interface AudioRecorderOptions {
  sampleRate?: number;
  silenceThreshold?: number; // RMS threshold below which audio is considered silence
  silenceDurationMs?: number; // Duration of silence (ms) to trigger auto-stop
}

export class AudioRecorderVAD {
  private mediaStream: MediaStream | null = null;
  private audioContext: AudioContext | null = null;
  private mediaStreamSource: MediaStreamAudioSourceNode | null = null;
  private scriptProcessor: ScriptProcessorNode | null = null;
  private analyser: AnalyserNode | null = null;

  private pcmBuffers: Float32Array[] = [];
  private pcmLength: number = 0;
  private isRecording: boolean = false;
  private isPausedState: boolean = false;

  private sampleRate: number = 16000;
  private silenceThreshold: number = 0.01;
  private silenceDurationMs: number = 2500;
  private silenceStartTime: number | null = null;

  private onAutoStopCallback?: () => void;
  private onAudioLevelCallback?: (level: number) => void;

  private hasSpoken: boolean = false;

  constructor(options: AudioRecorderOptions = {}) {
    this.sampleRate = options.sampleRate || 16000;
    this.silenceThreshold = options.silenceThreshold || 0.008;
    this.silenceDurationMs = options.silenceDurationMs || 4000; // Allow 4 seconds pause while speaking
  }

  public async start(callbacks?: {
    onAutoStop?: () => void;
    onAudioLevel?: (level: number) => void;
  }): Promise<void> {
    this.onAutoStopCallback = callbacks?.onAutoStop;
    this.onAudioLevelCallback = callbacks?.onAudioLevel;

    this.pcmBuffers = [];
    this.pcmLength = 0;
    this.silenceStartTime = null;
    this.hasSpoken = false;

    try {
      this.mediaStream = await navigator.mediaDevices.getUserMedia({
        audio: {
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
          channelCount: 1,
          sampleRate: this.sampleRate,
        },
      });

      const AudioContextClass = window.AudioContext || (window as any).webkitAudioContext;
      this.audioContext = new AudioContextClass({ sampleRate: this.sampleRate });

      this.mediaStreamSource = this.audioContext.createMediaStreamSource(this.mediaStream);
      this.analyser = this.audioContext.createAnalyser();
      this.analyser.fftSize = 512;

      // Create ScriptProcessor for raw PCM sampling (bufferSize 4096)
      this.scriptProcessor = this.audioContext.createScriptProcessor(4096, 1, 1);

      this.scriptProcessor.onaudioprocess = (e: AudioProcessingEvent) => {
        if (!this.isRecording || this.isPausedState) return;

        const inputBuffer = e.inputBuffer.getChannelData(0);
        const bufferCopy = new Float32Array(inputBuffer.length);
        bufferCopy.set(inputBuffer);
        this.pcmBuffers.push(bufferCopy);
        this.pcmLength += bufferCopy.length;

        // Compute RMS audio level for VAD and UI visualization
        let sumSq = 0;
        for (let i = 0; i < bufferCopy.length; i++) {
          sumSq += bufferCopy[i] * bufferCopy[i];
        }
        const rms = Math.sqrt(sumSq / bufferCopy.length);

        if (this.onAudioLevelCallback) {
          this.onAudioLevelCallback(rms);
        }

        // Check if user has started speaking
        if (rms >= this.silenceThreshold) {
          this.hasSpoken = true;
          this.silenceStartTime = null;
        } else if (this.hasSpoken) {
          // Voice Activity Detection (VAD) silence check ONLY after speech has started
          if (this.silenceStartTime === null) {
            this.silenceStartTime = Date.now();
          } else if (Date.now() - this.silenceStartTime > this.silenceDurationMs) {
            // Auto-stop on prolonged silence (> 4.0 seconds) after speech
            if (this.onAutoStopCallback) {
              this.onAutoStopCallback();
            }
          }
        }
      };

      this.mediaStreamSource.connect(this.analyser);
      this.analyser.connect(this.scriptProcessor);
      this.scriptProcessor.connect(this.audioContext.destination);

      this.isRecording = true;
      this.isPausedState = false;
    } catch (err) {
      this.cleanup();
      throw err;
    }
  }

  public pause(): void {
    this.isPausedState = true;
  }

  public resume(): void {
    this.isPausedState = false;
  }

  public isPaused(): boolean {
    return this.isPausedState;
  }

  public getIsRecording(): boolean {
    return this.isRecording;
  }

  public getAnalyser(): AnalyserNode | null {
    return this.analyser;
  }

  public async stop(): Promise<Blob> {
    this.isRecording = false;
    this.isPausedState = false;

    const wavBlob = this.encodeWAV();
    this.cleanup();
    return wavBlob;
  }

  private cleanup(): void {
    if (this.scriptProcessor) {
      try {
        this.scriptProcessor.disconnect();
      } catch { /* ignore */ }
      this.scriptProcessor = null;
    }
    if (this.mediaStreamSource) {
      try {
        this.mediaStreamSource.disconnect();
      } catch { /* ignore */ }
      this.mediaStreamSource = null;
    }
    if (this.analyser) {
      try {
        this.analyser.disconnect();
      } catch { /* ignore */ }
      this.analyser = null;
    }
    if (this.mediaStream) {
      this.mediaStream.getTracks().forEach((t) => t.stop());
      this.mediaStream = null;
    }
    if (this.audioContext && this.audioContext.state !== 'closed') {
      try {
        this.audioContext.close();
      } catch { /* ignore */ }
      this.audioContext = null;
    }
  }

  private encodeWAV(): Blob {
    const actualSampleRate = this.audioContext?.sampleRate || this.sampleRate;
    const samples = new Float32Array(this.pcmLength);
    let offset = 0;
    for (const buf of this.pcmBuffers) {
      samples.set(buf, offset);
      offset += buf.length;
    }

    const buffer = new ArrayBuffer(44 + samples.length * 2);
    const view = new DataView(buffer);

    // RIFF chunk descriptor
    this.writeString(view, 0, 'RIFF');
    view.setUint32(4, 36 + samples.length * 2, true);
    this.writeString(view, 8, 'WAVE');

    // fmt sub-chunk
    this.writeString(view, 12, 'fmt ');
    view.setUint32(16, 16, true); // SubChunk1Size (16 for PCM)
    view.setUint16(20, 1, true); // AudioFormat (1 for PCM)
    view.setUint16(22, 1, true); // NumChannels (1 for Mono)
    view.setUint32(24, actualSampleRate, true);
    view.setUint32(28, actualSampleRate * 2, true); // ByteRate
    view.setUint16(32, 2, true); // BlockAlign
    view.setUint16(34, 16, true); // BitsPerSample

    // data sub-chunk
    this.writeString(view, 36, 'data');
    view.setUint32(40, samples.length * 2, true);

    // Convert Float32 PCM to 16-bit PCM
    let idx = 44;
    for (let i = 0; i < samples.length; i++) {
      const s = Math.max(-1, Math.min(1, samples[i]));
      view.setInt16(idx, s < 0 ? s * 0x8000 : s * 0x7fff, true);
      idx += 2;
    }

    return new Blob([view], { type: 'audio/wav' });
  }

  private writeString(view: DataView, offset: number, string: string): void {
    for (let i = 0; i < string.length; i++) {
      view.setUint8(offset + i, string.charCodeAt(i));
    }
  }
}
