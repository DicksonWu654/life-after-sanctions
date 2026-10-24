# Stablecoin issuer blacklist, unblacklist and destruction history

Produced by `scripts/freezes/fetch_freezes.py`. No OFAC address matching is performed here.

## Coverage and counts

Counts below are event logs, not unique addresses or legal determinations. All amounts are native token units (6 decimals), not USD.

| Chain | Token | Event | Logs | First event UTC | Last event UTC |
|---|---|---|---:|---|---|
| ETH | USDT | AddedBlackList | 3,180 | 2017-11-28T16:39:10Z | 2026-10-23T16:32:47Z |
| ETH | USDT | RemovedBlackList | 347 | 2017-11-28T16:59:39Z | 2026-08-20T16:41:35Z |
| ETH | USDT | DestroyedBlackFunds | 1,296 | 2017-11-28T16:52:01Z | 2026-10-21T19:51:35Z |
| ETH | USDC | Blacklisted | 906 | 2020-06-16T04:39:08Z | 2026-10-22T22:17:35Z |
| ETH | USDC | UnBlacklisted | 226 | 2021-12-23T23:35:00Z | 2026-09-23T08:01:11Z |
| TRX | USDT | AddedBlackList | 9,035 | 2020-06-26T15:22:39Z | 2026-10-23T16:04:48Z |
| TRX | USDT | RemovedBlackList | 988 | 2021-08-01T15:07:24Z | 2026-10-23T15:01:09Z |
| TRX | USDT | DestroyedBlackFunds | 1,270 | 2020-06-26T15:27:33Z | 2026-10-23T16:51:18Z |

| Chain | Snapshot block | Snapshot time UTC | Head evidence |
|---|---:|---|---|
| ETH | 26,257,132 | 2026-10-23T18:30:47Z | `data/raw/freezes/heads/9ce27325dcb887feb456ee00b70727a1785122a58005462a0647205253edacbe.json.gz` |
| TRX | 87,369,304 | 2026-10-23T18:44:39Z | `data/raw/freezes/heads/679183c497230d0fb764c160197211a93a36d0b47468741f3ee8455486f5667a.json.gz` |

## Completeness checks

Ethereum: Etherscan v2 scans every requested topic from block 0 through the finalized head. A range returning 1,000 or more logs is bisected until each leaf returns fewer than 1,000; only nonoverlapping leaf ranges contribute rows. Empty explorer ranges are retained as evidence. Independent Blockscout scans were attempted, but its unauthenticated quota returned HTTP 429. The source-comparison table states the exact block reached for each topic; a missing secondary history does not mean zero events. Within completed Blockscout ranges every event identity and payload is compared. Historical omissions and metadata differences are resolved against dRPC transaction receipts, which supply the canonical logs for each discrepant transaction. Every Ethereum topic also has independent dRPC `eth_getLogs` checks over deterministic single-block ranges spanning early, middle, recent and random populated blocks. Empty dRPC log queries timed out (HTTP 408), so sample ranges deliberately contain known events. A common omission by all checked sources cannot be ruled out; sample checks do not establish full independent coverage.

Tron: TronGrid scans each event from timestamp 0 through the same solidified head, with `only_confirmed=true`, limit 200, bounded min/max timestamps, and fingerprint paging to exhaustion. A second complete pass in descending order must reproduce every event identity and payload from the ascending pass. This checks paging, not independent indexer retention. TronScan's tested `/api/contract/events` endpoint ignored the event filter and returned ordinary token transfers; its total is not used. Full-history completeness remains bounded by TronGrid's indexed history.

Latest contract state: fixed-seed random samples of 20 addresses in each current blacklist, plus up to 10 cleared addresses per token, are checked using `isBlackListed(address)` for USDT and `isBlacklisted(address)` for USDC. All sampled results must match. Calls are latest state at request time; history ends at the finalized/solidified snapshot, so an intervening issuer action could produce a mismatch and requires a new refresh. The report contains every address and raw call reference.

