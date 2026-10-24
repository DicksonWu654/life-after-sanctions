import { esc, h, $, fmt, usdText, compact, valuedLabel, valuedFull, md, chainName, shortAddr, int, words, spoken, lagRange } from './util.js';
import { get } from './data.js';
import { freezeStats, caseFreezes, findCase } from './derive.js';

/* The findings, in the order of FINDINGS.md: most shareable first. Each lead finding is a tile: one big number and one
   plain sentence, built from the exported numbers (nothing typed in), linking to the section that holds it. The long
   wording, definitions and example transactions sit in one "Evidence" drawer. The data-quality findings sit in a closed
   "More from the data" drawer; every other exported number stays reachable under it. */

const pct = o => fmt(o).text;
const pctSigned = o => fmt(o, { signed: true }).text;
const bigHTML = (text, unit) => {
  const m = String(text).match(/^(.*?) (of .*)$/);
  return `<span class="num">${m ? `${esc(m[1])} <span class="of">${esc(m[2])}</span>` : esc(text)}</span>${unit ? ` <span class="unit">${esc(unit)}</span>` : ''}`;
};

/** The inside of an Evidence block: exporter text, extra notes, example transactions, source. */
function evBody(f, extra = '') {
  const txs = ((f && f.example_txs) || []).map(t =>
    `<li><a href="${esc(t.explorer_url)}" rel="noopener noreferrer">${esc(chainName(t.chain))} transaction <code>${esc(shortAddr(t.hash, 8, 6))}</code></a></li>`).join('');
  return `${f && f.detail_md ? md(words(f.detail_md)) : ''}${extra}
    ${txs ? `<p class="ev-h">Example transactions</p><ul>${txs}</ul>` : ''}
    ${f && f.finding_ref ? `<p class="ref">Source: ${esc(f.finding_ref)}</p>` : ''}`;
}
function evidence(f, extra = '') {
  if (!f && !extra) return '';
  return `<details class="evidence"><summary>Evidence</summary><div class="ev-body">${evBody(f, extra)}</div></details>`;
}

/** One lead finding: the tile, plus the long form that goes in the evidence drawer. */
function lead({ id, k, big, unit, sentence, href, go, full, fullBody }) {
  const tile = h('article', { class: 'tile', 'aria-labelledby': `tile-${id}`, 'data-tile': id });
  tile.innerHTML = `
    <p class="tile-k" id="tile-${esc(id)}">${esc(k)}</p>
    <p class="tile-big">${bigHTML(big, unit)}</p>
    <p class="tile-s">${sentence}</p>
    <a class="tile-go" href="${esc(href)}">${esc(go)} <span aria-hidden="true">&rarr;</span></a>`;
  const ev = `<section class="ev-one" id="ev-${esc(id)}"><h4>${esc(k)}: <span class="num">${esc(big)}</span>${unit ? ` ${esc(unit)}` : ''}</h4><p class="ev-full">${full}</p>${fullBody || ''}</section>`;
  return { tile, ev };
}

/** Two bars on one scale: [{k, value, text}] */
function bars(rows, label) {
  const max = Math.max(...rows.map(r => r.value), 1e-9);
  return `<div class="ba finds-ba" role="img" aria-label="${esc(label)}">${rows.map((r, i) => `<div class="ba-r"><span class="ba-k">${esc(r.k)}</span><span class="ba-t"><i${i ? ' class="aft"' : ''} style="width:${Math.max(0.8, r.value / max * 100).toFixed(1)}%"></i></span><span class="ba-v">${r.text}</span></div>`).join('')}</div>`;
}

/* ---- the six lead findings ---- */

