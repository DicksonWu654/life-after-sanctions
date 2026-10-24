"""Rebuild the destination-label CSV and SQLite index offline from frozen sources."""
from __future__ import annotations

import argparse
import collections
import csv
import gzip
import hashlib
import io
import json
import re
import sqlite3
import tempfile
from html.parser import HTMLParser
from pathlib import Path

try:
    from .policy import CHAIN_IDS, CHAIN_NAMES, CLASSES, EVM, classify, normalize_address, normalize_chain
    from .sources import ROOT
except ImportError:
    from policy import CHAIN_IDS, CHAIN_NAMES, CLASSES, EVM, classify, normalize_address, normalize_chain
    from sources import ROOT

OUT = ROOT / "data/labels"
FIELDS = ["chain", "address_normalized", "label", "class", "entity_name", "label_source", "source_ref",
          "confidence", "notes", "source_id", "source_url", "raw_ref", "evidence_locator", "license",
          "valid_from", "valid_to"]


def read_raw(file: dict) -> str:
    payload = gzip.decompress((ROOT / file["raw_ref"]).read_bytes())
    if hashlib.sha256(payload).hexdigest() != file["sha256"]:
        raise ValueError(f"Raw digest mismatch: {file['raw_ref']}")
    return payload.decode("utf-8-sig")


def object_at(text: str, start: int) -> tuple[str, int]:
    """Find one balanced literal object; data only, no JavaScript interpreter/eval."""
    start = text.index("{", start)
    depth, quote, escaped, line_comment, block_comment = 0, "", False, False, False
    for index in range(start, len(text)):
        char = text[index]
        following = text[index:index + 2]
        if line_comment:
            line_comment = char != "\n"
            continue
        if block_comment:
            if text[index - 1:index + 1] == "*/":
                block_comment = False
            continue
        if quote:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = ""
            continue
        if following == "//":
            line_comment = True
        elif following == "/*":
            block_comment = True
        elif char in "\"'`":
            quote = char
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[start:index + 1], index + 1
    raise ValueError("Unbalanced data object")


class Tables(HTMLParser):
    """Extract HTML table cells, excluding scripts and serialized hydration data."""
    def __init__(self):
        super().__init__()
        self.tables, self.table, self.row, self.cell = [], None, None, None

    def handle_starttag(self, tag, attrs):
        if tag == "table":
            self.table = []
        elif tag == "tr" and self.table is not None:
            self.row = []
        elif tag in ("td", "th") and self.row is not None:
            self.cell = []

    def handle_data(self, data):
        if self.cell is not None:
            self.cell.append(data)

    def handle_endtag(self, tag):
        if tag in ("td", "th") and self.cell is not None:
            self.row.append("".join(self.cell).strip())
            self.cell = None
        elif tag == "tr" and self.row is not None:
            self.table.append(self.row)
            self.row = None
        elif tag == "table" and self.table is not None:
            self.tables.append(self.table)
            self.table = None


