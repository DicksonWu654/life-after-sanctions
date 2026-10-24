/* Shared helpers: escaping, number formatting with units, tiny markdown, tooltip. No data values live here. */

export const $ = (sel, root = document) => root.querySelector(sel);
export const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));

export function esc(s) {
  return String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}

export function h(tag, attrs = {}, ...kids) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v == null || v === false) continue;
    if (k === 'class') e.className = v;
    else if (k === 'html') e.innerHTML = v;
    else if (k.startsWith('on')) e.addEventListener(k.slice(2), v);
    else e.setAttribute(k, v === true ? '' : v);
  }
  for (const kid of kids.flat()) if (kid != null && kid !== false) e.append(kid.nodeType ? kid : document.createTextNode(kid));
  return e;
}

const nf0 = new Intl.NumberFormat('en-US', { maximumFractionDigits: 0 });
const nf1 = new Intl.NumberFormat('en-US', { maximumFractionDigits: 1 });
const nf2 = new Intl.NumberFormat('en-US', { maximumFractionDigits: 2, minimumFractionDigits: 0 });
export const int = n => nf0.format(n);

export function compact(n) {
  const a = Math.abs(n);
  if (a >= 1e9) return nf1.format(n / 1e9) + 'B';
  if (a >= 1e6) return nf1.format(n / 1e6) + 'M';
  if (a >= 1e4) return nf0.format(n / 1e3) + 'K';
  if (a >= 1e3) return nf1.format(n / 1e3) + 'K';
  if (a >= 10) return nf0.format(n);
  return nf2.format(n);
}

export function usdText(v) {
  if (v == null) return 'n/a';
  if (v > 0 && v < 1) return '<$1';
  return '$' + compact(v);
}

/* Valuation labels. A USD figure is always shown with the time it is valued at. The export gives either one ISO
   timestamp (valued_at_iso) or an enum for mixed-time aggregates (valuation_basis); a plain statement is the last resort. */
const BASIS = {
  latest_saved_observations: 'USD at each address\u2019s latest saved balance',
  at_each_transfer_time: 'USD at each transfer\u2019s time',
  at_each_freeze_time: 'USD at each address\u2019s first freeze',
};
export function isoShort(iso) {
  const m = String(iso).match(/^(\d{4}-\d{2}-\d{2})(?:[T ](\d{2}:\d{2}))?/);
  if (!m) return String(iso);
  return !m[2] || m[2] === '00:00' ? m[1] : `${m[1]} ${m[2]} UTC`;
}
/** Takes a {valued_at, valued_at_iso, valuation_basis} object or a plain valued_at string. */
export function valuedLabel(v) {
  let s = v;
  if (v && typeof v === 'object') {
    if (v.valued_at_iso) return 'USD at ' + isoShort(v.valued_at_iso);
    if (v.valuation_basis && BASIS[v.valuation_basis]) return BASIS[v.valuation_basis];
    s = v.valued_at;
  }
  if (!s) return 'USD';
  s = String(s);
  if (/^\d{4}-\d{2}-\d{2}/.test(s)) return 'USD at ' + isoShort(s);
  const l = s.toLowerCase();
  if (l.includes('blacklist') || l.includes('freeze')) return BASIS.at_each_freeze_time;
  if (l.includes('constituent') || l.includes('transfer')) return BASIS.at_each_transfer_time;
  if (l.includes('latest') || l.includes('today')) return BASIS.latest_saved_observations;
  if (l.includes('own t') || l.includes('designation') || l.includes('listing')) return 'USD at each address\u2019s listing date';
  const t = s.replace(/^at\s+/i, '');
  return 'USD at ' + (t.length > 46 ? t.slice(0, 44).replace(/[ ,;]+\S*$/, '') + '\u2026' : t);
}
/** The exporter\u2019s own wording, kept for tooltips. */
export const valuedFull = v => { const t = v && typeof v === 'object' ? v.valued_at : v; return t ? String(t) : ''; };

const plural = (n, one, many) => (Math.abs(n) === 1 ? one : many);

