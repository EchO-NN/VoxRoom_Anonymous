'use strict';

const players = new Map();

document.querySelectorAll('.video-card').forEach(card => {
  const video = card.querySelector('video');
  const button = card.querySelector('.video-play');
  const status = card.querySelector('.video-status');
  let pendingSeek = null;
  let chapterUnavailable = false;
  const message = text => {
    status.textContent = text;
    status.hidden = !text;
  };
  const play = async () => {
    try {
      await video.play();
    } catch (_) {
      message('Press Play in the video controls, or open the video below.');
    }
  };
  const seekWhenReady = () => {
    if (pendingSeek === null || video.readyState < 1) return;
    for (let i = 0; i < video.seekable.length; i++) {
      if (pendingSeek >= video.seekable.start(i) && pendingSeek <= video.seekable.end(i)) {
        const target = pendingSeek;
        pendingSeek = null;
        video.currentTime = target;
        message('');
        return;
      }
    }
    pendingSeek = null;
    chapterUnavailable = true;
    message('Chapter seeking is unavailable on this host. Open the MP4 video below.');
  };
  const seek = seconds => {
    pendingSeek = seconds;
    chapterUnavailable = false;
    video.preload = 'auto';
    seekWhenReady();
    if (pendingSeek !== null) message('Loading video for this chapter…');
    play();
  };
  for (const event of ['loadedmetadata', 'progress', 'canplaythrough', 'durationchange']) {
    video.addEventListener(event, seekWhenReady);
  }

  button.hidden = false;
  button.addEventListener('click', play);
  video.addEventListener('playing', () => {
    for (const player of players.values()) {
      if (player.video !== video) player.video.pause();
    }
    button.hidden = true;
    if (!chapterUnavailable) message(pendingSeek === null ? '' : 'Loading video for this chapter…');
  });
  video.addEventListener('ended', () => { button.hidden = false; });
  video.addEventListener('error', () => {
    message('Unable to play this file. Open the MP4 or WebM version below.');
  });
  players.set(video.id, {video, play, seek});
});

document.querySelectorAll('[data-seek]').forEach(button => {
  button.addEventListener('click', () => {
    players.get('overview-video').seek(Number(button.dataset.seek));
  });
});
document.querySelectorAll('[data-watch]').forEach(link => {
  link.addEventListener('click', () => players.get(link.dataset.watch).play());
});