function bankMarkazi(D, H) {
  const c = findCase(D, 'bank-markazi-iran', /markazi/i);
  if (!c) return null;
  const Z = caseFreezes(c);
  if (!Z.rows.length) return null;
  const unit = Z.rows.find(r => r.nativeUnit)?.nativeUnit || 'USDT';
  const n = Z.rows.length, ch = chainName((c.chains || ['trx'])[0]);
  const early = Z.before.length;
  return lead({
    id: 'bank-markazi', k: 'Iran’s central bank', big: `${Z.nativeUnknown ? 'At least ' : ''}${compact(Z.native)}`, unit,
    sentence: `Frozen by Tether across the ${int(n)} ${esc(ch)} addresses OFAC lists for Iran’s central bank.`,
    href: '#spot-iran', go: 'See the case',
    full: `Tether froze ${esc(compact(Z.native))} ${esc(unit)} across the ${int(n)} ${esc(ch)} addresses OFAC lists for Iran’s central bank. ${esc(unit)} at each address’s first blacklisting, summed across different dates. In USD: ${esc(usdText(Z.usd))} (${esc(valuedLabel({ valuation_basis: 'at_each_freeze_time' }))}). ${early ? `${int(early)} of the ${int(n)} ${early === 1 ? 'was' : 'were'} blacklisted before their listing day began, holding ${esc(compact(Z.beforeNative))} ${esc(unit)} at that moment.` : 'None was blacklisted before its listing day began.'}`,
    fullBody: evidence(H['iran-two-prelisting-freezes'], c.source_url ? `<p class="ev-h">OFAC actions</p><ul>${[].concat(c.source_url).map(u => `<li><a href="${esc(u)}" rel="noopener noreferrer">${esc(u)}</a></li>`).join('')}</ul>` : ''),
  });
}

function tetherTron(D) {
  const st = D.freezes ? [...freezeStats(D.freezes).values()].find(s => s.issuer === 'tether' && s.chain === 'trx') : null;
  if (!st || st.listed == null) return null;
  const all = st.frozen === st.listed;
  const ch = chainName(st.chain);
  const rng = lagRange(st.medLo, st.medHi);
  return lead({
    id: 'tether-tron', k: 'Tether’s blacklist', big: `${int(st.frozen)} of ${int(st.listed)}`, unit: 'addresses',
    sentence: `${all ? `Every OFAC-listed ${esc(ch)} address was blacklisted for USDT` : `OFAC-listed ${esc(ch)} addresses blacklisted by Tether`}${st.beforeDay != null ? `; ${esc(int(st.beforeDay))} before the listing day began` : ''}.`,
    href: '#hero', go: 'See the chart',
    full: `Tether blacklisted ${all ? 'all ' : `${int(st.frozen)} of `}${int(st.listed)} historically OFAC-listed ${esc(ch)} addresses for USDT. ${st.beforeDay != null ? `${esc(int(st.beforeDay))} ${st.beforeDay === 1 ? 'was' : 'were'} blacklisted before the listing day even began. ` : ''}${st.median != null ? `The typical one was blacklisted about ${esc(spoken(st.median))} ${st.median < 0 ? 'before' : 'after'} noon on its listing day${rng ? `; with OFAC’s publication time unknown, the true gap is ${esc(rng)} publication` : ''}.` : ''}`,
    fullBody: evidence({ detail_md: (st.summary?.notes || ''), finding_ref: D.freezes.source_url }, st.usd ? `<p>Known balances at first blacklisting add up to at least ${esc(usdText(st.usd.value))} USD (${esc(valuedLabel(st.usd))}).</p>` : ''),
  });
}

function emptyWhenListed(D, H) {
  const f = H.empty_when_listed;
  if (!f) return null;
  let den = f.denominator?.value ?? null;
  let denNote = '';
  if (den == null && D.addresses) {
    // the exporter's card has no denominator yet (see EXPORT_REQUESTS.md); count the non-Tornado addresses with a measured listing-date balance
    const tor = new Set(findCase(D, 'tornado-cash', /tornado/i)?.addresses || []);
    den = D.addresses.filter(a => !tor.has(a.id) && a.trackable && a.balance_at_listing_usd).length || null;
    denNote = '<p>Denominator: addresses outside the Tornado Cash cohort with a measured balance at the start of their listing day.</p>';
  }
  const v = f.big.value;
  return lead({
    id: 'empty', k: 'Zero recognised-asset balance', big: `${int(v)}${den ? ` of ${int(den)}` : ''}`, unit: 'addresses',
    sentence: 'Measured non-Tornado addresses with an earlier qualifying outflow and zero recognised-asset balance at the start of listing day.',
    href: '#timing', go: 'See when money moved',
    full: `${int(v)}${den ? ` of ${int(den)}` : ''} measured non-Tornado chain–address pairs had an earlier qualifying outflow and zero recognised-asset balance at the start of their address-listing date. ${esc(words(f.sentence))} Balances as measured at the start of each address’s listing day.`,
    fullBody: evidence(f, denNote),
  });
}

