import { esc, $, fmt, usdText, lagText, lagPhrase, chainName, int, tip, table, onResize, reveal } from './util.js';
import { freezeStats } from './derive.js';

export const ISSUER = { tether: 'Tether', circle: 'Circle' };
const TICKS = [-26280, -8760, -2160, -720, -168, -24, -6, -1, 0, 1, 6, 24, 168, 720, 2160, 8760, 26280];
const TICK_LABEL = h => { if (h === 0) return '0'; const a = Math.abs(h); const s = a < 24 ? `${a} h` : a < 720 ? `${a / 24} d` : a < 8760 ? `${Math.round(a / 720)} mo` : `${a / 8760} yr`; return (h < 0 ? '−' : '+') + s; };
const medLabel = m => (m < 0 ? '\u2212' : '+') + lagText(m).text;
const sign = m => (m < 0 ? 'before' : 'after');

const SERIES = {
  'tether|trx': { color: 'var(--tether)', dash: null, tag: { y: 0.64, dx: -14, dy: 4, anchor: 'end' } },
  'circle|eth': { color: 'var(--circle)', dash: null, tag: { y: 0.3, dx: 12, dy: 16, anchor: 'start' } },
  'tether|eth': { color: 'var(--tether)', dash: '5 4', tag: { y: 0.5, dx: -12, dy: 4, anchor: 'end' } },
};

/** Cumulative curves of signed freeze lag: how many of the listed addresses were frozen by each moment.
    Zero is the noon ET proxy; only events outside the listing day establish publication order. Three zones:
    before the listing day began, the listing day itself (order unknown), after. `rows` are freezeStats entries. */
