"""Conservative chain assignment and address validation; never change source text."""
import hashlib
import re

B58 = '123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz'
EXPLORERS = {
    'BTC': 'https://mempool.space/docs/api/rest',
    'ETH': 'https://etherscan.io/',
    'TRX': 'https://tronscan.org/',
    'LTC': 'https://litecoinspace.org/',
    'BCH': 'https://blockchair.com/bitcoin-cash',
    'BSV': 'https://whatsonchain.com/',
    'DASH': 'https://chainz.cryptoid.info/dash/',
    'DOGE': 'https://dogechain.info/',
    'ZEC': 'https://mainnet.zcashexplorer.app/',
    'ETC': 'https://etc.blockscout.com/',
    'XVG': 'https://verge-blockchain.info/',
    'XRP': 'https://xrpscan.com/',
    'SOL': 'https://explorer.solana.com/',
    'ARB': 'https://arbiscan.io/',
    'BSC': 'https://bscscan.com/',
    'BNB': 'https://explorer.bnbchain.org/',
}

def b58decode(value, alphabet=B58):
    number = 0
    for ch in value:
        number = number * 58 + alphabet.index(ch)
    return b'\0' * (len(value) - len(value.lstrip(alphabet[0]))) + number.to_bytes((number.bit_length()+7)//8, 'big')

def b58encode(value):
    number = int.from_bytes(value, 'big')
    out = ''
    while number:
        number, rem = divmod(number, 58)
        out = B58[rem] + out
    return '1' * (len(value)-len(value.lstrip(b'\0'))) + out

def sha256d(value):
    return hashlib.sha256(hashlib.sha256(value).digest()).digest()

def cashaddr_valid(value):
    if value != value.lower() and value != value.upper():
        return False
    value = value.lower()
    prefix, body = value.split(':',1) if ':' in value else ('bitcoincash',value)
    try:
        data = ['qpzry9x8gf2tvdw0s3jn54khce6mua7l'.index(c) for c in body]
    except ValueError:
        return False
    checksum = 1
    for d in [ord(c)&31 for c in prefix]+[0]+data:
        top = checksum >> 35
        checksum = ((checksum & 0x07ffffffff)<<5)^d
        for i,g in enumerate([0x98f2bc8e61,0x79b76d99e2,0xf33e5fb3c4,0xae2eabe2a8,0x1e4f43e470]):
            if (top>>i)&1:
                checksum ^= g
    return checksum == 1

def bech32_valid(value):
    if value != value.lower() and value != value.upper():
        return False
    value = value.lower()
    pos = value.rfind('1')
    if pos < 1 or pos + 7 > len(value) or len(value) > 90:
        return False
    hrp = value[:pos]
    try:
        data = ['qpzry9x8gf2tvdw0s3jn54khce6mua7l'.index(c) for c in value[pos+1:]]
    except ValueError:
        return False
    chk = 1
    for v in [ord(x)>>5 for x in hrp] + [0] + [ord(x)&31 for x in hrp] + data:
        top = chk >> 25
        chk = ((chk & 0x1ffffff) << 5) ^ v
        for i, g in enumerate([0x3b6a57b2,0x26508e6d,0x1ea119fa,0x3d4233dd,0x2a1462b3]):
            if (top >> i) & 1:
                chk ^= g
    return chk == (1 if hrp == 'bnb' or data[0] == 0 else 0x2bc830a3)

def assign(ticker, address):
    address = address.strip()
    rule = 'explicit OFAC native-chain ticker'
    confidence = 'high'
    if ticker == 'XBT':
        chain = 'BTC'
    elif ticker in ('USDT', 'USDC'):
        if re.fullmatch('0[xX][0-9a-fA-F]{40}', address):
            chain, rule, confidence = 'ETH', 'stablecoin + 20-byte 0x format: Ethereum convention; EVM network not proven by format', 'medium'
        elif address.startswith('T') or re.fullmatch('41[0-9a-fA-F]{40}', address):
            chain, rule = 'TRX', 'stablecoin + Tron T-base58/41-hex address format'
        elif address.startswith(('1', '3', 'bc1')):
            chain, rule = 'BTC', 'stablecoin + Bitcoin-format address (Omni)'
        elif len(address) in range(32,45) and all(x in B58 for x in address):
            chain, rule, confidence = 'SOL', 'stablecoin + 32-byte base58 Solana format', 'medium'
        else:
            chain, rule, confidence = 'UNKNOWN', 'stablecoin chain cannot be resolved from address', 'low'
    elif ticker == 'BNB':
        chain, rule = ('BSC', 'BNB + 20-byte 0x format: BNB Smart Chain') if address.startswith('0x') else ('BNB', 'BNB native address format')
    else:
        chain = ticker
    source_ticker_mismatch = False
    # Preserve the source ticker, but do not send a valid Tron address to a BTC API.
    if ticker == 'XBT' and address.startswith('T'):
        try:
            check = b58decode(address)
            if len(check)==25 and check[0]==0x41 and sha256d(check[:-4])[:4]==check[-4:]:
                chain = 'TRX'
                rule = 'OFAC XBT label conflicts with valid Tron base58check/0x41 format; format override'
                confidence = 'medium'
                source_ticker_mismatch = True
        except ValueError:
            pass
    norm = address
    tron_hex = ''
    valid, validation = True, 'shape only'
    reason = ''
    try:
        if chain in ('ETH','ETC','BSC','ARB'):
            valid = bool(re.fullmatch('0[xX][0-9a-fA-F]{40}', address))
            norm = address.lower()
            validation = '20-byte hex shape; EIP-55 not checked'
        elif chain == 'TRX':
            if re.fullmatch('41[0-9a-fA-F]{40}', address):
                payload = bytes.fromhex(address)
                norm = b58encode(payload + sha256d(payload)[:4])
            decoded = b58decode(norm)
            valid = len(decoded) == 25 and decoded[0] == 0x41 and sha256d(decoded[:-4])[:4] == decoded[-4:]
            tron_hex = decoded[:-4].hex() if valid else ''
            validation = 'base58check + 0x41 version'
        elif chain in ('BTC','LTC') and address.lower().startswith(('bc1','ltc1')):
            norm = address.lower()
            valid = bech32_valid(address)
            validation = 'bech32/bech32m checksum'
        elif chain == 'BNB' and address.lower().startswith('bnb1'):
            norm = address.lower()
            valid = bech32_valid(address)
            validation = 'BNB Beacon Chain bech32 checksum'
        elif chain == 'SOL':
            valid = len(b58decode(address)) == 32
            validation = 'base58 32-byte public-key shape'
        elif chain == 'XMR':
            valid = len(address) in (95,106) and all(x in B58 for x in address)
            validation = 'Monero shape; Keccak checksum not checked'
        elif chain == 'ZEC' and address.startswith(('z','u1')):
            validation = 'shielded/unified format only'
        elif chain == 'BCH' and (address.lower().startswith(('q','p','bitcoincash:'))):
            norm = address.lower().removeprefix('bitcoincash:')
            valid = bool(re.fullmatch('[qp][a-z0-9]{41}',norm)) and cashaddr_valid(address)
            validation = 'cashaddr checksum (bitcoincash prefix)'
        elif chain == 'XRP':
            alphabet = 'rpshnaf39wBUDNEGHJKLM4PQRST7VWXYZ2bcdeCg65jkm8oFqi1tuvAxyz'
            decoded = b58decode(address, alphabet)
            valid = len(decoded) == 25 and decoded[0] == 0 and sha256d(decoded[:-4])[:4] == decoded[-4:]
            validation = 'XRP base58check'
        elif chain in ('BTC','LTC','BCH','BSV','BTG','DASH','DOGE','XVG','ZEC'):
            decoded = b58decode(address)
            valid = len(decoded) in (25,26) and sha256d(decoded[:-4])[:4] == decoded[-4:]
            versions = {'BTC':(b'\x00',b'\x05'),'LTC':(b'\x30',b'\x32',b'\x05'),
                        'BCH':(b'\x00',b'\x05'),'BSV':(b'\x00',b'\x05'),
                        'BTG':(b'\x26',b'\x17'),'DASH':(b'\x4c',b'\x10'),
                        'DOGE':(b'\x1e',b'\x16'),'XVG':(b'\x1e',b'\x21'),
                        'ZEC':(b'\x1c\xb8',b'\x1c\xbd')}
            valid = valid and any(decoded.startswith(v) for v in versions[chain])
            validation = 'base58check checksum + chain version'
        else:
            valid = False
            validation = 'unsupported format'
    except (ValueError, IndexError):
        valid = False
    if not valid:
        reason = 'Malformed address: failed ' + validation
    elif chain == 'XMR':
        reason = 'Monero privacy prevents public address-level full-history observation'
    elif chain == 'ZEC' and address.startswith(('z','u1')):
        reason = 'Shielded/unified Zcash address lacks public address-level full history'
    elif chain not in EXPLORERS:
        reason = 'No usable full-history public explorer identified for this chain'
    return dict(chain=chain, address_normalized=norm, tron_hex=tron_hex, chain_rule=rule,
                chain_confidence=confidence, address_valid=str(valid).lower(), address_validation=validation,
                source_ticker_mismatch=str(source_ticker_mismatch).lower(),
                trackable=str(not reason).lower(), untrackable_reason=reason, explorer_url=EXPLORERS.get(chain,''))
