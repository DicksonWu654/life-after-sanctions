"""Conservative, source-based role mapping. This never infers address ownership."""
import re

CHAIN_IDS = {1: "ETH", 10: "OP", 56: "BSC", 100: "GNO", 137: "POLYGON", 250: "FTM",
             480: "WORLD", 8453: "BASE", 42161: "ARB", 42170: "ARB_NOVA", 42220: "CELO",
             43114: "AVAX", 59144: "LINEA", 1101: "POLYGON_ZKEVM"}
CHAIN_NAMES = {"ethereum": "ETH", "optimism": "OP", "bsc": "BSC", "bnbchain": "BSC",
               "polygon": "POLYGON", "arbitrum": "ARB", "gnosis": "GNO", "base": "BASE",
               "avalanche": "AVAX", "celo": "CELO", "solana": "SOL", "nova": "ARB_NOVA",
               "linea": "LINEA", "polygonzk": "POLYGON_ZKEVM", "worldchain": "WORLD"}
ALIASES = {"ETHEREUM": "ETH", "MAINNET": "ETH", "BITCOIN": "BTC", "TRON": "TRX",
           "ARBITRUM": "ARB", "OPTIMISM": "OP", "BINANCE-SMART-CHAIN": "BSC", "AVALANCHE": "AVAX",
           "MATIC": "POLYGON", "GNOSIS": "GNO", "SOLANA": "SOL"}
EVM = set(CHAIN_IDS.values()) | {"ETC"}
BASE_CLASSES = ("mixer", "bridge", "dex", "cex_deposit", "cex_hot", "other_sanctioned", "defi_other",
           "issuer", "scam_poisoning", "unknown_service")
# Additional Round 2 taxonomy; retain the frozen Round 1 report's class columns.
ADDITIONAL_CLASSES = ("government_seizure",)
CLASSES = BASE_CLASSES + ADDITIONAL_CLASSES
DEX_TAGS = {"dex", "uniswap", "sushiswap", "pancakeswap", "curve-fi", "curve-finance", "1inch",
            "0x-protocol", "0x-protocol-ecosystem", "balancer", "bancor", "kyberswap", "airswap",
            "sun-swap", "sunswap", "burgerswap", "bscswap", "quickswap", "trader-joe", "dodo"}
DEFI_TAGS = {"aave", "compound", "maker", "sky", "lido", "yearn", "defi", "synthetix", "pendle",
             "cream-finance", "morpho", "euler", "convex-finance", "curve-finance", "curve-fi"}
CEX_TAGS = {"exchange", "binance", "coinbase", "kraken", "bitfinex", "bitstamp", "kucoin", "okx",
            "okex", "huobi", "htx", "bithumb", "bitget", "bybit", "gate-io", "gateio", "gemini",
            "poloniex", "mexc", "crypto-com", "crypto.com", "deribit", "bilaxy", "upbit", "bitflyer",
            "bitvavo", "bitmart", "bittrex", "cex-io", "ascendex", "bitmex", "coinex", "btse",
            "whitebit", "blofin-exchange", "catex", "lbank", "zb-com", "hotbit", "coinhako"}
BRIDGE_TAGS = {"bridge", "multichain", "hop-protocol", "stargate", "wormhole", "across-protocol",
               "bittorrent", "bttc", "thorchain", "avalanche-bridge", "arbitrum", "optimism"}
BRIDGE_NAMES = re.compile(r"\b(wormhole|portal|multichain|anyswap|stargate|across|hop|thorchain|bttc|"
                          r"bittorrent|avalanche(?::)? bridge|arbitrum|optimism|base:.*bridge|celer|cbridge|"
                          r"synapse|connext|polygon.*(?:bridge|predicate|root chain))\b", re.I)
ADMIN = re.compile(r"deployer|(?:proxy )?admin|governance|multisig|multi.sig|treasury|fee recipient|"
                   r"treasurer|bonder|fee lib|\binformation\b|\bregistry\b|(?:^|[ :])(?:torn|uni|sushi) token|\btoken\b|\boracle\b", re.I)


def normalize_chain(chain: str | int) -> str:
    value = str(chain).strip()
    if value.isdecimal():
        return CHAIN_IDS.get(int(value), value)
    return ALIASES.get(value.upper(), value.upper())


