import { loadCore, get, state, FILES, EVIDENCE } from './data.js';
import { $, $$, esc, dateTime, chainName, table, int, whenNear, openAround, onOpen, markScrollers } from './util.js';
import { initHero } from './hero.js';
import { initCases } from './cases.js';
import { initFindings } from './findings.js';
import { initMap } from './map.js';
import { initFlow } from './flow.js';
import { initFreeze, freezeIntro } from './freeze.js';
import { initTiming } from './timing.js';
import { initExplorer } from './explorer.js';
import { initFrozenBy } from './spotlight.js';

/* ---------- theme ---------- */
const root = document.documentElement;
const mq = matchMedia('(prefers-color-scheme: dark)');
const isDark = () => root.dataset.theme ? root.dataset.theme === 'dark' : mq.matches;
function syncThemeButton() {
  const b = $('#theme');
  b.setAttribute('aria-pressed', String(isDark()));
  b.setAttribute('aria-label', 'Dark mode');
}
$('#theme').addEventListener('click', () => {
  const next = isDark() ? 'light' : 'dark';
  root.dataset.theme = next;
  try { localStorage.setItem('las-theme', next); } catch (e) {}
  syncThemeButton();
});
mq.addEventListener('change', syncThemeButton);
syncThemeButton();

/* ---------- helpers ---------- */
function failBox(sel, what, msg) {
  const node = typeof sel === 'string' ? $(sel) : sel;
  if (node) node.innerHTML = `<p class="fail"><strong>${esc(what)} could not be loaded.</strong> ${esc(msg || '')} The data pipeline writes this file to <code>${esc(state.base)}</code>; reload once it exists.</p>`;
}

function ago(iso) {
  const ms = Date.now() - Date.parse(iso);
  if (!isFinite(ms) || ms < 0) return '';
  const hrs = ms / 36e5;
  if (hrs < 1) return 'less than an hour ago';
  if (hrs < 48) return `${Math.round(hrs)} hours ago`;
  return `${Math.round(hrs / 24)} days ago`;
}

const idle = fn => (window.requestIdleCallback ? requestIdleCallback(fn, { timeout: 1500 }) : setTimeout(fn, 250));
const guard = (name, sel, fn) => async () => { try { await fn(); } catch (e) { console.error(name, e); failBox(sel, name, e.message); } };

/* ---------- refreshed stamp, draft note, method ---------- */
const SOURCE_NAME = {
  ledger: 'the OFAC list', freezes: 'Tether and Circle blacklist events', prices: 'prices', evm: 'Ethereum-type chains',
  utxo: 'Bitcoin-type chains', tron: 'Tron', other: 'other chains',
};
const joinList = a => (a.length < 2 ? a.join('') : a.length === 2 ? a.join(' and ') : a.slice(0, -1).join(', ') + ' and ' + a[a.length - 1]);

/** The "Draft figures" note shows only when meta.json says a source is stale or the results are provisional. */
export function draftNote(m) {
  const el = $('#prov');
  const stale = Object.entries(m?.source_status || {}).filter(([, v]) => v && v.stale === true).map(([k]) => SOURCE_NAME[k] || k);
  const provisional = m?.provisional === true;
  el.hidden = !(stale.length || provisional);
  if (el.hidden) { el.innerHTML = ''; return; }
  const when = m.last_refreshed_utc ? dateTime(m.last_refreshed_utc) : '';
  el.innerHTML = `<b>Draft figures.</b> ${stale.length ? `The last data refresh ran out of time for ${esc(joinList(stale))}, so those figures come from earlier saved results${when ? ` (last complete refresh ${esc(when)})` : ''}.` : ''}${provisional ? ` The analysis is still being checked.` : ''} Numbers may change when the data refreshes.`;
}

