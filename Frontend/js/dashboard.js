/* dashboard.js — Camera feed streaming, canvas bounding box overlay, FPS tracking */

import { Api } from './api.js';
import { showToast } from './utils.js';

export class LiveFeedController {
  constructor(videoEl, canvasEl, onDetectionCallback, onFpsCallback) {
    this.video = videoEl;
    this.canvas = canvasEl;
    this.ctx = canvasEl ? canvasEl.getContext('2d') : null;
    this.onDetection = onDetectionCallback;
    this.onFps = onFpsCallback;
    this.stream = null;
    this.sessionId = null;
    this.isRunning = false;
    this.frameCount = 0;
    this.lastFrameTime = performance.now();
    this.fpsList = [];
    this.loopId = null;
  }

  async startCamera() {
    try {
      this.stream = await navigator.mediaDevices.getUserMedia({
        video: { width: { ideal: 1280 }, height: { ideal: 720 }, facingMode: 'environment' }
      });
      this.video.srcObject = this.stream;
      await this.video.play();

      // Start backend detection session
      const session = await Api.startSession('live');
      this.sessionId = session.session_id;

      this.isRunning = true;
      this.frameCount = 0;
      this.fpsList = [];
      this.processLoop();
      return this.sessionId;
    } catch (err) {
      showToast('Camera access denied or unavailable.', 'error');
      throw err;
    }
  }

  async stopCamera() {
    this.isRunning = false;
    if (this.loopId) cancelAnimationFrame(this.loopId);

    if (this.stream) {
      this.stream.getTracks().forEach(t => t.stop());
      this.stream = null;
    }

    if (this.ctx && this.canvas) {
      this.ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);
    }

    if (this.sessionId) {
      const avgFps = this.fpsList.length
        ? (this.fpsList.reduce((a, b) => a + b, 0) / this.fpsList.length).toFixed(1)
        : 0;
      try {
        await Api.endSession(this.sessionId, {
          frames_processed: this.frameCount,
          avg_fps: parseFloat(avgFps)
        });
      } catch (_) {}
      const finishedId = this.sessionId;
      this.sessionId = null;
      return finishedId;
    }
  }

  async processLoop() {
    if (!this.isRunning) return;

    const now = performance.now();
    const delta = (now - this.lastFrameTime) / 1000;
    this.lastFrameTime = now;
    const currentFps = delta > 0 ? (1 / delta) : 0;
    this.fpsList.push(currentFps);
    if (this.fpsList.length > 30) this.fpsList.shift();

    if (this.onFps) {
      const avg = (this.fpsList.reduce((a, b) => a + b, 0) / this.fpsList.length).toFixed(1);
      this.onFps(avg);
    }

    // Capture frame to temporary canvas
    if (this.video.videoWidth > 0 && this.video.videoHeight > 0) {
      if (this.canvas.width !== this.video.videoWidth || this.canvas.height !== this.video.videoHeight) {
        this.canvas.width = this.video.videoWidth;
        this.canvas.height = this.video.videoHeight;
      }

      const tempCanvas = document.createElement('canvas');
      tempCanvas.width = 320; // Downscale for fast transmission
      tempCanvas.height = Math.round(320 * (this.video.videoHeight / this.video.videoWidth));
      const tCtx = tempCanvas.getContext('2d');
      tCtx.drawImage(this.video, 0, 0, tempCanvas.width, tempCanvas.height);

      const base64 = tempCanvas.toDataURL('image/jpeg', 0.6).split(',')[1];
      this.frameCount++;

      try {
        const res = await Api.sendFrame({
          session_id: this.sessionId,
          frame: base64
        });

        this.drawDetections(res.detections || []);
        if (this.onDetection && res.detections && res.detections.length) {
          res.detections.forEach(d => this.onDetection(d));
        }
      } catch (_) {
        // Continue stream on network hitch
      }
    }

    // Schedule next frame with ~150ms delay to balance FPS and network throughput
    setTimeout(() => {
      if (this.isRunning) this.processLoop();
    }, 150);
  }

  drawDetections(detections) {
    if (!this.ctx || !this.canvas) return;
    this.ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);

    detections.forEach(d => {
      if (d.bbox) {
        const [x, y, w, h] = d.bbox;
        const scaleX = this.canvas.width / 320;
        const scaleY = this.canvas.height / (320 * (this.canvas.height / this.canvas.width));

        const bx = x * scaleX;
        const by = y * scaleY;
        const bw = w * scaleX;
        const bh = h * scaleY;

        // Bounding box
        this.ctx.strokeStyle = '#00e5ff';
        this.ctx.lineWidth = 3;
        this.ctx.strokeRect(bx, by, bw, bh);

        // Label tag
        const label = `${d.sign_name || 'Traffic Sign'} (${Math.round(d.confidence * 100)}%)`;
        this.ctx.font = 'bold 14px Inter, sans-serif';
        const textWidth = this.ctx.measureText(label).width;

        this.ctx.fillStyle = 'rgba(10, 15, 30, 0.85)';
        this.ctx.fillRect(bx, by - 24, textWidth + 12, 22);

        this.ctx.fillStyle = '#00e5ff';
        this.ctx.fillText(label, bx + 6, by - 8);
      }
    });
  }
}