def normalize_address(chain: str, address: str) -> str:
    value = address.strip()
    if chain in EVM:
        return value.lower()
    if chain == "BTC" and value.lower().startswith(("bc1", "tb1")):
        return value.lower()
    if chain == "TRX" and re.fullmatch(r"(?:0x)?41[0-9a-fA-F]{40}", value):
        # Tron hex and Base58Check refer to the same address; Base58 remains case-sensitive.
        import hashlib
        payload = bytes.fromhex(value.removeprefix("0x"))
        data = payload + hashlib.sha256(hashlib.sha256(payload).digest()).digest()[:4]
        alphabet = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
        number = int.from_bytes(data, "big")
        encoded = ""
        while number:
            number, digit = divmod(number, 58)
            encoded = alphabet[digit] + encoded
        return "1" * (len(data) - len(data.lstrip(b"\0"))) + encoded
    return value


def classify(name: str, tags: list[str]) -> tuple[str, str, str] | None:
    """Return (class, confidence, reason), or omit out-of-scope/personal labels."""
    if not name or name.startswith("Sum of "):
        return None
    lower = name.lower()
    tagset = set(tags)
    # A victim/exploit label alone does not establish a scam destination.
    if tagset & {"phish-hack", "scam", "scams", "address-poisoning"} and re.search(
            r"fake[_ ]?phishing|\bphishing\b|\bscammer\b|address.poison|\bscam\b", lower):
        return "scam_poisoning", "low", "Third-party risk label, unverified allegation; no independent poisoning determination."
    if "tornado" in lower and tagset & {"tornado-cash", "mixer"}:
        if not ADMIN.search(name) and (re.search(r"\b\d+(?:[.,]\d+)?\s*(eth|dai|cdai|usdc|usdt|wbtc|bnb|matic|avax|xdai)\b", lower)
                                         or re.search(r"router|proxy|pool", lower)):
            return "mixer", "medium", "Source explicitly names a Tornado Cash pool/router/proxy; not its token or governance."
        return "unknown_service", "medium", "Tornado-related source label; pool/router role not established."
    if tagset & {"tether", "circle", "centre"} and re.match(r"^(?:tether|circle|centre)(?:\b|:)", lower):
        return "issuer", "medium", "Issuer-related source label; token contracts and treasury roles are retained verbatim."
    if tagset & DEX_TAGS:
        if ADMIN.search(name) or re.search(r"deposit funder|merchant deposit", lower):
            return "unknown_service", "medium", "Named DEX ecosystem address; source identifies a token/admin/ancillary role."
        return "dex", "medium", "Source DEX/protocol category; pool/router/settlement and other operational contracts."
    if tagset & BRIDGE_TAGS:
        if ADMIN.search(name) or not BRIDGE_NAMES.search(name):
            return "unknown_service", "medium", "Bridge-related source category; cross-chain gateway role not established."
        return "bridge", "medium", "Named cross-chain protocol in source bridge category; activity and deployment dates unverified."
    if tagset & CEX_TAGS:
        specific_cex = bool(tagset & (CEX_TAGS - {"exchange"}))
        # Public Etherscan tooltips expand the displayed "Bitget Dep:" format to
        # "Bitget Deposit:" (saved direct verification in etherscan_public).
        # Require the exchange prefix to agree with the dataset category.
        abbreviated = re.fullmatch(r"(bitget|binance|okx|kucoin|gate) dep:\s*0x[0-9a-f]{40}", lower)
        if abbreviated:
            expected_tag = {"gate": "gate-io"}.get(abbreviated[1], abbreviated[1])
            if expected_tag in tagset:
                return "cex_deposit", "medium", "Explicit explorer 'Dep:' deposit label; exchange prefix agrees with source category. No transaction-pattern inference."
            return "unknown_service", "low", "Deposit-like source label conflicts with its exchange category; service/role attribution unresolved."
        if specific_cex and re.search(r"\bhot[ -]?wallet\b", lower):
            return "cex_hot", "medium", "Source explicitly says hot wallet."
        # Funding/deposit-funder/ETH2 depositor is not itself a customer deposit address.
        if specific_cex and re.search(r"\bdeposit(?: address| wallet)?(?:\s*\d+)?$", lower) and not re.search(
                r"funder|funding|eth2|staking|beacon|merchant", lower):
            return "cex_deposit", "medium", "Source explicitly says deposit; no deposit-pattern or ownership inference."
        return "unknown_service", "medium", "Exchange-related source label; deposit/hot-wallet role not established."
    if tagset & DEFI_TAGS:
        return "defi_other", "medium", "Source explicitly places this address in a named DeFi protocol/category."
    return None
