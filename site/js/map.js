import { esc, $, h, fmt, usdText, valuedLabel, valuedFull, int, tip, loadScript, programName, programWithCode, reveal } from './util.js';

const W = 960;
let topo, iso;

async function vendorJSON(path) {
  const r = await fetch(path);
  if (!r.ok) throw new Error(`${path}: HTTP ${r.status}`);
  return r.json();
}


export async function initMap(D) {
  await loadScript('vendor/topojson-client.min.js');
  const progs = [...D.programs].sort((a, b) => (b.addresses?.value || 0) - (a.addresses?.value || 0));
  [topo, iso] = await Promise.all([vendorJSON('vendor/world-countries-110m.topo.json'), vendorJSON('vendor/iso3-to-numeric.json')]);

  const fc = topojson.feature(topo, topo.objects.countries);
  const feats = fc.features.filter(f => f.id !== '010'); // no Antarctica
  const proj = d3.geoNaturalEarth1().fitExtent([[4, 4], [W - 4, W * 0.5]], { type: 'Sphere' });
  const path = d3.geoPath(proj);
  const H = Math.ceil(path.bounds({ type: 'Sphere' })[1][1]) + 4;

  // country (numeric id) -> programs
  const byId = new Map();
  const missing = new Set(), regions = new Set();
  const haveGeom = new Set(feats.map(f => f.id));
  for (const p of progs) {
    for (const r of p.regions || []) regions.add(r);
    for (const a3 of p.countries || []) {
      const num = iso[a3];
      if (!num || !haveGeom.has(num)) { missing.add(a3); continue; }
      if (!byId.has(num)) byId.set(num, []);
      byId.get(num).push(p);
    }
  }
  const maxN = Math.max(1, ...[...byId.values()].map(v => v.length));
  let selected = null;

  const host = $('#map-svg');
  host.innerHTML = '';
  const svg = d3.select(host).append('svg').attr('viewBox', `0 0 ${W} ${H}`).attr('class', 'mapsvg').attr('focusable', 'false');
  svg.append('path').attr('class', 'sphere').attr('d', path({ type: 'Sphere' }));
  svg.append('path').attr('class', 'graticule').attr('d', path(d3.geoGraticule10()));
  const paths = svg.append('g').selectAll('path').data(feats).join('path')
    .attr('class', 'country').attr('d', path)
    .on('mousemove', (ev, f) => showTip(ev, f))
    .on('mouseleave', () => tip.hide());

  function stepOf(f) { const n = (byId.get(f.id) || []).length; return n === 0 ? 0 : Math.min(4, Math.ceil((n / maxN) * 4)); }
  function paint() {
    paths.attr('data-step', f => {
      const list = byId.get(f.id) || [];
      if (selected) return list.includes(selected) ? 'sel' : (list.length ? 'dim' : '0');
      return String(stepOf(f));
    });
  }
  function showTip(ev, f) {
    const list = byId.get(f.id) || [];
    const name = f.properties.name;
    const body = list.length
      ? `<b>${esc(name)}</b><br>Linked to ${int(list.length)} ${list.length === 1 ? 'program' : 'programs'}:<ul>${list.map(p => `<li>${esc(programWithCode(p.program))}</li>`).join('')}</ul>`
      : `<b>${esc(name)}</b><br><span class="valued">No program links it</span>`;
    tip.show(body, ev);
  }

  // legend (units: programs per country)
  const cap = $('#map-cap');
  const steps = [1, 2, 3, 4];
  const lo = 1, hi = maxN;
  cap.innerHTML = `<span class="mleg" aria-hidden="true">${steps.map(s => `<i data-step="${s}"></i>`).join('')}</span>
    <span>Countries shaded by programs linked: from ${int(lo)} to ${int(hi)} ${hi === 1 ? 'program' : 'programs'}. Grey: none.</span>
    ${missing.size || regions.size ? `<span class="small">Not drawn: ${[...missing, ...regions].map(esc).join(', ')}${regions.size ? ' (regions are not countries)' : ''}.</span>` : ''}`;

  // program list
  const list = $('#prog-list');
  const maxVal = Math.max(1, ...progs.map(p => Math.max(p.value_at_designation_usd?.value || 0, p.value_today_usd?.value || 0)));
  const bar = (o, cls) => {
    const f = fmt(o);
    const w = Math.max(0.5, ((o?.value || 0) / maxVal) * 100);
    return `<div class="pbar ${cls}"><span class="k" title="${esc(valuedLabel(o))}${valuedFull(o) ? ': ' + esc(valuedFull(o)) : ''}">${cls === 'then' ? 'At listing' : 'Latest'}</span><span class="ptrack"><i style="width:${w.toFixed(2)}%"></i></span><span class="v">${esc(f.text)}</span></div>`;
  };
  const all = h('button', { type: 'button', class: 'prog on', 'aria-pressed': 'true', 'data-p': '' });
  all.innerHTML = `<span class="pname">All programs</span><span class="pmeta">Shade by number of programs</span>`;
  list.append(all);
  for (const p of progs) {
    const b = h('button', { type: 'button', class: 'prog', 'aria-pressed': 'false', 'data-p': p.program });
    b.innerHTML = `<span class="pname">${esc(programName(p.program))}${programName(p.program).includes(p.program) ? '' : ` <code>${esc(p.program)}</code>`}</span>
      <span class="pmeta">${esc(fmt(p.addresses).text)} ${esc(fmt(p.addresses).unit)} &middot; ${esc(fmt(p.entities).text)} ${esc(fmt(p.entities).unit)} &middot; ${esc(fmt(p.share_moved_after).text)} of ${p.denominators?.movement_observed_addresses != null ? esc(int(p.denominators.movement_observed_addresses)) + ' assessed ' : ''}addresses moved funds out after listing</span>
      ${bar(p.value_at_designation_usd, 'then')}${bar(p.value_today_usd, 'now')}`;
    list.append(b);
  }
  const unitsNote = document.createElement('p');
  unitsNote.className = 'cap prog-note';
  unitsNote.textContent = `Dollar bars are USD of known recognized assets: \u201cAt listing\u201d is valued at each address\u2019s own listing date, \u201cLatest\u201d at each address\u2019s latest saved balance. Programs overlap, so rows are not additive.`;
  list.after(unitsNote);
  list.addEventListener('click', ev => {
    const b = ev.target.closest('button.prog');
    if (!b) return;
    const code = b.dataset.p;
    selected = code ? progs.find(p => p.program === code) : null;
    for (const x of list.querySelectorAll('button.prog')) {
      const on = x === b; x.classList.toggle('on', on); x.setAttribute('aria-pressed', String(on));
    }
    paint();
  });
  paint();

  // the headline: the biggest program, in one line, from the data
  const topP = progs[0];
  if (topP) {
    const f = fmt(topP.addresses);
    const v = topP.value_at_designation_usd;
    $('#map-open').innerHTML = `${esc(programWithCode(topP.program))} is the biggest: <b>${esc(f.text)}</b> ${esc(f.unit)}${v?.value ? `, ${esc(usdText(v.value))} at listing` : ''}. Pick a program to light up its countries.`;
  }
  $('#prog-drawer-n').textContent = `All ${int(progs.length)} programs`;

  // a plain picker next to the map, kept in step with the program cards
  const sel = $('#prog-sel');
  sel.innerHTML = '<option value="">All programs</option>' + progs.map(p => `<option value="${esc(p.program)}">${esc(programWithCode(p.program))}</option>`).join('');
  const choose = code => {
    selected = code ? progs.find(p => p.program === code) : null;
    for (const x of list.querySelectorAll('button.prog')) { const on = (x.dataset.p || '') === (code || ''); x.classList.toggle('on', on); x.setAttribute('aria-pressed', String(on)); }
    sel.value = code || '';
    paint();
  };
  sel.addEventListener('change', () => choose(sel.value));
  list.addEventListener('click', ev => { const b = ev.target.closest('button.prog'); if (b) sel.value = b.dataset.p || ''; });
  reveal(host);
}