function initMeta(D) {
  const m = D.meta;
  if (m?.last_refreshed_utc) {
    const t = $('#refreshed-time');
    t.textContent = dateTime(m.last_refreshed_utc);
    t.setAttribute('datetime', m.last_refreshed_utc);
    $('#foot-refresh').innerHTML = `Data as of <time datetime="${esc(m.last_refreshed_utc)}">${esc(dateTime(m.last_refreshed_utc))}</time>. This page is a dated snapshot.` +
      (m.ofac_list_published_utc ? ` OFAC list as published ${esc(m.ofac_list_published_utc.length > 10 ? dateTime(m.ofac_list_published_utc) : m.ofac_list_published_utc)}.` : '');
  } else {
    $('#refreshed-time').textContent = 'unknown';
  }
  const k = m?.counts;
  if (k) $('#method-open').textContent = `${int(k.addresses)} historical chain–address pairs on ${int(k.chains)} mapped chains; ${int(k.addresses - (k.trackable_addresses ?? 0))} marked untrackable. Search identifiers, sampled transfers, coverage flags and source links.`;
  if (m?.last_refreshed_utc) $('#asof-date').textContent = m.last_refreshed_utc.slice(0, 10);
  if (state.fixture) $('#fixture-banner').hidden = false;
  draftNote(m);

  const cov = $('#coverage');
  if (m?.coverage?.length) {
    cov.innerHTML = table(
      ['Chain', { t: 'Addresses', r: 1 }, { t: 'Trackable', r: 1 }, 'Observed history', 'Notes'],
      m.coverage.slice().sort((a, b) => b.addresses - a.addresses).map(c => [esc(chainName(c.chain)), int(c.addresses), int(c.trackable), !c.readable_histories || !c.complete_histories ? 'Unavailable / incomplete' : c.complete_history ? 'Complete within source scope' : 'Incomplete', esc(c.notes || '')]),
      'cov stack');
    cov.insertAdjacentHTML('afterbegin', '<p class="cap">Counts are chain–address pairs. Trackable is a ledger capability classification. Observed history and asset coverage show what was obtained; saved files can contain no usable history. See the per-address flags.</p>');
  } else failBox(cov, 'Coverage', state.errors.meta);

  const names = {
    meta: 'Counts, coverage, refresh time', headline: 'Finding cards', cases: 'Case timelines', programs: 'Program map',
    sankey: 'Where the money went', freezes: 'Tether and Circle freezes', addresses: 'Address index (explorer)',
    freezes_evidence: 'Raw references and price details behind each freeze', cases_evidence: 'Raw references and issuer events behind each case',
  };
  $('#datafiles').innerHTML = '<ul>' + [...FILES, ...EVIDENCE].map(f => `<li><a href="${esc(state.base + f + '.json')}">${esc(state.base + f + '.json')}</a> ${esc(names[f])}</li>`).join('') +
    `<li>Per-address timelines load on demand from <code>${esc(state.base)}address/&lt;chain&gt;/&lt;address&gt;.json</code>, with sources and raw-response references.</li></ul>`;
}

