import { esc, $, int, chainName, onResize, spoken, lagRange, reveal } from './util.js';
import { freezeStats } from './derive.js';
import { drawCurves, freezeLegend } from './freeze.js';

const word = (n, one, many) => (n === 1 ? one : many);

/* The first screen: one number, one sentence, the chart. Everything that explains how to read it sits in a drawer. */
export function initHero(D) {
  const { freezes: F } = D;
  const stats = F ? freezeStats(F) : new Map();
  const th = [...stats.values()].find(s => s.issuer === 'tether' && s.chain === 'trx');
  const ci = [...stats.values()].find(s => s.issuer === 'circle' && s.chain === 'eth');
  const dirOf = m => (m < 0 ? 'before' : 'after');

  const stat = $('#hero-stat');
  if (th) {
    const of = th.listed != null && th.listed >= th.frozen ? int(th.listed) : null;
    const bits = [];
    if (th.median != null) bits.push(`The typical one was blacklisted about <b>${esc(spoken(th.median))} ${dirOf(th.median)}</b> noon on its listing day`);
    if (th.beforeDay) bits.push(`<b>${esc(int(th.beforeDay))}</b> ${word(th.beforeDay, 'was', 'were')} blacklisted before the listing day even began`);
    stat.innerHTML = `
      <h1 class="hs-h1"><span class="hs-big num">${esc(int(th.frozen))}${of ? ` <span class="hs-of">of</span> ${esc(of)}` : ''}</span>
        <span class="hs-what">Historically OFAC-listed ${esc(chainName(th.chain))} addresses were blacklisted for USDT by ${th.issuer === 'tether' ? 'Tether' : esc(th.issuer)}.</span></h1>
      ${bits.length ? `<p class="hs-lag">${bits.join('; ')}.</p>` : ''}
      <div class="stamp" aria-hidden="true"><span>BLACKLISTED</span></div>`;
  } else {
    stat.innerHTML = `<h1 class="hs-h1"><span class="hs-what">What happens to a crypto address after the Treasury blocks it?</span></h1><p class="fail">The freeze table did not load, so the headline number cannot be drawn.</p>`;
  }

  // the drawer under the chart: how to read it, the Circle line, units
  const body = $('#hero-howto-body');
  const rng = th ? lagRange(th.medLo, th.medHi) : '';
  const crng = ci ? lagRange(ci.medLo, ci.medHi) : '';
  body.innerHTML = `
    <p>Each line shows the share ever blacklisted for the issuer’s token by that lag. Zero is Noon ET (proxy) on the address-listing date${rng ? `; for Tether&rsquo;s typical address the true gap is then ${esc(rng)} publication` : ''}. The shaded band is Listing day (exact hour unknown). Only events outside it establish before/after publication. Dates measure first publication of each address; its named entity may already have been designated. The time scale stretches near zero so hours and years fit on one line. Hover for exact counts.</p>
    ${ci ? `<p><b>Circle, ${esc(chainName(ci.chain))}:</b> ${esc(int(ci.frozen))}${ci.listed != null && ci.listed >= ci.frozen ? ` of ${esc(int(ci.listed))}` : ''} historical identifiers ever blacklisted for USDC; ${ci.current != null ? `${int(ci.current)} still blacklisted; ${int(ci.unblacklisted)} later unblacklisted. ` : ''}The 217th string is malformed. Includes four Ethereum-convention network assignments.  ${ci.median != null ? `The typical one: <b>${esc(spoken(ci.median))} ${dirOf(ci.median)}</b> noon on its listing day${crng ? ` (${esc(crng)} publication)` : ''}.` : ''}</p>` : ''}
    <p class="valued">Circle removal dates (UTC): 90 on March 22, 2025, after Tornado’s delisting; one each on November 10, 2022 and February 6, 2024. Event dates establish sequence; reasons are unresolved. Units: chain–address pairs; lags from the noon proxy in hours.</p>
    <div class="legend" id="hero-legend"></div>`;

  const chartHost = $('#hero-svg');
  const rows = [th, ci].filter(Boolean);
  freezeLegend($('#hero-legend'), rows);
  if (rows.length) {
    const draw = () => drawCurves(chartHost, rows, { compact: true });
    draw();
    onResize(chartHost, draw);
    reveal(chartHost);
  }
}
