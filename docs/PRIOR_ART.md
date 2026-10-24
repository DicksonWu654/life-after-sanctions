# Prior art, novelty boundaries, and case references

Research snapshot: 23 October 2026. This document describes published claims, not new chain findings. The two requested arXiv papers were downloaded and read in full, including appendices; both versions of 2507.11721 were reviewed because its May 2026 revision materially changes the novelty comparison. Page references below are **one-based PDF pages**. The Bitcoin paper's printed pages match PDF pages; the New York Fed paper's printed pages are offset.

## What is new: the defensible claim

The brief's proposed novelty needs narrowing. **Neither Tron analysis, issuer freeze lag, dust awareness, cross-chain tracing, nor live monitoring is individually new.** In particular, the current Ethereum paper already compares issuer enforcement delays. Recent Bitquery work compares Tether and Circle against OFAC listing dates on Ethereum and Tron, and PublicAML publishes detailed Tron case histories. A project-wide claim that nobody has done those things would be wrong.

The contribution to aim for is a **public, reproducible, address-by-address sanctions lifecycle dataset across every OFAC-listed chain, combining action chronology, issuer events, controlled pre-designation comparisons, qualified inflows, and refreshable evidence**. In the sources reviewed here, I did not find a demonstrated implementation of that entire combination. This is a bounded literature-review result, rather than proof of worldwide priority. Actual chain and asset coverage is documented separately.

| Proposed contribution | What prior work already does | Precise increment this project should deliver |
| --- | --- | --- |
| Multi-chain population, including Tron | The Bitcoin paper studies a BTC population; Liu et al. start on Ethereum and parse bridges to other networks. Chainalysis, Elliptic, Bitquery and PublicAML already examine Tron. | One historical OFAC-derived denominator across chains, with native coin and tokens, chain/address/entity/action units kept separate, and privacy-chain/unavailable histories retained as explicit coverage gaps. This is broader source-population coverage, not the invention of cross-chain tracing. |
| Issuer freeze lag | Liu v2 section 4.2.2 compares USDT, USDC and sanctions-oracle delays. Bitquery's October 2026 table compares issuer response by listing period. PublicAML times Tron blacklists. | Reproducible event-level joins to the **date each identifier was added**, with timestamp precision recorded, uncertainty intervals when only a day is known, signed lag, balances at event order, burn/unfreeze episodes and clearly defined denominators. Do not call lag analysis itself new. |
| Movement before designation versus the address's own baseline | Liu compares long pre/during periods; the New York Fed examines announcement surprise and pre-announcement behavior; Chainalysis uses controls for a different counterparty-revenue question. | For the full trackable population, compare pre-designation outflows against each address's own matched historical windows, with placebos, inactive-address handling, chain/program strata and uncertainty. I did not find that specific population-wide, within-address design in the reviewed sources. It could identify an unusual pattern, not establish a leak. |
| Post-designation inflows split into substantive transfers, dust and poisoning | Liu v1 explicitly studies dusting and address-poisoning scams; PublicAML distinguishes real payments from tiny residual activity in its cases and reports post-freeze receipts. | Apply published, reproducible token-authenticity and spam rules to **incoming transfers to listed identifiers** across chains; preserve unclassified cases, sensitivity to thresholds and both raw and filtered totals. This differs from taint propagation outward from Tornado Cash. No transaction alone proves a sender's purpose. |
| Refreshable evidence | Liu v1 implements fast incremental updates and historical queries. Vendor products and public address-checking sites already monitor activity. | An open refresh command that rechecks new OFAC actions, preserves historical listing/delisting intervals, resumes partial fetches, records per-chain freshness, and reproduces published results from saved responses. Public multi-chain evidence and lifecycle maintenance are the increment; real-time monitoring is not new. |

Suggested launch wording, **once implemented and checked**: “An evidence-linked tracker of what happens to OFAC-listed crypto addresses across chains: movement, incoming transfers and issuer freezes, with historical action dates and a refreshable public dataset.” Avoid “the first,” “all funds traced,” or “sanctions failed” without a separately supported scope and denominator.