/** Format a {value, unit, valued_at?} object -> {text, unit, valued} (strings, unescaped). */
export function fmt(o, opts = {}) {
  if (!o) return { text: 'n/a', unit: '', valued: '' };
  const v = o.value, u = o.unit || '';
  if (v == null) return { text: 'n/a', unit: '', valued: '' };
  if (u === 'usd') return { text: usdText(v), unit: 'USD', valued: valuedLabel(o), valuedFull: valuedFull(o) };
  if (u === 'share') {
    const p = v * 100;
    const sign = opts.signed && p > 0 ? '+' : p < 0 ? '\u2212' : '';
    const ap = Math.abs(p);
    return { text: sign + (ap >= 100 ? nf1 : nf2).format(ap) + '%', unit: 'share', valued: '' };
  }
  if (u === 'days') return { text: nf1.format(v), unit: plural(v, 'day', 'days'), valued: '' };
  if (u === 'hours') return { text: nf1.format(v), unit: plural(v, 'hour', 'hours'), valued: '' };
  if (u.startsWith('native:')) return { text: compact(v), unit: u.slice(7), valued: '' };
  const words = { addresses: ['address', 'addresses'], entities: ['entity', 'entities'], actions: ['designation action', 'designation actions'], events: ['event', 'events'], asset_observations: ['asset reading', 'asset readings'] };
  if (words[u]) return { text: int(v), unit: plural(v, ...words[u]), valued: '' };
  return { text: compact(v), unit: u, valued: '' };
}

/** HTML for a number with its unit and valuation time; short form for inline use. */
export function numHTML(o, opts = {}) {
  const f = fmt(o, opts);
  const unit = f.unit && f.unit !== 'share' ? ` <span class="unit">${esc(f.unit)}</span>` : '';
  const val = f.valued && opts.valued !== false ? ` <span class="valued"${f.valuedFull ? ` title="${esc(f.valuedFull)}"` : ''}>${esc(f.valued)}</span>` : '';
  return `<span class="num">${esc(f.text)}</span>${unit}${val}`;
}

/** Signed hours -> {text, dir}: "4 d" with dir "before"/"after". */
export function lagText(hours) {
  const a = Math.abs(hours);
  let t;
  if (a < 1) t = '<1 h';
  else if (a < 48) t = nf0.format(a) + ' h';
  else if (a < 24 * 45) t = nf0.format(a / 24) + ' d';
  else if (a < 24 * 365 * 1.5) t = nf0.format(a / (24 * 30.4)) + ' mo';
  else t = nf1.format(a / (24 * 365)) + ' yr';
  return { text: t, dir: hours < 0 ? 'before' : 'after' };
}
export function lagPhrase(hours) {
  const l = lagText(hours);
  if (Math.abs(hours) < 1) return 'within an hour of the noon ET proxy';
  return `${l.text} ${l.dir} the noon ET proxy`;
}

/** Hours, said the way a person would: "7 hours", "2 days". */
export function spoken(h) {
  const l = lagText(h);
  if (l.text === '<1 h') return 'under an hour';
  const [n, u] = l.text.split(' ');
  const unit = { h: 'hour', d: 'day', mo: 'month', yr: 'year' }[u] || u;
  return `${n} ${unit}${Number(n) === 1 ? '' : 's'}`;
}

/** "between 19 hours before and 5 hours after", from the two ends of a lag interval in signed hours. */
export function lagRange(lo, hi) {
  if (lo == null || hi == null) return '';
  if (lo < 0 && hi > 0) return `between ${spoken(lo)} before and ${spoken(hi)} after`;
  if (hi <= 0) return `between ${spoken(hi)} and ${spoken(lo)} before`;
  return `between ${spoken(lo)} and ${spoken(hi)} after`;
}

export function daysPhrase(days) {
  if (days === 0) return 'same day';
  const a = Math.abs(days);
  const t = a >= 730 ? nf1.format(a / 365) + ' yr' : a >= 60 ? nf0.format(a / 30.4) + ' mo' : nf0.format(a) + (a === 1 ? ' day' : ' days');
  return days < 0 ? `${t} before` : `${t} after`;
}

export const dateOnly = s => (s ? String(s).slice(0, 10) : '');
export function dateTime(s) {
  if (!s) return '';
  return String(s).replace('T', ' ').replace(/:\d\d(\.\d+)?Z$/, '') + ' UTC';
}
export const dayDiff = (a, b) => Math.round((Date.parse(dateOnly(a)) - Date.parse(dateOnly(b))) / 864e5);

export function shortAddr(a, n = 6, m = 6) {
  return a.length > n + m + 3 ? `${a.slice(0, n)}…${a.slice(-m)}` : a;
}

const CHAIN_NAMES = { arb: 'Arbitrum', bch: 'Bitcoin Cash', bnb: 'BNB Beacon Chain', bsc: 'BNB Smart Chain', bsv: 'Bitcoin SV', btc: 'Bitcoin', btg: 'Bitcoin Gold', dash: 'Dash', doge: 'Dogecoin', etc: 'Ethereum Classic', eth: 'Ethereum', ltc: 'Litecoin', sol: 'Solana', trx: 'Tron', xmr: 'Monero', xrp: 'XRP Ledger', xvg: 'Verge', zec: 'Zcash',
  bitcoin: 'Bitcoin', ethereum: 'Ethereum', tron: 'Tron', litecoin: 'Litecoin', arbitrum: 'Arbitrum', monero: 'Monero', solana: 'Solana', zcash: 'Zcash', polygon: 'Polygon', avalanche: 'Avalanche', bitcoincash: 'Bitcoin Cash', dogecoin: 'Dogecoin' };
