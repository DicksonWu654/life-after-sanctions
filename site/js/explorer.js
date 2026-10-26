import { esc, $, h, fmt, usdText, compact, valuedLabel, daysPhrase, chainName, shortAddr, int, tip, dateOnly, table, programWithCode, lagRange } from './util.js';
import { frozenByEntity } from './derive.js';
import { loadAddress } from './data.js';

const FIRST = 5;   // rows shown before anyone asks for more
const PAGE = 20;
const STATUS = [
  ['any', 'Any status'], ['moved', 'Moved funds out after listing'], ['nomove', 'No outflow found'], ['before', 'Moved funds out in the week before listing'],
  ['frozen', 'Blacklisted by an issuer'], ['frozenbefore', 'Blacklisted before the listing day'], ['receiving', 'Still receiving transfers'], ['untrackable', 'Untrackable'],
];
const SORTS = [
  ['featured', 'Biggest names first'], ['listed-desc', 'Newest listing first'], ['listed-asc', 'Oldest listing first'], ['today-desc', 'Largest balance today'],
  ['listing-desc', 'Largest balance at listing'], ['outflow-asc', 'Fastest first outflow'],
];
const KIND = { in: 'Money in', out: 'Money out', freeze: 'Blacklisted', unfreeze: 'Unblacklisted', burn: 'Burned', designation: 'Listed', delisting: 'Delisted' };
/* The saved classification rules, said in words. A class is a value-threshold rule, not a judgement about purpose. */
const RULE = {
  recognized_asset_at_least_1_usd: 'Recognized asset worth at least 1 USD at transfer time',
  recognized_asset_below_1_usd: 'Recognized asset worth under 1 USD at transfer time',
  off_recognised_token_list: 'Token is not on the recognized list; its authenticity is unresolved',
  below_1_usd_at_transfer_time: 'Worth under 1 USD at transfer time',
  at_least_1_usd_at_transfer_time_and_no_poisoning_rule: 'Worth at least 1 USD at transfer time; no address-mimic pattern',
  zero_value_without_demonstrated_mimic: 'Zero value; no address-mimic pattern shown',
  zero_or_below_1_usd_sender_matches_first_and_last_4_of_prior_real_counterparty: 'Under 1 USD, and the sender mimics the first and last 4 characters of an earlier counterparty',
};
const CONF = { 'threshold_only; poisoning not independently tested outside the saved inflow index': 'value threshold only; address poisoning not tested separately' };

