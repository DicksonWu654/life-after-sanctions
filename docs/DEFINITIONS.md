# Analysis definitions

- **Unit of analysis:** a chain-address pair = row of `data/addresses.csv` (chain, address_normalized). Entity-level
  results aggregate addresses under `sdn_uids` and are labelled as entities. Never mix units.
- **T (designation):** `first_listed_date` of the chain-address pair (the OFAC action that first published that
  address string). OFAC's intraday publication time is usually unknown: treat T as the OFAC action date and, for
  hour-level metrics (freeze lag), use **T_pub = 12:00 America/New_York on that date** as the point estimate with the
  interval [00:00, 23:59:59 ET] reported alongside. If a ledger row records an exact time, use it.
- **Same address on other EVM chains:** OFAC listed the 0x string under a ticker; activity on another EVM chain under
  the same string is reported separately as "same address, other chain" and never merged into the listed chain's
  headline unless stated.
- **Checkpoints:** T−7d, T (end of the day before T, i.e. balance as of T 00:00 ET), T+7d, T+30d, T+365d, today
  (latest fetched block). Balances per asset in native units; USD via `scripts/prices/price.py usd()` at the checkpoint
  time, stating the valuation time. "Value at designation" = balance at T valued at T.
- **Moved after designation:** at least one outgoing transfer of a non-dust amount after T (any asset). Dust threshold:
  < 1 USD at transfer time, or the chain's documented spam pattern. **First outflow lag** = first such transfer time −
  T_pub (days, signed).
- **Inflow classes:** `real` (≥ 1 USD at transfer time and not poisoning), `dust` (< 1 USD), `poisoning` (zero-value or
  tiny transfers from an address that mimics the first/last 4+ chars of a real counterparty, or off-list token transfers whose authenticity is unresolved). Record the rule that classified each row.
- **Coverage:** an address with `coverage.complete=false` is counted with a flag; results say "within data checked".
- **Tornado Cash contracts** are a separate class (pool/router contracts, not wallets); exclude them from wallet-level
  headline shares and analyse them in the Tornado analysis.
- **Exchange-scale addresses** (>10k txs): keep them in, but report results with and without them.
- **Untrackable addresses** stay in every denominator table as a separate row ("untrackable").
- **Outputs:** each analysis writes `results/<analysis>.json` (machine-readable, every number with unit and valued_at), a
  `docs/analysis/<ANALYSIS>.md` write-up with example tx hashes, and its script under `scripts/analysis/`. Scripts take
  `--check` (recompute from saved data, exit non-zero on diff) and run offline from saved data except where the script
  explicitly fetches (fetches are cached under `data/raw/<analysis>/`).
