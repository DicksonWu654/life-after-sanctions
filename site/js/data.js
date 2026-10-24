/* Data loading. Reads site/data/*.json when present, else site/fixtures/*.json (contract: docs/DATA_CONTRACT.md).
   Only meta + headline + freezes + programs are fetched up front (they build the first screen). Everything else is fetched
   by get(name) when its section nears the viewport. */

import { setProgramLabels } from './util.js';

export const FILES = ['meta', 'headline', 'cases', 'programs', 'sankey', 'freezes', 'addresses'];
export const CORE = ['headline', 'freezes', 'programs'];
/** Raw references and price details; linked from Method, fetched by nothing on the page. */
export const EVIDENCE = ['freezes_evidence', 'cases_evidence'];

async function getJSON(url) {
  const r = await fetch(url, { cache: 'no-cache' });
  if (!r.ok) throw new Error(`${url}: HTTP ${r.status}`);
  const text = await r.text();
  try { return JSON.parse(text); } catch (e) { throw new Error(`${url}: not JSON`); }
}

export const state = { base: 'fixtures/', fixture: false, errors: {}, loadedFrom: {}, data: {} };
const pending = new Map();

function unwrap(f, j) {
  if (j && !Array.isArray(j) && j.fixture === true) state.fixture = true;
  if (j && !Array.isArray(j) && Array.isArray(j.items)) return j.items;
  return j;
}

/** Fetch one data file once; resolves to the parsed JSON or null (the reason is in state.errors[name]). */
export function get(name) {
  if (!pending.has(name)) {
    state.loadedFrom[name] = `${state.base}${name}.json`;
    pending.set(name, getJSON(state.loadedFrom[name]).then(j => (state.data[name] = unwrap(name, j)), e => { state.errors[name] = e.message; return (state.data[name] = null); }));
  }
  return pending.get(name);
}

export async function loadCore() {
  let metaRaw;
  try { metaRaw = await getJSON('data/meta.json'); state.base = 'data/'; }
  catch (e) {
    try { metaRaw = await getJSON('fixtures/meta.json'); state.base = 'fixtures/'; state.fixture = true; }
    catch (e2) { state.errors.meta = e2.message; metaRaw = null; }
  }
  state.data.meta = metaRaw;
  state.loadedFrom.meta = `${state.base}meta.json`;
  if (metaRaw && metaRaw.fixture === true) state.fixture = true;
  await Promise.all(CORE.map(get));
  setProgramLabels(state.data.programs);
  return state.data;
}

const cache = new Map();
/** Lazy per-address timeline: <base>/address/<chain>/<address>.json */
export function loadAddress(chain, address) {
  const url = `${state.base}address/${encodeURIComponent(chain)}/${encodeURIComponent(address)}.json`;
  if (!cache.has(url)) cache.set(url, getJSON(url).then(j => ({ ok: true, data: j, url }), e => ({ ok: false, error: e.message, url })));
  return cache.get(url);
}
