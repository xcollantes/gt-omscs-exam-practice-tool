'use strict';

const $ = (id) => document.getElementById(id);
const SVG_NS = 'http://www.w3.org/2000/svg';
const VIEWS = ['start', 'quiz', 'summary', 'dashboard'];

let pool = [];
let byId = {};
let run = null;
let timer = null;

// ---------- helpers ----------

function el(tag, props = {}, ...kids) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(props)) {
    if (k === 'class') node.className = v;
    else if (k.startsWith('on')) node.addEventListener(k.slice(2), v);
    else if (k in node) node[k] = v;
    else node.setAttribute(k, v);
  }
  node.append(...kids.flat().filter((k) => k != null && k !== false));
  return node;
}

function svg(tag, attrs = {}, text = null) {
  const node = document.createElementNS(SVG_NS, tag);
  for (const [k, v] of Object.entries(attrs)) node.setAttribute(k, v);
  if (text != null) node.textContent = text;
  return node;
}

const pct = (c, n) => (n ? Math.round((100 * c) / n) : 0);
const secs = (ms) => `${(ms / 1000).toFixed(1)}s`;
const when = (iso) => new Date(iso).toLocaleString([], {
  month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit',
});
const shortDate = (iso) => new Date(iso).toLocaleDateString([], {
  month: 'short', day: 'numeric',
});

function clock(ms) {
  const s = Math.floor(ms / 1000);
  const h = Math.floor(s / 3600);
  const m = Math.floor(s / 60) % 60;
  const ss = String(s % 60).padStart(2, '0');
  return h ? `${h}:${String(m).padStart(2, '0')}:${ss}` : `${m}:${ss}`;
}

function moduleLabel(modules) {
  const list = String(modules).split(',');
  return list.length === 6 ? 'All' : list.map((m) => `M${m}`).join(', ');
}

function optionLabel(q, key) {
  if (q.type !== 'MCQ') return key;
  return `${key}. ${q.options.find((o) => o.key === key).text}`;
}

function shuffle(items) {
  for (let i = items.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [items[i], items[j]] = [items[j], items[i]];
  }
  return items;
}

function tile(value, label, sub = null, hero = false) {
  return el('div', { class: `card tile${hero ? ' hero' : ''}` },
    el('div', { class: 'label' }, label),
    el('div', { class: 'value' }, value),
    sub && el('div', { class: 'sub' }, sub));
}

function show(view) {
  for (const id of VIEWS) $(id).hidden = id !== view;
  $('nav').hidden = view === 'quiz';
  for (const b of $('nav').querySelectorAll('button')) {
    if (b.dataset.view === view) b.setAttribute('aria-current', 'page');
    else b.removeAttribute('aria-current');
  }
  if (view === 'dashboard') loadDashboard();
  window.scrollTo(0, 0);
}

// ---------- start ----------

function renderStart() {
  const modules = [...new Set(pool.map((q) => q.module))].sort((a, b) => a - b);
  $('modules').replaceChildren(...modules.map((m) => {
    const qs = pool.filter((q) => q.module === m);
    const lesson = qs[0].lesson.replace(/^Lesson \d+:\s*/, '');
    return el('label', {},
      el('input', { type: 'checkbox', value: m, checked: true, onchange: updatePoolSize }),
      el('span', {}, `Module ${m}: ${lesson}`),
      el('span', { class: 'muted' }, `${qs.length}`));
  }));
  updatePoolSize();
}

function selectedModules() {
  return [...$('modules').querySelectorAll('input:checked')].map((i) => Number(i.value));
}

function updatePoolSize() {
  const modules = selectedModules();
  const n = pool.filter((q) => modules.includes(q.module)).length;
  $('count').max = n;
  $('pool-size').textContent = `of ${n} available`;
  $('start-btn').disabled = n === 0;
}

// ---------- quiz ----------