| Chain/token | Event-derived currently blacklisted addresses | Latest checks (active / cleared) |
|---|---:|---:|
| ETH:USDC | 656 | 20 / 10 |
| ETH:USDT | 2,827 | 20 / 10 |
| TRX:USDT | 8,023 | 20 / 10 |

The current set is obtained by replaying additions and removals in chain order. A later addition after removal restores membership; destruction does not remove a blacklist entry. It is not the naive difference of all historical add/remove address sets. USDC also internally blacklists its own token contract during initialization without a `Blacklisted` event; that known storage entry is listed separately in `known_non_event_blacklists` and checked directly. Event-derived counts exclude this initialization-only entry.

| Chain/token/event | Primary logs | Secondary logs in checked range | Secondary through block | Canonical logs | Discrepant transactions receipt-checked |
|---|---:|---:|---:|---:|---:|
| ETH/USDT/AddedBlackList | 3,180 | 3179 | 26257132 | 3,180 | 14 |
| ETH/USDT/RemovedBlackList | 347 | 347 | 26257132 | 347 | 0 |
| ETH/USDT/DestroyedBlackFunds | 1,296 | 1291 | 26257132 | 1,296 | 18 |
| ETH/USDC/Blacklisted | 906 | 906 | 26257132 | 906 | 1 |
| ETH/USDC/UnBlacklisted | 226 | 226 | 26257132 | 226 | 0 |
| TRX/USDT/AddedBlackList | 9,035 | 9035 | 87369304 | 9,035 | 0 |
| TRX/USDT/RemovedBlackList | 988 | 988 | 87369304 | 988 | 0 |
| TRX/USDT/DestroyedBlackFunds | 1,270 | 1270 | 87369304 | 1,270 | 0 |

Independent Ethereum RPC log-range checks: 30 single-block ranges. Each range, expected count and raw reference is saved in `check_report.json.gz`. Source failures are saved under `errors/` and the earlier throttle probes under `probes/`.

Every discrepancy is preserved in `check_report.json.gz` with primary, secondary and receipt log counts and raw receipt references. Transactions with a source payload or log-index difference are also receipt-checked even when the counts agree.

