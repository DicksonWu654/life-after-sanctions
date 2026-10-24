import { esc, $, h, fmt, usdText, valuedLabel, int, tip, table, onResize, programName, chainName, loadScript, reveal, onOpen } from './util.js';

const CLASSES = ['mixer', 'bridge', 'dex', 'cex_deposit', 'other_sanctioned', 'unlabelled', 'still_there', 'frozen'];
const CLASS_NAME = {
  mixer: 'Mixer', bridge: 'Bridge to another chain', dex: 'Decentralized exchange', cex_deposit: 'Exchange-labelled address',
  other_sanctioned: 'Another sanctioned address', unlabelled: 'Other / unclassified', still_there: 'Still in the address', frozen: 'Frozen by an issuer',
};
const classOf = n => (n && n.kind === 'destination_class' ? CLASSES.find(k => n.id === k || n.id.endsWith(':' + k) || n.id.endsWith('_' + k) || n.id.endsWith('/' + k)) : null);
const KIND_LABEL = { program: 'Programs', chain: 'Chains' };
const srcName = n => (n.kind === 'program' ? programName(n.label) : n.kind === 'chain' ? chainName(n.label) : n.label);
const OTHER = '__other__';

export async function initFlow(D) {
  await loadScript('vendor/d3-sankey.min.js');
  const S = D.sankey;
  const host = $('#flow-svg');
  const ctl = $('#flow-ctl');
  const nodesById = new Map(S.nodes.map(n => [n.id, n]));
  const hasIn = new Set(S.links.map(l => l.target));
  const srcKinds = [...new Set(S.nodes.filter(n => !hasIn.has(n.id) && S.links.some(l => l.source === n.id)).map(n => n.kind))];
  let view = srcKinds[0] || null;
  let without = false;
  const val = valuedLabel(S.total_usd || S.valued_at);

  // Exact cohort split from the exporter: links_excluding[cohort] is the whole graph with every edge of that OFAC
  // entity removed, in every program and chain link. Filter by source kind for the chosen view; never add the views.
  const cohort = Object.keys(S.links_excluding || {})[0] || null;
  const cohortUsd = cohort ? (S.total_usd?.value ?? 0) - (S.total_usd_excluding?.[cohort]?.value ?? 0) : 0;

  function viewLinks() {
    const src = without && cohort ? S.links_excluding[cohort] : S.links;
    return src.filter(l => l.value > 0 && (!view || nodesById.get(l.source)?.kind === view)).map(l => ({ ...l }));
  }

  // controls
  ctl.innerHTML = '';
  const mkSeg = (label, items, get, set) => {
    const wrap = h('div', { class: 'ctl' });
    wrap.append(h('span', { class: 'ctl-k' }, label));
    const seg = h('div', { class: 'seg', role: 'group', 'aria-label': label });
    for (const [k, t] of items) {
      const b = h('button', { type: 'button', 'aria-pressed': String(get() === k), 'data-k': String(k) }, t);
      b.addEventListener('click', () => { set(k); for (const x of seg.children) x.setAttribute('aria-pressed', String(x.dataset.k === String(get()))); render(); });
      seg.append(b);
    }
    wrap.append(seg);
    return wrap;
  };
  if (srcKinds.length > 1) ctl.append(mkSeg('Start from', srcKinds.map(k => [k, KIND_LABEL[k] || k]), () => view, k => (view = k)));
  if (cohort) {
    ctl.append(mkSeg('Show', [[false, 'All outflows'], [true, `Without ${cohort}`]], () => without, k => (without = k === true || k === 'true')));
  }
  const share = cohortUsd && S.total_usd?.value ? fmt({ value: cohortUsd / S.total_usd.value, unit: 'share' }).text : null;
  const wnote = cohort && S.unlabelled_share_excluding?.[cohort] ? `Without ${cohort}, ${fmt(S.unlabelled_share_excluding?.[cohort] || {}).text} of what is left went first to Other / unclassified destinations.` : '';

  // legend: destination classes in fixed order
  const legend = $('#flow-legend');
  legend.innerHTML = CLASSES.filter(k => S.nodes.some(n => classOf(n) === k)).map(k =>
    `<span class="lg"><i class="sw${k === 'unlabelled' ? ' grey' : ''}" style="background:var(--c-${k})"></i>${esc(CLASS_NAME[k])}</span>`).join('');

  // merge small sources so the picture reads; the table keeps every row
  function merged(L, total) {
    const bySrc = new Map();
    for (const l of L) bySrc.set(l.source, (bySrc.get(l.source) || 0) + l.value);
    const small = new Set([...bySrc].filter(([, v]) => v / total < 0.005).map(([k]) => k));
    if (small.size < 2) return { L, small: new Set() };
    const acc = new Map();
    const out = [];
    for (const l of L) {
      if (!small.has(l.source)) { out.push(l); continue; }
      const k = l.target;
      acc.set(k, (acc.get(k) || 0) + l.value);
    }
    for (const [target, value] of acc) out.push({ source: OTHER, target, value });
    return { L: out, small };
  }

  function draw() {
    const W = Math.max(280, Math.round(host.clientWidth));
    const narrow = W < 640;
    const L0 = viewLinks();
    const total = L0.reduce((a, l) => a + l.value, 0);
    // drop destinations too thin to draw; they are listed in the panel below
    const thin = new Set();
    const byDest = new Map();
    for (const l of L0) byDest.set(l.target, (byDest.get(l.target) || 0) + l.value);
    for (const [t, v] of byDest) if (v / total < 0.004) thin.add(t);
    const { L: Lm, small } = merged(L0.filter(l => !thin.has(l.target)), total);
    const kind = view || 'program';
    const used = new Set(Lm.flatMap(l => [l.source, l.target]));
    const nodes = [...used].map(id => id === OTHER
      ? { id, label: `${int(small.size)} smaller ${(KIND_LABEL[kind] || 'sources').toLowerCase()}`, kind, merged: true }
      : { ...nodesById.get(id) });
    const links = Lm.map(l => ({ ...l }));
    const mL = narrow ? 2 : 190, mR = narrow ? 2 : 230, mT = 16, mB = 6;
    const nSrc = nodes.filter(n => n.kind !== 'destination_class').length;
    const H = narrow ? Math.max(380, nSrc * 74) : Math.max(340, nSrc * 62);
    const sk = d3.sankey().nodeId(d => d.id).nodeWidth(narrow ? 10 : 14).nodePadding(narrow ? 16 : 14)
      .nodeSort((a, b) => {
        const ra = a.kind === 'destination_class' ? CLASSES.indexOf(classOf(a)) : -1;
        const rb = b.kind === 'destination_class' ? CLASSES.indexOf(classOf(b)) : -1;
        return (ra - rb) || ((a.merged ? -1 : 0) - (b.merged ? -1 : 0)) || (b.value - a.value);
      })
      .extent([[mL, mT], [W - mR, H - mB]]);
    const g = sk({ nodes, links });

    host.innerHTML = '';
    const svg = d3.select(host).append('svg').attr('width', W).attr('height', H).attr('viewBox', `0 0 ${W} ${H}`).attr('focusable', 'false');
    const linkSel = svg.append('g').attr('fill', 'none').selectAll('path').data(g.links).join('path')
      .attr('class', d => 'slink' + (classOf(d.target) === 'unlabelled' ? ' grey' : ''))
      .attr('d', d3.sankeyLinkHorizontal())
      .attr('stroke-width', d => Math.max(1, d.width))
      .style('stroke', d => { const c = classOf(d.target); return c ? `var(--c-${c})` : 'var(--ink-3)'; });
    const label = d => (d.kind === 'destination_class' ? CLASS_NAME[classOf(d)] || d.label : d.merged ? d.label : srcName(d));
    const nodeSel = svg.append('g').selectAll('g').data(g.nodes).join('g').attr('class', 'snode')
      .attr('tabindex', 0).attr('role', 'img')
      .attr('aria-label', d => `${label(d)}: ${usdText(d.value)} ${val}`);
    nodeSel.append('rect').attr('x', d => d.x0).attr('y', d => d.y0).attr('width', d => d.x1 - d.x0).attr('height', d => Math.max(1, d.y1 - d.y0))
      .style('fill', d => { const c = classOf(d); return c ? `var(--c-${c})` : 'var(--ink-2)'; });
    const isDest = d => d.kind === 'destination_class';
    const wrap = (t, n) => { const out = []; let cur = ''; for (const w of String(t).split(' ')) { if ((cur + ' ' + w).trim().length > n && cur) { out.push(cur); cur = w; } else cur = (cur + ' ' + w).trim(); } if (cur) out.push(cur); return out; };
    const LH = narrow ? 14 : 16, maxChars = narrow ? 22 : 26;
    const pct = v => { const p = (v / total) * 100; return p < 1 ? '<1%' : p >= 99 && p < 100 ? p.toFixed(1) + '%' : Math.round(p) + '%'; };
    nodeSel.each(function (d) {
      const lines = wrap(label(d), maxChars);
      if (classOf(d) === 'unlabelled' && !narrow) lines.push('includes other DeFi', 'and unknown roles');
      const valLine = usdText(d.value) + ` · ${pct(d.value)}`;
      const x = isDest(d) ? (narrow ? d.x0 - 6 : d.x1 + 10) : (narrow ? d.x1 + 6 : d.x0 - 10);
      const anchor = isDest(d) ? (narrow ? 'end' : 'start') : (narrow ? 'start' : 'end');
      const n = lines.length + 1;
      const t = d3.select(this).append('text').attr('class', narrow ? 'slabel halo' : 'slabel').attr('text-anchor', anchor)
        .attr('x', x).attr('y', (d.y0 + d.y1) / 2 - ((n - 1) * LH) / 2 + LH * 0.32);
      lines.forEach((l, i) => t.append('tspan').attr('class', i < wrap(label(d), maxChars).length ? 'sl-name' : 'sl-note').attr('x', x).attr('dy', i ? LH : 0).text(l));
      t.append('tspan').attr('class', 'sl-val').attr('x', x).attr('dy', LH).text(valLine);
    });

    const related = (d, node) => (node ? d.source === node || d.target === node : false);
    function hi(node, link) {
      linkSel.classed('on', d => (link ? d === link : related(d, node))).classed('off', d => (link ? d !== link : !related(d, node)));
      nodeSel.classed('off', n => node ? !(n === node || g.links.some(l => related(l, node) && (l.source === n || l.target === n))) : (link ? !(n === link.source || n === link.target) : false));
    }
    function clear() { linkSel.classed('on off', false); nodeSel.classed('off', false); }
    linkSel.on('mousemove', (ev, d) => {
      hi(null, d);
      tip.show(`<b>${esc(label(d.source))}</b> to <b>${esc(label(d.target))}</b><br>${esc(usdText(d.value))} <span class="valued">${esc(val)}</span><br><span class="valued">${Math.round((d.value / d.source.value) * 100)}% of ${esc(label(d.source))}</span>`, ev);
    }).on('mouseleave', () => { clear(); tip.hide(); });
    nodeSel.on('mousemove', (ev, d) => {
      hi(d);
      tip.show(`<b>${esc(label(d))}</b><br>${esc(usdText(d.value))} <span class="valued">${esc(val)}</span>${d.merged ? `<br><span class="valued">${[...small].map(id => esc(srcName(nodesById.get(id)))).join(', ')}</span>` : ''}`, ev);
    }).on('mouseleave', () => { clear(); tip.hide(); })
      .on('focus', (ev, d) => { hi(d); tip.show(`<b>${esc(label(d))}</b><br>${esc(usdText(d.value))} <span class="valued">${esc(val)}</span>`, { target: ev.target }); })
      .on('blur', () => { clear(); tip.hide(); });

    const srcList = g.nodes.filter(n => !isDest(n));
    host.setAttribute('aria-label', `Flow diagram. ${int(srcList.length)} ${(KIND_LABEL[kind] || 'sources').toLowerCase()} on the left, ${int(g.nodes.length - srcList.length)} destination types on the right. Total ${usdText(total)}, ${val}. A table follows.`);
    $('#flow-note').innerHTML = `Total in this view: <b>${esc(usdText(total))}</b> <span class="valued">${esc(val)}</span>.${without && cohort ? ` With ${esc(cohort)} left out, ${esc(usdText(cohortUsd))} is left out of the ${esc(kind === 'chain' ? 'chains' : 'programs')} it came from. ${esc(wnote)}` : ''} Programs and chains are two views of the same dollars, so adding them would count each dollar twice. ${esc(S.hop_rule ? 'How a destination is picked: ' + S.hop_rule.split('. ').slice(0, 2).join('. ') + '.' : '')}`;
  }

  /* The honest summary, built once from the whole of the exporter's graph (all outflows, first view): two plain numbers and the
     split by destination. It does not change with the controls inside the drawer. */
  function renderSummary() {
    const L = S.links.filter(l => l.value > 0 && (!srcKinds[0] || nodesById.get(l.source)?.kind === srcKinds[0]));
    const total = L.reduce((a, l) => a + l.value, 0) || 1;
    const by = Object.fromEntries(CLASSES.map(k => [k, 0]));
    for (const l of L) { const c = classOf(nodesById.get(l.target)); if (c) by[c] += l.value; }
    const known = CLASSES.filter(k => k !== 'unlabelled' && S.nodes.some(n => classOf(n) === k));
    const labelled = known.reduce((a, k) => a + by[k], 0);
    const pctText = v => { const p = (v / total) * 100; return p === 0 ? '0%' : p < 0.01 ? '<0.01%' : p < 1 ? p.toFixed(2) + '%' : p.toFixed(1) + '%'; };
    const unl = S.unlabelled_share?.value != null ? S.unlabelled_share.value : by.unlabelled / total;
    const stats = [`<div class="stat"><p class="stat-big num">${esc(pctText(unl * total))}</p><p class="stat-s">of measured priced gross first-hop outflow value went to Other / unclassified destinations. Original unknown-role share: <b>${S.original_unlabelled_share ? (S.original_unlabelled_share.value * 100).toFixed(2) + '%' : 'see the finding card'}</b>.</p></div>`];
    if (cohort && share) stats.push(`<div class="stat"><p class="stat-big num">${esc(share)}</p><p class="stat-s">of it came from one name, <b>${esc(cohort)}</b>, whose outflows coincide with a DOJ forfeiture and government custody.</p></div>`);
    $('#flow-stats').innerHTML = stats.join('') + `<p class="valued stat-note">Dollar figures: ${esc(val)}.</p>`;
    $('#flow-panel').innerHTML = `
      <div class="fp-head"><h4>Where it landed first</h4></div>
      <ul class="fp-list">${[...known, 'unlabelled'].map(k => `<li class="${k === 'unlabelled' ? 'unl' : ''}"><span class="fp-n"><i class="sw${k === 'unlabelled' ? ' grey' : ''}" style="background:var(--c-${k})"></i>${esc(CLASS_NAME[k])}</span>
          <span class="fp-v"><b>${esc(usdText(by[k]))}</b> <span class="valued">${esc(pctText(by[k]))}</span></span>
          <span class="fp-t"><i style="width:${Math.max(by[k] > 0 ? 0.6 : 0, (by[k] / total) * 100).toFixed(2)}%;background:var(--c-${k})"></i></span></li>`).join('')}</ul>
      <p class="cap"><b>Other / unclassified</b> combines unknown roles and other DeFi protocols. <b>Exchange-labelled address</b> combines deposit and hot-wallet roles. ${S.original_classes ? S.original_classes.filter(x => ['defi_other', 'cex_hot', 'cex_deposit'].includes(x.class)).map(x => `${esc(({defi_other: 'Other DeFi protocol', cex_hot: 'Exchange hot wallet', cex_deposit: 'Exchange deposit address'})[x.class])}: $${x.usd.value.toFixed(6)}`).join('; ') + '.' : ''} Gross first-hop transfers are valued at each transfer time; repeated funds can appear more than once.</p>`;
    reveal($('#flow-panel'));
  }

  function renderTable() {
    const L = viewLinks();
    const srcs = [...new Set(L.map(l => l.source))].map(id => nodesById.get(id)).filter(n => n.kind !== 'destination_class');
    const dests = CLASSES.filter(k => L.some(l => classOf(nodesById.get(l.target)) === k));
    const cell = (s, k) => { const v = L.filter(l => l.source === s.id && classOf(nodesById.get(l.target)) === k).reduce((a, l) => a + l.value, 0); return v ? esc(usdText(v)) : '&ndash;'; };
    const headers = [`Start (${val})`, ...dests.map(k => ({ t: CLASS_NAME[k], r: 1 }))];
    $('#flow-table').innerHTML = table(headers, srcs.sort((a, b) => L.filter(l => l.source === b.id).reduce((x, l) => x + l.value, 0) - L.filter(l => l.source === a.id).reduce((x, l) => x + l.value, 0)).map(s => [esc(srcName(s)), ...dests.map(k => cell(s, k))]));
  }

  function render() { draw(); renderTable(); }
  renderSummary();
  // the diagram itself lives in a closed drawer; it is drawn the first time the drawer opens, then follows the width
  onOpen('#flow-drawer', () => { render(); onResize(host, draw); reveal(host); });
}
