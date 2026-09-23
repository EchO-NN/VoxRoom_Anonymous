'use strict';

const navigation = document.querySelector('.header');
const navigationToggle = navigation.querySelector('.nav-toggle');
const mobileNavigation = window.matchMedia('(max-width: 600px)');
const navigationSections = [...navigation.querySelectorAll('nav a')].map(link => ({
  link, section: document.querySelector(link.getAttribute('href')),
}));
navigation.classList.add('navigation-ready');
let navigationFrame = null;
let navigationHeight = 0;
let navigationTop = 0;
let previousScrollY = window.scrollY;
let scrollDistance = 0;

function toggleNavigationMenu(open) {
  navigation.classList.toggle('menu-open', open);
  navigationToggle.setAttribute('aria-expanded', String(open));
  if (open) navigation.classList.remove('is-hidden');
}

function updateNavigation() {
  navigationFrame = null;
  const scrollY = Math.max(0, Math.min(window.scrollY, document.documentElement.scrollHeight - window.innerHeight));
  const delta = scrollY - previousScrollY;
  if (delta) {
    scrollDistance = Math.sign(delta) === Math.sign(scrollDistance) ? scrollDistance + delta : delta;
    previousScrollY = scrollY;
  }
  const keyboardFocus = navigation.querySelector(':focus-visible');
  if (scrollY < 80 || scrollDistance < -12 || keyboardFocus) {
    navigation.classList.remove('is-hidden');
  } else if (scrollY > 160 && scrollDistance > 24) {
    toggleNavigationMenu(false);
    navigation.classList.add('is-hidden');
  }
  navigation.classList.toggle('is-scrolled', scrollY > 16);
  // Keep section tracking stable while the header slides out of view.
  const threshold = navigationHeight + navigationTop + 36;
  let active = null;
  for (const entry of navigationSections) {
    if (entry.section.getBoundingClientRect().top <= threshold) active = entry.link;
  }
  if (window.scrollY + window.innerHeight >= document.documentElement.scrollHeight - 2) {
    active = navigationSections[navigationSections.length - 1].link;
  }
  for (const {link} of navigationSections) {
    if (link === active) link.setAttribute('aria-current', 'location');
    else link.removeAttribute('aria-current');
  }
}
function sizeNavigation() {
  navigationHeight = navigation.offsetHeight;
  navigationTop = parseFloat(getComputedStyle(navigation).top) || 0;
  document.documentElement.style.setProperty('--nav-offset', `${navigationHeight + navigationTop + 16}px`);
  updateNavigation();
}
navigationToggle.addEventListener('click', () => {
  toggleNavigationMenu(navigationToggle.getAttribute('aria-expanded') !== 'true');
});
navigation.addEventListener('focusin', () => {
  scrollDistance = 0;
  previousScrollY = window.scrollY;
  navigation.classList.remove('is-hidden');
});
navigation.addEventListener('click', event => {
  if (event.target.closest('a')) toggleNavigationMenu(false);
});
document.addEventListener('pointerdown', event => {
  if (!navigation.contains(event.target)) toggleNavigationMenu(false);
});
document.addEventListener('keydown', event => {
  if (event.key === 'Escape' && navigation.classList.contains('menu-open')) {
    toggleNavigationMenu(false);
    navigationToggle.focus({preventScroll: true});
  }
});
mobileNavigation.addEventListener('change', () => toggleNavigationMenu(false));
window.addEventListener('scroll', () => {
  if (navigationFrame === null) navigationFrame = requestAnimationFrame(updateNavigation);
}, {passive: true});
window.addEventListener('resize', sizeNavigation);
if (window.ResizeObserver) new ResizeObserver(sizeNavigation).observe(navigation);
sizeNavigation();

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
let activeSetting = 'simulation';
let chartWidth = 0;
function svgElement(tag, attributes, text) {
  const element = document.createElementNS(svgNS, tag);
  Object.entries(attributes).forEach(([name, value]) => element.setAttribute(name, value));
  if (text !== undefined) element.textContent = text;
  return element;
}