| Transaction | Block | Etherscan / Blockscout / receipt logs |
|---|---:|---:|
| `0x4306ca74f91a3eed57ce2e7bfa0469f4c4b76fda3057f6a12b75b7f46dcd3072` | 10013656 | 1 / 2 / 1 |
| `0x496737f15798d738c6bf8e61d2a41682d8e1669faa2fed8240621751c32b8ce4` | 10226155 | 1 / 1 / 1 |
| `0x4fca7116151400fcf7b52191505d6d03c0d3a8c489748cd38922f8df2c79d3cf` | 9612542 | 1 / 2 / 1 |
| `0x50823b9c9178e805edae2b5dd83648177d253fbbac067b97d61334c035e9749d` | 9813180 | 1 / 0 / 1 |
| `0x54172c432473eb3244007f3d3a31e347c7bb36e41e84d3d59a540c95bbf9ce14` | 9800326 | 1 / 1 / 1 |
| `0x6d60d36af38b5bd8aa8a0db805e6ded08a332f9aa0e8e9b88cd522a9fc8d59ed` | 10013663 | 1 / 0 / 1 |
| `0x98e6ae0980e30b7d76f81bed308ffba08ff3b85763ec3cc1b32f54cedd6874c3` | 10013673 | 1 / 1 / 1 |
| `0xa0c0a75be09f1e8a9a0b5404cfae554602928eb3a879dcff1cd646d309153975` | 10265489 | 1 / 1 / 1 |
| `0xa5f7d005d760c44392a30e3c0d03f7190d7476ede12ec4a1fc466d969cf57388` | 10013690 | 1 / 1 / 1 |
| `0xae07a26268f9819135d8b4d88487c1ef6fafdafdfcac49d14c8773144385f0ac` | 9800322 | 1 / 0 / 1 |
| `0xc0110ab57b38ad0cf225aa713a686436414ef5e338e02a2177323c31cfd914e8` | 9851696 | 1 / 0 / 1 |
| `0xc47f85037499675c54947d56f9309cfdaa9ee63247f53893ad02d94f90d3f009` | 10013656 | 1 / 2 / 1 |
| `0xcb0eab0ba3bf67230d415e5d32a31cd099ac10dbac91a77748230a915ecc3977` | 10013659 | 1 / 1 / 1 |
| `0xd8ea4a26e5354f8660df8dd24bc46b7f260865cbc5f9e5069665934a0265d6d8` | 10013648 | 1 / 1 / 1 |
| `0x278f838561884cd6bfd5c19e4a36feff47b8c4836e6839e659a826e856267a39` | 10013673 | 1 / 1 / 1 |
| `0x3be63366eb16a1aad5879e84251e214779ae343700186bf48889f1d0c3f93936` | 9800329 | 1 / 1 / 1 |
| `0x49fe52fe93396e8439ba129d2e2ec1dc45c1b20a73e06d26120fa1f3c50f47fb` | 10013675 | 1 / 0 / 1 |
| `0x4cc1b80bc1231a9a1af5dfb91b40c0774ebbbc5235f0f8436215d29535457736` | 10013699 | 1 / 0 / 1 |
| `0x54649c384e8bfb7c80de7fe6be4a219bfa76688444634abe0bd5e1000b2a8abd` | 9800316 | 1 / 0 / 1 |
| `0x55d4b70ddbe107bacd9739d6c80b58f6a9b566861b045df7c70bbb8730b54125` | 9800319 | 1 / 0 / 1 |
| `0x5c6172bd89058564bfe83e95f6e261cab83326666b09757ca5a4c61f9bf6652e` | 10226156 | 1 / 1 / 1 |
| `0x9970dfed9dbadc843a773238d564fe36e62454b5aed3bc77c393a88b85a5eb9d` | 10013683 | 1 / 1 / 1 |
| `0xa240419652dba079f807c6afec030dd628e74da757db1cc686281bb017b064b8` | 9482849 | 1 / 0 / 1 |
| `0xa7a6d20e8f7b95bcf95cf9ae849149a1b2831be9f7b8bb887fed85bab190baa5` | 10013673 | 1 / 1 / 1 |
| `0xbf90f844c08344dbbc55263f798bbcc90ec69939b6143637051013653f759234` | 10226158 | 1 / 1 / 1 |
| `0xc1355de745f173e4c1c02048bc2e246440acc56438480a257164465d1fe943e8` | 10013681 | 1 / 1 / 1 |
| `0xdacd8546fcddf236c196ba28973d1d1e925fa74b051d0ef48e976b3e88c33769` | 10226161 | 1 / 2 / 1 |
| `0xe285b6877d4714006fd4b72263c6079c569b2e8bcafaad969b4890306d9ba55d` | 10013643 | 1 / 0 / 1 |
| `0xef93fc93090341cb8135896edf906979553d651a40b2e5400ccc76dd41eba07b` | 9800329 | 1 / 1 / 1 |
| `0xf9a80e2c6bbdd310691661df36690eee874b6d5f93c43e61e4bc302f91d10052` | 10013643 | 1 / 0 / 1 |
| `0xfd2db1c547ea0e0363cda576df9bf8a9813b3ee48af9876b2c77150d53c12b2d` | 9612556 | 1 / 2 / 1 |
| `0xfde5fb62afa539d747038580fa5277c5846949440b6e406c466c85848a8a7b72` | 10013673 | 1 / 1 / 1 |
| `0x15cbde1b9bf285db50e22eeff1a7d04ea267dd94726df8ecabdb4cb6c2b590cb` | 10274701 | 1 / 1 / 1 |

Across these disputed transactions, Blockscout omitted 11 receipt logs and supplied 5 extra log entries. Etherscan matched the receipts for 33 of 33 disputed transactions. Equal-count rows in this table reflect payload or index differences rather than a count gap.

## Balances and destruction

Historical `balanceOf` was attempted for 40 randomly selected Ethereum freeze logs; 40 succeeded. Successful values are end-of-freeze-block balances, which can differ from the exact pre-log balance if another transaction in that block moved funds. Unavailable values remain blank, never zero. Tron historical balances are not supplied by the public constant-contract API.

