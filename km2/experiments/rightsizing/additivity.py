#!/usr/bin/env python3
"""枠(requests)適正化の第2版 — 加法性の確認 (手順書の修正項目 7)。

確かめたいこと:
  第2版のモデル  CPU_s = c0_s + a_s,buy × x_buy + a_s,view × x_view  は、
  「購入型と閲覧型の CPU は足し算できる (混ぜても互いの1周あたり CPU が変わらない)」ことを前提にしている。

既存データで確かめられる範囲 (mix / mix2 の分離アーム, buy=100 固定で view を 0→100→200→300):
  (a) view について直線か: 0→100, 100→200, 200→300 の増分 (= 区間ごとの a_view) が揃っているか。
      揃っていなければ、view を足すと購入側の CPU も変わる (相互作用) か、view 自体のカーブが曲がっている。
  (b) --table に rightsize2.py の出力 (a_buy, a_view, c0) を渡すと、それで mix の各点を予測した誤差も出す。
      これが本来の加法性の検証 (クラス別に1つずつ測った係数を足して、混ぜた実測に当てる)。
      STEP 1 (measure-class-cpu.sh) を回す前は (a) だけ。

CPU の求め方 (calibrate.py と同じ):
  timeline の各サンプルで  需要 = HPA 利用率 × 台数 × 枠  [m] (そのサービスが全台で使っている CPU)。
  計測窓 (t_rel >= WARM) のサンプルだけ使い、台数が変わってから SETTLE 秒以内のサンプルは捨てる。
  枠はログの「枠(req/上限lim)」行から、その点の直前に当てていた値を読む。
  取りこぼし (dropped_win > 0) の点は CPU が需要より少なく出るので捨てる。

使い方:
  python3 additivity.py --runs ../summer2026/mix ../summer2026/mix2
  python3 additivity.py --runs ../summer2026/mix ../summer2026/mix2 --table rightsize2-requests.csv
"""
import argparse, csv, re, statistics as st
from collections import defaultdict

ap = argparse.ArgumentParser()
ap.add_argument('--runs', nargs='+', required=True, help='拡張子なしのパス。<run>.log と timeline-<名>.csv, results-<名>.csv を読む')
ap.add_argument('--arm', default='normal')
ap.add_argument('--warm', type=float, default=180)
ap.add_argument('--settle', type=float, default=60, help='台数が変わってからこの秒数のサンプルは捨てる')
ap.add_argument('--p50-max', type=float, default=1e9, help='購入型の p50 [ms] がこれを超えた点 (待ち行列が伸びた点) も捨てる')
ap.add_argument('--table', help='rightsize2.py の出力 (a_buy, a_view, c0_m 列)。あれば予測誤差も出す')
a = ap.parse_args()

pt_re = re.compile(r'==== \[cyc(\d+)\]\[([^\]]+)\] 購入=(\d+)周/秒 閲覧=(\d+)周/秒')
req_re = re.compile(r'([\w-]+?)=?(\w[\w-]*):(\d+)m/')


def parse_req(line):
    """「枠(req/上限lim): a=c:300m/500m, b=c:1077m/1600m,c2:662m/1, ...」→ {deploy: m}。
    束ねた Pod のコンテナは "frontend=server:...,productcatalog:..." の形だが、分離アームでは1コンテナずつ。"""
    out = {}
    for item in line.split(':', 1)[1].split(', '):
        m = re.match(r'\s*([\w-]+)=([\w-]+):(\d+)m/', item)
        if m:
            out[m.group(1)] = float(m.group(3))
    return out


