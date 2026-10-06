#!/usr/bin/env python3
"""枠(requests)適正化の第2版 — 手順 STEP 4/5: 検証と較正。

STEP 4 (検証): 新しい枠を当て、HPA を入れて基準ミックスの負荷をかけた時系列(bundle-vs-loss2.sh の
  timeline-*.csv、分離アーム)から、各サービスの「1台で担当したときの利用率」u1 を求め、
  合格帯(既定 66〜74%)に入っているかを判定する。
    合格帯の根拠: HPA は利用率が 70%×(1±0.1) = 63〜77% の間では台数を変えない(許容幅)。
                  そこからサイクル間ばらつき(約3ポイント)を差し引いた内側を合格とする。
STEP 5 (較正): 不合格のサービスだけ  枠 ← U1 / θ  (U1 = 1台時の実測 CPU)に置き換えた表を書き出す。
  1回で足りなければ、その表で STEP 4 をもう一度回す。

1台時の CPU の求め方:
  時系列の各サンプルで  需要 = 利用率 × 台数 × 枠 [m]  (= そのサービス全体が使っている CPU)。
  HPA が2台以上にしていたら、増えた台数ぶんのアイドル分 c0 を引いて1台時に換算する:
    U1 = 需要 − c0 × (台数 − 1)
  c0 は rightsize2.py が出した表の c0_m 列を使う(無ければ 0 = 換算しない)。

使い方:
  python3 calibrate.py --timeline ../summer2026/timeline-xxx.csv --table rightsize2-requests.csv \
                       --rate 100 --browse 0 --out rightsize2-requests-cal1.csv
  # 第1版の検証(過去データ): mix/mix2 で適正化枠を当てていた4サービスだけ見る
  python3 calibrate.py --timeline ../summer2026/timeline-mix.csv --table ../summer2026/rightsize-requests.csv \
                       --services frontend productcatalogservice recommendationservice cartservice --no-c0
"""
import csv, argparse, statistics as st
from collections import defaultdict

ap = argparse.ArgumentParser()
ap.add_argument('--timeline', nargs='+', required=True)
ap.add_argument('--table', required=True, help='その実験で当てていた枠の表(deploy,container,request_m[,c0_m])')
ap.add_argument('--arm', default='normal')
ap.add_argument('--rate', default='100', help='購入型の負荷 (timeline の target_rate)')
ap.add_argument('--browse', default='0', help='閲覧型の負荷 (timeline の browse_rate)')
ap.add_argument('--warm', type=float, default=180, help='これより前のサンプルは捨てる [s]')
ap.add_argument('--target', type=float, default=0.70)
ap.add_argument('--band', type=float, nargs=2, default=[0.66, 0.74], help='合格帯(1台時の利用率)')
ap.add_argument('--services', nargs='*', help='見るサービス(省略で表の全サービス)')
ap.add_argument('--no-c0', action='store_true', help='c0 で1台時に換算しない')
ap.add_argument('--out', help='較正後の表を書き出す先(省略で書き出さない)')
a = ap.parse_args()

table = list(csv.DictReader(open(a.table)))
req = {r['deploy']: float(r['request_m']) for r in table}
c0 = {r['deploy']: (0.0 if a.no_c0 else float(r.get('c0_m') or 0)) for r in table}
svcs = set(a.services) if a.services else set(req)

acc = defaultdict(lambda: defaultdict(list))   # svc -> cycle -> [(U1, n)]
for path in a.timeline:
    for r in csv.DictReader(open(path)):
        s = r['deploy']
        if r['arm'] != a.arm or s not in svcs or r['hpa_util_pct'] == '':
            continue
        if r['target_rate'] != a.rate or (r.get('browse_rate') or '0') != a.browse:
            continue
        if float(r['t_rel']) < a.warm:
            continue
        n = int(r['current_replicas'])
        demand = float(r['hpa_util_pct']) / 100 * n * req[s]
        acc[s][(path, r['cycle'])].append((demand - c0[s] * (n - 1), n))

lo, hi = a.band
print("合格帯 %.0f〜%.0f%% (HPA の不感帯 %.0f〜%.0f%% の内側)   負荷 buy=%s view=%s   c0換算=%s"
      % (lo * 100, hi * 100, a.target * 90, a.target * 110, a.rate, a.browse, 'なし' if a.no_c0 else 'あり'))
print("%-24s %6s %8s %14s %10s %8s %s" % ("deploy", "枠m", "U1 m", "u1 % (sd, n)", "2台以上", "判定", "較正後の枠m"))
new = {}
fails = 0
for s in sorted(acc, key=lambda s: -req[s]):
    per_cyc = [st.mean(v[0] for v in L) for L in acc[s].values()]
    multi = sum(1 for L in acc[s].values() if st.mean(v[1] for v in L) > 1.5)
    U1 = st.mean(per_cyc)
    u1 = [x / req[s] for x in per_cyc]
    m = st.mean(u1); sd = st.stdev(u1) if len(u1) > 1 else 0.0
    ok = lo <= m <= hi
    fails += (not ok)
    new[s] = req[s] if ok else round(U1 / a.target)
    print("%-24s %6.0f %8.0f %6.1f (%4.1f, %d) %7d/%d %8s %s" % (
        s, req[s], U1, m * 100, sd * 100, len(u1), multi, len(u1), '合格' if ok else '★不合格',
        '' if ok else '%d (%+.0f%%)' % (new[s], (new[s] / req[s] - 1) * 100)))
print("\n不合格 %d / %d サービス。「2台以上」= 計測窓の平均台数が 1.5 を超えたサイクル数"
      "(合格でもここが多ければ、立ち上がりの過渡で増えて戻らなかった可能性)。" % (fails, len(acc)))

if a.out:
    with open(a.out, 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(table[0].keys()))
        w.writeheader()
        for r in table:
            r = dict(r)
            if r['deploy'] in new:
                r['request_m'] = new[r['deploy']]
            w.writerow(r)
    print("書き出し: %s  → この表で STEP 4 をもう一度回し、全サービス合格なら確定。" % a.out)
