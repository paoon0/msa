#!/usr/bin/env python3
"""枠(requests)適正化の第2版 — 手順 STEP 4/5: 検証と較正。

STEP 4 (検証): 新しい枠を当て、HPA を入れて基準ミックスの負荷をかけた時系列(bundle-vs-loss2.sh の
  timeline-*.csv、分離アーム)から、各サービスの枠 r_s を「採用してよいか」を判定する。
  次の2つを両方満たしたら採用 (2026-10-07 に定義。旧版の「合格帯 66〜74%」は廃止):
    採用条件 (i)  1台時の利用率 u1 が 64% 以上 68% 以下 (--band)。
                  u1 = 1台で担当したときの CPU ÷ r_s。サイクルごとに中央値を取り、サイクル間で平均する。
    採用条件 (ii) 開始台数が1台の実験でも2台の実験でも、計測窓の終わりに1台になっている。
                  → timeline を PRESCALE=1 と PRESCALE=2 の両方で渡す (開始台数は t_rel=0 の台数から自動で読む)。
  帯の根拠: HPA は 70%×1.1 = 77% を超えると増やすが、いったん2台になると、合計の需要が 1台の 70% 以下に
  ならないと1台に戻らない。だから 70〜77% は「履歴次第で1台にも2台にもなる帯」。上限 68% はそこから
  サイクル間ばらつき (約2ポイント) を離した値、幅 4 ポイントはサービス間で u1 を揃えるため。
STEP 5 (較正): 採用条件を満たさないサービスだけ  枠 ← U1 / θ  (θ = 0.66) に置き換えた表を書き出す。
  その表で STEP 4 をもう一度回す。

精度として報告するのは「較正前」の誤差だけ (修正項目 6)。較正後は STEP 4 の実測に合わせ込んだ値なので、
  それで誤差を測ると0に近く出るのは当たり前で、精度の証拠にならない。
  較正前の誤差 = (表の U_ref_m − 実測 U1) ÷ 実測 U1。表に U_ref_m 列が無い (第1版の表) ときは出さない。

1台時の CPU の求め方:
  時系列の各サンプルで  需要 = 利用率 × 台数 × 枠 [m] (= そのサービス全体が使っている CPU)。
  2台以上なら、増えた台数ぶんのアイドル分 c0 を引いて1台時に換算する:  U1 = 需要 − c0 × (台数 − 1)
  c0 は rightsize2.py の表の c0_m 列 (無ければ 0 = 換算しない。そのときは警告を出す)。
  捨てるサンプル (修正項目 4): ウォームアップ (--warm) より前、台数が変わってから --settle 秒 (既定 60s) 以内。
  サイクル内は平均でなく中央値 (起動直後の跳ね上がりなど外れ値に引きずられないため)。

使い方:
  python3 calibrate.py --timeline ../rightsizing/timeline-rs2-verify-p1.csv ../rightsizing/timeline-rs2-verify-p2.csv \
                       --table rightsize2-requests.csv --rate 100 --browse 0 --out rightsize2-requests-cal1.csv
  # 第1版の検証(過去データ): mix/mix2 で適正化枠を当てていた4サービスだけ見る
  python3 calibrate.py --timeline ../summer2026/timeline-mix.csv --table ../summer2026/rightsize-requests.csv \
                       --services frontend productcatalogservice recommendationservice cartservice --no-c0
"""
import csv, argparse, statistics as st
from collections import defaultdict

ap = argparse.ArgumentParser()
ap.add_argument('--timeline', nargs='+', required=True, help='PRESCALE=1 と 2 の両方を渡すと採用条件 (ii) も判定する')
ap.add_argument('--table', required=True, help='その実験で当てていた枠の表(deploy,container,request_m[,c0_m,U_ref_m])')
ap.add_argument('--arm', default='normal')
ap.add_argument('--rate', default='100', help='購入型の負荷 (timeline の target_rate)')
ap.add_argument('--browse', default='0', help='閲覧型の負荷 (timeline の browse_rate)')
ap.add_argument('--warm', type=float, default=180, help='これより前のサンプルは捨てる [s]')
ap.add_argument('--settle', type=float, default=60, help='台数が変わってからこの秒数のサンプルは捨てる [s]')
ap.add_argument('--target', type=float, default=0.66, help='設計利用率 θ (較正後の枠 = U1 / θ)')
ap.add_argument('--band', type=float, nargs=2, default=[0.64, 0.68], help='採用条件 (i) の帯 (1台時の利用率)')
ap.add_argument('--services', nargs='*', help='見るサービス(省略で表の全サービス)')
ap.add_argument('--no-c0', action='store_true', help='c0 で1台時に換算しない')
ap.add_argument('--out', help='較正後の表を書き出す先(省略で書き出さない)')
a = ap.parse_args()

table = list(csv.DictReader(open(a.table)))
req = {r['deploy']: float(r['request_m']) for r in table}
has_c0 = 'c0_m' in table[0]
if not a.no_c0 and not has_c0:
    print("!! 表に c0_m 列が無い (第1版の表は idle_m)。2台以上のサンプルは1台時に換算せずに使う = U1 が c0 ぶん大きく出る")
