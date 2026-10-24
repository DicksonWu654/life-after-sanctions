import { esc, h, $, fmt, compact, daysPhrase, dayDiff, dateOnly, chainName, int, programName, words } from './util.js';
import { frozenSpotlight, tornadoSpotlight } from './spotlight.js';
import { eventRows } from './events.js';
import { findCase, caseFreezes } from './derive.js';

export function searchExplorer(q) {
  document.dispatchEvent(new CustomEvent('explorer:search', { detail: { q } }));
  document.getElementById('explorer').scrollIntoView({ behavior: matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth' });
}

function station(cls, title, date, note, extra = '') {
  return `<li class="${cls}"><span class="dot" aria-hidden="true"></span><b>${esc(title)}</b><span class="when">${date ? esc(dateOnly(date)) : '&nbsp;'}</span><span class="delta">${note}</span>${extra}</li>`;
}

/** Cases without a curated first-outflow event still say what the address index knows about movement after listing. */
function movedStation(c, addrById) {
  const rows = (c.addresses || []).map(id => addrById.get(id)).filter(Boolean);
  const assessed = rows.filter(r => r.moved_after != null);
  if (!assessed.length) return { st: station('off', 'First move', '', 'not assessed'), short: 'not assessed', on: false };
  const moved = assessed.filter(r => r.moved_after === true).length;
  if (!moved) return { st: station('off', 'First move', '', 'none found'), short: 'none found', on: false };
  const days = rows.map(r => r.first_outflow_days).filter(d => d != null);
  const first = days.length ? Math.min(...days) : null;
  return { st: station('on', 'First move', '', `${int(moved)} of ${int(assessed.length)} moved${first != null ? `, first ${esc(daysPhrase(Math.round(first)))}` : ''}`), short: `${int(moved)} of ${int(assessed.length)} moved`, on: true };
}

/** One row of the scoreboard: name, listed, first move, blacklisted, today. Opens to the case timeline. */
function row(c, addrById) {
  const ev = [...(c.events || [])].sort((a, b) => a.date.localeCompare(b.date));
  const first = k => ev.find(e => (Array.isArray(k) ? k.includes(e.kind) : e.kind === k));
  const out = first('first_outflow'), frz = first(['freeze', 'burn']);
  const todayAmt = c.today?.balance_usd;
  const mv = out ? { st: station('on', 'First move', out.date, esc(daysPhrase(dayDiff(out.date, c.designated)))), short: daysPhrase(dayDiff(out.date, c.designated)), on: true } : movedStation(c, addrById);
  let stFrz, frzShort, frzEarly = false;
  if (frz) {
    const dd = dayDiff(frz.date, c.designated);
    frzEarly = dd < 0;
    stFrz = station('on' + (dd < 0 ? ' early' : ''), frz.kind === 'burn' ? 'Burned' : 'Blacklisted', frz.date, esc(daysPhrase(dd)));
    frzShort = daysPhrase(dd);
  } else { stFrz = station('off', 'Blacklisted', '', 'none found'); frzShort = 'none found'; }
  const f = todayAmt ? fmt(todayAmt) : null;
  const stToday = station('on now', 'Today', '', f ? esc(f.text) : '', f ? `<span class="valued" title="${esc(f.valuedFull || '')}">${esc(f.valued)}</span>` : '');
  const prog = programName(String(c.program || '').split(/[;(]/)[0].trim());
  const nAddr = (c.addresses || []).length;
  const d = h('details', { class: 'srow', id: `case-${c.id}` });
  d.innerHTML = `
    <summary>
      <span class="s-name"><b>${esc(c.name)}</b><span class="s-prog" title="${esc(c.program)}">${esc(prog)}</span></span>
      <span class="s-c"><span class="lbl">Listed</span><span class="s-v"><time>${esc(c.designated)}</time></span></span>
      <span class="s-c"><span class="lbl">First move</span><span class="s-v${mv.on ? '' : ' none'}">${esc(mv.short)}</span></span>
      <span class="s-c"><span class="lbl">Blacklisted</span><span class="s-v${frz ? (frzEarly ? ' early' : '') : ' none'}">${esc(frzShort)}</span></span>
      <span class="s-c"><span class="lbl">Today</span><span class="s-v">${f ? esc(f.text) : 'n/a'}</span></span>
    </summary>
    <div class="s-body">
      <p class="case-meta">Listed <time>${esc(c.designated)}</time> &middot; ${(c.chains || []).map(x => esc(chainName(x))).join(', ')} &middot; ${int(nAddr)} ${nAddr === 1 ? 'address' : 'addresses'}</p>
      <p class="case-one">${esc(c.one_liner)}</p>
      <ol class="track" aria-label="Timeline">${station('on', 'Listed', c.designated, 'day 0')}${mv.st}${stFrz}${stToday}</ol>
      <p class="cap">${esc(words(c.today?.status_sentence || ''))}${c.today?.covers ? ` Covers ${esc(c.today.covers)}.` : ''}</p>
      <details class="subdrawer case-more"><summary>All ${int(ev.length)} ${ev.length === 1 ? 'event' : 'events'}</summary><ol class="evlist">${eventRows(ev)}</ol></details>
      <p class="case-links">
        ${c.press_release_url ? `<a href="${esc(c.press_release_url)}" rel="noopener noreferrer">Treasury press release</a>` : ''}
        <button type="button" class="linkbtn" data-q="${esc(c.name)}">See its ${int(nAddr)} ${nAddr === 1 ? 'address' : 'addresses'} in the explorer</button>
      </p>
    </div>`;
  return { el: d, todayValued: f?.valued || '' };
}

export function initCases(D) {
  const spots = $('#spots');
  const grid = $('#cases-grid');
  spots.innerHTML = '';
  grid.innerHTML = '';
  const addrById = new Map((D.addresses || []).map(a => [a.id, a]));
  const s1 = frozenSpotlight(D);
  const s2 = tornadoSpotlight(D);
  [s1, s2].filter(Boolean).forEach(s => spots.append(s));
  $('#cases').addEventListener('click', ev => {
    const q = ev.target.closest('[data-q]'); if (q) searchExplorer(q.dataset.q);
    const o = ev.target.closest('[data-open]'); if (o) document.dispatchEvent(new CustomEvent('explorer:open', { detail: { id: o.dataset.open } }));
  });
  const tc = findCase(D, 'tornado-cash', /tornado/i);
  const bm = findCase(D, 'bank-markazi-iran', /markazi/i);
  const rest = (D.cases || []).filter(c => !(s2 && c === tc) && !(s1 && c === bm));
  const rows = rest.map(c => row(c, addrById));
  if (rows.length) {
    grid.insertAdjacentHTML('beforeend', '<div class="score-head" aria-hidden="true"><span>Listing</span><span>Listed</span><span>First move</span><span>Blacklisted</span><span>Today</span></div>');
    rows.forEach(r => grid.append(r.el));
    const labels = [...new Set(rows.map(r => r.todayValued).filter(Boolean))];
    $('#score-note').textContent = `Dollar figures in \u201cToday\u201d are ${labels.length === 1 ? labels[0] : 'USD at each address\u2019s latest saved balance'}. \u201cFirst move\u201d and \u201cBlacklisted\u201d count from the listing day (day 0). Open a row for its full timeline.`;
  }
  const mh = $('#cases-more-h'); if (rest.length) mh.removeAttribute('data-pending'); else mh.hidden = true;

  // one number and one plain sentence under the heading
  if (s1) {
    const Z = caseFreezes(bm);
    const unit = Z.rows.find(r => r.nativeUnit)?.nativeUnit || 'USDT';
    const dl = H(D, 'tornado_delisting'), ds = H(D, 'tornado_designation');
    const tn = (t, w) => (t ? `${t.big.value < 0 ? 'fell' : 'rose'} ${fmt({ value: Math.abs(t.big.value), unit: 'share' }).text} ${w}` : '');
    const tpart = ds || dl ? ` Tornado Cash deposits ${[tn(ds, 'around its designation'), tn(dl, 'after delisting')].filter(Boolean).join(', then ')}.` : '';
    $('#cases-open').textContent = `Tether froze ${compact(Z.native)} ${unit} across ${int(Z.rows.length)} addresses OFAC lists for Iran\u2019s central bank.${tpart}`;
  }
}

const H = (D, id) => (D.headline || []).find(f => f.id === id);
