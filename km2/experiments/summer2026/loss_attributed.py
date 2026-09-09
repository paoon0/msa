#!/usr/bin/env python3
"""束ね起因の粒度損だけを取り出す(合計の引き算ではなく、サービス単位の帰属で数える)。

なぜ作り直したか(2026-09-01):
  それまでは「束ねに関係する4サービスの予約枠の合計」を分離構成と引き算していた。
  しかし productcatalog / recommendation / cart は 200周/s でちょうど 70% の崖の上に並んでおり、
  束ねと無関係に 2台↔3台を行き来する。束ねていない側のサービスのコイン投げが差に混ざり、
  「frontcart の損 +0.74」のような、実際には recommendation の1台増だけが理由の数字が出ていた。

考え方:
  束ねの損とは「同じPodに入れられたせいで、自分に必要な台数より多く立たされた」分だけ。
    束ねPodの台数 n_bundle に対し、
    損 = Σ_{s∈束ね} 枠_s × max(0, n_bundle − そのサービスが単独なら必要だった台数)
  「単独なら必要だった台数」は分離構成(normal)の同じ負荷での台数を使う。
  束ねに入っていないサービスは一切数えない(それがノイズの発生源だったため)。
"""
import csv, sys, collections, statistics as st

REQ = {r['deploy']: float(r['request_m'])
       for r in csv.DictReader(open('rightsize-requests.csv'))}
# 束ねPodに同居しているサービス(frontend 以外)。3つ以上でも同じ枠組みで扱える。
PARTNERS = {'frontcatalog':     ['productcatalogservice'],
            'frontreco':        ['recommendationservice'],
            'frontcart':        ['cartservice'],
            'frontrecocatalog': ['recommendationservice', 'productcatalogservice'],
            'frontrecocartcatalog': ['recommendationservice', 'productcatalogservice', 'cartservice']}

def parse(s):
    d = {}
    for t in s.split():
        k, _, v = t.rpartition(':')
        try: d[k] = int(v)
        except ValueError: pass
    return d

path = sys.argv[1] if len(sys.argv) > 1 else 'results-rs4.csv'
rows = list(csv.DictReader(open(path)))

# 分離構成の台数(= 単独なら必要だった台数)。同じ (cycle, rate) の normal を使う。
# 再開などで同じラベルが重複する場合は、出現順に対応づける。
solo = collections.defaultdict(list)
for r in rows:
    if r['arm'] == 'normal':
        solo[(r['cycle'], r['target_rate'])].append(parse(r['replicas']))

print(f"# {path}\n# 束ね起因の粒度損 = Σ 枠 ×(束ねPodの台数 − 単独で必要だった台数)、負の分は0\n")
print(f"{'cyc':>3} {'負荷':>5} {'束ね':<13}{'束ねPod台数':>11}{'内訳(単独なら)':>26}{'損[コア]':>9}  {'p50':>7}{'取りこぼし(窓)':>12}")
agg = collections.defaultdict(list)
for r in rows:
    arm = r['arm']
    if arm == 'normal': continue
    ps = PARTNERS[arm]
    ss = solo.get((r['cycle'], r['target_rate']))
    if not ss: continue
    s0 = ss[-1]                      # 同ラベルが複数あれば最後(=やり直した方)を使う
    rep = parse(r['replicas'])
    nb = rep.get('frontend', 0)
    n_fe = s0.get('frontend', 0)
    loss = REQ['frontend'] * max(0, nb - n_fe)
    for p in ps:
        loss += REQ[p] * max(0, nb - s0.get(p, 0))
    loss /= 1000
    agg[(r['target_rate'], arm)].append(loss)
    detail = "frontend %d / %s" % (n_fe, " ".join("%s %d" % (p[:9], s0.get(p, 0)) for p in ps))
    d = r.get('dropped_win')
    print(f"{r['cycle']:>3} {r['target_rate']:>5} {arm:<13}{nb:>11}{detail:>26}{loss:>+9.2f}  "
          f"{float(r['p50']):>6.0f}ms{(d if d not in (None,'') else '-'):>12}")

print("\n## まとめ(負荷ごと)")
for rate in ('150', '200', '250'):
    print(f"  {rate}周/s")
    for arm in ('frontcatalog', 'frontreco', 'frontcart'):
        v = agg.get((rate, arm))
        if not v: continue
        sd = st.stdev(v) if len(v) > 1 else 0.0
        print(f"    {arm:<13} 損 {st.mean(v):+.2f} ± {sd:.2f} コア  (各回 {[round(x,2) for x in v]}, 損が出た回 {sum(1 for x in v if x>0)}/{len(v)})")
