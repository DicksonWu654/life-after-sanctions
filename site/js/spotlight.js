import { esc, $, fmt, numHTML, compact, usdText, valuedLabel, isoShort, lagText, shortAddr, chainName, int, dateOnly, words, table, reveal } from './util.js';
import { frozenByEntity, monthYear, caseFreezes, findCase } from './derive.js';
import { eventRows } from './events.js';

const plural = (n, a, b) => (n === 1 ? a : b);
const list = a => (a.length < 2 ? a.join('') : a.length === 2 ? a.join(' and ') : a.slice(0, -1).join(', ') + ' and ' + a[a.length - 1]);

const WHEN = { before: 'Before the listing day', same_day: 'Listing day, order unknown', after: 'After publication', unknown: '' };

/** Bank Markazi, Iran's central bank: read straight from its case entry (per-address listing and freeze events).
    A short card: the number, one sentence, the links. The address table and the full timeline sit in drawers. */
export function frozenSpotlight(D) {
  const c = findCase(D, 'bank-markazi-iran', /markazi/i);
  if (!c) return null;
  const Z = caseFreezes(c);
  if (!Z.rows.length) return null;
  const unit = Z.rows.find(r => r.nativeUnit)?.nativeUnit || 'USDT';
  const n = Z.rows.length;
  const atLeast = Z.nativeUnknown > 0;
  const months = [...new Set(Z.rows.map(r => r.listed).filter(Boolean).sort().map(monthYear))];
  const T = (D.freezes?.summary || []).find(s => s.issuer === 'tether' && s.chain === 'trx');
  const usdAll = T?.usd_frozen;
  const parts = [];
  if (Z.before.length) parts.push(`${int(Z.before.length)} ${plural(Z.before.length, 'was', 'were')} blacklisted before the listing day began, holding ${numHTML({ value: Z.beforeNative, unit: 'native:' + unit }, { valued: false })} at that moment`);
  if (Z.same.length) parts.push(`${int(Z.same.length)} on the listing day itself, so their order against OFAC\u2019s publication is unknown`);
  if (Z.after.length) parts.push(`${int(Z.after.length)} after publication`);
  const rows = Z.rows.slice().sort((x, y) => (y.native ?? -1) - (x.native ?? -1)).map(r => {
    const t = r.lag != null ? lagText(r.lag) : null;
    return [`<button type="button" class="linkbtn mono" data-open="${esc(r.id)}" title="${esc(r.address)}">${esc(shortAddr(r.address, 7, 5))}</button>`,
      esc(r.listed || ''),
      `<span class="${r.when === 'before' ? 'early' : ''}">${t ? `${esc(t.text)} ${t.dir}` : 'n/a'}</span><span class="valued"><br>${esc(WHEN[r.when])}</span>`,
      r.native != null ? esc(compact(r.native)) : '<span class="valued">not known</span>',
      r.usd != null ? esc(usdText(r.usd)) : '<span class="valued">not known</span>'];
  });
  const today = c.today?.balance_usd;
  const times = today?.valuation_times || [];
  const todayWhen = times.length ? `${isoShort(times[0])} to ${isoShort(times[times.length - 1]).replace(/^\d{4}-\d{2}-\d{2} /, '')}` : '';
  const ev = [...(c.events || [])].sort((x, y) => x.date.localeCompare(y.date));
  const art = document.createElement('article');
  art.className = 'spot spot-frozen';
  art.id = 'spot-iran';
  art.setAttribute('aria-labelledby', 'spot-iran-h');
  art.innerHTML = `
    <p class="spot-tag">Tether blacklist, ${esc(chainName((c.chains || ['trx'])[0]))}</p>
    <h3 id="spot-iran-h">${esc(c.name)}</h3>
    <p class="spot-gloss">Iran&rsquo;s central bank, as OFAC names it.</p>
    <p class="spot-big"><span class="num">${atLeast ? 'At least ' : ''}${esc(compact(Z.native))}</span> <span class="unit">${esc(unit)}</span></p>
    <p class="spot-sentence">Tether blacklisted ${n === Z.listedCount ? 'all ' : ''}${int(n)} ${esc(chainName((c.chains || ['trx'])[0]))} ${plural(n, 'address', 'addresses')} that OFAC lists under this name${months.length ? `, listed in ${list(months)}` : ''}. ${parts.length ? parts.join('; ') + '.' : ''}</p>
    <p class="valued">${esc(unit)} counted at each address\u2019s first blacklisting, summed across different dates${atLeast ? `; ${int(Z.nativeUnknown)} ${plural(Z.nativeUnknown, 'address has', 'addresses have')} no known amount` : ''}. In USD that is ${esc(usdText(Z.usd))} (${esc(valuedLabel({ valuation_basis: 'at_each_freeze_time' }))}).</p>
    <details class="drawer">
      <summary>See the ${int(n)} ${plural(n, 'address', 'addresses')}</summary>
      <div class="drawer-body">
        ${table(['Address', 'Listed', 'Blacklisted, against noon on the listing day', unit, { t: 'USD', r: 1 }].map((h, i) => (i === 3 ? { t: h, r: 1 } : h)), rows, 'spot-t stack')}
        <p class="cap">While the blacklist is active, ordinary USDT transfers from the address are restricted. Issuer burns and removals are separate events. OFAC publishes a date, not a time, so \u201cbefore\u201d and \u201cafter\u201d are against noon New York time on the listing date.</p>
        <p class="cap">${usdAll && Z.usd ? `That is ${esc(fmt({ value: Z.usd / usdAll.value, unit: 'share' }).text)} of the ${esc(usdText(usdAll.value))} (${esc(valuedLabel(usdAll))}) held on all ${int(T.all_ofac_chain_addresses.value)} listed ${esc(chainName(T.chain))} addresses. ` : ''}${today ? `Today the ${int(n)} addresses hold ${esc(usdText(today.value))} (${esc(valuedLabel(today))}${todayWhen ? `, ${esc(todayWhen)}` : ''}). ${esc(c.today.status_sentence || '')}` : ''}</p>
      </div>
    </details>
    <details class="drawer">
      <summary>All ${int(ev.length)} events in the case timeline</summary>
      <div class="drawer-body"><ol class="evlist">${eventRows(ev)}</ol></div>
    </details>
    <p class="case-links"><button type="button" class="linkbtn" data-q="${esc(c.name)}">See ${int(n)} ${plural(n, 'address', 'addresses')} in the explorer</button>${c.press_release_url ? `<a href="${esc(c.press_release_url)}" rel="noopener noreferrer">Treasury press release</a>` : ''}</p>`;
  return art;
}

