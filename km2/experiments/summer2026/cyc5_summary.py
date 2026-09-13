#!/usr/bin/env python3
"""cyc1-5 で表2(組み合わせごとの需要の伸びと粒度損)と表3(FE+email 詳細)を再集計する。2026-09-14
需要 = 利用率×台数 を normal の計測窓(t_rel 180..420, 最後のブロック)で平均、サイクル平均。
粒度損 = 帰属方式(loss_attributed.py と同じ): 束ねPod台数 − 同サイクル normal の各サービス台数、正の分×枠。
"""
import csv, collections, statistics as st
REQ = {r['deploy']: float(r['request_m']) for r in csv.DictReader(open('rightsize-requests.csv'))}
WARM, MEAS = 180, 240
CYCLES = {'1','2','3','4','5'}
EXPS = {
 'mix':  ('results-mix.csv','timeline-mix.csv',
          {'frontcatalog':('frontend',['frontend','productcatalogservice']),
           'frontreco':   ('frontend',['frontend','recommendationservice']),
           'frontcart':   ('frontend',['frontend','cartservice'])}),
 'mix2': ('results-mix2.csv','timeline-mix2.csv',
          {'frontemail':     ('frontend',['frontend','emailservice']),
           'frontcheckout':  ('frontend',['frontend','checkoutservice']),
           'checkoutemail':  ('checkoutservice',['checkoutservice','emailservice']),
           'catalogcheckout':('productcatalogservice',['productcatalogservice','checkoutservice'])}),
}
def parse(s):
    d={}
    for t in s.split():
        k,_,v=t.rpartition(':'); d[k]=int(v)
    return d

for exp,(res,tl,arms) in EXPS.items():
    print(f"\n######## {exp} ########")
    # --- 需要(normal) ---
    rows=[r for r in csv.DictReader(open(tl)) if r['arm']=='normal' and r['cycle'] in CYCLES and r['container']!='-']
    # ブロック分割: (cycle,browse) ごとに t_rel が戻ったら新ブロック
    blocks=collections.defaultdict(list); prev={}
    for r in rows:
        key=(r['cycle'],r['browse_rate']); t=float(r['t_rel'])
        if key in prev and t<prev[key]: blocks[key]=[]
        prev[key]=t; blocks[key].append(r)
    dem=collections.defaultdict(lambda: collections.defaultdict(list))  # svc -> browse -> [cycle mean]
    for (cyc,brw),b in blocks.items():
        per=collections.defaultdict(list)
        for r in b:
            t=float(r['t_rel'])
            if not (WARM<=t<=WARM+MEAS) or not r['hpa_util_pct']: continue
            per[r['deploy']].append(float(r['hpa_util_pct'])/100*int(r['current_replicas']))
        for s,v in per.items(): dem[s][brw].append(st.mean(v))
    svcs=sorted({s for a in arms.values() for s in a[1]})
    print("需要(利用率×台数, normal, cyc平均±sd)  伸び=300/0")
    growth={}
    for s in svcs:
        m={b:st.mean(dem[s][b]) for b in ('0','100','200','300')}
        sd={b:st.stdev(dem[s][b]) for b in ('0','100','200','300')}
        growth[s]=m['300']/m['0']
        print(f"  {s:22s} "+"  ".join(f"v{b}:{m[b]:.2f}±{sd[b]:.2f}" for b in m)+f"   伸び {growth[s]:.2f}倍 (n={len(dem[s]['0'])})")
    # --- 粒度損(帰属) ---
    rr=[r for r in csv.DictReader(open(res)) if r['cycle'] in CYCLES]
    solo={}
    for r in rr:
        if r['arm']=='normal': solo[(r['cycle'],r['browse_rate_target'])]=parse(r['replicas'])
    print("\n粒度損[m] 帰属方式 (各サイクル / 損が出た回数)")
    for arm,(dep,members) in arms.items():
        line=[]
        for brw in ('0','100','200','300'):
            L=[]; who=collections.Counter()
            for r in rr:
                if r['arm']!=arm or r['browse_rate_target']!=brw: continue
                s0=solo.get((r['cycle'],brw)); 
                if not s0: continue
                nb=parse(r['replicas']).get(dep,0); loss=0
                for m in members:
                    d=max(0,nb-s0.get(m,0)); loss+=REQ[m]*d
                    if d>0: who[m[:5]]+=1
                L.append(loss)
            line.append(f"v{brw}: {st.mean(L):5.0f}m [{'/'.join(f'{x:.0f}' for x in L)}] 損{sum(1 for x in L if x>0)}/{len(L)} {dict(who) if who else ''}")
        print(f"  {arm:16s} 伸び {'/'.join(f'{growth[m]:.1f}' for m in members)}倍")
        for l in line: print("     ",l)
    # normal の台数(表3用)
    print("\nnormal の台数(cyc1-5): ")
    for brw in ('0','300'):
        c=collections.Counter()
        for (cyc,b),s0 in solo.items():
            if b==brw: c[tuple((m,s0.get(m)) for m in svcs)]+=1
        for k,v in c.items(): print(f"  v{brw}: {v}回 ", ' '.join(f'{m[:8]}={n}' for m,n in k))