c0 = {r['deploy']: (0.0 if a.no_c0 else float(r.get('c0_m') or 0)) for r in table}
uref = {r['deploy']: float(r['U_ref_m']) for r in table if r.get('U_ref_m')}
svcs = set(a.services) if a.services else set(req)

acc = defaultdict(lambda: defaultdict(list))   # svc -> (file, cycle) -> [U1]
start_n = defaultdict(dict)                    # svc -> (file, cycle) -> 開始台数 (t_rel 最小のサンプル)
end_n = defaultdict(dict)                      # svc -> (file, cycle) -> 窓の終わりの台数
dropped = defaultdict(int)
for path in a.timeline:
    prev, changed, first_t = {}, {}, {}
    for r in csv.DictReader(open(path)):
        s = r['deploy']
        if r['arm'] != a.arm or s not in svcs or s not in req:
            continue
        if r['target_rate'] != a.rate or (r.get('browse_rate') or '0') != a.browse:
            continue
        key = (path, r['cycle'])
        if r['current_replicas'] == '':
            continue
        t, n = float(r['t_rel']), int(r['current_replicas'])
        if key not in first_t.setdefault(s, {}) or t < first_t[s][key]:
            first_t[s][key] = t
            start_n[s][key] = n
        end_n[s][key] = n                         # 時系列は時刻順に並んでいる
        if prev.get((s, key)) is not None and prev[(s, key)] != n:
            changed[(s, key)] = t
        prev[(s, key)] = n
        if r['hpa_util_pct'] == '' or t < a.warm:
            continue
        if t - changed.get((s, key), -1e9) < a.settle:
            dropped[s] += 1
            continue
        demand = float(r['hpa_util_pct']) / 100 * n * req[s]
        acc[s][key].append(demand - c0[s] * (n - 1))

lo, hi = a.band
print("採用条件 (i) 1台時の利用率 %.0f〜%.0f%%   (ii) 開始台数によらず窓の終わりに1台   負荷 buy=%s view=%s"
      % (lo * 100, hi * 100, a.rate, a.browse))
print("サンプル: t_rel>=%.0fs、台数変化後 %.0fs は除外、サイクル内は中央値   c0換算=%s"
      % (a.warm, a.settle, 'なし' if a.no_c0 else ('あり' if has_c0 else 'なし(列が無い)')))
print("%-24s %6s %7s %15s %6s %-14s %5s %5s %s" % (
    "deploy", "枠m", "U1 m", "u1 % (sd, n)", "(i)", "終わりの台数", "(ii)", "採用", "較正前の誤差 / 較正後の枠m"))
new, n_ng = {}, 0
for s in sorted(acc, key=lambda s: -req[s]):
    per_cyc = [st.median(L) for L in acc[s].values() if L]
    if not per_cyc:
        continue
    U1 = st.mean(per_cyc)
    u1 = [x / req[s] for x in per_cyc]
    m = st.mean(u1); sd = st.stdev(u1) if len(u1) > 1 else 0.0
    ok1 = lo <= m <= hi
    # (ii): 開始台数ごとに、窓の終わりの台数
    by_start = defaultdict(list)
    for key, n_end in end_n[s].items():
        by_start[start_n[s][key]].append(n_end)
    ends = ' '.join('%d台→%s' % (k, ','.join(map(str, v))) for k, v in sorted(by_start.items()))
    starts = set(by_start)
    ok2 = all(x == 1 for v in by_start.values() for x in v)
    judged2 = {1, 2} <= starts
    ok = ok1 and ok2
    n_ng += (not ok)
    new[s] = req[s] if ok else round(U1 / a.target)
    err = '%+5.1f%%' % ((uref[s] - U1) / U1 * 100) if s in uref else '   -  '
    print("%-24s %6.0f %7.0f %6.1f (%4.1f, %d) %6s %-14s %5s %5s %s %s" % (
        s, req[s], U1, m * 100, sd * 100, len(u1), '満たす' if ok1 else '×',
        ends, ('満たす' if ok2 else '×') if judged2 else '(未判定)', '採用' if ok else '★不採用',
        err, '' if ok else '→ %d (%+.0f%%)' % (new[s], (new[s] / req[s] - 1) * 100)))
print("\n不採用 %d / %d サービス。(ii) が「未判定」= PRESCALE=1 と 2 の両方の時系列が渡されていない。" % (n_ng, len(acc)))
print("較正前の誤差 = (表の U_ref − 実測 U1) ÷ 実測 U1。**精度として報告するのはこの値だけ** (較正後の表では測らない)。")
if dropped:
    print("台数変化の直後で捨てたサンプル数: " + ', '.join('%s=%d' % kv for kv in sorted(dropped.items())))

if a.out:
    with open(a.out, 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(table[0].keys()))
        w.writeheader()
        for r in table:
            r = dict(r)
            if r['deploy'] in new:
                r['request_m'] = new[r['deploy']]
            w.writerow(r)
    print("書き出し: %s  → この表で STEP 4 をもう一度回し、全サービスが採用条件 (i)(ii) を満たせば確定。" % a.out)
