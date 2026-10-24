import { esc, $, int, tip, table, onResize, reveal, onOpen } from './util.js';

/* Bins are definitions, not data.
   After listing: first_outflow_days is days after the listing date for movers whose first outflow can be placed after
   publication. A mover whose first outflow fell on the listing day itself has no such number (OFAC publishes a date, not a
   time), only first_outflow_after_days with an interval that spans zero; those form their own row and are never read as
   "before".
   Before listing: moved_before_designation is the checkpoint flag for any outflow in the seven days before the listing day;
   last_outflow_before_days gives how long before listing the most recent earlier outflow was. */
export const AFTER = [
  { id: 'a1', label: 'Less than a day after', test: d => d < 1 },
  { id: 'a7', label: '1 to 6 days after', test: d => d >= 1 && d < 7 },
  { id: 'a30', label: '7 to 29 days after', test: d => d >= 7 && d < 30 },
  { id: 'a90', label: '30 to 89 days after', test: d => d >= 30 && d < 90 },
  { id: 'a365', label: '90 to 364 days after', test: d => d >= 90 && d < 365 },
  { id: 'a365p', label: 'A year or more after', test: d => d >= 365 },
];
export const BEFORE = [
  { id: 'b30', label: '8 to 29 days before', test: d => d < 30 },
  { id: 'b90', label: '30 to 89 days before', test: d => d >= 30 && d < 90 },
  { id: 'b365', label: '90 to 364 days before', test: d => d >= 90 && d < 365 },
  { id: 'b365p', label: 'A year or more before', test: d => d >= 365 },
];

export function binCounts(rows) {
  const after = AFTER.map(b => ({ ...b, n: 0 }));
  const before = BEFORE.map(b => ({ ...b, n: 0 }));
  const c = { after, before, none: 0, notAssessed: 0, untrack: 0, tracked: 0, listingDay: 0, undated: 0, week: 0, noEarlier: 0 };
  for (const r of rows) {
    if (!r.trackable) { c.untrack++; continue; }
    c.tracked++;
    // after listing
    if (r.moved_after == null) c.notAssessed++;
    else if (!r.moved_after) c.none++;
    else if (r.first_outflow_days != null) {
      const b = after.find(x => x.test(r.first_outflow_days));
      if (b) b.n++; else c.undated++;
    } else if (r.first_outflow_after_days != null) c.listingDay++;
    else c.undated++;
    // before listing
    if (r.moved_before_designation === true) c.week++;
    else if (r.last_outflow_before_days != null) {
      const b = before.find(x => x.test(Math.abs(r.last_outflow_before_days)));
      if (b) b.n++; else c.week++;
    } else c.noEarlier++;
  }
  return c;
}