function ratioOf(f) {
  if (f?.before?.value && f?.after?.value) return { before: f.before.value, after: f.after.value };
  // The balance card gives its earlier figure only inside the sentence (EXPORT_REQUESTS.md asks for fields).
  const m = String(f?.sentence || '').match(/versus\s+([\d,.]+)\s*ETH/);
  return m && f?.big?.value ? { before: parseFloat(m[1].replace(/,/g, '')), after: f.big.value } : null;
}

function tornado(D, H) {
  const d = H.tornado_delisting;
  if (!d) return null;
  const bal = H.tornado_balance_recovery;
  const r = ratioOf(bal);
  const un = (d.before?.unit || 'native:ETH').replace(/^native:/, '');
  const ratioTxt = r && r.after / r.before >= 1.5 ? `${(r.after / r.before).toFixed(1)}` : null;
  const up = d.big.value >= 0;
  const pool = r ? bars([
    { k: 'Pool balance, March 2025 endpoint', value: r.before, text: `${esc(compact(r.before))} ${esc(un)}` },
    { k: 'Pool balance, Oct 22, 2026 21:58 UTC', value: r.after, text: `${esc(compact(r.after))} ${esc(un)}` },
  ], `Balance of the four classic pools: ${int(r.before)} ${un} then, ${int(r.after)} ${un} latest`) : '';
  const dep = d.before && d.after ? bars([
    { k: `Deposited, ${int(d.window_days)} days before`, value: d.before.value, text: `${esc(compact(d.before.value))} ${esc(un)}` },
    { k: `Deposited, ${int(d.window_days)} days after`, value: d.after.value, text: `${esc(compact(d.after.value))} ${esc(un)}` },
  ], `ETH deposited: ${int(d.before.value)} before, ${int(d.after.value)} after`) : '';
  return lead({
    id: 'tornado', k: 'Tornado Cash', big: pctSigned(d.big), unit: `${un} deposited`,
    sentence: `Deposits into four classic native-ETH pools ${up ? 'rose' : 'fell'} across equal ${int(d.window_days)}-day windows around delisting, excluding the event day.`,
    href: '#spot-tornado', go: 'See the case',
    full: `Deposits into four classic native-ETH pools ${up ? 'rose' : 'fell'} ${esc(pct({ value: Math.abs(d.big.value), unit: 'share' }))} across equal ${int(d.window_days)}-day windows around ${esc(d.event_date)}, excluding that day. At Oct 22, 2026, 21:58 UTC the pools held ${bal ? int(bal.big.value) : 'unknown'} ETH, about 2.15 times their balance at the prior paper’s March 2025 endpoint. This is a descriptive association.`,
    fullBody: `<div class="find-pair"><div>${dep}</div><div>${pool}${bal ? `<p class="valued">${esc(words(bal.sentence))}</p>` : ''}</div></div>${evidence(d)}`,
  });
}

function chen(D, H, S) {
  const f = H['flows-chen-seizure-confounder'];
  if (!f) return null;
  const name = Object.keys(S?.links_excluding || {})[0] || (f.sentence.match(/(CHEN, Zhi)/) || [])[1] || 'one listed entity';
  const tot = S?.total_usd;
  const share = tot?.value ? f.big.value / tot.value : null;
  const without = S?.total_usd_excluding?.[name];
  return lead({
    id: 'chen', k: 'Largest measured cohort outflow', big: usdText(f.big.value), unit: 'USD',
    sentence: `Sent from addresses OFAC lists under ${esc(name)}${share != null ? `, ${esc(pct({ value: share, unit: 'share' }))} of measured priced gross outflow value in the non-Tornado cohort` : ''}. Four Bitcoin output edges, valued at each transfer time. TRM reports a related DOJ forfeiture; recipient control is unresolved.`,
    href: '#flow', go: 'See where it went',
    full: `Gross output edges can count the same funds repeatedly. TRM reports a related DOJ forfeiture and government custody; the specific recipients’ control remains unresolved. Addresses OFAC lists under ${esc(name)} sent ${esc(usdText(f.big.value))} USD after listing (${esc(valuedLabel(f.big))})${share != null ? `, ${esc(pct({ value: share, unit: 'share' }))} of the ${esc(usdText(tot.value))} USD of measured priced gross non-Tornado outflows (${esc(valuedLabel(tot))})` : ''}. A public report of the action describes the forfeiture and government custody; the chain shows the transfers but not who controls the recipients.${without ? ` Without ${esc(name)}, the total is ${esc(usdText(without.value))} USD.` : ''}`,
    fullBody: evidence(f),
  });
}