export function drawCurves(host, rows, opts = {}) {
  const compact = !!opts.compact;
  const W = Math.max(280, Math.round(host.clientWidth));
  const narrow = W < 560;
  const mL = narrow ? 38 : 46, mR = narrow ? 12 : 22, mT = 56, mB = 32;
  const H = opts.height || (compact ? (narrow ? 250 : 340) : (narrow ? 300 : 400));
  const pts = rows.flatMap(r => r.points);
  const lo = Math.min(0, d3.min(pts, p => p.lag_hours) ?? 0), hi = Math.max(0, d3.max(pts, p => p.lag_hours) ?? 0);
  const x = d3.scaleSymlog().constant(6).domain([lo, hi]).range([mL, W - mR]).nice();
  const y = d3.scaleLinear().domain([0, 1]).range([H - mB, mT]);
  const [d0, d1] = x.domain();
  const half = rows[0]?.half ?? 12;
  const kept = [];
  for (const t of TICKS.filter(t => t >= d0 && t <= d1).sort((a, b) => Math.abs(a) - Math.abs(b))) {
    if (kept.every(k => Math.abs(x(k) - x(t)) >= (narrow ? 44 : 56))) kept.push(t);
  }
  const ticks = kept.sort((a, b) => a - b);

  host.innerHTML = '';
  const svg = d3.select(host).append('svg').attr('width', W).attr('height', H).attr('viewBox', `0 0 ${W} ${H}`).attr('focusable', 'false');
  const zx = x(0), zl = x(-half), zr = x(half), zTop = mT - 6, zH = H - mB - zTop;
  const zones = svg.append('g').attr('class', 'fzones');
  zones.append('rect').attr('class', 'z-before').attr('x', mL).attr('y', zTop).attr('width', Math.max(0, zl - mL)).attr('height', zH);
  zones.append('rect').attr('class', 'z-day').attr('x', zl).attr('y', zTop).attr('width', Math.max(2, zr - zl)).attr('height', zH);
  const grid = svg.append('g').attr('class', 'fgrid');
  grid.selectAll('line.gx').data(ticks.filter(t => t !== 0)).join('line').attr('class', 'gx').attr('x1', x).attr('x2', x).attr('y1', zTop).attr('y2', H - mB);
  grid.selectAll('line.gy').data([0, 0.25, 0.5, 0.75, 1]).join('line').attr('class', 'gy').attr('x1', mL).attr('x2', W - mR).attr('y1', y).attr('y2', y);
  grid.selectAll('text.tx').data(ticks).join('text').attr('class', 'tx').attr('x', x).attr('y', H - 12).attr('text-anchor', 'middle').text(TICK_LABEL);
  grid.selectAll('text.ty').data([0, 0.25, 0.5, 0.75, 1]).join('text').attr('class', 'ty').attr('x', mL - 6).attr('y', d => y(d) + 4).attr('text-anchor', 'end').text(d => Math.round(d * 100) + '%');
  svg.append('line').attr('class', 'fzero-line').attr('x1', zx).attr('x2', zx).attr('y1', zTop - 2).attr('y2', H - mB);
  // annotations
  const ann = svg.append('g').attr('class', 'fann');
  ann.append('text').attr('class', 'fside early').attr('x', Math.max(mL + 2, zx - 10)).attr('y', 14).attr('text-anchor', 'end').text(narrow ? '← Before day' : '← Before listing day');
  ann.append('text').attr('class', 'fside').attr('x', Math.min(W - mR, zx + 10)).attr('y', 14).attr('text-anchor', 'start').text(narrow ? 'After day →' : 'After listing day →');
  const flagW = 132, fx = Math.min(Math.max(zx, mL + flagW / 2), W - mR - flagW / 2);
  ann.append('rect').attr('class', 'fflag').attr('x', fx - flagW / 2).attr('y', 22).attr('width', flagW).attr('height', 22).attr('rx', 3);
  ann.append('text').attr('class', 'fflag-t').attr('x', fx).attr('y', 37.5).attr('text-anchor', 'middle').text('Noon ET (proxy)');
  if (zl - mL > 90) ann.append('text').attr('class', 'fzone-t').attr('x', mL + 8).attr('y', zTop + 14).text(narrow ? 'Before the day' : 'Before the listing day began');

  // curves
  const curves = rows.map(rw => {
    const N = Math.max(rw.listed ?? 0, rw.points.length) || 1;
    const lags = rw.points.map(p => p.lag_hours).sort((a, b) => a - b);
    const path = [[d0, 0]];
    lags.forEach((l, i) => path.push([l, (i + 1) / N]));
    path.push([d1, lags.length / N]);
    const at = t => { let c = 0; for (const l of lags) { if (l <= t) c++; else break; } return c; };
    return { rw, N, lags, path, at, spec: SERIES[`${rw.issuer}|${rw.chain}`] || { color: 'var(--ink-2)', dash: null, tag: { y: 0.5, dx: 10, dy: 0, anchor: 'start' } } };
  });
  const line = d3.line().x(d => x(d[0])).y(d => y(d[1])).curve(d3.curveStepAfter);
  const g = svg.append('g').attr('class', 'fcurves');
  const gTags = svg.append('g').attr('class', 'ftags');
  for (const c of curves) g.append('path').attr('class', 'fcurve').attr('d', line(c.path)).style('stroke', c.spec.color).style('stroke-dasharray', c.spec.dash);
  // median dots and labels
  for (const c of curves) {
    if (c.rw.median == null) continue;
    const mx = x(c.rw.median), my = y(c.at(c.rw.median) / c.N);
    g.append('circle').attr('class', 'fmed-dot').attr('cx', mx).attr('cy', my).attr('r', 4.5).style('stroke', c.spec.color);
  }
  // direct tags with the name and the count
  for (const c of curves) {
    const tgt = c.spec.tag;
    const i = c.lags.findIndex((_, k) => (k + 1) / c.N >= tgt.y);
    if (i < 0) continue;
    const tx = x(c.lags[i]) + tgt.dx, ty = y(tgt.y) + tgt.dy;
    const name = `${ISSUER[c.rw.issuer]}, ${chainName(c.rw.chain)}`;
    const t = gTags.append('text').attr('class', 'ftag').attr('x', tx).attr('y', ty).attr('text-anchor', tgt.anchor).style('fill', c.spec.color);
    t.append('tspan').attr('x', tx).text(name);
    if (c.rw.median != null) t.append('tspan').attr('class', 'ftag-s').attr('x', tx).attr('dy', 14).text(`median ${medLabel(c.rw.median)}`);
  }
  // before-the-day callouts on the first group
  // hover crosshair
  const cross = svg.append('line').attr('class', 'fcross').attr('y1', zTop).attr('y2', H - mB).style('display', 'none');
  const dots = curves.map(c => svg.append('circle').attr('class', 'fhover').attr('r', 4).style('fill', c.spec.color).style('display', 'none'));
  svg.append('rect').attr('class', 'fhit').attr('x', mL).attr('y', zTop).attr('width', W - mL - mR).attr('height', zH)
    .on('mousemove touchmove', ev => {
      const [mx] = d3.pointer(ev, svg.node());
      const t = x.invert(Math.max(mL, Math.min(W - mR, mx)));
      cross.attr('x1', mx).attr('x2', mx).style('display', null);
      const lines = curves.map((c, k) => {
        const n = c.at(t);
        dots[k].attr('cx', mx).attr('cy', y(n / c.N)).style('display', null);
        return `<span class="tsw" style="background:${c.spec.color}"></span>${esc(ISSUER[c.rw.issuer])}, ${esc(chainName(c.rw.chain))}: <b>${int(n)}</b> of ${int(c.N)} ever blacklisted (${Math.round((n / c.N) * 100)}%)`;
      });
      tip.show(`<b>By ${esc(Math.abs(t) < 1 ? 'Noon ET (proxy)' : lagText(t).text + ' ' + (t < 0 ? 'before' : 'after') + ' the noon ET proxy')}</b><br>${lines.join('<br>')}<br><span class="valued">Publication hour unknown within listing day (±12 h from proxy).</span>`, ev);
    }).on('mouseleave', () => { tip.hide(); cross.style('display', 'none'); dots.forEach(d => d.style('display', 'none')); });
  host.setAttribute('aria-label', `Cumulative chart of how many listed addresses were frozen by each moment, relative to the noon ET proxy at zero; publication hour unknown. ${rows.map(r => `${ISSUER[r.issuer]} on ${chainName(r.chain)}: ${int(r.frozen)}${r.listed ? ` of ${int(r.listed)}` : ''} addresses ever blacklisted, ${r.beforeDay != null ? int(r.beforeDay) : 'an unknown number'} before the listing day began, median ${r.median != null ? lagPhrase(r.median) : 'unknown'}.`).join(' ')} A table follows.`);
}

