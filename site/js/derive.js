/* Numbers the site derives from the export, never typed in. Each function states its rule in a comment so the
   page and EXPORT_REQUESTS.md can point at it. */

export const keyOf = (issuer, chain) => `${issuer}|${chain}`;

/** Rows per issuer and chain, read from the exporter's summary rows (freezes.json). Nothing is recounted here:
    listed = every OFAC-listed address on that chain, frozen = those the issuer blacklisted, beforeDay = frozen before the
    listing day began (whole uncertainty interval of the lag below zero), medLo/medHi = the median lag if OFAC had
    published at the earliest and the latest hour of the listing date. Points are only used to draw the curves. */
export function freezeStats(F) {
  const pts = F?.points || [];
  const sum = F?.summary || [];
  const keys = [...new Set([...sum.map(s => keyOf(s.issuer, s.chain)), ...pts.map(p => keyOf(p.issuer, p.chain))])];
  const v = o => (o && o.value != null ? o.value : null);
  const out = new Map();
  for (const k of keys) {
    const [issuer, chain] = k.split('|');
    const mine = pts.filter(p => p.issuer === issuer && p.chain === chain);
    const s = sum.find(x => x.issuer === issuer && x.chain === chain) || null;
    const half = mine.length && mine[0].lag_hours_interval ? (mine[0].lag_hours_interval[1] - mine[0].lag_hours_interval[0]) / 2 : 12;
    out.set(k, {
      key: k, issuer, chain, points: mine, summary: s,
      frozen: v(s?.frozen) ?? mine.length,
      current: v(s?.blacklisted_current), unblacklisted: v(s?.unblacklisted_ever),
      listed: v(s?.all_ofac_chain_addresses),
      share: v(s?.share_frozen),
      holders: v(s?.sanctioned_addresses_holding_token), holdersFrozen: v(s?.frozen_observed_holders),
      median: v(s?.median_lag_hours), medLo: v(s?.median_lag_interval_lower_hours), medHi: v(s?.median_lag_interval_upper_hours),
      p90: v(s?.p90_lag_hours),
      beforeDay: v(s?.definitely_before_publication) ?? v(s?.before_listing_day),
      afterCount: mine.filter(p => p.lag_hours > 0).length, half,
      usd: s?.usd_frozen || null,
    });
  }
  return out;
}

/** Tether's frozen USDT by the OFAC name of the address, joined through addresses.json (id = chain:address).
    Returns [{name, programs, addresses:[{row, point, usd, listed}], usd (known subtotal), unknown (addresses with no known amount)}]
    sorted by known subtotal. */
export function frozenByEntity(F, addresses, issuer = 'tether', chain = 'trx') {
  const byId = new Map(addresses.map(a => [a.id, a]));
  const groups = new Map();
  for (const p of F.points) {
    if (p.issuer !== issuer || p.chain !== chain) continue;
    const row = byId.get(`${chain}:${p.address}`);
    const name = row?.entities?.[0]?.name || 'Name not in the index';
    const g = groups.get(name) || { name, programs: new Set(), addresses: [], usd: 0, unknown: 0 };
    const usd = p.amount_frozen?.value ?? null;
    if (usd == null) g.unknown++; else g.usd += usd;
    (row?.programs || []).forEach(x => g.programs.add(x));
    g.addresses.push({ row, point: p, usd, listed: row?.listed || p.ofac_action_date });
    groups.set(name, g);
  }
  return [...groups.values()].sort((a, b) => b.usd - a.usd);
}

export const monthYear = d => new Date(d + 'T12:00:00Z').toLocaleDateString('en-US', { month: 'long', year: 'numeric', timeZone: 'UTC' });

/** First-blacklisting rows for one case (cases.json), joined to each address's listing date.
    `when` places the freeze against the listing day: before (whole lag interval below zero), after (above zero) or
    same_day (the interval spans zero, so the order against OFAC's publication is unknown). Native USDT and USD are
    kept apart; a null amount stays null (unknown), never zero. */
export function caseFreezes(c) {
  const ev = c?.events || [];
  const listed = new Map();
  for (const e of ev) if (e.kind === 'designation' && e.address_id) listed.set(e.address_id, String(e.date).slice(0, 10));
  const rows = ev.filter(e => e.kind === 'freeze' && e.address_id).map(e => {
    const iv = e.lag_hours_interval || null;
    return {
      id: e.address_id, address: e.address_id.slice(e.address_id.indexOf(':') + 1), date: e.date, listed: listed.get(e.address_id) ?? null,
      lag: e.lag_hours ?? null, interval: iv, when: !iv ? 'unknown' : iv[1] < 0 ? 'before' : iv[0] > 0 ? 'after' : 'same_day',
      native: e.amount_native?.value ?? null, nativeUnit: e.amount_native?.unit?.replace(/^native:/, '') || e.asset || '',
      usd: e.amount?.unit === 'usd' ? e.amount.value : null, usdObj: e.amount?.unit === 'usd' ? e.amount : null,
      tx: e.tx || null, source_url: e.source_url || null,
    };
  });
  const tot = (arr, k) => arr.reduce((a, r) => a + (r[k] ?? 0), 0);
  const group = w => rows.filter(r => r.when === w);
  return {
    rows, listedCount: listed.size,
    native: tot(rows, 'native'), usd: tot(rows, 'usd'),
    nativeUnknown: rows.filter(r => r.native == null).length, usdUnknown: rows.filter(r => r.usd == null).length,
    before: group('before'), same: group('same_day'), after: group('after'),
    beforeNative: tot(group('before'), 'native'), beforeUsd: tot(group('before'), 'usd'),
  };
}

/** Case lookup by id, falling back to a name match. */
export const findCase = (D, id, re) => (D.cases || []).find(c => c.id === id) || (re ? (D.cases || []).find(c => re.test(c.name)) : null);