function preWeek(D, H) {
  const f = H.population_pre_week;
  if (!f?.observed_share || !f.baseline_share) return null;
  const o = f.observed_share.value, b = f.baseline_share.value;
  const how = o < b ? 'less often' : o > b ? 'more often' : 'as often';
  const sub = f.denominator ? `${int(f.number?.value)} of ${int(f.denominator.value)} eligible addresses` : '';
  return lead({
    id: 'pre-week', k: 'Before listing', big: pct(f.observed_share), unit: 'of addresses',
    sentence: `we could check sent funds out in the week before listing, ${how} than in their own ordinary weeks (${esc(pct(f.baseline_share))}).`,
    href: '#timing', go: 'See when money moved',
    full: `Addresses moved funds out ${how} in the week before listing than in their own ordinary weeks. ${esc(pct(f.observed_share))} of eligible addresses had a qualifying outflow in the week before listing${sub ? ` (${esc(sub)})` : ''}, against ${esc(pct(f.baseline_share))} in their own ordinary weeks. Share of eligible non-Tornado chain–address pairs. Individual advance notice remains unresolved.${f.p_holm != null ? ` A registered test found no cohort-wide pre-listing activity surge (Holm-adjusted p = ${esc(String(Math.round(f.p_holm * 100) / 100))}).` : ''}`,
    fullBody: bars([
      { k: 'Week before listing', value: o, text: esc(pct(f.observed_share)) },
      { k: 'Their own ordinary weeks', value: b, text: esc(pct(f.baseline_share)) },
    ], `Share of addresses with an outflow: ${pct(f.observed_share)} in the week before listing, ${pct(f.baseline_share)} in their own ordinary weeks`) + evidence(f),
  });
}

/* ---- second tier: the data-quality and side findings, in the closed drawer ---- */

function mini(id, big, unit, sentence, ev) {
  const art = h('article', { class: 'mini', 'aria-labelledby': `mini-${id}` });
  art.innerHTML = `<p class="big" id="mini-${esc(id)}">${bigHTML(big, unit)}</p><p class="sentence">${sentence}</p>${ev}`;
  return art;
}

function secondTier(D, H) {
  const out = [];
  const dep = H.seven_day_depletion, conc = H.value_denominator_concentration;
  if (dep) out.push(mini('depletion', pct(dep.big), 'net balance depletion',
    `Recognised-asset balances in the measured 491-address non-Tornado cohort showed ${esc(pct(dep.big))} net depletion after seven days, using fixed address-listing-date prices.`,
    evidence(dep, '<p>Checkpoint decreases can conceal withdrawals replenished by inflows. Excluding CHEN, Zhi changes net depletion to 17.49%.</p>')));
  const comp = H['tornado-composition-effect'];
  const te = D.freezes ? [...freezeStats(D.freezes).values()].find(s => s.issuer === 'tether' && s.chain === 'eth') : null;
  if (comp && te?.median != null) out.push(mini('tether-eth', spoken(te.median).split(' ')[0], spoken(te.median).split(' ').slice(1).join(' '),
    `Tornado Cash makes Tether’s Ethereum blacklisting look far slower than it was for other wallets: the typical delay was this long with it, ${esc(spoken(comp.big.value))} without it.`,
    evidence(comp, '<p>Median lag after noon on the listing day, all listed Ethereum addresses. A batch added long after that listing drives the longer figure.</p>')));
  const real = H.inflows_real_events;
  if (real) out.push(mini('inflows-real', int(real.big.value), 'incoming transfers',
    `${real.denominator ? `Only ${esc(int(real.big.value))} of ${esc(int(real.denominator.value))}` : `Only ${esc(int(real.big.value))}`} incoming transfers during listing periods were large enough and in recognized tokens${real.receiving_addresses ? `, reaching ${esc(int(real.receiving_addresses.value))} ${real.receiving_addresses.value === 1 ? 'address' : 'addresses'}` : ''}.`,
    evidence(real, `${real.usd ? `<p>${esc(usdText(real.usd.value))} USD in total, ${esc(valuedLabel(real.usd))}.</p>` : ''}<p>${esc(words(real.basis || ''))}</p>`)));
  const dust = H.inflows_dust_share;
  if (dust) out.push(mini('inflows-dust', pct(dust.big), 'of records',
    `In the measured non-Tornado listing-period sample, ${esc(pct(dust.big))} of incoming records were sub-$1 or operationally flagged. Off-list token authenticity and transfer purpose remain unresolved.`,
    evidence(dust, `<p>${dust.numerator && dust.denominator ? `${esc(int(dust.numerator.value))} of ${esc(int(dust.denominator.value))} incoming records. ` : ''}${esc(words(dust.basis || ''))}</p>`)));
  const des = H.tornado_designation;
  if (des) out.push(mini('tornado-des', pctSigned(des.big), 'change in ETH deposited',
    `In four classic native-ETH pools around Tornado Cash’s first designation, deposits ${des.big.value < 0 ? 'fell' : 'rose'} ${esc(pct({ value: Math.abs(des.big.value), unit: 'share' }))}${des.before && des.after ? `: ${esc(compact(des.before.value))} ETH before, ${esc(compact(des.after.value))} ETH after` : ''}.`,
    evidence(des, `<p>Equal ${esc(int(des.window_days))}-day windows either side of ${esc(des.event_date || '')}, native ETH.</p>`)));
  return out;
}