export function freezeLegend(el, rows = []) {
  const sw = (c, dash) => `<svg width="26" height="10" viewBox="0 0 26 10" aria-hidden="true"><line x1="0" y1="5" x2="26" y2="5" stroke="${c}" stroke-width="2.6" ${dash ? `stroke-dasharray="${dash}"` : ''}/></svg>`;
  const items = (rows.length ? rows : [{ issuer: 'tether', chain: 'trx' }, { issuer: 'circle', chain: 'eth' }]).map(r => {
    const sp = SERIES[`${r.issuer}|${r.chain}`] || {};
    return `<span class="lg">${sw(sp.color || 'var(--ink-2)', sp.dash)}${esc(ISSUER[r.issuer])} on ${esc(chainName(r.chain))}</span>`;
  });
  el.innerHTML = items.join('') +
    `<span class="lg"><i class="sw zone zb"></i>Frozen before the listing day began</span>` +
    `<span class="lg"><i class="sw zone zd"></i>Listing day (exact hour unknown)</span>`;
}

/** The line under the heading: one number, from the exporter's summary rows. */
export function freezeIntro(D) {
  const ci = [...freezeStats(D.freezes).values()].find(r => r.issuer === 'circle' && r.chain === 'eth');
  if (ci && ci.listed != null) $('#freeze-open').innerHTML = `Circle ever blacklisted <b>${esc(int(ci.frozen))} of ${esc(int(ci.listed))}</b> historical ${esc(chainName(ci.chain))} identifiers for USDC; ${ci.current != null ? `${int(ci.current)} still blacklisted, ${int(ci.unblacklisted)} later unblacklisted. ` : ''}The 217th string is malformed. Tether on Tron is the chart at the top of this page. Open the full version to add Tether on Ethereum and the table behind every line.`;
}

