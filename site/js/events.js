/* Case timeline rows, shared by the case cards and the spotlights. Rows that repeat across many addresses on the same
   day (a freeze batch, a listing batch) are folded into one row with the addresses behind a toggle. */
import { esc, numHTML, dateOnly, chainName, shortAddr, int, words, lagPhrase } from './util.js';

export const KIND = {
  designation: 'Listed', first_outflow: 'First outflow', freeze: 'Blacklisted', burn: 'Burned', unfreeze: 'Unblacklisted', delisting: 'Delisted',
  inflow: 'Money in', mixer: 'To a mixer', exchange: 'To an exchange', other: 'Note',
};
const FOLD_MIN = 3;

const amounts = e => [e.amount_native, e.amount, e.usd].filter(a => a && a.value != null)
  .filter((a, i, all) => all.findIndex(b => b.unit === a.unit) === i)
  .map(a => numHTML(a)).join(' &middot; ');

const links = e => {
  const tx = e.tx ? `<a href="${esc(e.tx.explorer_url)}" rel="noopener noreferrer">transaction on ${esc(chainName(e.tx.chain))}</a>` : '';
  const src = e.source_url && !(e.tx && e.source_url === e.tx.explorer_url) ? `<a href="${esc(e.source_url)}" rel="noopener noreferrer">source</a>` : '';
  return [tx, src].filter(Boolean).join(' &middot; ');
};

const lagNote = e => (e.lag_hours != null && e.kind === 'freeze'
  ? `<span class="valued">${esc(lagPhrase(e.lag_hours).replace('the announcement', 'noon on the listing day'))}</span>` : '');

function single(e) {
  const amt = amounts(e);
  const l = links(e);
  return `<li class="k-${esc(e.kind)}"><time>${esc(dateOnly(e.date))}</time><div><b>${esc(KIND[e.kind] || e.kind)}</b> ${esc(words(e.label))} ${amt ? `<span class="ev-amt">${amt}</span>` : ''} ${lagNote(e)}${l ? `<div class="ev-links">${l}</div>` : ''}</div></li>`;
}

function folded(kind, day, list) {
  const sumBy = unit => list.reduce((a, e) => a + ([e.amount_native, e.amount].find(x => x && x.unit === unit)?.value ?? 0), 0);
  const known = list.filter(e => e.amount_native && e.amount_native.value != null).length;
  const unit = list.find(e => e.amount_native)?.amount_native.unit;
  const usd = list.filter(e => e.amount && e.amount.unit === 'usd' && e.amount.value != null);
  const tot = unit && known ? numHTML({ value: sumBy(unit), unit }) + (known < list.length ? ` <span class="valued">from ${int(known)} of ${int(list.length)} with a known amount</span>` : '') : '';
  const totUsd = usd.length ? numHTML({ ...usd[0], value: usd.reduce((a, e) => a + e.amount.value, 0), valued_at: 'at each address’s first freeze', valued_at_iso: null, valuation_basis: 'at_each_freeze_time' }) : '';
  const items = list.map(e => {
    const id = e.address_id || '';
    const a = id.slice(id.indexOf(':') + 1);
    const amt = amounts(e);
    return `<li><button type="button" class="linkbtn mono" data-open="${esc(id)}" title="${esc(a)}">${esc(shortAddr(a, 7, 5))}</button> ${amt ? `<span class="ev-amt">${amt}</span>` : ''} ${lagNote(e)} ${links(e) ? `<span class="ev-links">${links(e)}</span>` : ''}</li>`;
  }).join('');
  return `<li class="k-${esc(kind)}"><time>${esc(day)}</time><div><b>${esc(KIND[kind] || kind)}</b> ${int(list.length)} addresses ${esc(words(list[0].label || ''))} ${tot || totUsd ? `<span class="ev-amt">${[tot, totUsd].filter(Boolean).join(' &middot; ')}</span>` : ''}
    <details class="ev-fold"><summary>Show the ${int(list.length)} addresses</summary><ul class="ev-sub">${items}</ul></details></div></li>`;
}

/** rows for a sorted event list */
export function eventRows(ev) {
  const buckets = new Map();
  for (const e of ev) {
    if (!e.address_id || !['designation', 'freeze'].includes(e.kind)) continue;
    const k = `${e.kind}|${dateOnly(e.date)}|${e.label || ''}`;
    (buckets.get(k) || buckets.set(k, []).get(k)).push(e);
  }
  const done = new Set();
  const out = [];
  for (const e of ev) {
    const k = `${e.kind}|${dateOnly(e.date)}|${e.label || ''}`;
    const b = buckets.get(k);
    if (b && b.length >= FOLD_MIN) {
      if (!done.has(k)) { done.add(k); out.push(folded(e.kind, dateOnly(e.date), b)); }
    } else out.push(single(e));
  }
  return out.join('');
}
