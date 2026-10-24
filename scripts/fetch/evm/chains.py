"""Chain identifiers, public endpoints, and canonical native tickers."""
CHAINS = {
    "eth": {"id": 1, "symbol": "ETH", "rpc": "https://rpc.mevblocker.io", "blockscout": "https://eth.blockscout.com", "etherscan": True, "seconds": 12},
    "bsc": {"id": 56, "symbol": "BNB", "rpc": "https://bsc-rpc.publicnode.com", "etherscan": True, "routescan": True, "seconds": 0.75},
    "arb": {"id": 42161, "symbol": "ETH", "rpc": "https://arbitrum-one.public.blastapi.io", "blockscout": "https://arbitrum.blockscout.com", "etherscan": True, "seconds": 0.25},
    "polygon": {"id": 137, "symbol": "POL", "rpc": "https://polygon.drpc.org", "blockscout": "https://polygon.blockscout.com", "etherscan": True, "seconds": 2},
    "base": {"id": 8453, "symbol": "ETH", "rpc": "https://mainnet.base.org", "blockscout": "https://base.blockscout.com", "etherscan": True, "routescan": True, "seconds": 2},
    "op": {"id": 10, "symbol": "ETH", "rpc": "https://mainnet.optimism.io", "blockscout": "https://optimism.blockscout.com", "etherscan": True, "seconds": 2},
    "avax": {"id": 43114, "symbol": "AVAX", "rpc": "https://avalanche-c-chain-rpc.publicnode.com", "etherscan": True, "routescan": True, "seconds": 2},
    "etc": {"id": 61, "symbol": "ETC", "rpc": "https://etc.blockscout.com/api/eth-rpc", "blockscout": "https://etc.blockscout.com", "seconds": 13},
}
ALIASES = {"ethereum": "eth", "ethereum classic": "etc", "arbitrum": "arb", "arbitrum-one": "arb", "optimism": "op", "avalanche": "avax", "avalanche c": "avax", "avalanche-c": "avax", "binance smart chain": "bsc", "bnb": "bsc", "matic": "polygon", "pol": "polygon"}
TICKERS = {"ETH": "eth", "ETC": "etc", "BSC": "bsc", "BNB": "bsc", "ARB": "arb", "MATIC": "polygon", "POL": "polygon", "AVAX": "avax", "BASE": "base", "OP": "op", "USDT": "eth", "USDC": "eth"}
CROSS_CHAINS = ("eth", "bsc", "arb", "polygon", "base", "op")
STABLECOINS = {
    "bsc": {"0x55d398326f99059ff775485246999027b3197955": ("Binance-Peg BSC-USD", 18), "0x8ac76a51cc950d9822d68b83fe1ad97b32cd580d": ("Binance-Peg USDC", 18)},
    "eth": {"0xdac17f958d2ee523a2206206994597c13d831ec7": ("USDT", 6), "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48": ("USDC", 6)},
    "arb": {"0xfd086bc7cd5c481dcc9c85ebe478a1c0b69fcbb9": ("USDT", 6), "0xaf88d065e77c8cc2239327c5edb3a432268e5831": ("USDC", 6)},
    "polygon": {"0xc2132d05d31c914a87c6611c10748aeb04b58e8f": ("USDT", 6), "0x3c499c542cef5e3811e1192ce70d8cc03d5c3359": ("USDC", 6)},
    "base": {"0x833589fcd6edb6e08f4c7c32d4f71b54bda02913": ("USDC", 6)},
    "op": {"0x0b2c639c533813f4aa9d7837caf62653d097ff85": ("USDC", 6), "0x94b008aa00579c1307b0ef2c499ad98a8ce58e58": ("USDT", 6)},
}
