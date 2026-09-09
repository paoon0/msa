#!/usr/bin/env python3
"""束ねに関係するサービスだけで予約枠を数え直す(=無関係サービスの台数ノイズを除く)。

第1版の反省: checkout/payment/shipping などの台数が回ごとにばらつき、そのノイズ(1.32コア)が
束ね起因の差(0.64コア)より大きかった。これらは「どの構成でも同じ仕事量」を受け持つので、
差を取るときに消えるはず = 合計から外してよい。
"""
import csv, sys, statistics as st

REQ = {}
for r in csv.DictReader(open('rightsize-requests.csv')):
    REQ[(r['deploy'], r['container'])] = float(r['request_m'])

# 束ねに関係するサービス(=アームによって配置が変わるもの)
RELATED = {'frontend', 'productcatalogservice', 'recommendationservice', 'cartservice'}
# アームごとの frontend Pod の中身
BUNDLE = {
    'normal':       [('frontend','server')],
    'frontcatalog': [('frontend','server'), ('productcatalogservice','server')],
    'frontreco':    [('frontend','server'), ('recommendationservice','server')],
    'frontcart':    [('frontend','server'), ('cartservice','server')],
}
SOLO = {'productcatalogservice':('productcatalogservice','server'),
        'recommendationservice':('recommendationservice','server'),
        'cartservice':('cartservice','server')}

def restricted(arm, repl):
    """関係サービスだけの予約枠[コア]"""
    tot = 0.0
    for dep, n in repl.items():
        if dep == 'frontend':
            tot += n * sum(REQ[k] for k in BUNDLE[arm])
        elif dep in SOLO:
            tot += n * REQ[SOLO[dep]]
    return tot / 1000.0

def parse(s):
    d = {}
    for tok in s.split():
        k, _, v = tok.rpartition(':')
        try: d[k] = int(v)
        except ValueError: pass
    return d

for path in sys.argv[1:]:
    rows = list(csv.DictReader(open(path)))
    print("\n########", path)
    by = {}
    for r in rows:
        by.setdefault((r['cycle'], r['target_rate']), {})[r['arm']] = r
    diffs = {}
    for (cyc, rate), d in sorted(by.items()):
        if 'normal' not in d: continue
        base_all  = float(d['normal']['running_cores'])
        base_rest = restricted('normal', parse(d['normal']['replicas']))
        print(f"-- {rate}周/s cyc{cyc}  normal: 全体{base_all:.2f} / 関係だけ{base_rest:.2f} コア")
        for arm in ('frontcatalog','frontreco','frontcart'):
            if arm not in d: continue
            r = d[arm]
            rest = restricted(arm, parse(r['replicas']))
            l_all  = float(r['running_cores']) - base_all
            l_rest = rest - base_rest
            diffs.setdefault((rate,arm),[]).append((l_all,l_rest))
            print(f"     {arm:<13} 損(全体){l_all:+7.2f}  →  損(関係だけ){l_rest:+7.2f} コア   [{r['replicas'][:0]}]")
    print("  --- まとめ(平均±標準偏差) ---")
    for (rate,arm),v in sorted(diffs.items()):
        a=[x[0] for x in v]; b=[x[1] for x in v]
        sd=lambda z: st.stdev(z) if len(z)>1 else 0.0
        print(f"   {rate}周/s {arm:<13} 損(全体) {st.mean(a):+6.2f}±{sd(a):.2f}   損(関係だけ) {st.mean(b):+6.2f}±{sd(b):.2f}  (n={len(v)})")