export function initTiming(D) {
  const host = $('#timing-svg');
  const C = binCounts(D.addresses);
  const movedAfter = C.after.reduce((a, b) => a + b.n, 0) + C.listingDay + C.undated;
  const rows = [
    { head: true, label: 'After listing: when the first outflow happened' },
    ...(C.listingDay ? [{ id: 'day', group: 'after', label: 'On the listing day itself', note: 'OFAC publishes a date, not a time, so these outflows could be just before or just after publication', n: C.listingDay }] : []),
    ...C.after.map(b => ({ id: b.id, group: 'after', label: b.label, n: b.n })),
    ...(C.undated ? [{ id: 'unk', group: 'other', label: 'Moved, date not recorded', n: C.undated }] : []),
    { id: 'none', group: 'none', label: 'No outflow found', n: C.none },
    ...(C.notAssessed ? [{ id: 'na', group: 'other', label: 'History incomplete, not assessed', n: C.notAssessed }] : []),
    { head: true, label: 'Before listing: the most recent earlier outflow' },
    { id: 'week', group: 'before', label: 'In the 7 days before the listing day', n: C.week },
    ...C.before.map(b => ({ id: b.id, group: 'before', label: b.label, n: b.n })),
    { id: 'noearlier', group: 'none', label: 'No earlier outflow found', n: C.noEarlier },
    { head: true, label: 'Not tracked' },
    { id: 'untrack', group: 'untrack', label: 'Untrackable', n: C.untrack },
  ];
  const data = rows.filter(r => !r.head);
  const max = Math.max(1, ...data.map(r => r.n));

  /* Break a heading into lines that fit the chart width (it used to run off the right edge on a phone). */
  function wrapLines(svg, text, cls, maxW) {
    const probe = svg.append('text').attr('class', cls).attr('x', 0).attr('y', -999);
    const lines = [];
    let cur = '';
    for (const w of String(text).split(' ')) {
      const t = (cur ? cur + ' ' : '') + w;
      probe.text(t);
      if (cur && probe.node().getComputedTextLength() > maxW) { lines.push(cur); cur = w; } else cur = t;
    }
    if (cur) lines.push(cur);
    probe.remove();
    return lines;
  }

  function draw() {
    const W = Math.max(280, Math.round(host.clientWidth));
    const narrow = W < 560;
    const mL = narrow ? 8 : 250, rowH = narrow ? 32 : 28, mT = 4;
    const labelBlock = narrow ? 17 : 0, headH = narrow ? 34 : 38;
    host.innerHTML = '';
    const svg = d3.select(host).append('svg').attr('width', W).attr('viewBox', `0 0 ${W} 100`).attr('focusable', 'false');
    const heads = new Map(rows.filter(r => r.head).map(r => [r, wrapLines(svg, r.label, 'thead', W - 6)]));
    const hOf = r => (headH + (heads.get(r).length - 1) * 19);
    const H = mT + rows.reduce((a, r) => a + (r.head ? hOf(r) : rowH + labelBlock), 0) + 8;
    svg.attr('height', H).attr('viewBox', `0 0 ${W} ${H}`);
    const x = d3.scaleLinear().domain([0, max]).range([0, Math.max(40, W - mL - 96)]);
    let y = mT;
    rows.forEach(r => {
      if (r.head) {
        const lines = heads.get(r);
        const t = svg.append('text').attr('class', 'thead').attr('x', 0).attr('y', y + hOf(r) - 12 - (lines.length - 1) * 19);
        lines.forEach((l, i) => t.append('tspan').attr('x', 0).attr('dy', i ? 19 : 0).text(l));
        y += hOf(r);
        return;
      }
      const g = svg.append('g').attr('class', 'trow g-' + r.group).attr('transform', `translate(0,${y})`);
      g.append('text').attr('class', 'tlabel').attr('x', narrow ? mL : mL - 12).attr('y', narrow ? 12 : rowH / 2).attr('dy', narrow ? 0 : '0.32em').attr('text-anchor', narrow ? 'start' : 'end').text(r.label);
      const by = labelBlock + (rowH - 18) / 2 - (narrow ? 2 : 0);
      const w = Math.max(r.n ? 2 : 0, x(r.n));
      g.append('path').attr('class', 'tbar')
        .attr('d', `M${mL},${by} h${Math.max(0, w - 4)} a4,4 0 0 1 4,4 v10 a4,4 0 0 1 -4,4 h${-Math.max(0, w - 4)} z`)
        .style('display', r.n ? null : 'none');
      const pct = C.tracked && r.group !== 'untrack' ? `${r.n && r.n / C.tracked < 0.01 ? '<1' : Math.round((r.n / C.tracked) * 100)}%` : '';
      g.append('text').attr('class', 'tval').attr('x', mL + w + 8).attr('y', by + 9).attr('dy', '0.32em')
        .text(int(r.n)).append('tspan').attr('class', 'tpct').attr('dx', 6).text(pct);
      g.append('rect').attr('x', 0).attr('width', W).attr('y', 0).attr('height', rowH + labelBlock).attr('fill', 'transparent')
        .on('mousemove', ev => tip.show(`<b>${esc(r.label)}</b><br>${int(r.n)} addresses${pct ? ` <span class="valued">${esc(pct)} of ${int(C.tracked)} tracked addresses</span>` : ''}${r.note ? `<br><span class="valued">${esc(r.note)}</span>` : ''}`, ev))
        .on('mouseleave', () => tip.hide());
      y += rowH + labelBlock;
    });
    host.setAttribute('aria-label', `Bar chart of ${int(C.tracked)} tracked addresses. After listing: ${int(movedAfter)} moved funds out, ${int(C.none)} had no outflow found, ${int(C.notAssessed)} were not assessed. Before listing: ${int(C.week)} moved funds out in the seven days before the listing day. ${int(C.untrack)} untrackable addresses are shown apart. A table follows.`);
  }

  $('#timing-table').innerHTML = table(['When', 'Group', { t: 'Addresses', r: 1 }, { t: 'Share of tracked addresses', r: 1 }],
    data.map(r => [esc(r.label), esc({ after: 'After listing', before: 'Before listing', none: 'No outflow', other: 'Not assessed', untrack: 'Not tracked' }[r.group] || ''), int(r.n), r.group === 'untrack' || !C.tracked ? 'n/a' : Math.round((r.n / C.tracked) * 100) + '%']));

  const mr = D.meta?.movement_reconciliation;
  $('#timing-note').innerHTML = `Units are addresses. Shares are of the ${int(C.tracked)} tracked addresses; the ${int(C.untrack)} untrackable addresses stay in the counts but are shown apart. The two groups overlap: an address can have moved funds out before listing and again after. The flag for the seven days before the listing day marks ${esc(int(mr?.checkpoint_pre_week_movers?.value ?? C.week))} addresses, including those under Tornado Cash. A pattern to report, not proof of a leak. \u201cNo outflow found\u201d means none within the data we checked.`;

  // the visible summary: the one fact, then three bars
  const pctOf = n => (C.tracked ? (n && n / C.tracked < 0.01 ? '<1' : Math.round((n / C.tracked) * 100)) + '%' : '');
  const bar = (label, n, cls) => `<li class="${cls}"><span class="hb-n">${esc(label)}</span><span class="hb-v"><b>${int(n)}</b> <span class="valued">${esc(pctOf(n))}</span></span><span class="hb-t"><i style="width:${Math.max(n ? 0.6 : 0, (n / Math.max(1, C.tracked)) * 100).toFixed(2)}%"></i></span></li>`;
  $('#timing-sum').innerHTML = `
    <div class="statpair"><div class="stat"><p class="stat-big num">${esc(pctOf(C.none))}</p><p class="stat-s">of the ${int(C.tracked)} tracked addresses had <b>no outflow found</b> after listing, within the data we checked.</p></div></div>
    <ul class="hbars sumbars">
      ${bar('Moved funds out after listing', movedAfter, 'after')}
      ${bar('No outflow found', C.none, 'none')}
      ${C.notAssessed ? bar('History incomplete, not assessed', C.notAssessed, 'other') : ''}
    </ul>
    <p class="cap">${int(C.week)} addresses (${esc(pctOf(C.week))}) also moved funds out in the seven days before their listing day.</p>`;
  reveal($('#timing-sum'));
  onOpen('#timing-drawer', () => { draw(); onResize(host, draw); reveal(host); });
}
