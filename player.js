'use strict';

// The default player displays predecoded image tiles. It never decodes video or
// copies frames through a canvas, so a broken media/GPU path cannot blank it.
const players = new Map();
const clockText = seconds => {
  const value = Math.max(0, Math.floor(Number.isFinite(seconds) ? seconds : 0));
  return `${Math.floor(value / 60)}:${String(value % 60).padStart(2, '0')}`;
};

class ImagePlayer {
  constructor(card) {
    this.card = card;
    this.video = card.querySelector('video');
    this.frame = card.querySelector('.video-frame');
    this.playButton = card.querySelector('.video-play');
    this.status = card.querySelector('.video-status');
    this.duration = Number(this.video.dataset.duration);
    this.position = 0;
    this.playing = false;
    this.compatible = true;
    this.sheets = new Map();
    this.generation = 0;
    this.animation = null;
    this.anchor = 0;
    this.waiting = false;
    this.manifestURL = new URL(this.video.dataset.playback, document.baseURI);
    this.audioURL = this.video.dataset.audio;
    this.muted = false;

    this.wrapper = document.createElement('div');
    this.wrapper.className = 'video-player';
    this.frame.before(this.wrapper);
    this.wrapper.append(this.frame);
    this.stage = document.createElement('div');
    this.stage.className = 'image-playback';
    this.stage.setAttribute('role', 'img');
    this.stage.setAttribute('aria-label', this.video.getAttribute('aria-label'));
    this.poster = new Image();
    this.poster.className = 'video-poster';
    this.poster.src = this.video.poster;
    this.poster.alt = '';
    this.stage.append(this.poster);
    this.frame.append(this.stage);
    if (window.ResizeObserver) new ResizeObserver(() => this.fitStage()).observe(this.frame);

    this.controls = document.createElement('div');
    this.controls.className = 'video-controls';
    this.controls.innerHTML = '<button type="button" class="video-toggle" aria-label="Play video">Play</button><input class="video-progress" type="range" min="0" step="0.1" value="0" aria-label="Video position"><output class="video-time"></output><button type="button" class="video-fullscreen" aria-label="Enter fullscreen">⛶</button>';
    this.wrapper.append(this.controls);
    this.toggle = this.controls.querySelector('.video-toggle');
    this.progress = this.controls.querySelector('.video-progress');
    this.time = this.controls.querySelector('.video-time');
    this.fullscreen = this.controls.querySelector('.video-fullscreen');
    this.sound = document.createElement('button');
    this.sound.type = 'button';
    this.sound.className = 'video-sound';
    this.sound.hidden = !this.audioURL;
    this.sound.innerHTML = '<svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><path d="M11 5 6 9H3v6h3l5 4Z"/><path class="sound-waves" d="M15 8a6 6 0 0 1 0 8m3-11a10 10 0 0 1 0 14"/><path class="sound-off" d="m15 9 6 6m0-6-6 6"/></svg>';
    this.fullscreen.before(this.sound);
    this.sound.addEventListener('click', () => {
      this.muted = !this.muted;
      this.video.muted = this.muted;
      if (this.gain) this.gain.gain.value = this.muted ? 0 : this.video.volume;
      this.update();
    });
    this.mode = document.createElement('button');
    this.mode.type = 'button';
    this.mode.className = 'video-mode';
    this.mode.textContent = 'Standard video';
    card.querySelector('.video-links').prepend(this.mode);

    this.playButton.addEventListener('click', () => this.play());
    this.toggle.addEventListener('click', () => this.playing ? this.pause() : this.play());
    this.stage.addEventListener('click', () => this.playing ? this.pause() : this.play());
    this.progress.addEventListener('input', () => this.seek(Number(this.progress.value), this.playing));
    this.progress.addEventListener('keydown', event => {
      if (event.key === 'ArrowLeft' || event.key === 'ArrowRight') {
        event.preventDefault();
        this.seek(this.position + (event.key === 'ArrowRight' ? 5 : -5), this.playing);
      }
    });
    this.mode.addEventListener('click', () => this.switchMode());
    this.fullscreen.hidden = !document.fullscreenEnabled;
    this.fullscreen.addEventListener('click', async () => {
      try {
        if (document.fullscreenElement) await document.exitFullscreen();
        else await this.wrapper.requestFullscreen();
      } catch (_) { this.fullscreen.focus(); }
    });
    document.addEventListener('fullscreenchange', () => this.fullscreen.setAttribute('aria-label', document.fullscreenElement === this.wrapper ? 'Exit fullscreen' : 'Enter fullscreen'));
    this.video.addEventListener('playing', () => {
      if (!this.compatible) {
        for (const player of players.values()) if (player !== this) player.pause();
        this.playButton.hidden = true;
      }
    });
    this.video.addEventListener('error', () => {
      if (!this.compatible) this.message('If the video does not display, choose Image playback below.');
    });
    this.applyMode();
    this.update();
  }

  message(text) {
    this.status.textContent = text;
    this.status.hidden = !text;
  }