The overlap evidence is [Liu v2](https://arxiv.org/pdf/2507.11721v2), [Bitquery's issuer comparison](https://bitquery.io/investigations/crypto-censorship-stablecoin-issuers), [Bitquery's USDT audit](https://bitquery.io/investigations/tether-blacklist-audit), [PublicAML's Tron cases](https://publicaml.org/isis-k-hamas-tron-sanctions/), and [New York Fed Staff Report 1112](https://www.newyorkfed.org/research/staff_reports/sr1112.html). Saved evidence: `papers/arxiv-2507-11721-v2.*`, `pages/bitquery-censorship.*`, `pages/bitquery-blacklist.*`, `pages/publicaml-tron.*`, `papers/nyfed-sr1112.*` under `data/raw/priorart/`.

## 2507.11721: Evasion Under Blockchain Sanctions

Endong Liu, Mark Ryan, Liyi Zhou and Pascal Berrang. [v1, 15 July 2025](https://arxiv.org/pdf/2507.11721v1); [v2, 19 May 2026](https://arxiv.org/pdf/2507.11721v2), camera-ready WWW 2026 version. [arXiv version history](https://arxiv.org/abs/2507.11721). Saved PDFs: `data/raw/priorart/papers/arxiv-2507-11721-v1.pdf.gz` and `arxiv-2507-11721-v2.pdf.gz`; page-marked text extracts and request/hash metadata sit beside them.

### Dataset and scope

- **Chain:** Ethereum mainnet is the implemented source-ledger study. Both versions parse outbound bridge metadata; this must not be described as having no cross-chain component. V1 explicitly says it did not run the algorithm on other EVM chains (p12).
- **Address cohorts:** the introduction mentions 170 OFAC Ethereum addresses (both versions p1). The main empirical subject is Tornado Cash, especially its four ETH pools; it is not an equally detailed study of every named sanctioned entity. The downstream population is distinct from the original OFAC-address population.
- **Time:** sanction-period blocks 15,302,392 to 22,097,863, dated 2022-08-08 to 2025-03-21, described by the authors as 957 days, 6.79 million blocks and 1.07 billion transactions (v1 p5; v2 pp1,3). The deposit comparison uses 966 days before and 957 days during sanctions; the plotted full series starts 2019-12-16 (v1 pp5-6; v2 p5). These are nearly equal windows, not exactly equal-length samples.
- **Other data:** service labels; BlockSec's incident list as of 2025-03-21; v1's Bybit proxy labels from Etherscan and Elliptic. V2 p4 tabulates 67,944,117 downstream addresses with nonzero/exposure-related history under its propagation model; they are not additional OFAC-designated addresses.

### Methods

The authors propagate a proportional “impurity” measure through account balance changes to quantify exposure to source funds. V1 details archive-node execution traces, balances, fees and rewards, withdrawal beneficiaries recovered from logs rather than the submitting relayer, graph pruning, service classification and an experimental score threshold. It validates an implementation against vendor-labelled Bybit addresses and benchmarks incremental state updates (v1 pp3-5,10-12).

Both versions compare Tornado deposits and withdrawals before/during sanctions, examine builder inclusion of direct and downstream transactions, and characterize downstream destinations and behavior. Bridge metadata parsers cover 20 bridges and two proxy aggregators (v1 pp8-10; v2 p7). The existence of a bridge interaction does not mean all downstream destination-ledger activity has been reconstructed. V2 reorganizes the paper around consensus-layer, application-layer and user reactions, with the updating algorithm in Appendix A (p10).

### Headline figures: exact quoted numbers and correct units

The quotation fragments preserve the paper's numeric text; PDF layout whitespace is normalized. The first two were also visually checked on the PDF first page. `paper_findings.json` records page-level excerpts; `build_reference.py --check` verifies them against the saved extracts.

| Finding | Exact quotation fragment | PDF reference and interpretation |
| --- | --- | --- |
| Initial aggregate native balance | “499,769.74 ETH (983 million USD)” | v2 p1; also v1 p1. Aggregate balance of the 170-address introductory cohort at their designation times. The paragraph does not state a USD valuation timestamp. |
| Remaining aggregate native balance | “145,579.38 ETH (286 million USD)” | v2 p1; also v1 p1. Endpoint 2025-03-21. This is a balance, not gross flow, seized value, or money proven to have been laundered. |
| Tornado deposit-volume decrease | “71.03%” | v2 p5 Table 2; v1 p5 Table 1. Native ETH volume: the table rounds pre/during deposit totals to 3.49 million and 1.01 million ETH. The approximate USD equivalent in the abstract is a different unit. |
| Tornado use in the incident subsample | “78.33%” | v2 pp5-6; v1 p6. 47 of 60 selected incidents with active laundering, after exclusions from the incident database; not the percentage of all Ethereum exploits or of sanctioned addresses. |

The authors assign Tornado 44.17% of the cohort's initial native balance and 99.12% of its remaining balance (p1). That is a **concentration statement**, not evidence that most of the cohort's balance decrease moved through Tornado. The brief's “mostly via Tornado Cash” wording should not be inferred solely from those balance shares.

V1 additionally reports precision of “97.61%”, recall of “74.08%”, and an average new-block update time of “0.07 ± 0.03” seconds (pp1,11, Table 3). Those are an algorithm benchmark and proxy-label evaluation, not measured accuracy of every case in this project. V1 p8 reports 40 frozen tainted-USDT holder addresses and two tainted-USDC holder addresses in its downstream cohort; these are not issuer coverage rates for explicitly listed OFAC identifiers.

### The v2 addition that changes our novelty claim

V2 section 4.2.2 (p5) measures policy-to-enforcement delay and within-block ordering for USDC blacklisting, USDT blacklisting and the Chainalysis sanctions oracle. Its date reference is the block closest to **midnight on the OFAC publication date in Eastern Time**, rather than a verified intraday press-release timestamp. It reports qualitatively shorter and less variable USDC delays, with larger/dispersed USDT delays. The within-block average positions are 29.83%, 47.01% and 63.62%, respectively; these positions are not hours or days of freeze lag.

Therefore “we add stablecoin freeze timing missing from this Ethereum paper” is false for the version currently on arXiv. A useful improvement is accurate identifier-addition chronology, temporal precision/intervals, cross-chain issuer coverage, amount-at-freeze reconstruction and open event-level evidence.

### Limitations and cautions

- **Coverage:** ETH-centric source tracing and service samples cannot establish outcomes for every OFAC-listed chain. V1 p12 says selected services account for 83.34% of withdrawal funds, not complete downstream visibility. V1 pp11-12 acknowledges incomplete ERC-20 tracking and that token conversions can interrupt its native-asset tracing. Detecting token interactions is not the same as maintaining complete token provenance.
- **Model versus legal status:** a proportional exposure score is an analytical allocation model. Receipt of funds does not establish common control, knowledge, a legal violation, or that a service failed its obligations. We must not import the paper's stronger legal/evasion language as a conclusion about a named exchange.
- **Ground truth:** v1's proprietary-label proxy is incomplete and threshold-dependent. Its text describes 12,394 proxy addresses while Table 4 uses 12,210; that denominator difference is not adequately reconciled in the displayed discussion. The adjusted perfect-precision interpretation relies on the authors' manual reclassification. Retain the reported unadjusted benchmark and its limitations.
- **Timing and denominators:** a date-midnight proxy can produce misleading small positive/negative lag. The 170-address introduction, the four-pool activity sample, the incident subset, and millions of propagated addresses answer different questions.
- **Dust and poisoning already covered:** v1 pp5,16-18 and v2 pp6,10-11 address dusting; v1 specifically discusses address poisoning. Our novelty must be the reproducible incoming-transfer classification at the listed-address level, not discovering spam.
- **Causality:** before/after changes can also reflect market conditions, token prices, service substitution, hacks, seizure, or legal developments. Neither a balance fall nor continued transactions alone measures legal compliance or the isolated causal effect of sanctions.

## 2409.10031: Assessing the Impact of Sanctions in the Crypto Ecosystem

Francesco Zola, Jon Ander Medina and Raúl Orduna, [arXiv v1, 16 September 2024](https://arxiv.org/pdf/2409.10031v1), *Effective Measures or Ineffective Deterrents?* This is the preprint of the CBT 2024 workshop paper. [Version metadata](https://arxiv.org/abs/2409.10031). Saved PDF: `data/raw/priorart/papers/arxiv-2409-10031-v1.pdf.gz`, with extracts and metadata beside it.

### Dataset, methods and exact headline

- **Inventory versus analyzed sample:** the February 2024 SDN snapshot is described as 600 cryptocurrency addresses across 17 cryptocurrencies (p6). The Bitcoin analysis studies 43 of 56 available entities (p8), using **387 BTC-sanctioned addresses** (p12). The 17 figure is a ticker inventory, not a verified chain count.
- **Chain/time:** the entire Bitcoin blockchain through block 830,000, dated 2024-02-11, containing more than 900 million transactions (p8). Historical observation begins with the full chain rather than a common fixed pre-period; each entity's sanction date defines its own split. There are no subsequent 2024-2026 observations in this study.
- **Labels:** WalletExplorer and GraphSense tagpacks provide more than 38 million addresses associated with almost 400 entities (p8). These labels cover only a small part of the full Bitcoin address population; the paper discusses coverage on p14.
- **Flow analysis:** address-transaction bipartite graphs at one step, measured before sanctions, in the first seven days, in the first 30 days and from designation through the dataset endpoint (p9). It extracts incoming/outgoing transaction counts, BTC balances and USD-valued flow, using the BTC/USD value on each transaction day, and aggregates addresses by entity.
- **Behavioral analysis:** one- and two-step downstream graphs enriched with labels, not a perpetual proof of ownership through every hop (pp9-10,12-15).

Its exact headline sentence is: **“only 21 entities stopped to receive money, and 25 to send funds.”** (p10). The same paragraph says seven entities still moved funds within seven days. Preserve the unit **entities**. The abstract's “half” characterization must not become a claim that exactly half of the listed addresses were immobilized.

Table 2 (p12) reports post-sanctions activity by program: for example, CYBER2 has 305 transactions and about USD 3 million of combined incoming/outgoing volume, while ILLICIT-DRUGS has 747 transactions and about USD 8 million. Those are rounded source estimates valued on transaction days. They are not balances, unique externally received dollars, or disjoint program totals: one entity can have more than one program.

Table 3 (pp12-13) reaches 4,008 addresses at one step, of which 340 are labelled; at two steps it reaches more than ten million addresses, of which 175,444 are labelled. Among labelled addresses, exchanges dominate. That supports a description of the labelled graph sample, not a claim that most **value** reached exchanges or that an exchange allowed withdrawals.

### Limitations we should explicitly improve

The analysis is Bitcoin-only; newer designations have less follow-up time (pp14-15). Public labels are incomplete and the two-step method assumes ownership has not changed, which the authors acknowledge cannot be assured from the chain (p15). There is no issuer-freeze event study or reproducible classification of all incoming dust/spam in this paper.

The limitations paragraph calls the cohort 40 entities (p14), conflicting with the 43-entity methods/results. Use the explicit 43/387 methods/results with a caveat; do not silently repair the paper. Program names/descriptions in its background table also must not replace OFAC's own program tags. Most importantly, cessation of listed-address activity is an observed outcome, not proof that the entity ceased operating elsewhere or that sanctions alone caused it.

## Other work that limits novelty

### Brownworth et al., New York Fed Staff Report 1112

[Regulating Decentralized Systems: Evidence from Sanctions on Tornado Cash](https://www.newyorkfed.org/research/staff_reports/sr1112.html), August 2024. Saved PDF `data/raw/priorart/papers/nyfed-sr1112.pdf.gz`; landing page `pages/nyfed-sr1112-page.html.gz`. This additional paper was reviewed for the abstract, data/method sections, event-study results and anticipation discussion; full-PDF review was required and completed for the two arXiv papers above.

It studies Ethereum and TORN market data over January 2020-December 2023, using Dune and AWS public blockchain data. It examines protocol use, market reaction, user diversity, pools' net flows, and builder cooperation, including reactions to legal developments. It already considers whether the announcement was anticipated (PDF p4 / printed p3; see claim IDs `NYFED-TC-VOLUME` and `NYFED-ANTICIPATION`). An address's own historical outflow baseline across the complete OFAC population remains a different proposed design. Preserve this paper's distinction between **gross activity dropping** and **pool net balances recovering**; those outcomes can occur together.

### Vendor and public investigations

The full structured list is [vendor_claims.csv](../data/reference/vendor_claims.csv). It includes 37 selected claims from 24 sources, spanning Chainalysis, Elliptic, TRM Labs, Circle, Tether, Bitquery, PublicAML and the New York Fed research paper. These are sources' claims awaiting chain-data replication. Each row gives an exact short excerpt, publication-date basis, chain, unit, window, test plan, limitations, original URL and saved raw reference. Excerpts preserve spelling errors in the source. Table excerpts preserve cell order; whitespace and PDF ligatures are normalized for verification.

| Source / saved source ID | What to preserve or test | Main comparability issue |
| --- | --- | --- |
| [Chainalysis, January 2023](https://www.chainalysis.com/blog/how-2022-crypto-sanction-designations-affected-crypto-crime/) — `chainalysis-2022-impact` | Different reactions by Hydra, Garantex and Tornado; pre/post inflows and counterparty controls. | Short-window USD inflows differ from Liu's long-window ETH volumes. Seizure, jurisdiction and service design differ. |
| [TRM, October 2023](https://www.trmlabs.com/resources/blog/tornado-cash-volume-dramatically-reduced-post-sanctions-but-illicit-actors-are-still-using-the-mixer) — `trm-tornado-2023` | Matched six-month comparisons of Tornado deposits. | Match months, token/contract cohort and prices before comparing percentage changes. |
| [Elliptic, March 2025](https://www.elliptic.co/insights/elliptic-in-action-garantex/) — `elliptic-garantex` | Garantex continuation, primarily Tron USDT, and assets frozen at disruption. | The vendor's inferred exchange cluster is much larger than the public SDN identifier set. |
| [Chainalysis, July 2026 ISIS-K](https://www.chainalysis.com/blog/isis-designation-crypto-addresses-july-2026/) — `chainalysis-isis-2026` | Added Tron/Monero identifiers, issuer coverage and flows. | A blacklist event can target an empty address; Monero identifiers do not provide public flow visibility. |
| [Chainalysis, July 2026 Hamas](https://www.chainalysis.com/blog/ofac-sanctions-hamas-facilitators-illicit-finance-july-2026/) — `chainalysis-hamas-2026` | The newly designated Al-Jebouri Tron cohort. | Article date and action date differ; its cryptocurrency/USD total differs from PublicAML's USDT-only external-flow total. |
| [Circle, August 2022](https://www.circle.com/blog/the-responsibility-of-trust) — `circle-tornado` | Primary issuer confirmation of blocking Tornado-related addresses. | It does not state a frozen amount or count. Distinguish Centre's token blocking from Circle Account access controls. |
| [Tether, December 2023](https://tether.io/news/tether-introduces-new-policy-to-strengthen-ecosystem-security/) — `tether-policy` | Policy extension covering previously listed wallets. | Separate the decision date, announcement date and observed on-chain event dates. |
| [Tether, April 2026](https://tether.io/news/tether-supports-freeze-of-more-than-344-million-in-usdt-in-coordination-with-ofac-and-u-s-law-enforcement/) — `tether-iran-2026` | Issuer statement about a coordinated freeze before OFAC's identifier addition. | Need the official identifier set and event histories to establish the exact match and lag. |
| [Bitquery, August 2026](https://bitquery.io/investigations/tether-blacklist-audit) — `bitquery-blacklist` | Event counts, balance reconstruction checked against burns, and separation of exact SDN identifiers from inferred labels. | Its universe is all USDT freezes, not just OFAC. The article itself rejects using entity dates as identifier dates. |
| [Bitquery, October 2026](https://bitquery.io/investigations/crypto-censorship-stablecoin-issuers) — `bitquery-censorship` | USDT/USDC listing-to-freeze timing, including a table by period. | Direct prior art for our proposed issuer comparison; replicate temporal joins rather than claiming priority. |
| [PublicAML, October 2026](https://publicaml.org/isis-k-hamas-tron-sanctions/) — `publicaml-tron` | Full USDT histories of the ISIS-K and Al-Jebouri cohorts, balances caught and receipts after freezing. | Different internal-flow treatment and asset scope may explain differences from vendor headlines. Its small number of cases does not establish population-wide patterns. |
| [TRM, June 2026](https://www.trmlabs.com/resources/blog/the-top-takeover-tornado-cashs-latest-chapter) — `trm-tornado-2026` | Tornado activity after delisting. | Continued protocol use after delisting must be labelled by that legal period; this is not by itself a sanctions breach. |

These pages were read from saved HTML/text, not just search snippets. Other case-specific vendor references, including Suex, Chatex, Cryptex, hosting providers, fentanyl suppliers, LockBit, Prince Group and IT-worker cases, are linked with raw copies in `cases.csv` and the source index.

[0xB10C's extraction README](https://raw.githubusercontent.com/0xB10C/ofac-sanctioned-digital-currency-addresses/master/README.md) is a useful discovery/diff aid, not the date authority. The saved README is `pages/github-b10c-readme.html.gz` (the response is plain Markdown despite the generic collector extension). No downloaded repository code was executed.

[SanctionFlow](https://sanctionflow.io/) is another discovery lead. Saved homepage, entity-directory and methodology URLs returned an app shell without enough readable methodology to determine its complete analytical scope. Treat overlap with that product as unresolved; its existence is another reason not to claim public-tracker priority. Do not infer capabilities from search snippets alone.

## Famous cases and action-date rules

[cases.csv](../data/reference/cases.csv) contains **20 editorial case families**, with eight additional action records in its `related_actions` JSON field. These are not 20 unique entities or 28 distinct Treasury publication days. Related actions retain separate entity names, dates, programs, source URLs and saved references. Treasury's numeric date text is stored in `date_verification_quote` and checked against the saved Recent Actions page. The primary name field uses OFAC's names, including its punctuation.

The CSV covers the first SamSam identifiers; Evil Corp; Suex; Chatex; Hydra; Garantex and Grinex; Lazarus/Ronin; Blender; Tornado's initial designation, re-designation and delisting; Sinbad; the Wang Hongfei fentanyl-precursor case; Cryptex/PM2BTC context; LockBit affiliates and its leader; Zservers/Aeza; Funnull; DPRK IT-worker cases in 2025 and 2026; the Karen National Army context; Prince Group/Chen Zhi with Huione context; and the 2026 ISIS-K and Al-Jebouri Tron cohorts.

### Corrections that matter to an address-level tracker

1. **Lazarus/Ronin:** [2022-04-14](https://ofac.treasury.gov/recent-actions/20220414) is an ETH identifier addition, not the group's initial designation. The [2019-09-13 action](https://ofac.treasury.gov/recent-actions/20190913) and [Treasury release](https://home.treasury.gov/news/press-releases/sm774) establish the older entity action. No press release is linked on the April 2022 Recent Actions page; the later [Blender release](https://home.treasury.gov/news/press-releases/jy0768) explicitly recalls the April 14 addition. The CSV explains why its press link has a different publication date.
2. **Tornado:** preserve [2022-08-08](https://ofac.treasury.gov/recent-actions/20220808), [2022-11-08](https://ofac.treasury.gov/recent-actions/20221108) and [2025-03-21](https://ofac.treasury.gov/recent-actions/20250321) as separate actions. The November original-entry removal and immediate re-designation do not create an ordinary unsanctioned interval. The March 2025 protocol delisting does not determine the status of every person ever associated with it.
3. **Garantex/Grinex:** use [2022-04-05](https://ofac.treasury.gov/recent-actions/20220405) for the initial action and [2025-08-14](https://ofac.treasury.gov/recent-actions/20250814) for additional Garantex authorities/identifiers and Grinex. Do not backdate the newly added Tron identifiers to the first entity date.
4. **ISIS-K:** [2026-07-01](https://ofac.treasury.gov/recent-actions/20260701) adds identifiers to ISIL KHORASAN's existing entry. That page's linked Treasury release concerns a different, Brazilian network. No case-specific Treasury press release was found; the CSV intentionally leaves that press URL blank and cites Recent Actions directly. Do not use the unrelated release as evidence.
5. **Bitzlato:** the verified [2023-01-18 FinCEN action](https://www.fincen.gov/news/news-releases/fincen-identifies-virtual-currency-exchange-bitzlato-primary-money-laundering) is a section 9714 order, not an OFAC SDN designation. The source also distinguishes the order's issue date from its effective date. It is kept as context, not invented as an OFAC case row. Saved source: `pages/fincen-bitzlato.*`.
6. **Cryptex/PM2BTC:** the [2024-09-26 Treasury release](https://home.treasury.gov/news/press-releases/jy2616/) distinguishes Cryptex/Sergey Ivanov OFAC designations from the PM2BTC FinCEN measure. Chainalysis explicitly corrected its interpretation of UAPS in the saved post. Preserve that correction.
7. **Prince/Huione:** the [2025-10-14 action](https://home.treasury.gov/news/press-releases/sb0278) distinguishes OFAC's Prince Group sanctions from FinCEN's Huione section 311 final rule. This statement concerns that action, not every later action. The explicit Bitcoin identifiers in Recent Actions are under CHEN, Zhi. The [2025-05-01 FinCEN Huione finding](https://www.fincen.gov/news/news-releases/fincen-finds-cambodia-based-huione-group-be-primary-money-laundering-concern) is separately saved (`pages/fincen-huione.*`).
8. **Evil Corp and Karen National Army:** these requested context cases have no digital-currency identifiers in the specific saved designation actions. Keep them as case references, not manufactured address cohorts. No case-specific vendor article was verified for the Karen National Army action; the CSV records that gap.
9. **USDT is not a chain:** Suex, Chatex and initial Garantex entries include Bitcoin-format USDT identifiers. The CSV marks network resolution as unresolved instead of assuming that every USDT identifier is Tron or Ethereum. ETH/TRX/XBT identifiers and explicit XRP/LTC entries provide different evidence.

Each action above is saved under `pages/ofac-YYYYMMDD.*` and/or its corresponding `treasury-*` or `fincen-*` source ID. Exact URL-to-file mappings, request times and hashes are in `data/raw/priorart/source_index.csv`.

### Additional verified 2026 Iran leads

These are supplemental context rather than expanding the requested case-family CSV beyond 20 rows.

| Action / date | Verified primary sources and saved IDs | Treatment |
| --- | --- | --- |
| Central Bank of Iran identifiers, 2026-04-24 | [Recent Actions](https://ofac.treasury.gov/recent-actions/20260424), `ofac-20260424`; [Tether statement dated 2026-04-23](https://tether.io/news/tether-supports-freeze-of-more-than-344-million-in-usdt-in-coordination-with-ofac-and-u-s-law-enforcement/), `tether-iran-2026` | Entry name is BANK MARKAZI JOMHOURI ISLAMI IRAN, with Central Bank of Iran as an alias. Use the identifier addition rather than the older entity date. The issuer statement and chain events should be checked for a freeze preceding the public addition. |
| Nobitex and other Iranian exchanges, 2026-06-02 | [Treasury release](https://home.treasury.gov/news/press-releases/sb0519), `treasury-iran-exchanges`; [Recent Actions](https://ofac.treasury.gov/recent-actions/20260602), `ofac-20260602`; [Chainalysis post](https://www.chainalysis.com/blog/ofac-sanctions-iranian-crypto-exchanges-june-2026/), `chainalysis-iran-2026` | A verified exchange designation is not automatically a set of publicly listed crypto identifiers. The saved action has no digital-currency identifiers; keep vendor-labelled exchange clusters separate. |

## Things prior work did that we must not get worse at

- **Comparable observation windows and honest censoring.** Preserve first-week/month outcomes from the Bitcoin paper and full-period context from Liu. Do not compare a recently listed address with a long-observed one without reporting follow-up availability; a future checkpoint is unavailable, not zero.
- **Correct transaction semantics.** For Tornado, use actual withdrawal beneficiaries and pool events, not only top-level senders. On EVM chains distinguish successful value transfers from failed calls and log-only counterfeit-token spam; on UTXO chains distinguish spent outputs, change and self-transfer from external value moved.
- **Native amounts and time-specific USD.** Keep balances, gross transfers, net flows and incoming/outgoing volumes separate. Retain transaction-time valuation when replicating the Bitcoin study or Suex claims. Do not substitute today's price into a historical vendor estimate without explaining it.
- **Downstream context and uncertainty.** The Bitcoin paper shows that a single hop can miss labelled services; Liu provides bridge, DEX, CEX and privacy-tool context. Provide documented hops and label sources where available, while making coverage gaps and possible ownership changes visible. A destination label is not proof of what a service knew or did.
- **Dust robustness and source authenticity.** Liu already shows why tiny unsolicited receipts make simple taint rules unreliable and discusses poisoning. Keep raw histories and filtered totals side by side, identify token contracts, and disclose ambiguous classifications. “Real payment” should mean an operational classification, not verified intent or a newly identified person.
- **Reconciliation against independent invariants.** Bitquery compares reconstructed balances with burn event values. Match transfer/balance/event ordering and show failures rather than silently deleting mismatches or negative balances.
- **Action history and issuer state.** Keep the historical SDN set, additions/removals, unblacklist events, repeat freezes and differences between issuer policy announcements and chain events. The Bitquery warning about identifier dates is particularly relevant to this project's freeze-lag result.
- **Controls and causal restraint.** The New York Fed examines announcement anticipation, and Chainalysis uses a control group for counterparty revenue. Our pre-movement analysis needs its promised own-history baseline and placebo windows, not a visually striking event-day chart alone. Concurrent seizures and enforcement are material confounders.
- **Explicit cohorts.** Do not put an official-address result next to a vendor's inferred exchange-cluster total as if both measure the same population. Publish per-chain coverage, distinguish identifiers from (address,entity) pairs, and preserve inaccessible/private-chain identifiers in the inventory.
- **Operational proof.** A static page with a “last refreshed” label is weaker than Liu v1's demonstrated incremental implementation. Before claiming refreshability, show successful repeat refreshes, reproducible checks and per-source freshness.

## Evidence, reproducibility, and remaining limits


`source_index.csv` indexes 100 successful saved responses. The two arXiv works are retained as version-pinned gzip PDFs, alongside page-marked extracts; the older Ethereum version is also retained. HTML pages and text extracts are gzip-compressed. Each metadata JSON records the requested URL, GET method, retrieval time, final URL, content type, byte count and SHA-256 of the response and extract. Failed exploratory URLs are metadata-only, excluded from the successful-source index and never used as citations.

`collect.py` is the resumable public-source collector; `sources*.json` record retrieval inputs. It uses no API credentials. Its only non-stdlib dependency for PDF extraction is recorded in the scoped `requirements.txt`; it was installed with uv into a temporary target so the shared project environment was not mutated. `build_reference.py` uses only the standard library, checks all referenced raw hashes, verifies the short claim excerpts, validates paper excerpts at their cited pages and verifies every primary/related case action date in its saved Treasury page. Inputs are `case_inputs.json`, `claim_inputs.json` and `paper_findings.json`.

Run from the repository root:

```sh
.venv/bin/python data/raw/priorart/build_reference.py --check
```

To intentionally regenerate only these owned reference tables and source index, omit `--check`. This is a reference-integrity check, not a reproduction of vendors' chain analytics. `validation.json` records the latest successful build counts and checks.

Open limits: vendor address clusters and some pricing/flow conventions are not public; some article display dates differ from UTC publication metadata and both are retained in `date_basis`; a day-only Treasury publication date cannot support precise intraday lag; USDT-only external flow and all-asset gross flow need alignment; SanctionFlow's scope remains unresolved; there is no verified case-specific Treasury press release for the ISIS-K identifier update and no verified vendor post for the Karen National Army action. The review is a documented source sample, not an exhaustive academic bibliography or proof that no overlapping tracker exists.

This is research, not legal or compliance advice. Attribution follows OFAC or the explicitly cited source. Receipt from a listed identifier is an on-chain relationship; it does not establish knowledge, control or unlawful conduct by a recipient, exchange or other party.
