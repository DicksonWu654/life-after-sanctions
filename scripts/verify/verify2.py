#!/usr/bin/env python3
"""Independent saved-timeline audit of three headline claims. No analysis-script imports.

Run: .venv/bin/python -S scripts/verify/verify2.py [--live]
--live requests 20 selected mempool.space address histories, caching gzip bodies.
"""
from __future__ import annotations
import argparse, bisect, collections, csv, datetime as dt, gzip, hashlib, json, math, random, time, urllib.request, urllib.error
from decimal import Decimal, InvalidOperation
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT=Path(__file__).resolve().parents[2]
ET=ZoneInfo('America/New_York'); UTC=dt.timezone.utc
OUT=ROOT/'data/verify'; RAW=ROOT/'data/raw/verify2'
NATIVE={'ARB':'ETH','BSC':'BNB','BNB':'BNB','BTC':'BTC','BCH':'BCH','BSV':'BSV','BTG':'BTG','DASH':'DASH','DOGE':'DOGE','ETC':'ETC','ETH':'ETH','LTC':'LTC','SOL':'SOL','TRX':'TRX','XRP':'XRP','XVG':'XVG','ZEC':'ZEC'}
TOKENS={
'ETH':{'0xdac17f958d2ee523a2206206994597c13d831ec7':'USDT','0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48':'USDC','0x6b175474e89094c44da98b954eedeac495271d0f':'DAI','0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2':'ETH','0x2260fac5e5542a773aa44fbcfedf7c193bc2c599':'BTC','0xa47c8bf37f92abed4a126bda807a7b7498661acd':'UST','0x674c6ad92fd080e4004b2312b45f796a192d27a0':'USDN','0x5a98fcbea516cf06857215779fd812ca3bef1b32':'LDO','0x514910771af9ca656af840dff83e8264ecf986ca':'LINK','0x7d1afa7b718fb893db30a3abc0cfc608aacfebb0':'MATIC','0x95ad61b0a150d79219dcf64e1e6cc01f0b64c4ce':'SHIB','0x1f9840a85d5af5bf1d1762f925bdaddc4201f984':'UNI','0x7f39c581f595b53c5cb19bd0b3f8da6c935e2ca0':'WSTETH','0xae7ab96520de3a18e5e111b5eaab095312d7fe84':'STETH','0xd533a949740bb3306d119cc777fa900ba034cd52':'CRV','0x04fa0d235c4abf4bcf4787af4cf447de572ef828':'UMA','0x408e41876cccdc0cfc608aacfebb0c47de3f03':'REN','0x77777feddddffc19ff86db637967013e6c6a116c':'TORN'},
'TRX':{'TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t':'USDT','TEkxiTehnzSmSe2XqrBj4w32RUN966rdz8':'USDC','TEk2J6HjyBKu47ai6ScwkbchfkWnPWuckM':'TUSD'},
'ARB':{'0xfd086bc7cd5c481dcc9c85ebe478a1c0b69fcbb9':'USDT','0xaf88d065e77c8cc2239327c5edb3a432268e5831':'USDC','0xff970a61a04b1ca14834a43f5de4533ebddb5cc8':'USDC','0x82af49447d8a07e3bd95bd0d56f35241523fbab1':'ETH','0x912ce59144191c1204e64559fe8253a0e49e6548':'ARB'},
'SOL':{'EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v':'USDC','Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB':'USDT'},
'BSC':{'0x55d398326f99059ff775485246999027b3197955':'USDT','0x8ac76a51cc950d9822d68b83fe1ad97b32cd580d':'USDC'}}
# Deliberately no price by ticker alone: these recognised contracts require a saved price.
PRICE_ALIASES={'POL':'MATIC/POL'}
def parse(s):
 if not s:return None
 try:return dt.datetime.fromisoformat(str(s).replace('Z','+00:00')).astimezone(UTC)
 except (ValueError,TypeError):return None
def etmid(date,days=0):return dt.datetime.combine(dt.date.fromisoformat(date)+dt.timedelta(days=days),dt.time(),ET).astimezone(UTC)
def dec(x):
 try:return Decimal(str(x or '0'))
 except (InvalidOperation,ValueError):return Decimal(0)
def rel(p):return str(p.relative_to(ROOT))
def rows(path):
 with open(path,newline='') as f: return list(csv.DictReader(f))