export function initExplorer(D) {
  const rows = D.addresses;
  for (const r of rows) {
    r._ent = (r.entities && r.entities[0]?.name) || '';
    r._h = [r.address, r.id, r.chain, chainName(r.chain), r.ticker, (r.programs || []).join(' '), (r.entities || []).map(e => e.name + ' ' + (e.uid ?? '')).join(' ')].join(' ').toLowerCase();
    r._t = r.balance_today_usd?.value ?? -1;
    r._l = r.balance_at_listing_usd?.value ?? -1;
  }
  const byId = new Map(rows.map(r => [r.id, r]));
  const todayLabel = valuedLabel(rows.find(r => r.balance_today_usd)?.balance_today_usd?.valued_at);

  const q = $('#xq'), selChain = $('#xchain'), selProg = $('#xprog'), selStatus = $('#xstatus'), selSort = $('#xsort');
  const body = $('#xbody'), more = $('#xmore'), count = $('#xcount'), detail = $('#detail');
  detail.hidden = false;
  const grid = $('#xgrid');

  // headers get units
  $('#th-val').innerHTML = `Value <span class="th-sub">USD at listing date, and ${esc(todayLabel)}</span>`;

  const chains = [...new Set(rows.map(r => r.chain))].sort((a, b) => rows.filter(r => r.chain === b).length - rows.filter(r => r.chain === a).length);
  selChain.innerHTML = '<option value="">All chains</option>' + chains.map(c => `<option value="${esc(c)}">${esc(chainName(c))} (${int(rows.filter(r => r.chain === c).length)})</option>`).join('');
  const progs = [...new Set(rows.flatMap(r => r.programs || []))].sort();
  selProg.innerHTML = '<option value="">All programs</option>' + progs.map(p => `<option value="${esc(p)}">${esc(programWithCode(p))}</option>`).join('');
  selStatus.innerHTML = STATUS.map(([v, t]) => `<option value="${v}">${esc(t)}</option>`).join('');
  selSort.innerHTML = SORTS.map(([v, t]) => `<option value="${v}">${esc(t)}</option>`).join('');

  // example searches come from the data: the biggest frozen name, the first cases, a chain
  const tryEl = $('#xtry');
  const short = n => { const w = String(n).split(',')[0].split(/\s+/); return w.slice(0, w.length > 3 ? 2 : w.length).join(' ').toLowerCase().replace(/(^|\s)\S/g, c => c.toUpperCase()); };
  const topFrozen = D.freezes ? frozenByEntity(D.freezes, rows).slice(0, 1).map(g => g.name) : [];
  const examples = [...new Set([...topFrozen, ...(D.cases || []).slice(0, 4).map(c => c.name)].map(short))].slice(0, 4).concat([chainName(chains[0]), progs[0]].filter(Boolean));
  tryEl.innerHTML = '<span class="try-k">Try</span> ' + examples.map(e => `<button type="button" class="chipbtn" data-q="${esc(e)}">${esc(e)}</button>`).join(' ');
  tryEl.addEventListener('click', ev => { const b = ev.target.closest('[data-q]'); if (b) { q.value = b.dataset.q; apply(); } });

  let list = [], shown = 0, selectedId = null, lastTrigger = null, pager = null, featured = false;

  function statusMatch(r, s) {
    switch (s) {
      case 'moved': return r.moved_after === true;
      case 'nomove': return r.moved_after === false;
      case 'before': return r.moved_before_designation === true;
      case 'frozenbefore': return r.frozen_before_listing_day === true;
      case 'frozen': return !!r.frozen;
      case 'receiving': return (r.flags || []).includes('still_receiving');
      case 'untrackable': return !r.trackable;
      default: return true;
    }
  }
  const sorters = {
    featured: (a, b) => b._l - a._l,
    'listed-desc': (a, b) => b.listed.localeCompare(a.listed),
    'listed-asc': (a, b) => a.listed.localeCompare(b.listed),
    'today-desc': (a, b) => b._t - a._t,
    'listing-desc': (a, b) => b._l - a._l,
    'outflow-asc': (a, b) => (a.first_outflow_days ?? a.first_outflow_after_days ?? 1e9) - (b.first_outflow_days ?? b.first_outflow_after_days ?? 1e9),
  };

  function apply(resetHash = true) {
    const toks = q.value.toLowerCase().split(/\s+/).filter(Boolean);
    const c = selChain.value, p = selProg.value, s = selStatus.value;
    list = rows.filter(r => (!c || r.chain === c) && (!p || (r.programs || []).includes(p)) && statusMatch(r, s) && toks.every(t => r._h.includes(t)));
    list.sort(sorters[selSort.value]);
    // With nothing typed or filtered, the first view is the biggest address under each OFAC name, so the five rows are five different stories.
    featured = selSort.value === 'featured' && !toks.length && !c && !p && s === 'any';
    if (featured) {
      const seen = new Set();
      list = list.filter(r => { const k = r._ent || r.id; if (seen.has(k)) return false; seen.add(k); return true; });
    }
    shown = 0; body.innerHTML = '';
    renderMore(true);
  }

  function chips(r) {
    const o = [];
    const fl = r.flags || [];
    if (!r.trackable) o.push(`<span class="chip c-un" title="${esc(r.untrackable_reason || '')}">Untrackable</span>`);
    else if (r.moved_after === true) {
      const when = r.first_outflow_days != null ? ' ' + daysPhrase(Math.round(r.first_outflow_days)) : ' on the listing day';
      o.push(`<span class="chip c-mv"${r.first_outflow_days == null ? ' title="OFAC publishes a date, not a time, so this outflow could be just before or just after publication"' : ''}>Moved${esc(when)}</span>`);
    } else if (r.moved_after === false) o.push('<span class="chip c-no" title="Within the data checked">No outflow found</span>');
    if (r.moved_before_designation === true) o.push('<span class="chip c-bf" title="A qualifying outflow in the 7 days before the listing day">Moved before listing</span>');
    if (r.frozen) o.push(`<span class="chip c-fz">${r.frozen_before_listing_day ? 'Blacklisted before listing day' : 'Blacklisted'}</span>`);
    if (fl.includes('still_receiving')) o.push('<span class="chip c-rc">Still receiving</span>');
    if (fl.includes('partial_history')) o.push('<span class="chip c-un" title="At least one history source is incomplete">Partial history</span>');
    return o.join(' ');
  }

  function rowHTML(r) {
    const ents = r.entities || [];
    const usd1 = r.balance_at_listing_usd, usd2 = r.balance_today_usd;
    const v = (o, k) => `<span class="vl"><span class="vk">${k}</span> ${o ? `<b title="${esc(valuedLabel(o.valued_at))}">${esc(usdText(o.value))}</b>` : '<span class="valued">n/a</span>'}</span>`;
    return `<tr data-id="${esc(r.id)}"${r.id === selectedId ? ' class="sel" aria-selected="true"' : ''}>
      <td data-l="Address"><button type="button" class="abtn" aria-label="Open timeline for ${esc(r.address)}"><span class="ctag">${esc(chainName(r.chain))}</span><span class="mono" title="${esc(r.address)}">${esc(shortAddr(r.address, 8, 6))}</span></button>
        <span class="ent">${esc(r._ent)}</span>${ents.length > 1 ? ` <span class="valued">+${int(ents.length - 1)} more</span>` : ''}<span class="progs">${(r.programs || []).map(x => `<code>${esc(x)}</code>`).join(' ')}</span></td>
      <td data-l="Listed" class="nw c-listed">${esc(r.listed)}${r.delisted ? `<span class="valued"><br>removed ${esc(r.delisted)}</span>` : ''}</td>
      <td data-l="Value (USD)" class="nw c-value">${v(usd1, 'at listing')}<br>${v(usd2, 'today')}</td>
      <td data-l="What happened" class="st">${chips(r)}</td></tr>`;
  }

  function renderMore(first = false) {
    const next = list.slice(shown, shown + (first ? FIRST : PAGE));
    body.insertAdjacentHTML('beforeend', next.map(rowHTML).join(''));
    shown += next.length;
    const all = `<span class="valued">(${int(rows.length)} addresses on the list)</span>`;
    count.innerHTML = list.length
      ? (featured ? `Showing ${int(shown)} of ${int(list.length)} names, the biggest address under each. Search above to find any of the ${int(rows.length)} addresses.` : `Showing ${int(shown)} of ${int(list.length)} matching addresses ${all}`)
      : `No address matches. Try fewer words, or clear a filter. ${all}`;
    more.hidden = shown >= list.length;
    more.textContent = `Show ${int(Math.min(PAGE, list.length - shown))} more`;
  }

  let t;
  q.addEventListener('input', () => { clearTimeout(t); t = setTimeout(apply, 120); });
  [selChain, selProg, selStatus, selSort].forEach(s => s.addEventListener('change', apply));
  more.addEventListener('click', () => renderMore());
  body.addEventListener('click', ev => {
    const tr = ev.target.closest('tr[data-id]');
    if (tr) { lastTrigger = tr.querySelector('.abtn'); open(tr.dataset.id); }
  });

  /* ---------- detail ---------- */
  const isSheet = () => matchMedia('(max-width: 1023px)').matches;
  function close() {
    detail.classList.remove('open');
    grid.classList.remove('has-detail');
    document.documentElement.classList.remove('sheet-open');
    selectedId = null;
    body.querySelectorAll('tr.sel').forEach(tr => { tr.classList.remove('sel'); tr.removeAttribute('aria-selected'); });
    detail.innerHTML = placeholder();
    try { history.replaceState(null, '', location.pathname + location.search + '#explorer'); } catch (e) {}
    if (lastTrigger && document.contains(lastTrigger)) lastTrigger.focus();
  }
  const placeholder = () => '<div class="detail-empty"><p><b>Nothing selected.</b></p><p>Pick an address on the left to see its balances at each checkpoint, its transfers over time and where it points.</p></div>';
  detail.innerHTML = placeholder();
  document.addEventListener('keydown', ev => { if (ev.key === 'Escape' && detail.classList.contains('open')) close(); });
  detail.addEventListener('click', ev => {
    if (ev.target.closest('[data-close]')) close();
    const cp = ev.target.closest('[data-copy]');
    if (cp) { try { navigator.clipboard.writeText(cp.dataset.copy); cp.textContent = 'Copied'; setTimeout(() => (cp.textContent = 'Copy address'), 1400); } catch (e) {} }
    const pg = ev.target.closest('[data-page]');
    if (pg && pager) pager.go(pg.dataset.page);
  });

  async function open(id, opts = {}) {
    const r = byId.get(id);
    if (!r) return;
    selectedId = id;
    body.querySelectorAll('tr.sel').forEach(tr => { tr.classList.remove('sel'); tr.removeAttribute('aria-selected'); });
    const tr = body.querySelector(`tr[data-id="${CSS.escape(id)}"]`);
    if (tr) { tr.classList.add('sel'); tr.setAttribute('aria-selected', 'true'); }
    try { history.replaceState(null, '', '#addr=' + encodeURIComponent(id)); } catch (e) {}
    detail.classList.add('open');
    grid.classList.add('has-detail');
    if (isSheet()) document.documentElement.classList.add('sheet-open');
    detail.innerHTML = headHTML(r) + '<p class="loading">Loading timeline</p>';
    if (opts.scroll) document.getElementById('explorer').scrollIntoView({ behavior: 'auto' });
    detail.scrollTop = 0;
    if (isSheet()) $('.dh-title', detail)?.focus();
    if (!r.trackable) { detail.innerHTML = headHTML(r) + '<p class="cap">There is no on-chain timeline to draw for an untrackable address. It stays in the counts.</p>'; return; }
    const res = await loadAddress(r.chain, r.address);
    if (selectedId !== id) return;
    if (!res.ok) {
      detail.innerHTML = headHTML(r) + `<p class="fail">No timeline file for this address yet (<code>${esc(res.url)}</code>). The row above is all the index holds. A missing file does not mean nothing happened.</p>`;
      return;
    }
    detail.innerHTML = headHTML(r) + bodyHTML(res.data, r);
    initPager(res.data, r);
    drawBalances($('#dBal', detail), res.data);
    drawTransfers($('#dTx', detail), res.data);
  }

  function headHTML(r) {
    const ents = (r.entities || []).map(e => `${esc(e.name)}${e.uid != null ? ` <span class="valued">OFAC entity ${esc(e.uid)}</span>` : ''}`).join('<br>');
    const lastTx = r.last_outflow_before_tx;
    const lastOut = r.last_outflow_before_days != null
      ? `${esc(daysPhrase(Math.round(r.last_outflow_before_days)))} the listing day${lastTx?.explorer_url ? ` (<a href="${esc(lastTx.explorer_url)}" rel="noopener noreferrer">transaction</a>)` : ''}`
      : 'none found within the data checked';
    const pw = r.pre_week_test;
    const pwText = !pw ? '' : pw.eligible ? (pw.active ? 'Moved funds out in the week before listing.' : 'No funds moved out in the week before listing.') : 'Not enough history to test.';
    return `<div class="dhead">
      <button type="button" class="btn close" data-close>Close</button>
      <p class="ctag-l">${esc(chainName(r.chain))} <span class="valued">${esc(r.ticker || '')}</span></p>
      <h3 class="dh-title" tabindex="-1"><span class="mono addr">${esc(r.address)}</span></h3>
      <p class="dh-actions"><button type="button" class="linkbtn" data-copy="${esc(r.address)}">Copy address</button>${r.explorer_url ? ` &middot; <a href="${esc(r.explorer_url)}" rel="noopener noreferrer">View on a block explorer</a>` : ''}</p>
      <dl class="dmeta">
        <div><dt>Entity</dt><dd>${ents || 'n/a'}</dd></div>
        <div><dt>Programs</dt><dd>${(r.programs || []).map(p => `<span class="prg">${esc(programWithCode(p))}</span>`).join(', ') || 'n/a'}</dd></div>
        <div><dt>Listed</dt><dd>${esc(r.listed)}${r.delisted ? `, removed ${esc(r.delisted)}` : ''}</dd></div>
        <div><dt>Value at listing</dt><dd>${r.balance_at_listing_usd ? `${esc(usdText(r.balance_at_listing_usd.value))} <span class="valued">${esc(valuedLabel(r.balance_at_listing_usd))}</span>` : 'n/a'}</dd></div>
        <div><dt>Value today</dt><dd>${r.balance_today_usd ? `${esc(usdText(r.balance_today_usd.value))} <span class="valued">${esc(valuedLabel(r.balance_today_usd))}</span>` : 'n/a'}</dd></div>
        ${r.trackable ? `<div><dt>Last outflow before listing</dt><dd>${lastOut}</dd></div>` : ''}
        ${pwText ? `<div><dt>Week before listing</dt><dd>${esc(pwText)}</dd></div>` : ''}
      </dl>
      ${r.balance_scope ? `<p class="cap">${esc(r.balance_scope)}${r.unpriced_assets_today_count ? ` ${esc(int(r.unpriced_assets_today_count))} other assets held today have no price and are left out of the dollar figure.` : ''}</p>` : ''}
      ${r.chain_confidence === 'medium' ? `<p class="cap warn">${r.chain === 'eth' ? 'OFAC didn\u2019t name the network for this address; Ethereum is assumed from its format.' : 'OFAC listed this address under a Bitcoin ticker; Tron is assumed from its format.'}</p>` : ''}
      <p class="dchips">${chips(r)}</p>
      <p class="dverdict">${verdict(r)}</p>
    </div>`;
  }

  function verdict(r) {
    if (!r.trackable) return esc(r.untrackable_reason ? `Untrackable: ${r.untrackable_reason}` : 'Untrackable on a public ledger. It stays in the counts.');
    if (r.moved_after === false) return 'No outflow found after listing, within the data checked.';
    if (r.moved_after === true) {
      if (r.first_outflow_days != null) return `First outflow ${esc(daysPhrase(Math.round(r.first_outflow_days)))} the listing day.`;
      const iv = r.first_outflow_lag_interval_days;
      const rng = iv ? lagRange(iv[0] * 24, iv[1] * 24) : '';
      return `First outflow on the listing day itself. OFAC publishes a date, not a time${rng ? `, so it came ${esc(rng)} publication` : ''}.`;
    }
    return '';
  }

  const assetName = a => {
    const t = String(a || '');
    if (/^trc10:/i.test(t)) return 'TRC-10 token ' + t.slice(6);
    return t.length > 14 ? 'token ' + shortAddr(t, 5, 4) : t;
  };
  const amountText = e => `${esc(fmt({ value: e.amount, unit: 'native:' + (e.asset || '') }).text.replace(/^n\/a$/, 'amount n/a'))} ${esc(assetName(e.asset))}`;
  const KEYS = ['designation', 'delisting', 'freeze', 'unfreeze', 'burn'];
  const MARKS = ['freeze', 'unfreeze', 'burn'];

  function classChip(e) {
    if (!e.class) return '';
    const title = [RULE[e.classification_rule] || (e.classification_rule || '').replace(/_/g, ' '), e.classification_confidence ? `Confidence: ${CONF[e.classification_confidence] || e.classification_confidence}` : ''].filter(Boolean).join('. ');
    const chip = (cls, text) => `<span class="chip ${cls}" title="${esc(title)}">${text}</span>`;
    if (e.class === 'dust') return chip('c-dust', 'Dust');
    if (e.class === 'poisoning') return chip('c-poisoning', 'Possible address poisoning');
    // "real" is a size rule; only an incoming transfer that passed it is one of the counted incoming transfers
    if (e.class === 'real' && e.kind === 'in') return chip('c-real', 'Passed study filters');
    return '';
  }

  function evRow(e) {
    const isMark = KEYS.includes(e.kind);
    const moved = !isMark && e.amount != null ? amountText(e) : esc(assetName(e.asset));
    const usd = e.usd != null ? `<span class="valued"> ${esc(usdText(e.usd))} USD, ${esc(valuedLabel(e.valued_at))}</span>` : (!isMark && e.amount != null ? '<span class="valued"> no price</span>' : '');
    const amt = ['designation', 'delisting'].includes(e.kind) ? '' : `${isMark ? esc(assetName(e.asset)) : moved}${usd}`;
    const cp = e.counterparty ? `<span class="mono" title="${esc(e.counterparty)}">${esc(shortAddr(e.counterparty, 8, 6))}</span>${e.counterparty_label ? ` <span class="chip lead" title="Label source: ${esc(e.label_source || 'not given')}. A lead.">${esc(e.counterparty_label)}</span>` : ''}` : '';
    const tx = e.explorer_url ? `<a href="${esc(e.explorer_url)}" rel="noopener noreferrer">transaction</a>` : (e.source_url ? `<a href="${esc(e.source_url)}" rel="noopener noreferrer">source</a>` : '');
    return `<li class="evrow k-${esc(e.kind)}"><time>${esc(dateOnly(e.time))}</time><div><b>${esc(KIND[e.kind] || e.kind)}</b> ${amt} ${classChip(e)}<div class="evsub">${cp} ${tx}${e.date_basis ? ` <span class="valued">${esc(e.date_basis)}</span>` : ''}</div></div></li>`;
  }

  function bodyHTML(d, r) {
    const ev = [...(d.events || [])].sort((a, b) => a.time.localeCompare(b.time));
    const cps = (d.checkpoints || []).filter(c => Date.parse(c.time) <= Date.now());
    const key = ev.filter(e => KEYS.includes(e.kind));
    const tr = ev.filter(e => !KEYS.includes(e.kind));
    const cpTable = cps.length ? table(['Checkpoint', 'Time', { t: 'Balance', r: 1 }, { t: 'USD', r: 1 }],
      cps.map(c => [esc(CP[c.label] || c.label), esc(dateOnly(c.time)),
        c.balances.map(b => `${esc(fmt({ value: b.native, unit: 'native:' + b.asset }).text)} ${esc(assetName(b.asset))}`).join('<br>'),
        c.balances.map(b => `${b.usd != null ? esc(usdText(b.usd)) : '<span class="valued">no price</span>'} <span class="valued">${esc(valuedLabel(b.valued_at))}</span>`).join('<br>')])) : '';
    const T = d.truncation;
    const sampled = !!(T && T.omitted_transfer_events > 0);
    const tz = sampled
      ? `<p class="cap warn">This timeline shows a sample of ${int(T.retained_transfer_events)} of ${int(T.observed_transfer_events)} saved transfers${T.observed_designation_window_transfers ? `, including ${int(T.retained_designation_window_transfers ?? 0)} of the ${int(T.observed_designation_window_transfers)} around the listing date` : ''}. Every listing, delisting and issuer event is kept. The monthly bars above count all ${int(T.observed_transfer_events)}.</p>` : '';
    const C = d.coverage;
    const cov = C && C.from_time ? `<p class="cap">History checked: ${esc(dateOnly(C.from_time))} to ${esc(dateOnly(C.to_time))}${C.complete === false ? ', which may be incomplete' : ''}. “No outflow found” means none in this range.</p>` : '';
    const monthly = !!(d.monthly_counts && d.monthly_counts.length && (sampled || tr.length > 400));
    const assets = (r.assets_today || []).slice().sort((a, b) => (b.usd ?? -1) - (a.usd ?? -1));
    const assetTable = assets.length ? `<details class="tview"><summary>Held today (${int(assets.length)} priced ${assets.length === 1 ? 'asset' : 'assets'})</summary>${table(['Asset', { t: 'Amount', r: 1 }, { t: 'USD', r: 1 }],
      assets.map(a => [esc(assetName(a.asset)), esc(compact(a.native)), a.usd != null ? `${esc(usdText(a.usd))} <span class="valued">${esc(valuedLabel(a.valued_at))}</span>` : '<span class="valued">no price</span>']))}${r.unpriced_assets_today_count ? `<p class="cap">${int(r.unpriced_assets_today_count)} further assets have no price and are not counted in any dollar figure.</p>` : ''}</details>` : '';
    return `
      <h4>Balance at each checkpoint</h4>
      <div id="dBal" class="dchart" role="img" aria-label="Balance at each checkpoint, in USD at each checkpoint date"></div>
      <p class="cap">USD, valued at each checkpoint date; recognized assets only.</p>
      ${assetTable}
      <h4>Transfers over time</h4>
      <div id="dTx" class="dchart" role="img" aria-label="Transfers in and out over time"></div>
      <p class="cap dleg"><span class="lg"><i class="dot-in"></i>Money in</span> <span class="lg"><i class="dot-out"></i>Money out</span> <span class="lg"><i class="dot-fz"></i>Blacklisted or burned</span> <span class="lg"><i class="dot-uf"></i>Unblacklisted</span> <span class="lg"><i class="dot-ln"></i>Listing date</span> ${monthly ? 'Bars count all saved transfers per month.' : 'Dot area follows USD value at transfer date; transfers without a price get the smallest dot.'}</p>
      ${tz}${cov}
      <details class="tview"><summary>Checkpoint table</summary>${cpTable}</details>
      <h4>Key moments</h4>
      ${key.length ? `<ol class="evlist ledger">${key.map(evRow).join('')}</ol>` : '<p class="valued">No listing or blacklist events recorded for this address.</p>'}
      <h4>Transfers${sampled ? ' (sample)' : ''}</h4>
      ${tr.length ? `<ol class="evlist ledger" id="dEv"></ol><p class="pager" id="dPager"></p>` : '<p class="valued">No transfers recorded.</p>'}
      <h4>Evidence</h4>
      <ul class="srcs">${(d.sources || []).map(u => `<li><a href="${esc(u)}" rel="noopener noreferrer">${esc(u)}</a></li>`).join('')}${(d.raw_refs || []).slice(0, 12).map(u => `<li>Raw response: <code>${esc(u)}</code></li>`).join('')}${(d.raw_refs || []).length > 12 ? `<li class="valued">and ${int(d.raw_refs.length - 12)} more raw responses, listed in the address file</li>` : ''}</ul>`;
  }

  /** Transfers page forward from just before the listing date, 40 at a time. */
  function initPager(d, r) {
    const list = $('#dEv', detail), bar = $('#dPager', detail);
    if (!list) { pager = null; return; }
    const tr = (d.events || []).filter(e => !KEYS.includes(e.kind)).sort((a, b) => a.time.localeCompare(b.time));
    const SIZE = 40;
    const sampledNote = d.truncation && d.truncation.omitted_transfer_events > 0 ? ` (a sample of ${int(d.truncation.observed_transfer_events)} saved transfers)` : '';
    const idx = tr.findIndex(e => e.time >= (r.listed || ''));
    let start = Math.max(0, (idx < 0 ? 0 : idx) - 10);
    const show = () => {
      const slice = tr.slice(start, start + SIZE);
      list.innerHTML = slice.map(evRow).join('');
      bar.innerHTML = `<span class="valued">Transfers ${int(start + 1)} to ${int(start + slice.length)} of ${int(tr.length)} shown${sampledNote}, oldest first. Starts just before the listing date.</span><br>` +
        `<button type="button" class="btn" data-page="prev" ${start <= 0 ? 'disabled' : ''}>Earlier</button> <button type="button" class="btn" data-page="next" ${start + SIZE >= tr.length ? 'disabled' : ''}>Later</button>`;
    };
    pager = { go(dir) { start = dir === 'next' ? Math.min(Math.max(0, tr.length - 1), start + SIZE) : Math.max(0, start - SIZE); show(); } };
    show();
  }

  const CP = { 'T-7d': '7 days before', T: 'Listing day', 'T+7d': '7 days after', 'T+30d': '30 days after', 'T+365d': '1 year after', today: 'Today' };
  function drawBalances(host, d) {
    const cps = (d.checkpoints || []).filter(c => Date.parse(c.time) <= Date.now());
    if (!host || !cps.length) { if (host) host.innerHTML = '<p class="valued">No checkpoint balances recorded.</p>'; return; }
    const W = Math.max(260, host.clientWidth), H = 150, mL = 4, mR = 4, mT = 22, mB = 34;
    const vals = cps.map(c => c.balances.reduce((a, b) => a + (b.usd || 0), 0));
    const y = d3.scaleLinear().domain([0, Math.max(1, d3.max(vals))]).range([H - mB, mT]);
    const x = d3.scaleBand().domain(cps.map(c => c.label)).range([mL, W - mR]).padding(0.28);
    const svg = d3.select(host).html('').append('svg').attr('width', W).attr('height', H).attr('viewBox', `0 0 ${W} ${H}`);
    svg.append('line').attr('class', 'axis').attr('x1', mL).attr('x2', W - mR).attr('y1', H - mB).attr('y2', H - mB);
    cps.forEach((c, i) => {
      const bx = x(c.label), bw = x.bandwidth(), by = y(vals[i]);
      const g = svg.append('g');
      const hgt = Math.max(vals[i] > 0 ? 2 : 0, H - mB - by);
      g.append('path').attr('class', 'bar' + (c.label === 'T' ? ' at-list' : '')).attr('d', `M${bx},${H - mB} v${-(Math.max(0, hgt - 4))} a4,4 0 0 1 4,-4 h${Math.max(0, bw - 8)} a4,4 0 0 1 4,4 v${Math.max(0, hgt - 4)} z`);
      g.append('text').attr('class', 'bval').attr('x', bx + bw / 2).attr('y', by - 6).attr('text-anchor', 'middle').text(usdText(vals[i]));
      g.append('text').attr('class', 'blab').attr('x', bx + bw / 2).attr('y', H - mB + 14).attr('text-anchor', 'middle').text(({ 'T-7d': '-7 d', T: 'Listing', 'T+7d': '+7 d', 'T+30d': '+30 d', 'T+365d': '+1 yr', today: 'Today' })[c.label] || c.label);
      g.append('text').attr('class', 'bsub').attr('x', bx + bw / 2).attr('y', H - mB + 26).attr('text-anchor', 'middle').text(dateOnly(c.time).slice(2));
      g.append('rect').attr('x', bx - 4).attr('width', bw + 8).attr('y', mT - 14).attr('height', H - mT + 14).attr('fill', 'transparent')
        .on('mousemove', ev => tip.show(`<b>${esc(c.label)}</b> ${esc(dateOnly(c.time))}<br>${c.balances.map(b => `${esc(fmt({ value: b.native, unit: 'native:' + b.asset }).text)} ${esc(b.asset)}: ${esc(usdText(b.usd))} <span class="valued">${esc(valuedLabel(b.valued_at))}</span>`).join('<br>')}`, ev))
        .on('mouseleave', () => tip.hide());
    });
  }

  function drawTransfers(host, d) {
    const ev = (d.events || []).filter(e => e.time);
    if (!host) return;
    if (!ev.length) { host.innerHTML = '<p class="valued">No transfers recorded.</p>'; return; }
    const moves = ev.filter(e => !KEYS.includes(e.kind));
    const mc = d.monthly_counts || [];
    const T = d.truncation;
    const monthly = mc.length && ((T && T.omitted_transfer_events > 0) || moves.length > 400);
    const W = Math.max(260, host.clientWidth), H = 190, mL = 8, mR = 8, mT = 14, mB = 26, mid = (H - mB + mT) / 2;
    const times = ev.map(e => new Date(e.time));
    if (monthly) mc.forEach(m => times.push(new Date(m.month + '-01T00:00:00Z')));
    const now = new Date();
    const x = d3.scaleTime().domain([d3.min(times), d3.max([...times, now])]).range([mL + 6, W - mR - 6]).nice();
    const svg = d3.select(host).html('').append('svg').attr('width', W).attr('height', H).attr('viewBox', `0 0 ${W} ${H}`);
    svg.append('line').attr('class', 'axis').attr('x1', mL).attr('x2', W - mR).attr('y1', mid).attr('y2', mid);
    const ax = svg.append('g').attr('class', 'tx-ax').attr('transform', `translate(0,${H - mB + 4})`).call(d3.axisBottom(x).ticks(Math.max(2, Math.floor(W / 90))).tickSizeOuter(0));
    ax.select('.domain').remove();
    ev.filter(e => e.kind === 'designation' || e.kind === 'delisting').forEach(e => {
      svg.append('line').attr('class', e.kind === 'designation' ? 'lline' : 'lline del').attr('x1', x(new Date(e.time))).attr('x2', x(new Date(e.time))).attr('y1', mT - 4).attr('y2', H - mB);
      svg.append('text').attr('class', 'ltxt').attr('x', x(new Date(e.time)) + 4).attr('y', mT + 6).text(e.kind === 'designation' ? 'Listed' : 'Delisted');
    });
    svg.append('text').attr('class', 'lane').attr('x', mL).attr('y', mid - 6).text('In');
    svg.append('text').attr('class', 'lane').attr('x', mL).attr('y', mid + 14).text('Out');
    const marks = ev.filter(e => MARKS.includes(e.kind));
    const drawMarks = () => marks.forEach(e => {
      const cx = x(new Date(e.time));
      svg.append('path').attr('class', e.kind === 'unfreeze' ? 'tx-uf' : 'tx-fz').attr('transform', `translate(${cx},${mid})`).attr('d', d3.symbol().type(d3.symbolDiamond).size(150)());
      svg.append('circle').attr('cx', cx).attr('cy', mid).attr('r', 10).attr('fill', 'transparent')
        .on('mousemove', ev2 => tip.show(`<b>${esc(KIND[e.kind])}</b> ${esc(dateOnly(e.time))}<br>${esc(e.asset || '')}${e.usd != null ? `<br>${esc(usdText(e.usd))} USD <span class="valued">${esc(valuedLabel(e.valued_at))}</span>` : ''}`, ev2))
        .on('mouseleave', () => tip.hide());
    });
    if (monthly) {
      // all saved transfers, counted per month (the dots would only show a sample): in above the axis, out below
      const maxN = Math.max(1, ...mc.flatMap(m => [m.in || 0, m.out || 0]));
      const hy = d3.scaleSqrt().domain([0, maxN]).range([0, (H - mB - mT) / 2 - 10]);
      const g = svg.append('g');
      const usdLine = (n, o) => (o != null ? `<br><span class="valued">${esc(usdText(o))} USD known, ${esc(valuedLabel({ valuation_basis: 'at_each_transfer_time' }))}${n ? `; ${int(n)} unpriced` : ''}</span>` : (n ? `<br><span class="valued">${int(n)} unpriced</span>` : ''));
      mc.forEach(m => {
        const t0 = new Date(m.month + '-01T00:00:00Z');
        const t1 = new Date(Date.UTC(t0.getUTCFullYear(), t0.getUTCMonth() + 1, 1));
        const bx = x(t0), bw = Math.max(1.5, x(t1) - x(t0) - 1);
        if (m.in) g.append('rect').attr('class', 'agg-in').attr('x', bx).attr('width', bw).attr('y', mid - 2 - hy(m.in)).attr('height', hy(m.in));
        if (m.out) g.append('rect').attr('class', 'agg-out').attr('x', bx).attr('width', bw).attr('y', mid + 2).attr('height', hy(m.out));
        const cls = ['class_real', 'class_dust', 'class_poisoning', 'class_unknown'].filter(k => m[k]).map(k => `${int(m[k])} ${k.slice(6) === 'real' ? 'passed filters' : k.slice(6)}`).join(', ');
        g.append('rect').attr('x', bx - 1).attr('width', bw + 2).attr('y', mT).attr('height', H - mB - mT).attr('fill', 'transparent')
          .on('mousemove', ev2 => tip.show(`<b>${esc(d3.timeFormat('%B %Y')(t0))}</b><br>${int(m.in || 0)} transfers in${usdLine(m.unpriced_in, m.priced_in_usd)}<br>${int(m.out || 0)} transfers out${usdLine(m.unpriced_out, m.priced_out_usd)}${cls ? `<br><span class="valued">Classes (in and out): ${esc(cls)}</span>` : ''}`, ev2))
          .on('mouseleave', () => tip.hide());
      });
      svg.append('text').attr('class', 'lane').attr('x', W - mR).attr('y', mT + 2).attr('text-anchor', 'end').text(`up to ${int(maxN)} per month`);
      drawMarks();
      return;
    }
    const rScale = d3.scaleSqrt().domain([0, Math.max(1, d3.max(moves, e => e.usd || 0))]).range([2.6, 9]);
    const placed = [];
    const dots = svg.append('g').selectAll('g').data(moves).join('g');
    dots.each(function (e) {
      const cx = x(new Date(e.time)), r = rScale(e.usd || 0);
      const dir = e.kind === 'in' ? -1 : 1;
      let cy = mid + dir * (r + 3);
      let tries = 0;
      while (tries++ < 14 && placed.some(p => Math.hypot(p.cx - cx, p.cy - cy) < p.r + r + 0.5 && p.dir === dir)) cy += dir * (r + 2);
      cy = Math.max(mT + 14 + r, Math.min(H - mB - 4 - r, cy));
      placed.push({ cx, cy, r, dir });
      const g = d3.select(this);
      g.append('circle').attr('class', 'tx-' + e.kind + (e.class && e.class !== 'real' ? ' faint' : '')).attr('cx', cx).attr('cy', cy).attr('r', r);
      g.append('circle').attr('cx', cx).attr('cy', cy).attr('r', Math.max(r, 9)).attr('fill', 'transparent')
        .on('mousemove', ev2 => tip.show(`<b>${esc(KIND[e.kind] || e.kind)}</b> ${esc(dateOnly(e.time))}<br>${e.amount != null ? esc(fmt({ value: e.amount, unit: 'native:' + (e.asset || '') }).text) + ' ' : ''}${esc(assetName(e.asset))}${e.usd != null ? `<br>${esc(usdText(e.usd))} USD <span class="valued">${esc(valuedLabel(e.valued_at))}</span>` : '<br><span class="valued">no price</span>'}${e.counterparty_label ? `<br><span class="valued">${esc(e.counterparty_label)} (lead)</span>` : ''}`, ev2))
        .on('mouseleave', () => tip.hide());
    });
    drawMarks();
  }

  /* ---------- wiring ---------- */
  document.addEventListener('explorer:search', ev => {
    q.value = ev.detail.q || ''; selChain.value = ''; selProg.value = ''; selStatus.value = 'any'; selSort.value = 'featured'; apply();
  });
  document.addEventListener('explorer:open', ev => {
    const id = ev.detail.id;
    const r = byId.get(id);
    if (!r) return;
    q.value = r.address; selChain.value = ''; selProg.value = ''; selStatus.value = 'any'; selSort.value = 'featured'; apply();
    lastTrigger = null;
    open(id, { scroll: true });
  });

  apply();
  const m = location.hash.match(/^#addr=(.+)$/);
  if (m) { const id = decodeURIComponent(m[1]); if (byId.has(id)) { q.value = byId.get(id).address; apply(); open(id, { scroll: true }); } }
}