  fitStage() {
    const ratio = this.manifest ? this.manifest.width / this.manifest.height : 16 / 9;
    const width = Math.min(this.frame.clientWidth, this.frame.clientHeight * ratio);
    const height = width / ratio;
    Object.assign(this.stage.style, {
      width: `${width}px`, height: `${height}px`,
      left: `${(this.frame.clientWidth - width) / 2}px`,
      top: `${(this.frame.clientHeight - height) / 2}px`,
    });
  }

  update() {
    this.progress.max = this.duration;
    this.progress.value = this.position;
    this.progress.setAttribute('aria-valuetext', `${clockText(this.position)} of ${clockText(this.duration)}`);
    this.time.textContent = `${clockText(this.position)} / ${clockText(this.duration)}`;
    this.toggle.textContent = this.playing ? 'Pause' : 'Play';
    this.toggle.setAttribute('aria-label', this.playing ? 'Pause video' : 'Play video');
    this.frame.dataset.time = this.position.toFixed(3);
    this.frame.dataset.playing = String(this.playing);
    this.sound.setAttribute('aria-label', this.muted ? 'Unmute audio' : 'Mute audio');
    this.sound.setAttribute('aria-pressed', String(this.muted));
    this.sound.title = this.muted ? 'Unmute audio' : 'Mute audio';
    this.sound.classList.toggle('is-muted', this.muted);
  }

  prepareAudio() {
    if (!this.audioURL) return Promise.resolve();
    if (!this.audioContext) {
      this.audioContext = new (window.AudioContext || window.webkitAudioContext)();
      this.gain = this.audioContext.createGain();
      this.gain.gain.value = this.muted ? 0 : this.video.volume;
      this.gain.connect(this.audioContext.destination);
    }
    // Resume during the click itself, before fetching images or decoding audio.
    // The browser can then authorize sound even when those requests take time.
    const resumed = this.audioContext.resume();
    if (!this.audioLoading) {
      this.audioLoading = fetch(this.audioURL).then(response => {
        if (!response.ok) throw new Error('Audio could not load.');
        return response.arrayBuffer();
      }).then(data => this.audioContext.decodeAudioData(data)).then(buffer => {
        this.audioBuffer = buffer;
      }).catch(error => {
        this.audioLoading = null;
        throw error;
      });
    }
    return Promise.all([resumed, this.audioLoading]);
  }

  stopAudio() {
    if (this.audioSource) {
      this.audioSource.stop();
      this.audioSource.disconnect();
      this.audioSource = null;
    }
  }

  startClock() {
    this.stopAudio();
    if (this.audioBuffer) {
      const now = this.audioContext.currentTime;
      this.anchor = now - this.position;
      this.audioSource = this.audioContext.createBufferSource();
      this.audioSource.buffer = this.audioBuffer;
      this.audioSource.connect(this.gain);
      this.audioSource.start(now, Math.min(this.position, this.audioBuffer.duration));
    } else this.anchor = performance.now() / 1000 - this.position;
  }

  async initialize() {
    if (this.manifest) return;
    if (!this.initializing) {
      this.initializing = fetch(this.manifestURL).then(response => {
        if (!response.ok) throw new Error('Video images could not load.');
        return response.json();
      }).then(manifest => {
        this.manifest = manifest;
        this.duration = manifest.duration;
        this.frame.style.aspectRatio = `${manifest.width} / ${manifest.height}`;
        this.fitStage();
      }).catch(error => {
        this.initializing = null;
        throw error;
      });
    }
    await this.initializing;
  }

  loadSheet(index) {
    if (this.sheets.has(index)) return this.sheets.get(index);
    const image = new Image();
    image.className = 'video-sheet';
    image.alt = '';
    image.draggable = false;
    image.decoding = 'async';
    image.src = new URL(this.manifest.sheets[index], this.manifestURL).href;
    const entry = {image, ready: false};
    entry.promise = image.decode().then(() => { entry.ready = true; return entry; });
    // Prefetch failures are reported only when that sheet is actually needed.
    entry.promise.catch(() => {
      if (this.sheets.get(index) === entry) this.sheets.delete(index);
    });
    this.sheets.set(index, entry);
    return entry;
  }

  locate(seconds) {
    const m = this.manifest;
    const index = Math.max(0, Math.min(m.frames - 1, Math.floor(seconds * m.fps)));
    return {sheet: Math.floor(index / (m.columns * m.rows)), cell: index % (m.columns * m.rows), index};
  }

  display(position, entry, location) {
    const m = this.manifest;
    const image = entry.image;
    image.style.width = `${m.columns * 100}%`;
    image.style.height = `${m.rows * 100}%`;
    image.style.left = `${-(location.cell % m.columns) * 100}%`;
    image.style.top = `${-Math.floor(location.cell / m.columns) * 100}%`;
    if (this.stage.firstElementChild !== image) this.stage.replaceChildren(image);
    this.position = position;
    this.frame.dataset.frame = String(location.index);
    this.playButton.hidden = true;
    for (const index of this.sheets.keys()) {
      if (index < location.sheet - 1 || index > location.sheet + 2) this.sheets.delete(index);
    }
    for (let ahead = 1; ahead <= 2; ahead++) {
      if (location.sheet + ahead < m.sheets.length) this.loadSheet(location.sheet + ahead);
    }
    this.update();
  }