export function initFreeze(D) {
  const F = D.freezes;
  const host = $('#freeze-svg');
  const stats = freezeStats(F);
  const rows = [...stats.values()].sort((a, b) => (a.issuer === b.issuer ? b.points.length - a.points.length : a.issuer < b.issuer ? 1 : -1));
  freezeLegend($('#freeze-legend'), rows);

  const T = $('#freeze-table');
  const addr = n => `${int(n)} <span class="unit">${n === 1 ? 'address' : 'addresses'}</span>`;
  const medCell = s => {
    if (s.median == null) return 'n/a';
    const rng = s.medLo != null && s.medHi != null ? `<span class="valued">range ${esc(lagPhrase(s.medLo).replace(' the announcement', ''))} to ${esc(lagPhrase(s.medHi).replace(' the announcement', ''))}</span>` : '';
    return `${esc(lagPhrase(s.median).replace(' the announcement', ''))}${rng ? `<br>${rng}` : ''}`;
  };
  T.innerHTML = '<h4 class="tbl-h">Summary table</h4>' + table(
    ['Issuer', 'Chain', { t: 'OFAC-listed on chain', r: 1 }, { t: 'Ever blacklisted', r: 1 }, { t: 'Still blacklisted', r: 1 }, { t: 'Before the listing day', r: 1 }, { t: 'Median lag from noon proxy', r: 1 }, { t: '90th percentile', r: 1 }, { t: 'Blacklisted, observed token holders', r: 1 }, { t: 'Known balance when blacklisted', r: 1 }],
    rows.map(s => [esc(ISSUER[s.issuer] || s.issuer), esc(chainName(s.chain)),
      s.listed != null ? addr(s.listed) : 'n/a',
      `${addr(s.frozen)}${s.share != null ? ` <span class="valued">${esc(fmt({ value: s.share, unit: 'share' }).text)}</span>` : ''}`,
      s.current != null ? addr(s.current) : 'n/a',
      s.beforeDay != null ? addr(s.beforeDay) : 'n/a',
      medCell(s),
      s.p90 != null ? esc(lagPhrase(s.p90).replace(' the announcement', '')) : 'n/a',
      s.holders != null ? `${int(s.holdersFrozen ?? 0)} of ${int(s.holders)} <span class="unit">addresses</span>` : 'n/a',
      s.usd ? `${esc(usdText(s.usd.value))}` : 'n/a']), 'stack'
  ) + '<p class="cap">Lag is first blacklisting time minus the noon ET proxy on the address-listing date. Negative means before that proxy. Publication order is known only outside the listing day. The range gives the median if OFAC published at the very start or the very end of that date. \u201cBefore the listing day\u201d counts blacklistings earlier than 00:00 New York time on the listing date, so they are earlier whatever the true minute was. Tether\u2019s Ethereum row is dominated by a batch added long after the Tornado Cash listing, so its median measures that delay, not a response time. The balance column is USD at each address\u2019s first blacklisting and adds only the amounts we could read, so it is a floor.</p>';

  if (F.network_sensitivity?.length) T.insertAdjacentHTML('beforeend', '<p class="cap">ETH includes four Ethereum-convention assignments from stablecoin-only identifiers and one malformed historical string. Excluding the four inferred assignments: ' + F.network_sensitivity.map(s => `${ISSUER[s.issuer]}: ${s.listed} strings, ${s.ever} ever, ${s.current} still blacklisted; median lag from noon proxy ${s.median_hours.toFixed(2)} h (publication-time range ${s.median_lower_hours.toFixed(2)} to ${s.median_upper_hours.toFixed(2)} h)`).join('; ') + '.</p>');
  const draw = () => drawCurves(host, rows);
  draw();
  onResize(host, draw);
  reveal(host);
}