def write_csv(name,rr):
 if not rr:return
 p=OUT/name
 with open(p,'w',newline='') as f:
  w=csv.DictWriter(f,fieldnames=list(rr[0]),extrasaction='ignore');w.writeheader();w.writerows(rr)
 print('wrote',rel(p),len(rr))
class Prices:
 def __init__(self):self.cache={}
 def load(self,sym,freq):
  k=(sym,freq)
  if k in self.cache:return self.cache[k]
  p=ROOT/'data/prices'/f'{sym.replace("/","-")}_{freq}.csv.gz'; rr=[]
  if p.exists():
   with gzip.open(p,'rt',newline='') as f:
    for r in csv.DictReader(f):
     t=parse(r['valuation_time_utc'])
     if t:rr.append((t,dec(r['price_usd']),r['raw_ref'],r['source_url']))
  self.cache[k]=([r[0] for r in rr],rr);return self.cache[k]
 def get(self,sym,t):
  sym=PRICE_ALIASES.get(sym,sym)
  for freq,maxage in [('1h',dt.timedelta(hours=2)),('1d',dt.timedelta(days=2))]:
   tt,rr=self.load(sym,freq);i=bisect.bisect_right(tt,t)-1
   if i>=0 and t-tt[i]<=maxage:return rr[i]
  return None

def symbol(chain,asset):
 if asset==NATIVE.get(chain):return asset
 return TOKENS.get(chain,{}).get(asset)