function startRun() {
  const modules = selectedModules();
  const available = pool.filter((q) => modules.includes(q.module));
  if (!available.length) return;
  const wanted = Math.floor(Number($('count').value)) || 20;
  const n = Math.max(1, Math.min(available.length, wanted));
  run = {
    id: crypto.randomUUID(),
    startedAt: new Date().toISOString(),
    runT0: performance.now(),
    modules,
    questions: shuffle([...available]).slice(0, n),
    i: 0,
    results: [],
  };
  show('quiz');
  clearInterval(timer);
  timer = setInterval(tick, 250);
  renderQuestion();
}

function renderQuestion() {
  const q = run.questions[run.i];
  run.qT0 = performance.now();
  run.answered = null;
  $('progress').textContent = `Question ${run.i + 1} of ${run.questions.length}`;
  $('q-meta').textContent = `Module ${q.module} · ${q.topic}`;
  $('figure').hidden = !q.figure;
  if (q.figure) {
    $('figure-img').src = q.figure;
    $('figure-img').alt = q.caption;
    $('figure-cap').textContent = q.caption;
  }
  $('stem').textContent = q.stem;
  $('options').classList.remove('answered');
  $('options').replaceChildren(...q.options.map((o) => el('button',
    { class: 'option', onclick: () => answer(o.key) },
    q.type === 'MCQ' && el('span', { class: 'key' }, `${o.key}.`),
    el('span', {}, o.text))));
  $('feedback').hidden = true;
  $('save-warn').hidden = true;
  $('next-btn').disabled = true;
  $('next-btn').textContent = run.i + 1 === run.questions.length ? 'Finish' : 'Next';
  $('kbd-hint').textContent = q.type === 'MCQ' ? 'Keys: A–D or 1–4' : 'Keys: T or F';
  tick();
}

function answer(key) {
  if (!run || run.answered) return;
  const q = run.questions[run.i];
  const ms = Math.round(performance.now() - run.qT0);
  const ok = key === q.answer;
  run.answered = key;
  run.results.push({ q, chosen: key, ok, ms });

  $('options').classList.add('answered');
  [...$('options').children].forEach((button, idx) => {
    const optKey = q.options[idx].key;
    if (optKey === q.answer) {
      button.classList.add('correct');
      button.append(el('span', { class: 'tag' }, ok ? '✓ Your answer' : '✓ Correct answer'));
    } else if (optKey === key) {
      button.classList.add('wrong');
      button.append(el('span', { class: 'tag' }, '✗ Your answer'));
    }
  });
  $('verdict').className = `verdict ${ok ? 'good' : 'bad'}`;
  $('verdict').replaceChildren(
    el('span', { class: 'icon', 'aria-hidden': 'true' }, ok ? '✓' : '✗'),
    ok ? 'Correct' : `Incorrect. The answer is ${q.answer}.`);
  $('why').textContent = q.why;
  $('feedback').hidden = false;
  $('next-btn').disabled = false;
  $('next-btn').focus();
  tick();
  saveAnswer({
    run_id: run.id,
    started_at: run.startedAt,
    modules: run.modules,
    question_count: run.questions.length,
    question_id: q.id,
    chosen: key,
    duration_ms: ms,
  });
}

