'use strict';

const players = new Map();
const videoData = new Map();
const useBufferedMP4 = window.origin === 'null';
let requestedVideo = null;

window.voxroomVideoData = (name, chunks) => {
  const parts = chunks.map(encoded => {
    const decoded = atob(encoded.replace(/_0/g, '+').replace(/_1/g, '/'));
    const bytes = new Uint8Array(decoded.length);
    for (let i = 0; i < decoded.length; i++) bytes[i] = decoded.charCodeAt(i);
    return bytes;
  });
  videoData.set(name, new Blob(parts, {type: 'video/mp4'}));
};

// Sandboxed hosts can serve MP4 without byte ranges or CORS. A local Blob keeps seeking available.
const loadBufferedMP4 = video => new Promise((resolve, reject) => {
  const script = document.createElement('script');
  script.src = video.dataset.mp4Data;
  script.onload = () => {
    const name = video.id.replace(/-video$/, '');
    const data = videoData.get(name);
    videoData.delete(name);
    script.remove();
    if (data) resolve(URL.createObjectURL(data));
    else reject(new Error('Missing video data'));
  };
  script.onerror = () => {
    script.remove();
    reject(new Error('Video download failed'));
  };
  document.head.append(script);
});

document.querySelectorAll('.video-card').forEach(card => {
  const video = card.querySelector('video');
  const button = card.querySelector('.video-play');
  const status = card.querySelector('.video-status');
  let pendingSeek = null;
  let sourcePromise = null;
  let objectURL = null;
  const message = text => {
    status.textContent = text;
    status.hidden = !text;
  };
  const play = async () => {
    requestedVideo = video;
    try {
      if (useBufferedMP4 && !objectURL) {
        message('Loading video…');
        button.disabled = true;
        if (!sourcePromise) {
          sourcePromise = loadBufferedMP4(video).then(url => {
            objectURL = url;
            video.src = url;
            video.load();
          }).catch(error => {
            sourcePromise = null;
            throw error;
          });
        }
        await sourcePromise;
      }
      if (requestedVideo !== video) return;
      video.preload = 'auto';
      seekWhenReady();
      await video.play();
    } catch (_) {
      message('Press Play in the video controls, or open the video below.');
    } finally {
      button.disabled = false;
    }
  };
  const seekWhenReady = () => {
    if (pendingSeek === null || video.readyState < 1) return;
    if (useBufferedMP4 && !objectURL) return;
    video.currentTime = Math.min(pendingSeek, video.duration);
    pendingSeek = null;
    message('');
  };
  const seek = seconds => {
    pendingSeek = seconds;
    play();
  };
  for (const event of ['loadedmetadata', 'durationchange']) {
    video.addEventListener(event, seekWhenReady);
  }

  button.hidden = false;
  button.addEventListener('click', play);
  video.addEventListener('play', () => {
    if (useBufferedMP4 && !objectURL) {
      video.pause();
      play();
    }
  });
  video.addEventListener('playing', () => {
    for (const player of players.values()) {
      if (player.video !== video) player.video.pause();
    }
    button.hidden = true;
    message('');
  });
  video.addEventListener('ended', () => { button.hidden = false; });
  video.addEventListener('error', () => {
    message('Unable to play this video. Open the MP4 below.');
  });
  players.set(video.id, {video, play, seek});
});

document.querySelectorAll('[data-seek]').forEach(button => {
  button.addEventListener('click', () => {
    players.get('overview-video').seek(Number(button.dataset.seek));
  });
});
document.querySelectorAll('[data-watch]').forEach(link => {
  link.addEventListener('click', event => {
    if (event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
    event.preventDefault();
    document.querySelector(link.hash).scrollIntoView();
    players.get(link.dataset.watch).play();
  });
});
