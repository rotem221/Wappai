class WappaiPCM extends AudioWorkletProcessor {
  constructor() {
    super();
    this.buffer = new Int16Array(320);
    this.index = 0;
    this.phase = 0;
  }
  process(inputs) {
    const input = inputs[0]?.[0];
    if (input)
      for (const sample of input) {
        this.phase += 16000 / sampleRate;
        if (this.phase >= 1) {
          this.phase -= 1;
          this.buffer[this.index++] = Math.max(
            -32768,
            Math.min(32767, Math.round(sample * 32767)),
          );
          if (this.index === this.buffer.length) {
            this.port.postMessage(this.buffer.buffer, [this.buffer.buffer]);
            this.buffer = new Int16Array(320);
            this.index = 0;
          }
        }
      }
    return true;
  }
}
registerProcessor("wappai-pcm", WappaiPCM);