  async show(position, generation) {
    await this.initialize();
    if (generation !== this.generation || !this.compatible) return false;
    const location = this.locate(position);
    const entry = this.loadSheet(location.sheet);
    await entry.promise;
    if (generation !== this.generation || !this.compatible) return false;
    this.display(position, entry, location);
    this.message('');
    return true;
  }

  schedule() {
    if (this.playing && !this.waiting && this.animation === null) this.animation = requestAnimationFrame(now => this.tick(now));
  }

  tick(now) {
    this.animation = null;
    if (!this.playing || !this.compatible || this.waiting) return;
    // Sound and images share the audio clock; buffering pauses both together.
    const clock = this.audioBuffer ? this.audioContext.currentTime : now / 1000;
    let target = Math.max(0, Math.min(this.duration, clock - this.anchor));
    if (target >= this.duration && this.video.loop) {
      target = this.position = 0;
      this.startClock();
    }
    const location = this.locate(target);
    const entry = this.loadSheet(location.sheet);
    if (entry.ready) {
      if (Number(this.frame.dataset.frame) !== location.index) this.display(target, entry, location);
      else { this.position = target; this.update(); }
      if (target >= this.duration) this.pause();
      else this.schedule();
      return;
    }
    this.waiting = true;
    this.stopAudio();
    this.message('Loading video…');
    const generation = this.generation;
    this.show(target, generation).then(shown => {
      if (!shown) return;
      this.waiting = false;
      this.startClock();
      this.schedule();
    }).catch(error => this.fail(error, generation));
  }

  fail(error, generation) {
    if (generation !== this.generation) return;
    this.pause();
    this.playButton.hidden = false;
    this.message('Playback could not load. Press Play to retry, or download the video below.');
  }

  async play() {
    if (!this.compatible) {
      try { await this.video.play(); } catch (_) { this.message('Choose Image playback below if the video does not display.'); }
      return;
    }
    for (const player of players.values()) if (player !== this) player.pause();
    await this.seek(this.position >= this.duration ? 0 : this.position, true);
  }

  pause() {
    this.generation++;
    this.playing = false;
    this.waiting = false;
    if (this.animation !== null) cancelAnimationFrame(this.animation);
    this.animation = null;
    if (!this.video.paused) this.video.pause();
    this.stopAudio();
    this.message('');
    this.update();
  }

  async seek(seconds, resume = true) {
    const target = Math.max(0, Math.min(this.duration, seconds));
    if (!this.compatible) {
      if (this.video.readyState >= 1) this.video.currentTime = target;
      else this.video.addEventListener('loadedmetadata', () => { this.video.currentTime = target; }, {once: true});
      if (resume) await this.play();
      return;
    }
    this.pause();
    const generation = this.generation;
    this.playing = resume;
    this.waiting = true;
    this.message('Loading video…');
    this.update();
    try {
      if (resume) for (const player of players.values()) if (player !== this) player.pause();
      const audioReady = resume ? this.prepareAudio() : Promise.resolve();
      const [shown] = await Promise.all([this.show(target, generation), audioReady]);
      if (!shown || generation !== this.generation || !this.compatible) return;
      this.waiting = false;
      if (resume) this.startClock();
      this.schedule();
    } catch (error) { this.fail(error, generation); }
  }

  applyMode() {
    this.frame.classList.toggle('image-player', this.compatible);
    this.video.hidden = this.compatible;
    this.stage.hidden = !this.compatible;
    this.controls.hidden = !this.compatible;
    this.video.controls = !this.compatible;
    this.mode.textContent = this.compatible ? 'Standard video' : 'Image playback';
    this.playButton.hidden = false;
  }

  async switchMode() {
    const position = this.compatible ? this.position : this.video.currentTime;
    this.muted = this.video.muted;
    if (this.gain) this.gain.gain.value = this.muted ? 0 : this.video.volume;
    this.pause();
    this.compatible = !this.compatible;
    this.applyMode();
    this.message('');
    if (this.compatible) await this.seek(position, false);
    else {
      this.video.preload = 'metadata';
      this.video.load();
      await this.seek(position, false);
    }
  }
}

document.querySelectorAll('.video-card').forEach(card => {
  const player = new ImagePlayer(card);
  players.set(player.video.id, player);
});
document.querySelectorAll('[data-seek]').forEach(button => button.addEventListener('click', () => players.get('overview-video').seek(Number(button.dataset.seek))));
document.querySelectorAll('[data-watch]').forEach(link => link.addEventListener('click', () => players.get(link.dataset.watch).play()));
