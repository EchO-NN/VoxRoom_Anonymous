'use strict';

// Stage-wise segmentation results.
const settings = {
  simulation: {
    title: 'VoxRoom · simulation', kicker: 'InteriorAgent + GRScene', count: '74', unit: 'test scenes',
    description: '370 trajectories and 2,568 evaluation snapshots, from 20% exploration to the final observation.',
    protocol: 'Average within each trajectory, then within each scene, then equally across scenes.',
    f1: [93.0, 93.9, 94.4, 94.7, 94.6, 94.9, 95.4], iou: [73.9, 74.5, 75.1, 76.9, 78.9, 81.7, 83.8], avgF1: '94.4%', avgIou: '77.8%'
  },
  robot: {
    title: 'VoxRoom · real robot', kicker: 'Direct simulation-to-real transfer', count: '9', unit: 'runs · 5 apartments',
    description: 'Online segmentation at 0.5 Hz. The verifier is trained only in simulation, with no real-world fine-tuning.',
    protocol: 'Equal weighting across nine runs at each stage. Average then combines the seven evaluation stages.',
    f1: [94.5, 94.7, 93.9, 95.3, 95.4, 95.6, 97.2], iou: [85.7, 87.5, 66.8, 79.5, 76.1, 74.4, 81.2], avgF1: '95.2%', avgIou: '78.7%'
  }
};

const svgNS = 'http://www.w3.org/2000/svg';
const stages = ['20%', '40%', '60%', '70%', '80%', '90%', 'Final'];
function svgElement(tag, attributes, text) {
  const element = document.createElementNS(svgNS, tag);
  Object.entries(attributes).forEach(([name, value]) => element.setAttribute(name, value));
  if (text !== undefined) element.textContent = text;
  return element;
}

function renderChart(setting) {
  const data = settings[setting];
  const svg = svgElement('svg', {viewBox: '0 0 620 262', role: 'img', 'aria-labelledby': 'plot-title plot-desc'});
  svg.append(svgElement('title', {id: 'plot-title'}, `${data.title}: F1 and room-mIoU by exploration progress`));
  svg.append(svgElement('desc', {id: 'plot-desc'}, stages.map((stage, index) => `${stage}: F1 ${data.f1[index]}%, room-mIoU ${data.iou[index]}%.`).join(' ')));
  const x = index => 40 + index * 90;
  const y = value => 218 - (value - 60) * 4.65;
  [60, 70, 80, 90, 100].forEach(value => {
    svg.append(svgElement('line', {x1: 40, y1: y(value), x2: 580, y2: y(value), stroke: '#e7e9ee', 'stroke-width': '1'}));
    svg.append(svgElement('text', {x: 28, y: y(value) + 4, fill: '#818792', 'font-size': '10', 'text-anchor': 'end'}, value));
  });
  stages.forEach((stage, index) => svg.append(svgElement('text', {x: x(index), y: 245, fill: '#717782', 'font-size': '10', 'text-anchor': 'middle'}, stage)));
  [['f1', '#315de5'], ['iou', '#727986']].forEach(([metric, color]) => {
    svg.append(svgElement('polyline', {points: data[metric].map((value, index) => `${x(index)},${y(value)}`).join(' '), fill: 'none', stroke: color, 'stroke-width': '2.5', 'stroke-linejoin': 'round', 'stroke-dasharray': metric === 'iou' ? '6 4' : 'none'}));
    data[metric].forEach((value, index) => {
      const dot = svgElement('circle', {cx: x(index), cy: y(value), r: '4', fill: '#ffffff', stroke: color, 'stroke-width': '2'});
      dot.append(svgElement('title', {}, `${stages[index]} · ${metric === 'f1' ? 'F1' : 'Room-mIoU'}: ${value.toFixed(1)}%`));
      svg.append(dot);
    });
    const last = data[metric][6];
    svg.append(svgElement('text', {x: 580, y: y(last) - 12, fill: color, 'font-size': '11', 'font-weight': '600', 'text-anchor': 'end'}, last.toFixed(1)));
  });
  document.getElementById('progress-chart').replaceChildren(svg);
  document.getElementById('chart-title').textContent = data.title;
  document.getElementById('result-kicker').textContent = data.kicker;
  const count = document.getElementById('result-count');
  const unit = document.createElement('span');
  unit.textContent = data.unit;
  count.replaceChildren(document.createTextNode(`${data.count} `), unit);
  document.getElementById('result-description').textContent = data.description;
  document.getElementById('result-protocol').textContent = data.protocol;
  document.getElementById('context-f1').textContent = data.avgF1;
  document.getElementById('context-iou').textContent = data.avgIou;
  document.querySelectorAll('[data-setting]').forEach(button => button.setAttribute('aria-pressed', String(button.dataset.setting === setting)));
}

document.querySelectorAll('[data-setting]').forEach(button => button.addEventListener('click', () => renderChart(button.dataset.setting)));
const players = new Map();
document.querySelectorAll('.video-card').forEach(card => {
  const video = card.querySelector('video');
  const button = card.querySelector('.video-play');
  const status = card.querySelector('.video-status');
  const sources = [...video.querySelectorAll('source')];
  const failed = new Set();
  let wantsPlayback = false;
  let pendingTime = null;
  let loadingTimer;
  video.muted = true;
  button.hidden = false;

  const message = text => {
    status.textContent = text;
    status.hidden = !text;
  };
  const clearLoading = () => {
    clearTimeout(loadingTimer);
    message('');
  };
  const play = () => {
    wantsPlayback = true;
    const attempt = video.play();
    if (attempt) attempt.catch(error => {
      if (error.name === 'AbortError') return;
      button.hidden = false;
      if (error.name === 'NotAllowedError') {
        message('Press the play button to start the video.');
      } else if (!video.error) {
        message('The video could not start. You can open either version below.');
      }
    });
  };
  const seek = seconds => {
    pendingTime = seconds;
    wantsPlayback = true;
    if (video.readyState >= 1) {
      video.currentTime = pendingTime;
      pendingTime = null;
    }
    play();
  };
  video.addEventListener('loadedmetadata', () => {
    if (pendingTime !== null) {
      video.currentTime = Math.min(pendingTime, video.duration);
      pendingTime = null;
    }
  });
  video.addEventListener('playing', () => {
    wantsPlayback = true;
    button.hidden = true;
    clearLoading();
  });
  video.addEventListener('pause', () => {
    wantsPlayback = false;
    clearLoading();
  });
  video.addEventListener('ended', () => { button.hidden = false; });
  video.addEventListener('waiting', () => {
    clearTimeout(loadingTimer);
    loadingTimer = setTimeout(() => {
      if (!video.paused) message('Loading video…');
    }, 1500);
  });
  video.addEventListener('error', () => {
    failed.add(video.currentSrc);
    const fallback = sources.find(source => !failed.has(source.src) && video.canPlayType(source.type));
    if (fallback) {
      pendingTime = pendingTime ?? video.currentTime;
      video.src = fallback.src;
      video.load();
      if (wantsPlayback) play();
    } else {
      clearTimeout(loadingTimer);
      button.hidden = false;
      message('The video could not load. Open either version using the links below.');
    }
  });
  button.addEventListener('click', play);
  players.set(video.id, {play, seek});
});
document.querySelectorAll('[data-seek]').forEach(button => button.addEventListener('click', () => {
  players.get('overview-video').seek(Number(button.dataset.seek));
}));
document.querySelectorAll('[data-watch]').forEach(link => link.addEventListener('click', () => {
  players.get(link.dataset.watch).play();
}));
renderChart('simulation');