class Builder:
    def __init__(self):
        self.manifest = json.loads((OUT / "sources.json").read_text())
        self.sources = {s["source_id"]: s for s in self.manifest["sources"]}
        self.rows = []
        self.omitted = collections.Counter()

    def add(self, source: dict, file: dict, chain: str, address: str, name: str, role: str,
            confidence: str, notes: str, locator: dict, *, entity: str = "", valid_from="", valid_to=""):
        chain = normalize_chain(chain)
        address = normalize_address(chain, address)
        if not address or not name or (source["source_id"] != "ofac" and chain in EVM and not re.fullmatch(r"0x[0-9a-f]{40}", address)):
            self.omitted["invalid_or_empty_address_or_name"] += 1
            return
        if chain in EVM and address == "0x" + "0" * 40:
            self.omitted["zero_address"] += 1
            return
        self.rows.append(dict(zip(FIELDS, [chain, address, name, role, entity or name,
            source["name"] + " @ " + source["revision"], file["raw_ref"], confidence, notes,
            source["source_id"], file["url"], file["raw_ref"], json.dumps(locator, separators=(",", ":")),
            source["license"], valid_from, valid_to])))

    def ofac(self):
        source = self.sources["ofac"]
        addresses_file, ledger_file = source["files"]
        addresses = list(csv.DictReader(io.StringIO(read_raw(addresses_file))))
        ledger = list(csv.DictReader(io.StringIO(read_raw(ledger_file))))
        names = collections.defaultdict(list)
        for row in ledger:
            names[row["address_normalized"]].append(row)
        for index, row in enumerate(addresses):
            members = names[row["address_normalized"]]
            seen = set()
            for member in members:
                if member["sdn_uid"] in seen:
                    continue
                seen.add(member["sdn_uid"])
                name = member["sdn_name"]
                notes = (f"OFAC ledger entity UID {member['sdn_uid']}; chain comes from addresses.csv. "
                         f"Listed {member['listed_date'] or 'date unresolved'}; "
                         f"current_in_sdn={member.get('current_in_sdn', 'unresolved')}; "
                         f"delisted={member.get('delisted_date') or 'not recorded'}. "
                         f"Ledger address_valid={member.get('address_valid', 'unrecorded')}; malformed input addresses are retained verbatim, never repaired. "
                         f"Upstream evidence: {member['raw_ref']}; {member['source_url']}. "
                         "Historical list membership is not a claim of current sanctions or address control.")
                locator = {"kind": "ofac", "index": index, "entity_uid": member["sdn_uid"],
                           "ledger_ref": ledger_file["raw_ref"]}
                self.add(source, addresses_file, row["chain"], row["address_normalized"],
                         "OFAC listed: " + name, "other_sanctioned", "high", notes, locator, entity=name,
                         valid_from=member["listed_date"], valid_to=member.get("delisted_date", ""))
                # Exact OFAC service names; not blockchain clustering or inferred ownership.
                if re.fullmatch(r"(?:BLENDER\.IO|SINBAD(?:\.IO)?)", name, re.I):
                    self.add(source, addresses_file, row["chain"], row["address_normalized"], name,
                             "mixer", "high", notes + " Mixer service expressly named by OFAC.", locator, entity=name,
                             valid_from=member["listed_date"], valid_to=member.get("delisted_date", ""))
            if not members:
                raise ValueError(f"OFAC address has no entity record: {row['address_normalized']}")

    def open_sets(self):
        brian = self.sources["brian"]
        explorer_chains = {"etherscan": "ETH", "arbiscan": "ARB", "avalanche": "AVAX", "bscscan": "BSC",
                           "ftmscan": "FTM", "optimism": "OP", "polygonscan": "POLYGON"}
        for file in brian["files"]:
            chain = explorer_chains[file["path"].split("/")[1]]
            for address, record in json.loads(read_raw(file)).items():
                result = classify(record.get("name", ""), record.get("labels", []))
                if result:
                    role, confidence, notes = result
                    self.add(brian, file, chain, address, record["name"], role, confidence,
                             notes + " Source tags: " + ", ".join(record.get("labels", [])) +
                             ". Third-party snapshot from 2023; no temporal ownership guarantee.",
                             {"kind": "json_label", "key": address})
                else:
                    self.omitted["brian_out_of_scope_or_unnamed"] += 1
        daws = self.sources["daws"]
        for file in daws["files"]:
            # Aggregate categories per exact address/name so one source's repeated tags do not multiply rows.
            groups = collections.defaultdict(list)
            rows = list(csv.DictReader(io.StringIO(read_raw(file))))
            for index, row in enumerate(rows):
                if int(row["chainId"]) not in CHAIN_IDS:
                    self.omitted["daws_unsupported_chain"] += 1
                    continue
                groups[(row["chainId"], row["address"], row["nameTag"])].append(index)
            claims_by_address_name = collections.defaultdict(set)
            for chain, address, name in groups:
                claims_by_address_name[(address.lower(), name)].add(chain)
            for (chain, address, name), indexes in groups.items():
                tags = sorted({rows[i]["label"] for i in indexes})
                result = classify(name, tags)
                if result:
                    role, confidence, notes = result
                    repeated_chains = claims_by_address_name[(address.lower(), name)]
                    if len(repeated_chains) > 1:
                        confidence = "low"
                        notes += " Same address/name occurs on multiple source chain IDs (" + ",".join(sorted(repeated_chains)) + "); chain-specific operation is unverified."
                    self.add(daws, file, chain, address, name, role, confidence,
                             notes + " Source tags: " + ", ".join(tags) + ".",
                             {"kind": "csv_label", "indexes": indexes})
                else:
                    self.omitted["daws_out_of_scope_or_unnamed"] += 1

    def tornado(self):
        source = self.sources["tornado"]
        file = source["files"][0]
        text = read_raw(file)
        supported = set(CHAIN_IDS)
        for match in re.finditer(r"\bnetId(\d+):\s*\{", text):
            chain_id = int(match[1])
            if chain_id not in supported:
                continue
            block, end = object_at(text, match.start())
            for asset in re.finditer(r"\b(\w+):\s*\{\s*instanceAddress:\s*\{([^}]+)\}", block):
                for pool in re.finditer(r"'([^']+)'\s*:\s*'(0x[0-9a-fA-F]{40})'", asset[2]):
                    name = f"Tornado Cash: {pool[1]} {asset[1]} pool"
                    self.add(source, file, str(chain_id), pool[2], name, "mixer", "high",
                             "Official classic UI instanceAddress; mainnet only. Token, multicall, registry, governance and testnet addresses excluded.",
                             {"kind": "tornado_pool", "network": chain_id, "asset": asset[1], "denomination": pool[1]}, entity="Tornado Cash")
            for router in re.finditer(r"'(tornado-(?:router|proxy-light)\.contract\.tornadocash\.eth)'\s*:\s*'(0x[0-9a-fA-F]{40})'", block):
                self.add(source, file, str(chain_id), router[2], "Tornado Cash: " + router[1], "mixer", "high",
                         "Official mainnet router/proxy configuration; function and current operation are not independently verified.",
                         {"kind": "tornado_router", "network": chain_id, "key": router[1]}, entity="Tornado Cash")

    def railgun(self):
        source = self.sources["railgun"]
        file = source["files"][0]
        text = read_raw(file)
        for field in ("RailgunProxyContract", "RelayAdaptContract", "RailgunTokenVaultV3Contract"):
            marker = re.search(r"export const " + field + r"\b[^=]*=\s*\{", text)
            if not marker:
                continue
            block, _ = object_at(text, marker.start())
            for match in re.finditer(r"\[NetworkName\.(Ethereum|BNBChain|Polygon|Arbitrum)\]:\s*'(0x[0-9a-fA-F]{40})'", block):
                chain = CHAIN_NAMES[match[1].lower()]
                self.add(source, file, chain, match[2], "RAILGUN: " + field, "mixer", "high",
                         "Official privacy-protocol mainnet proxy/relay/vault. Mixer is the research taxonomy, not a sanctions designation.",
                         {"kind": "railgun", "field": field, "network": match[1]}, entity="RAILGUN")

    def hop(self):
        source = self.sources["hop"]
        file = source["files"][0]
        text = read_raw(file)
        block, _ = object_at(text, text.index("bridges:"))
        # Only the protocol's own bridge/AMM-wrapper contracts; exclude canonical tokens and all bonders.
        pattern = r"(?:'([^']+)'|(\w+)):\s*\{"
        for asset in re.finditer(r"^    " + pattern, block, re.M):
            asset_name = asset[1] or asset[2]
            asset_block, _ = object_at(block, asset.start())
            for network in re.finditer(r"^      (\w+):\s*\{", asset_block, re.M):
                network_name = network[1]
                if network_name not in CHAIN_NAMES:
                    continue
                network_block, _ = object_at(asset_block, network.start())
                for match in re.finditer(r"\b(l1Bridge|l2Bridge|l2AmmWrapper|cctpL1Bridge|cctpL2Bridge):\s*'(0x[0-9a-fA-F]{40})'", network_block):
                    # l1* fields always live on Ethereum, even inside a child network's config.
                    chain = "ETH" if match[1] in ("l1Bridge", "cctpL1Bridge") else CHAIN_NAMES[network_name]
                    self.add(source, file, chain, match[2], f"Hop: {asset_name} {match[1]}", "bridge", "high",
                             "Official mainnet SDK bridge/wrapper field. Canonical token fields, bonders and third-party canonical gateways excluded.",
                             {"kind": "hop", "asset": asset_name, "network": network_name, "field": match[1]}, entity="Hop")

    def wormhole(self):
        source = self.sources["wormhole"]
        file = source["files"][0]
        text = read_raw(file).split('"Testnet"')[0]
        for match in re.finditer(r'\["(\w+)",\s*"([^"\n]+)"\]', text):
            chain = CHAIN_NAMES.get(match[1].lower())
            if not chain:
                self.omitted["wormhole_chain_outside_supported_address_schemas"] += 1
                continue
            self.add(source, file, chain, match[2], "Wormhole: tokenBridgeContracts", "bridge", "high",
                     "Official SDK mainnet token bridge contract/program; testnet and devnet excluded.",
                     {"kind": "wormhole", "network": match[1]}, entity="Wormhole")

    def across(self):
        source = self.sources["across"]
        file = source["files"][0]
        for chain_id, chain in json.loads(read_raw(file))["chains"].items():
            if int(chain_id) not in CHAIN_IDS:
                continue
            for field, contract in chain.get("contracts", {}).items():
                if not (field in ("HubPool", "SpokePool", "SpokePoolPeriphery") or field.endswith(("_SpokePool", "_SwapAndBridge"))):
                    continue
                self.add(source, file, chain_id, contract["address"], "Across: " + field, "bridge", "high",
                         "Official mainnet deployed-addresses registry; deployment block " + str(contract.get("block_number", "unrecorded")) + ".",
                         {"kind": "across", "chain_id": chain_id, "field": field}, entity="Across")

    def canonical(self):
        source = self.sources["op_registry"]
        file = source["files"][0]
        registry = json.loads(read_raw(file))
        for chain_id, name in (("10", "OP Mainnet"), ("8453", "Base")):
            for field in ("L1StandardBridgeProxy", "L1ERC721BridgeProxy", "OptimismPortalProxy", "EthLockboxProxy"):
                if field in registry.get(chain_id, {}):
                    self.add(source, file, "ETH", registry[chain_id][field], f"{name}: {field}", "bridge", "high",
                             "Official superchain registry. L1 address is on Ethereum, not the destination L2. Historical versions may differ.",
                             {"kind": "op_registry", "chain_id": chain_id, "field": field}, entity=name)
        source = self.sources["arbitrum"]
        file = source["files"][0]
        text = read_raw(file)
        for marker in ("mainnetTokenBridge", "mainnetETHBridge"):
            block, _ = object_at(text, text.index("const " + marker))
            for match in re.finditer(r"\b(\w+):\s*'(0x[0-9a-fA-F]{40})'", block):
                field, address = match.groups()
                if marker == "mainnetTokenBridge" and not re.search(r"Gateway(?:Router)?$", field):
                    continue
                if marker == "mainnetETHBridge" and field not in ("bridge", "inbox", "outbox"):
                    continue
                chain = "ARB" if field.startswith("child") else "ETH"
                self.add(source, file, chain, address, "Arbitrum One: " + field, "bridge", "high",
                         "Official mainnet SDK registry; parent fields are Ethereum, child fields Arbitrum. Admins, WETH token and sequencer infrastructure excluded.",
                         {"kind": "arbitrum", "object": marker, "field": field}, entity="Arbitrum One")

    def tronscan(self):
        source = self.sources["tronscan"]
        for file in source["files"]:
            envelope = json.loads(read_raw(file))
            response = envelope.get("response", {})
            if not isinstance(response, dict) or envelope.get("http_status") != 200:
                self.omitted["tronscan_unsuccessful_response"] += 1
                continue
            # Account name can be self-selected, and tokens' names describe their issuers, not their holders.
            found = False
            for field in ("addressTag", "publicTag"):
                value = response.get(field)
                if isinstance(value, str) and value.strip():
                    found = True
                    self.add(source, file, "TRX", response["address"], value, "unknown_service", "low",
                             "Explorer public tag only; role and controller unverified. Account names/token names are not used.",
                             {"kind": "tronscan", "field": field})
            if not found:
                self.omitted["tronscan_no_usable_public_tag"] += 1

    def walletexplorer(self):
        source = self.sources["walletexplorer"]
        for file in source["files"]:
            payload = json.loads(read_raw(file))
            if not payload.get("found") or not payload.get("label"):
                self.omitted["walletexplorer_cluster_not_found"] += 1
                continue
            name = payload["label"]
            is_mixer = name in ("HelixMixer", "BitcoinFog", "BitMixer.io")
            for index, address in enumerate(payload.get("addresses", [])):
                self.add(source, file, "BTC", address["address"], name, "mixer" if is_mixer else "unknown_service", "low",
                         f"WalletExplorer heuristic co-spend cluster {payload['wallet_id']}; first 100 addresses only of "
                         f"{payload.get('addresses_count', 'unreported')} cluster addresses. Role is not evidence of hot/deposit function. "
                         "FAQ says names are generally not updated since 2016; website aliases may be newer. Historical control unverified.",
                         {"kind": "walletexplorer", "index": index}, entity=name)

    def uniswap(self):
        source = self.sources["uniswap"]
        networks = {"ethereum": "ETH", "arbitrum": "ARB", "optimism": "OP", "polygon": "POLYGON",
                    "base": "BASE", "bsc": "BSC", "avalanche": "AVAX"}
        allowed = {"UniswapV3Factory", "SwapRouter", "SwapRouter02", "UniversalRouter", "NonfungiblePositionManager"}
        for file in source["files"]:
            parser = Tables()
            parser.feed(read_raw(file))
            for table_index, table in enumerate(parser.tables):
                if not table or table[0][0] != "Contract" or len(table[0]) < 2:
                    continue
                # Reviewed official pages place this network's mainnet in column 1,
                # followed by explicitly named Sepolia columns where present.
                mainnet_col = 1
                if "sepolia" in table[0][mainnet_col].lower():
                    raise ValueError("Unexpected testnet column in deployment table")
                for row_index, row in enumerate(table):
                    if not row or row[0] not in allowed or len(row) <= mainnet_col:
                        continue
                    address = row[mainnet_col].strip("`")
                    if not re.fullmatch(r"0x[0-9a-fA-F]{40}", address):
                        continue
                    self.add(source, file, networks[file["path"]], address, "Uniswap: " + row[0], "dex", "high",
                             "Official deployment table mainnet column only; Sepolia/testnet columns and shared multicall/Permit2 excluded.",
                             {"kind": "html_table", "table": table_index, "row": row_index, "column": mainnet_col,
                              "contract": row[0]}, entity="Uniswap")

    def official_web(self):
        source = self.sources["sun"]
        for file in source["files"]:
            parser = Tables()
            parser.feed(read_raw(file))
            for table_index, table in enumerate(parser.tables):
                if not table or table[0] != ["", "Chain", "Address"]:
                    continue
                for row_index, row in enumerate(table):
                    if len(row) != 3 or row[1] != "TRON" or not row[0]:
                        continue
                    self.add(source, file, "TRX", row[2], "SUN.io " + file["path"].split("/")[0] + ": " + row[0],
                             "dex", "high", "Official SUN.io TRON mainnet contract table; NILE testnet excluded.",
                             {"kind": "html_table", "table": table_index, "row": row_index, "column": 2,
                              "contract": row[0]}, entity="SUN.io")
        source = self.sources["stargate"]
        for file in source["files"]:
            text = read_raw(file)
            current_chain = None
            current_heading = ""
            heading_map = {"Ethereum": "ETH", "BNB Chain": "BSC", "Avalanche": "AVAX", "Polygon": "POLYGON",
                           "Arbitrum": "ARB", "Optimism": "OP", "Fantom": "FTM", "Base": "BASE"}
            for line_index, line in enumerate(text.splitlines()):
                if line.startswith("### "):
                    current_heading = line[4:].replace("\u200b", "").strip()
                    current_chain = heading_map.get(current_heading)
                if not current_chain:
                    continue
                match = re.search(r"\* `([^`]+):`\s*\[`(0x[0-9a-fA-F]{40})`\]", line)
                if not match:
                    continue
                field, address = match.groups()
                if not (field.lstrip("*") in ("Router.sol", "RouterETH.sol", "Bridge.sol", "StargateComposer.sol", "WidgetSwap.sol")
                        or field.startswith("Pool.sol")):
                    continue
                self.add(source, file, current_chain, address, "Stargate: " + field, "bridge", "high",
                         "Official legacy/v1 mainnet contract list. LayerZero chainId is not an EVM chain ID; network comes from the section heading. Current operation unverified.",
                         {"kind": "markdown_line", "line": line_index, "heading": current_heading, "field": field}, entity="Stargate")
        source = self.sources["base"]
        file = source["files"][0]
        parser = Tables()
        parser.feed(read_raw(file))
        # These exact snapshot tables were reviewed against Mainnet and Sepolia headings.
        # Table 0 = Base mainnet L2; table 2 = Ethereum mainnet L1. Tables 1/3 are Sepolia.
        for table_index, chain, allowed in ((0, "BASE", {"L2StandardBridge", "L2ERC721Bridge", "L2ToL1MessagePasser"}),
                                             (2, "ETH", {"L1StandardBridge", "L1ERC721Bridge", "OptimismPortal"})):
            table = parser.tables[table_index]
            if table[0] != ["Name", "Address"]:
                raise ValueError("Unexpected Base documentation structure")
            for row_index, row in enumerate(table):
                if len(row) == 2 and row[0] in allowed:
                    self.add(source, file, chain, row[1], "Base: " + row[0], "bridge", "high",
                             "Official Base mainnet contract table. L1 contracts live on Ethereum; L2 contracts on Base. Sepolia tables excluded.",
                             {"kind": "html_table", "table": table_index, "row": row_index, "column": 1,
                              "contract": row[0]}, entity="Base")
        source = self.sources["etherscan_public"]
        for file in source["files"]:
            text = read_raw(file)
            title = re.search(r"<title[^>]*>([\s\S]*?)</title>", text, re.I)
            if not title:
                raise ValueError("Explorer has no title")
            title = " ".join(title[1].split())
            if " | Address:" not in title:
                raise ValueError("Explorer title is not a labelled address page")
            name = title.split(" | Address:")[0]
            if name != file["expected_label"]:
                raise ValueError("Explorer label changed; review the source before accepting it")
            notes = ("Public Etherscan name tag independently checked on Ethereum. "
                     "Explicit Bitget Deposit label; the public tooltip expands the displayed 'Dep:' abbreviation." if file["class"] == "cex_deposit" else
                     "Public Etherscan name tag independently checked on Ethereum. eXch service-type/mixer taxonomy is not established by this name tag; no CEX or mixer role inferred.")
            self.add(source, file, "ETH", file["path"], name, file["class"], "medium", notes,
                     {"kind": "html_title", "title": title}, entity=name)
        source = self.sources["avalanche_bridge"]
        file = source["files"][0]
        text = read_raw(file)
        for chain, address, href in (
            ("ETH", "0x8eb8a3b98659cce290402893d0123abb75e3ab28", "https://etherscan.io/address/0x8eb8a3b98659cce290402893d0123abb75e3ab28"),
            ("AVAX", "0xeb1bb70123b2f43419d070d7fde5618971cc2f8f", "https://subnets.avax.network/c-chain/address/0xeb1bb70123b2f43419d070d7fde5618971cc2f8f"),
        ):
            if 'href="' + href + '"' not in text:
                raise ValueError("Official Avalanche bridge link changed")
            self.add(source, file, chain, address, "Avalanche Bridge", "bridge", "high",
                     "Official Avalanche Bridge FAQ links this address on the named network's explorer. Bridge address/vault lead; no historical-operation inference.",
                     {"kind": "official_link", "href": href}, entity="Avalanche Bridge")

    def thorchain(self):
        source = self.sources["thorchain"]
        file = source["files"][0]
        supported = EVM | {"BTC", "BCH", "LTC", "DOGE", "XRP", "TRX", "SOL"}
        for index, record in enumerate(json.loads(read_raw(file))):
            chain = normalize_chain(record["chain"])
            if chain not in supported:
                self.omitted["thorchain_unsupported_address_schema"] += 1
                continue
            for field in ("address", "router"):
                if not record.get(field):
                    continue
                self.add(source, file, chain, record[field], "THORChain: " + ("inbound vault" if field == "address" else "router"),
                         "bridge", "high", f"Current inbound-address API field {field}, observed {file.get('retrieved_at', 'see request metadata')}; "
                         f"halted={record.get('halted', 'unreported')}. Vaults rotate: this snapshot establishes no historical validity interval. "
                         "Use only as a current endpoint lead until transaction-time evidence is checked. API gateway is linked by official THORChain developer documentation.",
                         {"kind": "thorchain", "index": index, "field": field}, entity="THORChain")

    def build(self):
        for method in (self.ofac, self.open_sets, self.tornado, self.railgun, self.hop, self.wormhole,
                       self.across, self.canonical, self.tronscan, self.walletexplorer, self.uniswap, self.official_web,
                       self.thorchain):
            method()
        unique = {tuple(row[field] for field in FIELDS): row for row in self.rows}
        return sorted(unique.values(), key=lambda row: (row["chain"], row["address_normalized"], row["source_id"], row["label"], row["class"]))