# ---- データ: D[svc][(run, cycle)][view] = [需要サンプル] ----
D = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))
for run in a.runs:
    name = run.rsplit('/', 1)[-1]
    base = run.rsplit('/', 1)[0] if '/' in run else '.'
    reqs = {}          # (cycle, buy, view) -> 枠の辞書
    last = {}
    for line in open(run + '.log'):
        if '枠(req/上限lim)' in line:
            last = parse_req(line)
        m = pt_re.search(line)
        if m and m.group(2) == a.arm:
            reqs[(m.group(1), m.group(3), m.group(4))] = dict(last)
    bad = set()
    for r in csv.DictReader(open('%s/results-%s.csv' % (base, name))):
        if r['arm'] == a.arm and (float(r.get('dropped_win') or 0) > 0 or float(r.get('browse_dropped_win') or 0) > 0
                               or float(r.get('p50') or 0) > a.p50_max):
            bad.add((r['cycle'], r['target_rate'], r.get('browse_rate_target') or r.get('browse_rate')))
    prev_n = {}
    changed_at = {}
    for r in csv.DictReader(open('%s/timeline-%s.csv' % (base, name))):
        if r['arm'] != a.arm or r['hpa_util_pct'] == '':
            continue
        key = (r['cycle'], r['target_rate'], r['browse_rate'])
        s, t, n = r['deploy'], float(r['t_rel']), int(r['current_replicas'])
        pk = (key, s)
        if prev_n.get(pk) is not None and prev_n[pk] != n:
            changed_at[pk] = t
        prev_n[pk] = n
        if t < a.warm or t - changed_at.get(pk, -1e9) < a.settle:
            continue
        if key in bad or key not in reqs or s not in reqs[key]:
            continue
        D[s][(name, r['cycle'])][int(r['browse_rate'])].append(float(r['hpa_util_pct']) / 100 * n * reqs[key][s])
    print('%s: 点 %d, 取りこぼし (と p50 超過) で捨てた点 %d' % (name, len(reqs), len(bad)))

coef = {}
if a.table:
    for r in csv.DictReader(open(a.table)):
        coef[r['deploy']] = (float(r.get('c0_m') or 0), float(r.get('a_buy') or 'nan'), float(r.get('a_view') or 'nan'))

VIEWS = [0, 100, 200, 300]
print('\n(a) view について直線か。区間ごとの傾き a_view [m/(周/秒)] = 区間の CPU 増分 ÷ 100。')
print('    サイクルごとに出して、サイクル間の平均 ± 標準偏差 (n=サイクル数)。曲がり = (200→300 の傾き) ÷ (0→100 の傾き)')
print('%-22s %8s | %-16s %-16s %-16s | %6s' % ('deploy', 'CPU@v0', '0→100', '100→200', '200→300', '曲がり'))
for s in sorted(D, key=lambda s: -st.mean(st.median(v[0]) for v in D[s].values() if v.get(0))):
    seg = defaultdict(list)
    base0 = []
    for cyc, byv in D[s].items():
        med = {v: st.median(byv[v]) for v in VIEWS if byv.get(v)}
        if 0 in med:
            base0.append(med[0])
        for v0, v1 in zip(VIEWS, VIEWS[1:]):
            if v0 in med and v1 in med:
                seg[(v0, v1)].append((med[v1] - med[v0]) / 100)
    cells = []
    for k in zip(VIEWS, VIEWS[1:]):
        L = seg.get(k, [])
        cells.append('%5.2f±%4.2f(%2d)' % (st.mean(L), st.stdev(L) if len(L) > 1 else 0, len(L)) if L else '-')
    first, lastseg = seg.get((0, 100)), seg.get((200, 300))
    curv = st.mean(lastseg) / st.mean(first) if first and lastseg and abs(st.mean(first)) > 0.05 else float('nan')
    print('%-22s %8.0f | %-16s %-16s %-16s | %6.2f' % (s, st.mean(base0) if base0 else float('nan'), *cells, curv))

if coef:
    print('\n(b) クラス別の係数 (--table) で mix の各点を予測した誤差 [%] = (予測 − 実測) ÷ 実測。サイクル平均。')
    print('    台数 n のときの予測 = n × c0 + a_buy × 100 + a_view × view (全台合計の CPU)')
    print('%-22s ' % 'deploy' + ' '.join('%10s' % ('view%d' % v) for v in VIEWS))
    for s in sorted(D):
        if s not in coef:
            continue
        c0, ab, av = coef[s]
        cells = []
        for v in VIEWS:
            errs = []
            for cyc, byv in D[s].items():
                if byv.get(v):
                    meas = st.median(byv[v])
                    pred = c0 + ab * 100 + av * v     # 1台換算 (c0 の台数補正は calibrate.py と同じく別扱い)
                    errs.append((pred - meas) / meas * 100)
            cells.append('%+9.1f%%' % st.mean(errs) if errs else '%10s' % '-')
        print('%-22s ' % s + ' '.join(cells))