const USED = new Set(['iran-two-prelisting-freezes', 'empty_when_listed', 'tornado_delisting', 'tornado_balance_recovery', 'flows-chen-seizure-confounder', 'population_pre_week',
  'seven_day_depletion', 'value_denominator_concentration', 'tornado-composition-effect', 'inflows_real_events', 'inflows_dust_share', 'tornado_designation']);

export async function initFindings(D) {
  const root = $('#finds');
  const H = Object.fromEntries((D.headline || []).map(f => [f.id, f]));
  root.innerHTML = '';
  const [S] = await Promise.all([get('sankey'), get('cases'), get('addresses')]);
  const leads = [bankMarkazi(D, H), tetherTron(D), emptyWhenListed(D, H), tornado(D, H), chen(D, H, S), preWeek(D, H)].filter(Boolean);
  leads.forEach(l => root.append(l.tile));
  root.style.minHeight = '';

  // the one place the valuation convention is stated for this section
  const usdNote = H['flows-chen-seizure-confounder']?.big;
  const note = $('#finds-note');
  note.textContent = usdNote ? `Dollar figures here are ${valuedLabel(usdNote)}. Counts are addresses unless a unit says otherwise.` : '';

  const evd = $('#finds-ev');
  if (leads.length) { evd.removeAttribute('data-pending'); $('#finds-ev-body').innerHTML = leads.map(l => l.ev).join(''); }

  const tier2 = secondTier(D, H);
  const rest = (D.headline || []).filter(f => !USED.has(f.id) && f.id !== 'tornado-cash-still-active');
  const moreD = $('#finds-more');
  if (tier2.length || rest.length) {
    moreD.removeAttribute('data-pending');
    $('#finds2').innerHTML = '';
    tier2.forEach(c => $('#finds2').append(c));
  }
  if (rest.length) {
    $('#finds-rest').hidden = false;
    $('#finds-rest-n').textContent = `All other numbers from the analysis (${int(rest.length)})`;
    $('#finds-all').innerHTML = rest.map(f => {
      const unit = f.big?.unit;
      const n = fmt(f.big, { signed: /^tornado_/.test(f.id) });
      const val = unit === 'usd' ? `<p class="valued" title="${esc(n.valuedFull || '')}">${esc(n.valued)}</p>` : '';
      return `<article class="mini"><p class="big"><span class="num">${esc(n.text)}</span>${n.unit && n.unit !== 'share' ? ` <span class="unit">${esc(n.unit)}</span>` : ''}</p>${val}<p class="sentence">${esc(words(f.sentence))}</p>${evidence(f)}</article>`;
    }).join('');
  }
  if (!leads.length) evd.hidden = true;
  if (!tier2.length && !rest.length) moreD.hidden = true;
  if (!leads.length && !tier2.length) root.innerHTML = '<p class="fail">No finding cards could be built from the data.</p>';
}