def csv_bytes(rows: list[dict]) -> bytes:
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=FIELDS)
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue().encode()


def index_rows(rows: list[dict]) -> list[dict]:
    """The frozen base CSV plus evidence-linked supplemental rows; no overrides."""
    extra = OUT / "labels_extra.csv"
    if not extra.exists():
        return rows
    with extra.open(newline="") as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames != FIELDS:
            raise ValueError("labels_extra.csv schema differs from base labels")
        supplemental = list(reader)
    for row in supplemental:
        if not row["label_source"] or not row["source_ref"] or row["source_ref"] != row["raw_ref"]:
            raise ValueError("Supplemental labels require exact raw provenance")
        if not (ROOT / row["raw_ref"].split("#", 1)[0]).is_file():
            raise ValueError("Supplemental raw evidence is missing")
        if row["chain"] != normalize_chain(row["chain"]) or row["address_normalized"] != normalize_address(row["chain"], row["address_normalized"]):
            raise ValueError("Supplemental address is not normalized")
        if row["class"] not in CLASSES:
            raise ValueError("Unknown supplemental class")
    unique = {tuple(row[field] for field in FIELDS): row for row in rows + supplemental}
    return sorted(unique.values(), key=lambda row: (row["chain"], row["address_normalized"], row["source_id"], row["label"], row["class"]))