def valout(tx,chain,prices):
 if tx['direction']!='out' or tx['amount']<=0 or not tx['symbol']:return False
 p=prices.get(tx['symbol'],tx['time'])
 return p is not None and tx['amount']*p[1]>=1

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--live',action='store_true');ap.add_argument('--live-only',action='store_true');a=ap.parse_args()
 OUT.mkdir(parents=True,exist_ok=True);RAW.mkdir(parents=True,exist_ok=True)
 if a.live_only:live_check(rows(OUT/'verify2_empty.csv'));return
 listed=rows(ROOT/'data/addresses.csv'); ledger=rows(ROOT/'data/ledger.csv')
 ledger_by=collections.defaultdict(list)
 for r in ledger:ledger_by[(r['chain'],r['address_normalized'])].append(r)
 prices=Prices(); inventory=[]; master=[]; pre=[]; empty=[]; dep=[]; counts=collections.Counter(); quality=collections.Counter(); bychain=collections.Counter()
 for ar in listed:
  ch=ar['chain']; addr=ar['address_normalized']; lid=(ch,addr); ll=ledger_by[lid]
  action_url=(ll[0].get('listed_action_url') if ll else '') or ar.get('source_url') or ''
  excluded=any('TORNADO' in r['sdn_name'].upper() for r in ll)
  p=ROOT/'data/timelines'/ch.lower()/(addr+'.json.gz')
  if ar['trackable'].lower()!='true' or excluded:continue
  if not p.exists():counts['no_timeline']+=1;continue
  try:
   raw=p.read_bytes(); d=json.loads(gzip.decompress(raw))
  except Exception:counts['unreadable']+=1;continue
  inventory.append({'path':rel(p),'sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw),'raw_ref':rel(p)})
  counts['with_timeline']+=1;bychain[ch]+=1
  complete=d.get('coverage',{}).get('complete') is True
  if complete:counts['complete']+=1
  T=etmid(ar['first_listed_date']);T7=etmid(ar['first_listed_date'],7)
  end=parse(d.get('coverage',{}).get('checked_through_time') or d.get('coverage',{}).get('to_time'))
  if end is None:end=parse(d.get('fetched_at'))
  txs=[]; bad=0; seenhash=set()
  for i,r in enumerate(d.get('txs',[])):
   t=parse(r.get('time_utc'));direction=r.get('direction');amount=dec(r.get('amount'))
   if t is None or direction not in ('in','out','self') or amount<0:bad+=1;continue
   failed=r.get('success') is False or str(r.get('status') or '') in ('0','FAILED','FAILURE')
   asset=str(r.get('asset') or '');sym=symbol(ch,asset)
   if failed:
    if asset==NATIVE.get(ch) and dec(r.get('fee'))>0:direction='self';amount=Decimal(0)
    else:continue
   x={'time':t,'direction':direction,'amount':amount,'fee':dec(r.get('fee')),'asset':asset,'symbol':sym,'hash':r.get('hash') or '', 'raw_ref':r.get('raw_ref') or '', 'index':i}
   txs.append(x)
   if x['hash']:seenhash.add(x['hash'])
  txs.sort(key=lambda x:(x['time'],x['index']))
  quality['bad_rows']+=bad
  exchange=len(seenhash)>10000 or bool(d.get('fetch_state',{}).get('huge_address')) or int(d.get('reported_history_records') or 0)>10000
  if exchange:counts['exchange_scale']+=1
  observed={}
  for b in d.get('balance_now',[]) or []:
   asset=str(b.get('asset') or '')
   if symbol(ch,asset):observed[asset]=dec(b.get('amount'))
  state=collections.defaultdict(Decimal); minstate=collections.defaultdict(Decimal); atT={};atT7={};atT_set=False;atT7_set=False;current_time=None;touched=set()
  for x in txs:
   if current_time is not None and x['time']!=current_time:
    for prior_asset in touched:minstate[prior_asset]=min(minstate[prior_asset],state[prior_asset])
    touched.clear()
   current_time=x['time']
   if x['time']>=T and not atT_set:atT=dict(state);atT_set=True
   if x['time']>=T7 and not atT7_set:atT7=dict(state);atT7_set=True
   if not x['symbol']:continue
   asset=x['asset']
   if x['direction']=='in':state[asset]+=x['amount']
   elif x['direction']=='out':state[asset]-=x['amount']+x['fee']
   else:state[asset]-=x['fee']
   touched.add(asset)
  for prior_asset in touched:minstate[prior_asset]=min(minstate[prior_asset],state[prior_asset])
  if not atT_set:atT=dict(state)
  if not atT7_set:atT7=dict(state)
  assets=set(state)|set(observed)
  good={k for k in assets if k in observed and abs(state[k]-observed[k])<=Decimal('0.000001') and minstate[k]>=Decimal('-0.000000000001') and atT.get(k,Decimal(0))>=Decimal('-0.000000000001') and atT7.get(k,Decimal(0))>=Decimal('-0.000000000001')}
  history=complete and end is not None and end>=T and bad==0
  # A: zero across all recognised, reconciled assets; an unresolved recognised asset makes full zero unknown.
  allgood=history and assets<=good
  preout=[x for x in txs if x['time']<T and valout(x,ch,prices)]
  last=max(preout,key=lambda x:x['time']) if preout else None
  tzero=allgood and all(abs(atT.get(k,Decimal(0)))<=Decimal('0.000000000000001') for k in assets)
  if history:counts['history_for_T']+=1
  if allgood:counts['reconciled_T']+=1
  if tzero and last:
   delta=(T-last['time']).total_seconds()/86400
   category='within_30d' if delta<=30 else 'over_30d'
   empty.append({'chain':ch,'address':addr,'T_utc':T.isoformat(),'last_qualifying_out_utc':last['time'].isoformat(),'days_before_T':round(delta,6),'category':category,'last_tx_hash':last['hash'],'last_tx_raw_ref':last['raw_ref'],'timeline_raw_ref':rel(p),'source_url':action_url,'asset_count':len(assets),'tx_count':len(txs)})
  # B: per-asset gross net depletion at T prices, requiring both checkpoints.
  numerator=Decimal(0);denominator=Decimal(0);npriced=0;missing_price=0
  if allgood and end>=T7:
   for asset in good:
    opening=max(Decimal(0),atT.get(asset,Decimal(0)))
    if opening<=0:continue
    sym=symbol(ch,asset);pval=prices.get(sym,T) if sym else None
    if not pval:missing_price+=1;continue
    price=pval[1];denominator+=opening*price
    closing=max(Decimal(0),atT7.get(asset,Decimal(0)))
    numerator+=max(Decimal(0),opening-closing)*price;npriced+=1
  if denominator>0 and missing_price==0:
   dep.append({'chain':ch,'address':addr,'sdn_uids':ar.get('all_entity_uids') or '', 'T_utc':T.isoformat(),'value_T_usd':float(denominator),'net_depleted_T_usd':float(numerator),'priced_assets':npriced,'exchange_scale':exchange,'timeline_raw_ref':rel(p),'source_url':action_url})
  # C: weekly windows, first confirmed transaction begins observed exposure. Event/baseline windows are ET-calendar anchored.
  if not history or not txs:continue
  first=txs[0]['time']; outtimes=sorted(x['time'] for x in txs if valout(x,ch,prices))
  dormant=not any(T-dt.timedelta(days=180)<=x<T for x in outtimes)
  for w in (3,7,14):
   start=etmid(ar['first_listed_date'],-w)
   if end<start or first>start:continue
   k0=bisect.bisect_left(outtimes,start);k1=bisect.bisect_left(outtimes,T)
   real=int(k1>k0)
   baselines=[];last_end=None
   n=0
   while True:
    stop=etmid(ar['first_listed_date'],-35-7*n);begin=etmid(ar['first_listed_date'],-35-7*n-w)
    if begin<first:break
    i=bisect.bisect_left(outtimes,begin);j=bisect.bisect_left(outtimes,stop)
    baselines.append(int(j>i));last_end=stop;n+=1
    if n>3000:raise RuntimeError('too many baseline weeks')
   if len(baselines)<12:continue
   below=sum(x<real for x in baselines);equal=sum(x==real for x in baselines)+1
   rank=(below+0.5*equal)/(len(baselines)+1)
   pre.append({'window_days':w,'chain':ch,'address':addr,'T_utc':T.isoformat(),'real_active':real,'baseline_active_weeks':sum(baselines),'baseline_weeks':len(baselines),'baseline_share':sum(baselines)/len(baselines),'midrank':rank,'upper_tail_p':(1+sum(x>=real for x in baselines))/(len(baselines)+1),'dormant_prior_180d':dormant,'exchange_scale':exchange,'action_url':action_url, 'entity_uids':ar.get('all_entity_uids') or '', 'timeline_raw_ref':rel(p),'source_url':action_url})
  master.append({'chain':ch,'address':addr,'complete':complete,'history_for_T':history,'reconciled_all_assets':allgood,'T_zero':tzero,'prior_qualified_out':bool(preout),'T_value_usd':float(denominator),'T7_net_depleted_usd':float(numerator),'exchange_scale':exchange,'recognised_assets':len(assets),'reconciled_assets':len(good),'unpriced_positive_T_assets':missing_price,'timeline_raw_ref':rel(p),'source_url':action_url})
 write_csv('verify2_addresses.csv',master);write_csv('verify2_empty.csv',empty);write_csv('verify2_depletion.csv',dep);write_csv('verify2_premove.csv',pre);write_csv('verify2_manifest.csv',inventory)
 def summarize_depletion(rr):
  den=sum(x['value_T_usd'] for x in rr);num=sum(x['net_depleted_T_usd'] for x in rr)
  return {'n':len(rr),'den_usd':den,'depleted_usd':num,'share':num/den if den else None}
 print('A',len(empty),'recent',sum(x['category']=='within_30d' for x in empty),'long',sum(x['category']=='over_30d' for x in empty),'with_timeline',counts['with_timeline'],'reconciled_T',counts['reconciled_T'])
 print('B',summarize_depletion(dep));print('B no largest',summarize_depletion([x for x in dep if '55505' not in x['sdn_uids'].split(';')]));print('B no exchange',summarize_depletion([x for x in dep if not x['exchange_scale']]))
 for w in (3,7,14):
  q=[x for x in pre if x['window_days']==w]
  for name,subset in [('all',q),('active180',[x for x in q if not x['dormant_prior_180d']])]:
   if not subset:continue
   print('C',w,name,len(subset),sum(x['real_active'] for x in subset),sum(x['real_active'] for x in subset)/len(subset),'baseline',sum(x['baseline_share'] for x in subset)/len(subset),'mean_rank',sum(x['midrank'] for x in subset)/len(subset))
 print('counts',dict(counts),'quality',dict(quality),'bychain',dict(bychain))
 for window in (3,7,14):
  rank_test([x for x in pre if x['window_days']==window])
  rank_test([x for x in pre if x['window_days']==window and not x['dormant_prior_180d']])
 if a.live:live_check(empty)

def rank_test(q):
 # Independent component-clustered conditional Bernoulli rank randomization.
 n=len(q);parent=list(range(n))
 def find(i):
  while parent[i]!=i:
   parent[i]=parent[parent[i]];i=parent[i]
  return i
 def union(i,j):parent[find(i)]=find(j)
 membership={}
 for i,x in enumerate(q):
  keys=['action:'+x['action_url']] if 'ofac.treasury.gov/recent-actions/' in x['action_url'] else []
  keys += ['entity:'+e for e in x['entity_uids'].split(';') if e]
  for key in keys:
   if key in membership:union(i,membership[key])
   else:membership[key]=i
 components=collections.defaultdict(list)
 for i in range(n):components[find(i)].append(i)
 clusters=list(components.values())
 observed=sum(sum(q[i]['midrank']-0.5 for i in comp)/len(comp) for comp in clusters)/len(clusters)
 rng=random.Random(20261023);draws=9999;ge=0
 for _ in range(draws):
  total=0
  for comp in clusters:
   u=rng.random();score=0
   for i in comp:
    x=q[i];N=x['baseline_weeks']+1;ones=x['baseline_active_weeks']+x['real_active'];zeros=N-ones
    rank=(zeros+ones/2)/N if u>=zeros/N else zeros/(2*N)
    score+=rank-0.5
   total+=score/len(comp)
  ge += total/len(clusters)>=observed-1e-15
 print('C rank_test',{'addresses':n,'components':len(clusters),'observed_cluster_score':observed,'one_sided_upper_p':(ge+1)/(draws+1),'draws':draws})

def live_check(empty):
 # Low-volume BTC addresses permit full history within explorer's first 25 transactions.
 candidates=[x for x in empty if x['chain']=='BTC' and 1<=x['tx_count']<=25 and x['last_tx_hash']]
 recent=sorted([x for x in candidates if x['category']=='within_30d'],key=lambda x:(x['tx_count'],x['address']))
 long=sorted([x for x in candidates if x['category']=='over_30d'],key=lambda x:(x['tx_count'],x['address']))
 chosen=[];used=set()
 for pool,limit in [(recent,10),(long,10)]:
  selected=0
  for x in pool:
   if x['last_tx_hash'] in used:continue
   chosen.append(x);used.add(x['last_tx_hash']);selected+=1
   if selected>=limit:break
 if len(chosen)<20:chosen += [x for x in candidates if x not in chosen][:20-len(chosen)]
 report=[]
 for x in chosen:
  addr=x['address'];url=f'https://mempool.space/api/address/{addr}/txs'; key=hashlib.sha256(url.encode()).hexdigest();p=RAW/f'{key}.json.gz'
  if p.exists():body=gzip.decompress(p.read_bytes());status='cached'
  else:
   try:
    req=urllib.request.Request(url,headers={'User-Agent':'life-after-sanctions-verify2/1.0','Accept':'application/json'})
    with urllib.request.urlopen(req,timeout=20) as response:body=response.read();status=str(response.status)
    with gzip.open(p,'wb') as f:f.write(body)
   except Exception as e:
    report.append({**x,'explorer_url':url,'live_status':str(e),'live_raw_ref':'','last_out_seen':False,'no_later_preT_out_seen':False,'live_confirmed_balance_T_btc':''});continue
  try:txs=json.loads(body)
  except ValueError:txs=[]
  T=parse(x['T_utc']);out=[];delta=0
  for tx in txs:
   ts=tx.get('status',{}).get('block_time');t=dt.datetime.fromtimestamp(ts,UTC) if ts else None
   if t is None or t>=T:continue
   vin=sum(int(v.get('prevout',{}).get('value',0)) for v in tx.get('vin',[]) if v.get('prevout',{}).get('scriptpubkey_address')==addr)
   vout=sum(int(v.get('value',0)) for v in tx.get('vout',[]) if v.get('scriptpubkey_address')==addr)
   delta+=vout-vin
   if vin>0 and vout<vin:out.append((t,tx.get('txid'),vin-vout))
  out.sort(reverse=True)
  report.append({**x,'explorer_url':url,'live_status':status,'live_raw_ref':rel(p),'last_out_seen':any(z[1]==x['last_tx_hash'] for z in out),'no_later_preT_out_seen':bool(out) and out[0][1]==x['last_tx_hash'],'live_confirmed_balance_T_btc':f'{delta/1e8:.8f}','live_preT_tx_count':sum(1 for tx in txs if tx.get('status',{}).get('block_time') and dt.datetime.fromtimestamp(tx['status']['block_time'],UTC)<T)})
  time.sleep(.25)
 write_csv('verify2_live.csv',report)
 print('LIVE',len(report),'last tx matched',sum(x['last_out_seen'] for x in report),'latest matched',sum(x['no_later_preT_out_seen'] for x in report),'balance zero',sum(x['live_confirmed_balance_T_btc']=='0.00000000' for x in report))
if __name__=='__main__':main()