`DestroyedBlackFunds` amounts are decoded exactly with 6 decimals. They describe the balance destroyed immediately before that destruction call; they are not automatically the balance at the earlier freeze, because an address can receive additional funds while blacklisted. No burn amount is relabelled as an earlier freeze balance. `balance_at_freeze` is populated only by the explicitly labelled historical balance call.

## Circle burn/clawback review

The verified proxy source response `data/raw/freezes/contract_review/ac859002c7c3aefa7377a08b4b96541b59cea0f0262409ca167a66851a0be2d0.json.gz` identifies implementation `0x43506849D7C04F9138D1A2050bbF3A0c054402dd` (`FiatTokenV2_2`). Its full verified source/ABI is saved at `data/raw/freezes/contract_review/f88df9f50f4b09ad93068ee46a9268cf6b017c14e756eaadf934ada7e62c1c55.json.gz`. In `contracts/v1/FiatTokenV1.sol`, `burn(uint256)` (lines 360–374) is restricted to an unblacklisted minter and subtracts from `msg.sender`'s own balance. The ABI has no `destroyBlackFunds`, `wipeBlacklistedAddress`, or clawback function. `Rescuable.rescueERC20` transfers tokens held by the token contract; it cannot debit arbitrary frozen holders. V2.2's `_setBalance` also rejects blacklisted accounts. Accordingly no direct frozen-account destruction mechanism was found in the currently verified implementation. This is a code-level conclusion about the checked implementation, not a claim about future proxy upgrades or off-chain redemption/legal processes.

Ordinary USDC `Burn` events are minter burns, not evidence of frozen-fund seizure, and are intentionally excluded from the freeze table. V2.1 initialization transfers tokens accidentally held by the token contract to `lostAndFound` before internally blacklisting the contract itself; it is not a general clawback of frozen holders. The source snippets and the direct self-blacklist call are reproducible from the report's references.

## Reproduction and incremental operation

```sh
.venv/bin/python -S scripts/freezes/fetch_freezes.py --refresh
.venv/bin/python -S scripts/freezes/fetch_freezes.py --check
```

Only Python's standard library is required. `--check` makes no network requests and asserts byte-for-byte CSV agreement, source comparisons and receipt reconciliation, contiguous ranges, state-call evidence, and the saved count report. `--refresh` resumes unfinished snapshots, caches requests by credential-free URL/body, and then scans only blocks beyond each source/topic's completed range. Tron uses timestamps after the last completed solidified block. Fixed finalized snapshots avoid ordinary short reorganizations. A nonblocking `flock` prevents overlapping invocations; outputs/state are atomic replacements. A failed fetch leaves completed checkpoints intact and never publishes a partial replacement table. Etherscan requests are spaced at least 0.85 seconds apart (below 1.5 requests/second); HTTP 429 and transient errors back off. API keys are loaded at runtime and never included in raw metadata or error strings.

`data/raw/freezes/state.json.gz` is the saved scan manifest. Every row references a gzipped request/response envelope, and `data/raw/freezes/check_report.json.gz` holds counts, current address sets, sample calls, and CSV hash. Ethereum `log_index` is the block-wide receipt log index; Tron uses TronGrid's transaction-local `event_index`. A unique row is identified by chain, token, transaction hash and log index. Tron addresses are Base58Check strings with their equivalent 20-byte hex also supplied; Ethereum addresses are lowercase hex. Earlier probes remain under `probes/` and are not silently merged into the event table. Interrupted/bisected query responses may be cached but only manifest-listed leaves are counted.

Development validation, including two incremental refresh outputs, CSV hashes, the overlapping-run lock check and unit-test output, is saved in `data/raw/freezes/execution_validation.json.gz`.

## Other chains

Stretch chains were not collected: native USDC on Arbitrum, Base, Polygon, Avalanche and Optimism; other USDT deployments; and Solana freeze-authority instructions. Their histories and blacklist sets are unknown in this output. Bridged token contracts are not interchangeable with issuer-native deployments. This table must not be presented as an all-chain inventory.