function renderChart(setting) {
  activeSetting = setting;
  const data = settings[setting];
  const width = Math.max(220, Math.round(document.getElementById('progress-chart').clientWidth));
  chartWidth = width;
  const svg = svgElement('svg', {viewBox: `0 0 ${width} 262`, role: 'img', 'aria-labelledby': 'plot-title plot-desc'});
  svg.append(svgElement('title', {id: 'plot-title'}, `${data.title}: F1 and room-mIoU by exploration progress`));
  svg.append(svgElement('desc', {id: 'plot-desc'}, stages.map((stage, index) => `${stage}: F1 ${data.f1[index]}%, room-mIoU ${data.iou[index]}%.`).join(' ')));
  const x = index => 48 + index * (width - 72) / 6;
  const y = value => 218 - (value - 60) * 4.65;
  [60, 70, 80, 90, 100].forEach(value => {
    svg.append(svgElement('line', {x1: 48, y1: y(value), x2: x(6), y2: y(value), stroke: '#e7e9ee', 'stroke-width': '1'}));
    svg.append(svgElement('text', {x: 36, y: y(value) + 4, fill: '#6c768b', 'text-anchor': 'end'}, value));
  });
  stages.forEach((stage, index) => {
    if (width < 380 && index % 2) return;
    svg.append(svgElement('text', {x: x(index), y: 245, fill: '#6c768b', 'text-anchor': 'middle'}, stage));
  });
  [['f1', '#315de5'], ['iou', '#727986']].forEach(([metric, color]) => {
    svg.append(svgElement('polyline', {points: data[metric].map((value, index) => `${x(index)},${y(value)}`).join(' '), fill: 'none', stroke: color, 'stroke-width': '2.5', 'stroke-linejoin': 'round', 'stroke-dasharray': metric === 'iou' ? '6 4' : 'none'}));
    data[metric].forEach((value, index) => {
      const dot = svgElement('circle', {cx: x(index), cy: y(value), r: '4', fill: '#ffffff', stroke: color, 'stroke-width': '2'});
      dot.append(svgElement('title', {}, `${stages[index]} · ${metric === 'f1' ? 'F1' : 'Room-mIoU'}: ${value.toFixed(1)}%`));
      svg.append(dot);
    });
    const last = data[metric][6];
    svg.append(svgElement('text', {x: x(6), y: y(last) - 12, fill: color, 'font-weight': '600', 'text-anchor': 'end'}, last.toFixed(1)));
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
renderChart('simulation');
if (window.ResizeObserver) new ResizeObserver(entries => {
  if (Math.max(220, Math.round(entries[0].contentRect.width)) !== chartWidth) renderChart(activeSetting);
}).observe(document.getElementById('progress-chart'));

// Paper tables remain readable without JavaScript; tabs progressively enhance them.
const paperTabs = [...document.querySelectorAll('[data-paper-tab]')];
function selectPaperTable(key) {
  paperTabs.forEach(tab => {
    const selected = tab.dataset.paperTab === key;
    tab.setAttribute('aria-selected', String(selected));
    tab.tabIndex = selected ? 0 : -1;
    document.getElementById(tab.getAttribute('aria-controls')).hidden = !selected;
  });
}
paperTabs.forEach((tab, index) => {
  tab.addEventListener('click', () => selectPaperTable(tab.dataset.paperTab));
  tab.addEventListener('keydown', event => {
    let next;
    if (event.key === 'ArrowRight') next = (index + 1) % paperTabs.length;
    else if (event.key === 'ArrowLeft') next = (index + paperTabs.length - 1) % paperTabs.length;
    else if (event.key === 'Home') next = 0;
    else if (event.key === 'End') next = paperTabs.length - 1;
    else return;
    event.preventDefault();
    selectPaperTable(paperTabs[next].dataset.paperTab);
    paperTabs[next].focus();
    paperTabs[next].scrollIntoView({block: 'nearest', inline: 'nearest'});
  });
});
selectPaperTable('comparison');

const comparisonData = JSON.parse(document.getElementById('paper-comparison-data').textContent);
const stageSelect = document.getElementById('comparison-stage');
function renderComparison(stage) {
  const data = comparisonData.stages[stage];
  const table = document.getElementById('comparison-table');
  const header = document.createElement('tr');
  ['Method', ...data.metrics.map(metric => `${metric} ↑`)].forEach(label => {
    const cell = document.createElement('th');
    cell.scope = 'col';
    cell.textContent = label;
    header.append(cell);
  });
  const best = data.metrics.map((_, column) => Math.max(...data.rows.map(row => row[column])));
  const rows = [10, 0, 1, 2, 3, 4, 5, 6, 7, 8, 9].map(index => {
    const row = document.createElement('tr');
    if (comparisonData.methods[index] === 'VoxRoom') row.className = 'highlight';
    const method = document.createElement('th');
    method.scope = 'row';
    method.textContent = comparisonData.methods[index];
    row.append(method);
    data.rows[index].forEach((value, column) => {
      const cell = document.createElement('td');
      if (value === best[column]) {
        const strong = document.createElement('strong');
        strong.textContent = value.toFixed(1);
        cell.append(strong);
      } else cell.textContent = value.toFixed(1);
      row.append(cell);
    });
    return row;
  });
  table.tHead.replaceChildren(header);
  table.tBodies[0].replaceChildren(...rows);
  table.caption.textContent = `Table I. Simulation segmentation performance, ${stage.toLowerCase()} (%)`;
  document.getElementById('comparison-snapshots').textContent = `${data.snapshots.toLocaleString('en-US')} evaluation snapshots`;
}
stageSelect.addEventListener('change', () => renderComparison(stageSelect.value));
