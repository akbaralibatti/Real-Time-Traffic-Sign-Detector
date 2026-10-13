/* upload.js — Video file upload, drag-and-drop processing, progress tracking */

import { Api } from './api.js';
import { showToast } from './utils.js';

export class VideoUploadController {
  constructor({ dropZoneEl, fileInputEl, progressBarEl, progressPctEl, statusTextEl, onComplete }) {
    this.dropZone = dropZoneEl;
    this.fileInput = fileInputEl;
    this.progressBar = progressBarEl;
    this.progressPct = progressPctEl;
    this.statusText = statusTextEl;
    this.onComplete = onComplete;

    this.bindEvents();
  }

  bindEvents() {
    if (!this.dropZone) return;

    this.dropZone.addEventListener('click', () => this.fileInput && this.fileInput.click());

    this.dropZone.addEventListener('dragover', (e) => {
      e.preventDefault();
      this.dropZone.classList.add('drag-over');
    });

    this.dropZone.addEventListener('dragleave', () => {
      this.dropZone.classList.remove('drag-over');
    });

    this.dropZone.addEventListener('drop', (e) => {
      e.preventDefault();
      this.dropZone.classList.remove('drag-over');
      if (e.dataTransfer.files.length) {
        this.processFile(e.dataTransfer.files[0]);
      }
    });

    if (this.fileInput) {
      this.fileInput.addEventListener('change', () => {
        if (this.fileInput.files.length) {
          this.processFile(this.fileInput.files[0]);
        }
      });
    }
  }

  async processFile(file) {
    if (!file) return;

    // Validate video mime type and size (<100MB)
    if (!file.type.startsWith('video/')) {
      showToast('Please select a valid video file (.mp4, .avi, .mov, etc.)', 'error');
      return;
    }

    const maxSize = 100 * 1024 * 1024;
    if (file.size > maxSize) {
      showToast('Video exceeds maximum size of 100MB.', 'error');
      return;
    }

    const fd = new FormData();
    fd.append('video', file);

    // Simulate progress
    let progress = 0;
    const interval = setInterval(() => {
      progress = Math.min(progress + 3, 90);
      if (this.progressBar) this.progressBar.style.width = `${progress}%`;
      if (this.progressPct) this.progressPct.textContent = `${progress}%`;
      if (this.statusText) this.statusText.textContent = progress < 50 ? 'Uploading video…' : 'Analyzing traffic signs…';
    }, 150);

    try {
      const data = await Api.uploadVideo(fd);
      clearInterval(interval);

      if (this.progressBar) this.progressBar.style.width = '100%';
      if (this.progressPct) this.progressPct.textContent = '100%';
      if (this.statusText) this.statusText.textContent = 'Processing completed!';

      showToast('Video processed successfully!', 'success');
      if (this.onComplete) this.onComplete(data);
    } catch (err) {
      clearInterval(interval);
      showToast(err.message || 'Video processing failed', 'error');
      if (this.statusText) this.statusText.textContent = 'Failed to process video';
    }
  }
}