export const chainName = c => CHAIN_NAMES[String(c || '').toLowerCase()] || (c ? String(c).toUpperCase() : '');

/** Tiny markdown: paragraphs, - lists, **bold**, `code`, [text](http...) */
export function md(src) {
  const inline = t => esc(t)
    .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
    .replace(/`([^`]+)`/g, '<code>$1</code>')
    .replace(/\[([^\]]+)\]\((https?:[^)\s]+)\)/g, '<a href="$2" rel="noopener noreferrer">$1</a>');
  const out = [];
  let list = null;
  for (const raw of String(src || '').split(/\n/)) {
    const line = raw.trim();
    if (/^[-*] /.test(line)) { (list ||= []).push(`<li>${inline(line.slice(2))}</li>`); continue; }
    if (list) { out.push(`<ul>${list.join('')}</ul>`); list = null; }
    if (line) out.push(`<p>${inline(line)}</p>`);
  }
  if (list) out.push(`<ul>${list.join('')}</ul>`);
  return out.join('');
}

/* ---- tooltip ---- */
let tipEl;
export const tip = {
  show(html, ev) {
    tipEl ||= document.getElementById('tip');
    tipEl.innerHTML = html;
    tipEl.hidden = false;
    this.move(ev);
  },
  move(ev) {
    if (!tipEl || tipEl.hidden) return;
    const pad = 14, w = tipEl.offsetWidth, hh = tipEl.offsetHeight;
    let x, y;
    if (ev && ev.clientX != null) { x = ev.clientX + pad; y = ev.clientY + pad; }
    else if (ev && ev.target && ev.target.getBoundingClientRect) { const r = ev.target.getBoundingClientRect(); x = r.right + 6; y = r.top; }
    else { x = 20; y = 20; }
    if (x + w > innerWidth - 8) x = Math.max(8, (ev && ev.clientX != null ? ev.clientX : x) - w - pad);
    if (y + hh > innerHeight - 8) y = Math.max(8, innerHeight - hh - 8);
    tipEl.style.transform = `translate(${Math.round(x)}px, ${Math.round(y)}px)`;
  },
  hide() { tipEl ||= document.getElementById('tip'); tipEl.hidden = true; },
};
addEventListener('scroll', () => tip.hide(), { passive: true });

/** Keep a chart in sync with its container width. */
export function onResize(el, fn) {
  let w = 0, t;
  const ro = new ResizeObserver(() => {
    const nw = Math.round(el.clientWidth);
    if (nw === w || nw === 0) return;
    w = nw;
    clearTimeout(t);
    t = setTimeout(fn, 60);
  });
  ro.observe(el);
  return () => ro.disconnect();
}

export function cssVar(name) {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

export function el(node) { return typeof node === 'string' ? document.querySelector(node) : node; }

/** Data table. A table whose class list holds "stack" turns into labelled cards on phones (no sideways scrolling);
    any other table scrolls sideways inside its box, with edge shading and a "swipe" cue that shows only when it overflows. */
export function table(headers, rows, cls = '') {
  const stack = /\bstack\b/.test(cls);
  const lab = i => esc(headers[i] ? (headers[i].t ?? headers[i]) : '');
  const th = headers.map(c => `<th scope="col"${c.r ? ' class="r"' : ''}>${esc(c.t ?? c)}</th>`).join('');
  const tr = rows.map(r => `<tr>${r.map((c, i) => `<${i === 0 ? 'th scope="row"' : 'td'} data-l="${lab(i)}"${headers[i] && headers[i].r ? ' class="r"' : ''}>${stack ? `<span class="cv">${c}</span>` : c}</${i === 0 ? 'th' : 'td'}>`).join('')}</tr>`).join('');
  return `<div class="tscroll${stack ? ' stackw' : ''}"><table class="dt ${cls}"><thead><tr>${th}</tr></thead><tbody>${tr}</tbody></table></div>${stack ? '' : '<p class="swipe" aria-hidden="true">Swipe sideways for more columns &rarr;</p>'}`;
}

/** Mark each sideways-scrolling table that really overflows, so its cue shows. */
export function markScrollers(root = document) {
  for (const t of root.querySelectorAll('.tscroll:not(.stackw)')) t.classList.toggle('over', t.clientWidth > 0 && t.scrollWidth > t.clientWidth + 2);
}

/** Charts build once, the first time they scroll into view: adds `in` to the host (CSS plays the build-in animation).
    Everything is already drawn and readable without it, and reduced-motion turns the animation off in CSS. */
export function reveal(el, margin = '0px 0px -12% 0px') {
  const node = typeof el === 'string' ? document.querySelector(el) : el;
  if (!node || node.classList.contains('in')) return;
  const done = () => { node.classList.add('in'); setTimeout(() => node.classList.add('done'), 1600); };
  if (!('IntersectionObserver' in window) || matchMedia('(prefers-reduced-motion: reduce)').matches) { node.classList.add('in', 'done'); return; }
  const io = new IntersectionObserver(es => { if (es.some(e => e.isIntersecting)) { io.disconnect(); done(); } }, { rootMargin: margin, threshold: 0.15 });
  io.observe(node);
}

/** Open every closed <details> that holds `node` (a link into a drawer must land on something visible). */
export function openAround(node) {
  let n = node && node.parentElement, changed = false;
  while (n) { if (n.tagName === 'DETAILS' && !n.open) { n.open = true; changed = true; } n = n.parentElement; }
  return changed;
}

/** Run fn the first time a <details> opens (immediately if it already is open). */
export function onOpen(details, fn) {
  const node = typeof details === 'string' ? document.querySelector(details) : details;
  if (!node) return;
  if (node.open) { fn(); return; }
  const h = () => { if (node.open) { node.removeEventListener('toggle', h); fn(); } };
  node.addEventListener('toggle', h);
}

/** Run fn once when el comes within `margin` of the viewport (immediately if IntersectionObserver is missing). */
export function whenNear(el, fn, margin = '700px') {
  const node = typeof el === 'string' ? document.querySelector(el) : el;
  if (!node) return;
  if (!('IntersectionObserver' in window)) { fn(); return; }
  const io = new IntersectionObserver(es => { if (es.some(e => e.isIntersecting)) { io.disconnect(); fn(); } }, { rootMargin: margin });
  io.observe(node);
}

const scripts = new Map();
export function loadScript(src) {
  if (!scripts.has(src)) scripts.set(src, new Promise((res, rej) => {
    const s = document.createElement('script'); s.src = src; s.onload = res; s.onerror = () => rej(new Error('Could not load ' + src)); document.head.append(s);
  }));
  return scripts.get(src);
}

/** Plain-English program names come from programs.json (label). The code is the fallback. */
const progLabels = new Map();
export function setProgramLabels(list) {
  for (const p of Array.isArray(list) ? list : []) if (p && p.program && p.label) progLabels.set(p.program, p.label);
}
export const programName = c => progLabels.get(c) || c;
/** "Iran (IRAN)": the plain name, plus the code when the name does not already carry it. */
export const programWithCode = c => { const n = programName(c); return n === c || n.includes(c) ? n : `${n} (${c})`; };

/** noon America/New_York on a YYYY-MM-DD date, as a Date (OFAC publishes on a date; the exact minute is unknown). */
export function noonET(dateStr) {
  const [y, m, d] = String(dateStr).slice(0, 10).split('-').map(Number);
  let t = Date.UTC(y, m - 1, d, 17);
  const off = new Intl.DateTimeFormat('en-US', { timeZone: 'America/New_York', timeZoneName: 'shortOffset', hour: 'numeric' }).formatToParts(new Date(t)).find(p => p.type === 'timeZoneName')?.value || 'GMT-5';
  const hrs = Number((off.match(/-(\d+)/) || [0, 5])[1]);
  return new Date(Date.UTC(y, m - 1, d, 12 + hrs));
}

/** The pipeline calls the listing date "T" and says "chain-address pairs". Say it in words on the page. */
export const words = s => String(s || '')
  .replace(/\bpre-T\b/g, 'pre-listing').replace(/\bpost-T\b/g, 'post-listing')
  .replace(/after this address's T\b/g, 'after this address\u2019s listing date')
  .replace(/; T uses each address's first publication date/g, '; the listing date is each address\u2019s first publication date')
  .replace(/zero reconciled recognised-asset balance at T/g, 'a measured balance of zero at listing')
  .replace(/\bat T\b/g, 'at listing').replace(/\bT-value\b/g, 'listing-date value').replace(/\bown-T\b/g, 'own listing-date')
  .replace(/\brecognised\b/gi, m => (m[0] === 'R' ? 'Recognized' : 'recognized'))
  .replace(/SDN UID \d+ \(([^)]+)\)/g, '$1')
  .replace(/\bchain-address pairs\b/g, 'addresses').replace(/\bchain-address pair\b/g, 'address')
  .replace(/\bnoon-ET\b/g, 'noon New York time');