const TORNADO_TILES = { tornado_designation: 'Around OFAC\u2019s designation', tornado_delisting: 'After OFAC removed it' };

export function tornadoSpotlight(D) {
  const c = findCase(D, 'tornado-cash', /tornado/i);
  const H = Object.fromEntries((D.headline || []).map(h => [h.id, h]));
  const tiles = Object.keys(TORNADO_TILES).map(id => H[id]).filter(Boolean);
  if (!c && !tiles.length) return null;
  const max = Math.max(1, ...tiles.flatMap(t => [t.before?.value, t.after?.value].filter(v => v != null)));
  const delist = c && (c.events || []).find(e => e.kind === 'delisting');
  const unOf = t => (t.before?.unit || 'native:ETH').replace(/^native:/, '');
  const tileHTML = t => {
    const f = fmt(t.big, { signed: true });
    return `<div class="ttile"><p class="ttile-h">${esc(TORNADO_TILES[t.id])}${t.event_date ? ` <span class="valued">${esc(t.event_date)}</span>` : ''}</p>
      <p class="ttile-big"><span class="num ${t.big.value < 0 ? 'down' : 'up'}">${esc(f.text)}</span></p>
      <p class="valued">${esc(unOf(t))} deposited, ${t.window_days ? `${int(t.window_days)} days` : 'equal windows'} either side</p></div>`;
  };
  const barsHTML = t => {
    const days = t.window_days, un = unOf(t);
    const bar = (k, o, cls) => `<div class="ba-r"><span class="ba-k">${esc(days ? `${int(days)} days ${k}` : k)}</span><span class="ba-t"><i${cls ? ` class="${cls}"` : ''} style="width:${(o.value / max * 100).toFixed(1)}%"></i></span><span class="ba-v">${esc(compact(o.value))} ${esc(un)}</span></div>`;
    return t.before && t.after
      ? `<p class="ttile-h">${esc(TORNADO_TILES[t.id])}${t.event_date ? ` <span class="valued">${esc(t.event_date)}</span>` : ''}</p><div class="ba" role="img" aria-label="${esc(int(t.before.value))} ${esc(un)} deposited in the ${esc(days)} days before, ${esc(int(t.after.value))} in the ${esc(days)} days after">${bar('before', t.before)}${bar('after', t.after, 'aft')}</div>` : '';
  };
  const bal = H.tornado_balance_recovery;
  const ev = c ? [...(c.events || [])].sort((a, b) => a.date.localeCompare(b.date)) : [];
  const art = document.createElement('article');
  art.className = 'spot spot-tornado';
  art.id = 'spot-tornado';
  art.setAttribute('aria-labelledby', 'spot-tornado-h');
  art.innerHTML = `
    <p class="spot-tag">Listed ${esc(c?.designated || '')}${delist ? `, delisted ${esc(dateOnly(delist.date))}` : ''}</p>
    <h3 id="spot-tornado-h">${esc(c?.name || 'TORNADO CASH')}</h3>
    <p class="spot-gloss">${esc(c?.one_liner || '')}</p>
    <div class="tiles2">${tiles.map(tileHTML).join('')}</div>
    <details class="drawer">
      <summary>Deposit bars and pool balances</summary>
      <div class="drawer-body">
        ${tiles.map(barsHTML).join('')}
        ${bal ? `<p class="spot-sentence">${esc(words(bal.sentence))}</p>` : ''}
        <p class="cap">Deposits are native ETH principal in the four classic pools, in windows of equal length either side of the event, leaving out the day itself. They show what happened around each date, not why. Pool balances (${bal ? `${esc(fmt(bal.big).text)} ${esc(fmt(bal.big).unit)}` : 'see the timeline'}) are a quantity of ETH, not dollars.</p>
      </div>
    </details>
    ${c ? `<details class="drawer"><summary>All ${int(ev.length)} events in the case timeline</summary><div class="drawer-body"><ol class="evlist">${eventRows(ev)}</ol><p class="valued">${esc(words(c.today?.status_sentence))}</p></div></details>` : ''}
    <p class="case-links">${c?.press_release_url ? `<a href="${esc(c.press_release_url)}" rel="noopener noreferrer">Treasury press release</a>` : ''}
      <button type="button" class="linkbtn" data-q="Tornado">See its ${int((c?.addresses || []).length)} addresses in the explorer</button></p>`;
  return art;
}