async function saveAnswer(body) {
  try {
    const res = await fetch('/api/answers', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    if (!res.ok) throw new Error((await res.json()).error);
  } catch (e) {
    $('save-warn').textContent = `This answer was not saved: ${e.message}`;
    $('save-warn').hidden = false;
  }
}

function tick() {
  if (!run) return;
  const now = performance.now();
  const qms = run.answered ? run.results.at(-1).ms : now - run.qT0;
  const correct = run.results.filter((r) => r.ok).length;
  $('timers').textContent = `${correct}/${run.results.length} correct · `
    + `question ${clock(qms)} · total ${clock(now - run.runT0)}`;
}

function next() {
  if (!run || !run.answered) return;
  run.i += 1;
  if (run.i < run.questions.length) renderQuestion();
  else finishRun();
}

function finishRun() {
  clearInterval(timer);
  const finished = run;
  run = null;
  if (!finished || !finished.results.length) return show('start');
  renderSummary(finished, performance.now() - finished.runT0);
  show('summary');
}

document.addEventListener('keydown', (e) => {
  if (!run || $('quiz').hidden || e.metaKey || e.ctrlKey || e.altKey) return;
  const q = run.questions[run.i];
  const k = e.key.toLowerCase();
  if (!run.answered) {
    let idx = (q.type === 'MCQ' ? 'abcd' : 'tf').indexOf(k);
    if (idx < 0 && /^[1-4]$/.test(k)) idx = Number(k) - 1;
    if (idx >= 0 && idx < q.options.length) answer(q.options[idx].key);
  } else if (['enter', 'arrowright', 'n'].includes(k)) {
    e.preventDefault();
    next();
  }
});

// ---------- summary ----------

function missedQuestion(q, chosen) {
  return el('div', { class: 'missed' },
    el('p', { class: 'muted' }, `${q.id} · ${q.topic}`),
    el('p', { class: 'stem' }, q.stem),
    chosen && el('p', {}, `Your answer: ${optionLabel(q, chosen)}`),
    el('p', {}, el('strong', {}, 'Correct: '), optionLabel(q, q.answer)),
    el('p', { class: 'why' }, q.why));
}

function renderSummary(r, wallMs) {
  const n = r.results.length;
  const correct = r.results.filter((x) => x.ok).length;
  const answerMs = r.results.reduce((sum, x) => sum + x.ms, 0);
  const missed = r.results.filter((x) => !x.ok);
  $('summary').replaceChildren(
    el('h2', {}, n < r.questions.length ? 'Run ended early' : 'Run complete'),
    el('div', { class: 'tiles' },
      tile(`${pct(correct, n)}%`, 'Score', `${correct} of ${n} correct`, true),
      tile(clock(wallMs), 'Session time', `${clock(answerMs)} spent answering`),
      tile(secs(answerMs / n), 'Average per question')),
    el('div', { class: 'card' },
      el('h3', {}, missed.length ? `Missed (${missed.length})` : 'No misses this run'),
      missed.map((x) => missedQuestion(x.q, x.chosen))),
    el('div', { class: 'row' },
      el('button', { class: 'primary', onclick: startRun }, 'New run, same settings'),
      el('button', { onclick: () => show('start') }, 'Change settings'),
      el('button', { onclick: () => show('dashboard') }, 'Dashboard')));
}

// ---------- dashboard ----------

async function loadDashboard() {
  const root = $('dashboard');
  let s;
  try {
    s = await (await fetch('/api/stats')).json();
  } catch (e) {
    root.replaceChildren(el('p', { class: 'warn' }, `Could not load stats: ${e.message}`));
    return;
  }
  const t = s.totals;
  if (!t.answered) {
    root.replaceChildren(el('h2', {}, 'Dashboard'),
      el('p', { class: 'card' }, 'No answers recorded yet. Finish a few questions and your progress shows up here.'));
    return;
  }
  const topics = s.by_topic.slice(0, 12);
  root.replaceChildren(
    el('h2', {}, 'Dashboard'),
    el('div', { class: 'tiles' },
      tile(`${pct(t.correct, t.answered)}%`, 'Overall accuracy',
        `${t.correct} of ${t.answered} answers`, true),
      tile(String(t.runs), 'Runs'),
      tile(secs(t.avg_ms), 'Average per question'),
      tile(`${t.seen}/${t.pool_size}`, 'Questions seen', `${pct(t.seen, t.pool_size)}% of the pool`)),
    el('div', { class: 'card' }, el('h3', {}, 'Score per run'), scoreChart(s.runs)),
    el('div', { class: 'card' }, el('h3', {}, 'Runs'), runsTable(s.runs)),
    el('div', { class: 'card' }, el('h3', {}, 'Accuracy by module'),
      bars(s.by_module.map((m) => ({ ...m, name: `Module ${m.module}` })))),
    el('div', { class: 'card' },
      el('h3', {}, `Weakest topics (${topics.length} of ${s.by_topic.length})`),
      bars(topics.map((x) => ({ ...x, name: `M${x.module} · ${x.topic}` })))),
    s.most_missed.length ? el('div', { class: 'card' },
      el('h3', {}, 'Most missed questions'),
      s.most_missed.map(missedDetails)) : null);
}

function bars(rows) {
  return el('div', { class: 'bars' }, rows.map((r) => {
    const p = pct(r.correct, r.answered);
    return el('div', { class: 'bar-row' },
      el('span', { class: 'name' }, r.name),
      el('span', { class: 'figs' },
        `${p}% · ${r.correct}/${r.answered} · ${secs(r.avg_ms)} avg`),
      el('div', { class: 'meter', role: 'img', 'aria-label': `${p}% correct` },
        el('div', { style: `width: ${p}%` })));
  }));
}

function runsTable(runs) {
  const heads = ['Date', 'Modules', 'Score', 'Correct', 'Answering', 'Session', 'Avg / q'];
  return el('div', { class: 'table-wrap' }, el('table', {},
    el('thead', {}, el('tr', {},
      heads.map((h, i) => el('th', { class: i > 1 ? 'num' : '' }, h)))),
    el('tbody', {}, [...runs].reverse().map((r) => el('tr', {},
      el('td', {}, when(r.started_at)),
      el('td', {}, moduleLabel(r.modules)),
      el('td', { class: 'num' }, `${pct(r.correct, r.answered)}%`),
      el('td', { class: 'num' }, `${r.correct}/${r.answered}`
        + (r.answered < r.question_count ? ` of ${r.question_count}` : '')),
      el('td', { class: 'num' }, clock(r.answer_ms)),
      el('td', { class: 'num' }, clock(r.wall_ms)),
      el('td', { class: 'num' }, secs(r.answer_ms / r.answered)))))));
}

function missedDetails(m) {
  const q = byId[m.question_id];
  if (!q) return null; // question pool was re-parsed without it
  return el('details', {},
    el('summary', {}, el('strong', {}, `Missed ${m.misses} of ${m.attempts}`),
      ` · ${q.id} · ${q.topic}`),
    missedQuestion(q, null));
}

function scoreChart(runs) {
  const W = 640, H = 200, L = 40, R = 16, T = 16, B = 26;
  const iw = W - L - R, ih = H - T - B;
  const x = (i) => L + (runs.length === 1 ? iw / 2 : (i * iw) / (runs.length - 1));
  const y = (p) => T + ih * (1 - p / 100);
  const pts = runs.map((r, i) => {
    const p = pct(r.correct, r.answered);
    return { x: x(i), y: y(p), p, r };
  });
  const last = pts.at(-1);
  const root = svg('svg', {
    viewBox: `0 0 ${W} ${H}`, role: 'img', tabindex: 0,
    'aria-label': `Score per run for ${runs.length} runs; latest ${last.p}%. `
      + 'Use the left and right arrow keys to inspect each run.',
  });
  for (const p of [0, 25, 50, 75, 100]) {
    root.append(svg('line', {
      x1: L, x2: W - R, y1: y(p), y2: y(p),
      style: `stroke: var(${p === 0 ? '--axis' : '--grid'})`,
    }));
    root.append(svg('text', { x: L - 8, y: y(p) + 4, 'text-anchor': 'end' }, `${p}%`));
  }
  const dateLabel = (i, anchor) => root.append(svg('text',
    { x: x(i), y: H - 6, 'text-anchor': anchor }, shortDate(runs[i].started_at)));
  if (runs.length === 1) dateLabel(0, 'middle');
  else { dateLabel(0, 'start'); dateLabel(runs.length - 1, 'end'); }

  const cross = svg('line', { y1: T, y2: T + ih, style: 'stroke: var(--axis)', visibility: 'hidden' });
  root.append(cross, svg('polyline', {
    points: pts.map((p) => `${p.x},${p.y}`).join(' '),
    fill: 'none', 'stroke-width': 2, 'stroke-linejoin': 'round',
    'stroke-linecap': 'round', style: 'stroke: var(--accent)',
  }));
  const dots = pts.map((p) => svg('circle', {
    cx: p.x, cy: p.y, r: 4, 'stroke-width': 2,
    style: 'fill: var(--accent); stroke: var(--surface)',
  }));
  root.append(...dots, svg('text', {
    x: last.x, y: last.y - 10, 'text-anchor': runs.length === 1 ? 'middle' : 'end',
    style: 'fill: var(--ink-2); font-size: 12px; font-weight: 600',
  }, `${last.p}%`));

  const tip = el('div', { class: 'tooltip', hidden: true });
  const wrap = el('div', { class: 'chart' }, root, tip);
  let active = pts.length - 1;
  const focus = (i) => {
    active = i;
    const { x: px, y: py, p, r } = pts[i];
    cross.setAttribute('x1', px);
    cross.setAttribute('x2', px);
    cross.setAttribute('visibility', 'visible');
    dots.forEach((d, j) => d.setAttribute('r', j === i ? 6 : 4));
    tip.replaceChildren(
      el('strong', {}, `${p}%`),
      el('div', { class: 'secondary' }, `${r.correct}/${r.answered} correct · ${clock(r.answer_ms)} answering`),
      el('div', { class: 'muted' }, `${when(r.started_at)} · ${moduleLabel(r.modules)}`));
    tip.hidden = false;
    const scale = root.getBoundingClientRect().width / W;
    const left = px * scale - tip.offsetWidth / 2;
    tip.style.left = `${Math.min(Math.max(0, left), wrap.clientWidth - tip.offsetWidth)}px`;
    tip.style.top = `${Math.max(0, py * scale - tip.offsetHeight - 14)}px`;
  };
  const hide = () => {
    cross.setAttribute('visibility', 'hidden');
    dots.forEach((d) => d.setAttribute('r', 4));
    tip.hidden = true;
  };
  root.addEventListener('pointermove', (e) => {
    const rect = root.getBoundingClientRect();
    const sx = ((e.clientX - rect.left) * W) / rect.width;
    let best = 0;
    pts.forEach((p, i) => { if (Math.abs(p.x - sx) < Math.abs(pts[best].x - sx)) best = i; });
    focus(best);
  });
  root.addEventListener('pointerleave', hide);
  root.addEventListener('focus', () => focus(active));
  root.addEventListener('blur', hide);
  root.addEventListener('keydown', (e) => {
    if (e.key === 'ArrowLeft') focus(Math.max(0, active - 1));
    else if (e.key === 'ArrowRight') focus(Math.min(pts.length - 1, active + 1));
    else return;
    e.preventDefault();
  });
  return wrap;
}

// ---------- init ----------

$('nav').addEventListener('click', (e) => {
  const view = e.target.closest('button')?.dataset.view;
  if (view) show(view);
});
$('start-btn').addEventListener('click', startRun);
$('next-btn').addEventListener('click', next);
$('end-btn').addEventListener('click', finishRun);

fetch('questions.json')
  .then((res) => res.json())
  .then((questions) => {
    pool = questions;
    byId = Object.fromEntries(pool.map((q) => [q.id, q]));
    renderStart();
  })
  .catch((e) => {
    $('start').replaceChildren(el('p', { class: 'warn' },
      `Could not load questions.json (${e.message}). Run python parse_pdfs.py.`));
  });