/* ---------- boot ---------- */
(async function boot() {
  const D = await loadCore();
  const run = (name, sel, fn) => guard(name, sel, fn)();
  initMeta(D);
  await run('Hero', '#hero-stat', () => initHero(D));
  document.documentElement.dataset.ready = '1';

  // Explorer: needs the address index. Events that arrive before it is ready are replayed once it is.
  let explorerReady = null;
  const ensureExplorer = () => (explorerReady ||= (async () => {
    await Promise.all([get('addresses'), get('cases')]);
    if (!state.data.addresses) { failBox('#detail', 'Explorer', state.errors.addresses); return false; }
    initExplorer(state.data);
    return true;
  })().catch(e => { console.error('Explorer', e); failBox('#detail', 'Explorer', e.message); return false; }));
  let explorerLive = false;
  for (const type of ['explorer:search', 'explorer:open']) {
    document.addEventListener(type, ev => {
      if (explorerLive) return;
      ev.stopImmediatePropagation();
      ensureExplorer().then(ok => { explorerLive = ok; if (ok) document.dispatchEvent(new CustomEvent(type, { detail: ev.detail })); });
    }, true);
  }
  const startExplorer = () => ensureExplorer().then(ok => { explorerLive = ok; });
  // A deep link (#addr=...) loads every section at once, then scrolls to the explorer, so late content above
  // it cannot push the address off screen. Otherwise each section loads when it nears the viewport.
  const eager = location.hash.startsWith('#addr=');
  const jobs = [];
  // Each section builds when it nears the screen, or when the browser is idle after the first screen, in page order from the top,
  // so by the time anyone scrolls, the content above them is already in place and the page does not jump.
  const queue = [];
  const lazy = (sel, fn, margin) => {
    let ran = null;
    const once = () => (ran ||= Promise.resolve().then(fn));
    if (eager) jobs.push(once()); else { whenNear(sel, once, margin); queue.push(once); }
  };

  // Cases (and the two spotlight cards) load right after the first screen
  const casesJob = () => run('Cases', '#cases-grid', async () => {
    await Promise.all([get('cases'), get('addresses')]);
    if (!state.data.cases) throw new Error(state.errors.cases || 'cases.json missing');
    initCases(state.data);
  });
  if (eager) jobs.push(casesJob()); else idle(casesJob);

  lazy('#findings', () => run('Findings', '#finds', () => initFindings(state.data)), '900px');
  lazy('#freeze', () => run('Freezes', '#freeze-svg', () => { freezeIntro(state.data); onOpen('#freeze-drawer', () => initFreeze(state.data)); }));
  lazy('#frozenby', () => run('Frozen by name', '#frozenby-body', async () => { await get('addresses'); initFrozenBy(state.data); }), '700px');
  lazy('#flow', () => run('Flow', '#flow-svg', async () => { await get('sankey'); if (!state.data.sankey) throw new Error(state.errors.sankey); await initFlow(state.data); }));
  lazy('#timing', () => run('Timing', '#timing-svg', async () => { await get('addresses'); if (!state.data.addresses) throw new Error(state.errors.addresses); initTiming(state.data); }));
  lazy('#map', () => run('Map', '#map-svg', async () => { await get('programs'); if (!state.data.programs) throw new Error(state.errors.programs); await initMap(state.data); }));
  lazy('#explorer', startExplorer, '900px');
  wireDrawerLinks();
  if (!eager) queue.reduce((p, f) => p.then(() => new Promise(r => idle(() => Promise.resolve(f()).catch(() => {}).then(r)))), new Promise(r => idle(r)));
  if (eager) Promise.allSettled(jobs).then(() => setTimeout(() => document.getElementById('explorer').scrollIntoView({ behavior: 'auto' }), 400));
})();

/* ---------- links into drawers ---------- */
/** A link or address that points into a closed drawer opens the drawer first, then scrolls to the target. */
function wireDrawerLinks() {
  const go = id => {
    const t = id && document.getElementById(decodeURIComponent(id));
    if (!t) return false;
    openAround(t);
    const own = t.matches('details') ? t : t.querySelector(':scope > details.rf');
    if (own) own.open = true;
    requestAnimationFrame(() => t.scrollIntoView({ behavior: matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth', block: 'start' }));
    return true;
  };
  document.addEventListener('click', ev => {
    const a = ev.target.closest && ev.target.closest('a[href^="#"]');
    if (!a || a.getAttribute('href').length < 2) return;
    if (go(a.getAttribute('href').slice(1))) { ev.preventDefault(); try { history.replaceState(null, '', a.getAttribute('href')); } catch (e) {} }
  });
  addEventListener('hashchange', () => { if (!location.hash.startsWith('#addr=')) go(location.hash.slice(1)); });
  if (location.hash.length > 1 && !location.hash.startsWith('#addr=')) setTimeout(() => go(location.hash.slice(1)), 400);
}

/* ---------- sideways-scrolling tables: show the cue only where one really overflows ---------- */
let mkT;
const mk = () => { clearTimeout(mkT); mkT = setTimeout(() => markScrollers(), 120); };
addEventListener('resize', mk);
document.addEventListener('toggle', mk, true);
new MutationObserver(mk).observe(document.body, { childList: true, subtree: true });