/** Frozen USDT by OFAC name: ranked bars by OFAC name. Units: USD (USDT at its price when frozen), addresses. */
export function initFrozenBy(D) {
  const host = $('#frozenby-body');
  const groups = frozenByEntity(D.freezes, D.addresses);
  if (!groups.length) { host.innerHTML = '<p class="fail">No frozen Tron addresses in the data.</p>'; return; }
  const SHOW = 5;
  const top = groups.slice(0, SHOW);
  const rest = groups.slice(SHOW);
  const total = groups.reduce((a, g) => a + g.usd, 0);
  const rowsOf = gs => gs.map(g => ({ name: g.name, usd: g.usd, n: g.addresses.length, unknown: g.unknown }));
  const max = Math.max(...groups.map(g => g.usd));
  const li = r => `<li class="${r.other ? 'other' : ''}"><span class="hb-n">${esc(r.name)}</span>
      <span class="hb-v"><b>${esc(usdText(r.usd))}</b> <span class="valued">${int(r.n)} ${plural(r.n, 'address', 'addresses')}${r.unknown ? `, ${int(r.unknown)} unpriced` : ''}</span></span>
      <span class="hb-t"><i style="width:${Math.max(0.4, r.usd / max * 100).toFixed(2)}%"></i></span></li>`;
  const topN = groups[0];
  $('#frozenby-open').innerHTML = `The biggest name is ${esc(topN.name)}, <b>${esc(usdText(topN.usd))}</b> across ${int(topN.addresses.length)} ${plural(topN.addresses.length, 'address', 'addresses')}. Largest first.`;
  host.innerHTML = `<ol class="hbars">${rowsOf(top).map(li).join('')}</ol>
    ${rest.length ? `<details class="drawer"><summary>The other ${int(rest.length)} names</summary><div class="drawer-body"><ol class="hbars">${rowsOf(rest).map(li).join('')}</ol></div></details>` : ''}
    <p class="cap">USD, with USDT valued at each address\u2019s first freeze. Total of the amounts we can read: ${esc(usdText(total))}. Addresses whose frozen amount is unknown are counted but add nothing, so every bar is a floor. Names are exactly as OFAC lists them.</p>`;
  reveal(host);
}