def build_index(rows: list[dict], csv_digest: str):
    path = OUT / "labels.sqlite"
    # Separate builders may run in parallel; only the completed database rename
    # is shared. An existing reader keeps its original file descriptor.
    with tempfile.NamedTemporaryFile(dir=OUT, prefix=".labels-", suffix=".sqlite.tmp", delete=False) as handle:
        temporary = Path(handle.name)
    indexed = index_rows(rows)
    with sqlite3.connect(temporary) as connection:
        fields = ", ".join('"' + field + '" TEXT NOT NULL' for field in FIELDS)
        connection.execute("CREATE TABLE labels (" + fields + ")")
        connection.executemany("INSERT INTO labels VALUES (" + ",".join("?" for _ in FIELDS) + ")",
                               [[row[field] for field in FIELDS] for row in indexed])
        connection.execute("CREATE INDEX labels_chain_address ON labels(chain, address_normalized)")
        connection.execute("CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        connection.executemany("INSERT INTO metadata VALUES (?,?)", [("csv_sha256", csv_digest), ("schema_version", "1")])
        extra = OUT / "labels_extra.csv"
        if extra.exists():
            connection.execute("INSERT INTO metadata VALUES (?,?)", ("extras_sha256", hashlib.sha256(extra.read_bytes()).hexdigest()))
        if connection.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise ValueError("New label index failed integrity check")
    temporary.replace(path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Recompute and compare CSV and all index rows without network or writes")
    args = parser.parse_args()
    builder = Builder()
    rows = builder.build()
    payload = csv_bytes(rows)
    digest = hashlib.sha256(payload).hexdigest()
    if args.check:
        assert (OUT / "labels.csv").read_bytes() == payload, "CSV differs from frozen-source rebuild"
        with sqlite3.connect(f"file:{OUT / 'labels.sqlite'}?mode=ro", uri=True) as connection:
            assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
            assert connection.execute("SELECT value FROM metadata WHERE key='csv_sha256'").fetchone()[0] == digest
            stored = connection.execute("SELECT * FROM labels ORDER BY rowid").fetchall()
            assert stored == [tuple(row[field] for field in FIELDS) for row in index_rows(rows)], "Index rows differ"
            extra = OUT / "labels_extra.csv"
            if extra.exists():
                assert connection.execute("SELECT value FROM metadata WHERE key='extras_sha256'").fetchone()[0] == hashlib.sha256(extra.read_bytes()).hexdigest()
        print(json.dumps({"check": "passed", "label_rows": len(rows), "csv_sha256": digest}))
    else:
        if not (OUT / "labels.csv").exists() or (OUT / "labels.csv").read_bytes() != payload:
            (OUT / "labels.csv").write_bytes(payload)
        build_index(rows, digest)
        (OUT / "build_stats.json").write_text(json.dumps({"label_rows": len(rows), "csv_sha256": digest,
            "unique_chain_addresses": len({(r['chain'], r['address_normalized']) for r in rows}),
            "by_source": dict(collections.Counter(row["source_id"] for row in rows)),
            "omitted": dict(builder.omitted)}, indent=2) + "\n")
        print(json.dumps({"label_rows": len(rows), "csv_sha256": digest}))


if __name__ == "__main__":
    main()
