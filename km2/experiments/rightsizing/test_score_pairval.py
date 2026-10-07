#!/usr/bin/env python3
"""score_pairval.py の空回しテスト (偽データ)。

何のためか: 本走の結果を開く前に、採点規則 (prereg-pairval.md §4) の実装が期待どおり動くことを、
  予測表から作った偽の results / timeline / events で確かめる。本走のファイルには一切触らない。
偽データ: 予測表 K1 の中心値どおりの台数を出すベースラインを作り、1 つずつ細工して採点結果を確かめる。
  形式は summer2026/smoke/*-smoke-pairval.csv の列を真似ている。
使い方 (km2/experiments/rightsizing/ で): python3 test_score_pairval.py [偽データの出力先ディレクトリ]
  既定の出力先 = スクラッチパッドの fake/ (ベースラインの CSV を書き出して、CLI でも通ることを確かめる)。
"""
import csv
import io
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import score_pairval as sp  # noqa: E402

FAKE = sys.argv[1] if len(sys.argv) > 1 else \
    '/tmp/claude-1000/-home-mizuki--------msa/f19a71cf-0131-4423-8285-543cfa375857/scratchpad/fake'
WARM, MEAS, STEP = 180, 240, 15
ALL = ['adservice', 'cartservice', 'checkoutservice', 'currencyservice', 'emailservice', 'frontend',
       'paymentservice', 'productcatalogservice', 'recommendationservice', 'shippingservice']
# 同居アームで消える (別コンテナになる) Deployment
ABSORBED = {'pairsX': ['recommendationservice', 'paymentservice', 'emailservice'],
            'pairsY': ['paymentservice', 'recommendationservice', 'checkoutservice'],
            'pairsY2': ['emailservice', 'recommendationservice', 'shippingservice']}
RES_COLS = ('cycle,arm,target_rate,iter_rate,dropped,failed_rate,p50,p99,running_cores,pending_cores,'
            'eff_iter_per_running_core,pods,pending,node_cpu_sec,softirq_cpu_sec,k6_cpu_sec,prod_p50,cart_p50,chk_p50,'
            'prod_p99,cart_p99,chk_p99,replicas,limit_x,dropped_win,started,replicas_at_window_start,'
            'replicas_changed_in_window,browse_rate_target,browse_rate,browse_dropped_win,browse_p50,browse_p99,'
            'rs_scale,limit_scale,reserved_core_sec,pending_core_sec,reserved_avg_cores,n_samples,point,'
            'start_replicas,start_ok,frames_ok').split(',')
TL_COLS = ('cycle,arm,target_rate,limit_x,browse_rate,t_rel,deploy,container,hpa_util_pct,current_replicas,'
           'desired_replicas,ready_replicas,pending_pods,ns_running_cores,ns_pending_cores,point,start_replicas').split(',')
EV_COLS = 'cycle,arm,target_rate,limit_x,browse_rate,time,object,message,point,start_replicas'.split(',')

PRED1 = sp.load_pred(os.path.join(HERE, 'predictions-pairval-K1.csv'))
PRED2 = sp.load_pred(os.path.join(HERE, 'predictions-pairval-K2.csv'))


def normal_counts(pt, st):
    """予測表の中心値から、normal アームの Deployment ごとの台数を作る (予測表の内部整合は確認済み)。"""
    d = {x: 1 for x in ALL}
    for (pair, p, s), r in PRED1.items():
        if p == pt and s == st:
            d[r['s']] = int(float(r['n_s']))
            d[r['t']] = int(float(r['n_t']))
    return d


def pair_counts(arm, pt, st):
    """同居アームの Deployment ごとの台数。同居 Pod は予測の n_st、それ以外は normal と同じ。"""
    d = {k: v for k, v in normal_counts(pt, st).items() if k not in ABSORBED[arm]}
    for (pair, p, s), r in PRED1.items():
        if p == pt and s == st and sp.PAIR_POD[pair][0] == arm:
            d[sp.PAIR_POD[pair][1]] = int(float(r['n_st']))
    return d


class Fake:
    """偽データのビルダ。上書き (override) で細工する。"""

    def __init__(self, cycles=(1, 2, 3)):
        self.res, self.tl, self.ev = [], [], []
        self.cycles = cycles
        self.over = {}   # (cycle, arm, point, start) -> dict(counts=..., series=..., res=..., ready=...)

    def set(self, cyc, arm, pt, st, **kw):
        self.over.setdefault((str(cyc), arm, pt, str(st)), {}).update(kw)

    def build(self):
        self.res, self.tl, self.ev = [], [], []
        for c in self.cycles:
            for arm in ('normal', 'pairsX', 'pairsY', 'pairsY2'):
                for pt in sp.POINTS:
                    for st in sp.STARTS:
                        self.emit(c, arm, pt, st)
        return self

    def emit(self, c, arm, pt, st, extra_over=None):
        k = (str(c), arm, pt, st)
        ov = dict(self.over.get(k, {}))
        n0 = int(st)
        counts = normal_counts(pt, st) if arm == 'normal' else pair_counts(arm, pt, st)
        counts = dict(counts)
        counts.update(ov.get('counts', {}))
        bv = {'b100v0': (100, 0), 'b100v100': (100, 100), 'b100v150': (100, 150)}[pt]
        res = {k2: '' for k2 in RES_COLS}
        res.update(cycle=c, arm=arm, target_rate=bv[0], dropped_win=0, pending=0, browse_rate_target=bv[1],
                   browse_dropped_win=0, point=pt, start_replicas=st, start_ok=1, frames_ok=1, limit_x=0)
        res.update(ov.get('res', {}))
        for rep in range(ov.get('reruns_bad', 0)):   # 再実行テスト: 先行する無効な行
            bad = dict(res); bad['start_ok'] = 0
            self.res.append(bad)
            self.series(c, arm, pt, st, counts, {}, bv)
        self.res.append(res)
        self.series(c, arm, pt, st, counts, ov, bv)

    def series(self, c, arm, pt, st, counts, ov, bv):
        """15 秒ごと t=0..WARM+MEAS。series[deploy] = {t: (current, ready)} で細工できる。redis-cart は出さない。"""
        ser = ov.get('series', {})
        for t in range(0, WARM + MEAS + 1, STEP):
            for d, n in counts.items():
                cur, rdy = n, n
                if d in ser and t in ser[d]:
                    cur, rdy = ser[d][t]
                conts = ['server', 'x'] if (arm != 'normal' and d in [v[1] for v in sp.PAIR_POD.values()]) else ['server']
                for cn in conts:
                    pend = ov.get('pending_at', {}).get((d, t), 0)
                    self.tl.append(dict(cycle=c, arm=arm, target_rate=bv[0], limit_x=0, browse_rate=bv[1], t_rel=t,
                                        deploy=d, container=cn, hpa_util_pct=60, current_replicas=cur,
                                        desired_replicas=cur, ready_replicas=rdy, pending_pods=pend,
                                        ns_running_cores=9, ns_pending_cores=0, point=pt, start_replicas=st))

    def write(self, d):
        os.makedirs(d, exist_ok=True)
        for name, rows, cols in (('results', self.res, RES_COLS), ('timeline', self.tl, TL_COLS), ('events', self.ev, EV_COLS)):
            with open(os.path.join(d, name + '.csv'), 'w', newline='') as fh:
                w = csv.DictWriter(fh, fieldnames=cols, extrasaction='ignore')
                w.writeheader()
                w.writerows(rows)
        with open(os.path.join(d, 'fake.log'), 'w') as fh:
            fh.write('================ BUNDLE-VS-LOSS2 START fake arms=[normal] warm=%ds meas=%ds ================\n' % (WARM, MEAS))


def run(fake, **kw):
    """CSV を書いて読み直してから score() に通す (CSV の形式崩れも検出する)。"""
    with tempfile.TemporaryDirectory() as td:
        fake.write(td)
        rd = lambda n: sp.read_csv(os.path.join(td, n + '.csv'))
        warm, meas = sp.read_log_params(os.path.join(td, 'fake.log'))
        assert (warm, meas) == (WARM, MEAS), (warm, meas)
        return sp.score(rd('results'), rd('timeline'), rd('events'), PRED1, PRED2, warm, **kw)


def cell(cells, pair, pt, st):
    return [c for c in cells if (c['pair'], c['point'], c['start']) == (pair, pt, st)][0]


def find_cell(pred, **cond):
    """条件に合う (novel, 確定, 自明でない, 区分) の最初のセルのキーを返す。"""
    for k, r in sorted(pred.items()):
        if 'cat' in cond and r['category'] != cond['cat']:
            continue
        if cond.get('confirmed') and (r['category'] == '不明' or r['bistable'] != 'no'):
            continue
        if cond.get('novel') and k[0] in sp.OLD_PAIRS:
            continue
        if cond.get('nontrivial') and sp.triple_of(r) == (1, 1, 1):
            continue
        if 'min_nst' in cond and int(float(r['n_st'])) < cond['min_nst']:
            continue
        return k
    raise AssertionError('条件に合うセルがない: %s' % cond)


def summary_text(cells, runs, warnings):
    buf = io.StringIO()
    sp.summarize(cells, runs, warnings, buf)
    return buf.getvalue()


RESULTS = []


def check(name, cond, detail=''):
    RESULTS.append((name, bool(cond)))
    print('  [%s] %s %s' % ('OK' if cond else 'NG', name, detail))


def main():
    # ---------- (1) 全部予測どおり ----------
    f = Fake().build()
    f.write(FAKE)   # ベースラインを scratchpad に残す (CLI の確認用)
    cells, runs, warns = run(f)
    print('(1) 全部予測どおり')
    for K, sel in (('K1', lambda c: c['confirmed1']), ('K2', lambda c: c['confirmed2'])):
        kc, nc, _, _ = sp.agg(cells, lambda c: sel(c) and c['novel'], K)
        check('K=%s 損の区分 100%%' % K[1], nc > 0 and kc == nc, '(%d/%d)' % (kc, nc))
    kc, nc, _, _ = sp.agg(cells, lambda c: c['confirmed1'] and c['novel'], 'triple')
    check('3つ組の一致 100%', nc > 0 and kc == nc, '(%d/%d)' % (kc, nc))
    txt = summary_text(cells, runs, warns)
    n_ident = sum(1 for c in cells if c['valid_cell'] and c['novel'] and c['confirmed1']
                  and (c['pred']['K1'] != c['pred']['R1'] or c['pred']['K1'] != c['pred']['R2']))
    check('識別セルが 1 個以上ある (偽データで (ii) を判定できる)', n_ident > 0, '(%d 個)' % n_ident)
    check('合格と出力', '=> 判定: 合格' in txt)
    check('無効セル 0', all(c['valid_cell'] and c['n_invalid'] == 0 and c['n_unstable'] == 0 for c in cells))
    check('警告なし', not warns, str(warns))

    # 損ありの確定・新規・自明でないセル (細工用)
    kl = find_cell(PRED1, cat='損あり', confirmed=True, novel=True, nontrivial=True)
    pair, pt, st = kl
    arm, pod = sp.PAIR_POD[pair]
    p = PRED1[kl]
    print('   細工に使う損ありセル: %s (n_s,n_t,n_st=%s,%s,%s)' % (kl, p['n_s'], p['n_t'], p['n_st']))

    # ---------- (2) 損ありセルで実測が損なし → 外れ ----------
    f = Fake()
    n_s, n_t = int(float(p['n_s'])), int(float(p['n_t']))
    # n_st を損 0 になる値にする: n_st(r_s+r_t) = n_s r_s + n_t r_t を満たす整数が無いので、n_st = max(n_s, n_t) 未満にして得にならないよう
    # 代わりに normal 側を細工して n_s=n_t=n_st にする (損 = 0)
    nst = int(float(p['n_st']))
    for c in (1, 2, 3):
        f.set(c, 'normal', pt, st, counts={p['s']: nst, p['t']: nst})
    f.build()
    cells, runs, _ = run(f)
    c = cell(cells, pair, pt, st)
    check('(2) 実測が損なし -> K1 の一致 = 外れ', c['vote']['K1'] is False and all(m['cat'] == '損なし' for _, m in c['recs']))
    check('(2) 他の確定セルは影響なし (損の区分の外れは normal を共有する同サービス含むセルのみ)',
          sp.agg(cells, lambda x: x['confirmed1'] and x['novel'], 'K1')[0] < sp.agg(cells, lambda x: x['confirmed1'] and x['novel'], 'K1')[1])

    # ---------- (3) 窓内で台数が変わる → 不安定 = 外れ ----------
    f = Fake()
    ser = {pod: {t: (nst + 1, nst + 1) for t in range(WARM + 120, WARM + MEAS + 1, STEP)}}   # 窓の後半で +1 (9/17 サンプル)
    f.set(1, arm, pt, st, series=ser)
    f.build()
    cells, _, _ = run(f)
    c = cell(cells, pair, pt, st)
    m1 = c['recs'][0][1]
    check('(3a) 1サイクルで窓内変化 -> 不安定', m1['valid'] and m1['unstable'])
    check('(3a) そのサイクルは外れ、セルは 2/3 で多数決は当たり', c['cyc_hits']['K1'] == [False, True, True] and c['vote']['K1'] is True)
    # 最頻値 80% 以上でも値が2種類なら不安定 (1 サンプルだけ +1)
    f = Fake()
    f.set(1, arm, pt, st, series={pod: {WARM + 30: (nst + 1, nst + 1)}})
    f.build()
    cells, _, _ = run(f)
    check('(3b) 1 サンプルだけの変化でも (最頻値 94%) 台数が変わったので不安定',
          cell(cells, pair, pt, st)['recs'][0][1]['unstable'])
    # 窓の外 (ウォームアップ中) の変化は不安定にしない
    f = Fake()
    f.set(1, arm, pt, st, series={pod: {t: (nst + 1, nst + 1) for t in range(0, WARM, STEP)}})
    f.build()
    cells, _, _ = run(f)
    m = cell(cells, pair, pt, st)['recs'][0][1]
    check('(3c) ウォームアップ中 (t<WARM) の変化は無視', m['valid'] and not m['unstable'] and m['triple'][2] == nst)
    # 2 サイクル不安定 → セル外れ
    f = Fake()
    for cy in (1, 2):
        f.set(cy, arm, pt, st, series={pod: {t: (nst + 1, nst + 1) for t in range(WARM + 120, WARM + MEAS + 1, STEP)}})
    f.build()
    cells, _, _ = run(f)
    check('(3d) 2/3 サイクル不安定 -> セルは外れ', cell(cells, pair, pt, st)['vote']['K1'] is False)

    # ---------- (4) dropped_win > 0 → 無効 ----------
    f = Fake()
    f.set(1, arm, pt, st, res={'dropped_win': 5})
    f.build()
    cells, _, _ = run(f)
    c = cell(cells, pair, pt, st)
    check('(4a) 1サイクル dropped_win>0 -> そのサイクルだけ無効 (票は 2 票)', c['n_invalid'] == 1 and len(c['cyc_hits']['K1']) == 2 and c['valid_cell'])
    f = Fake()
    for cy in (1, 2, 3):
        f.set(cy, 'normal', pt, st, res={'dropped_win': 1})     # normal 側の無効も同サイクルを無効にする
    f.build()
    cells, runs, w = run(f)
    c = cell(cells, pair, pt, st)
    allc = sp.agg(cells, lambda x: x['confirmed1'] and x['novel'], 'K1')
    check('(4b) 全サイクル無効 -> 無効セル、分母から外れる', not c['valid_cell'] and c['vote']['K1'] is not False)
    base = sp.agg(Fake().build() and run(Fake().build())[0], lambda x: x['confirmed1'] and x['novel'], 'K1')
    check('(4b) 分母が減る (normal の同点を共有するセルも無効になる)', allc[1] < base[1], '(分母 %d -> %d)' % (base[1], allc[1]))
    check('(4b) 無効理由が出力に出る', 'dropped_win>0' in summary_text(cells, runs, w))

    # ---------- (5) start_ok = 0 → 無効 ----------
    f = Fake()
    f.set(2, arm, pt, st, res={'start_ok': 0})
    f.set(3, arm, pt, st, res={'frames_ok': 0})
    f.build()
    cells, _, _ = run(f)
    c = cell(cells, pair, pt, st)
    check('(5) start_ok=0 / frames_ok=0 のサイクルは無効', [m['valid'] for _, m in c['recs']] == [True, False, False]
          and c['n_valid'] == 1)

    # ---------- (6) 多数決の同数 → 外れ ----------
    f = Fake()
    f.set(1, arm, pt, st, res={'start_ok': 0})                         # 1 本無効
    f.set(2, 'normal', pt, st, counts={p['s']: nst, p['t']: nst})       # サイクル2: 損なしに (外れ)
    f.build()                                                           # サイクル3: 予測どおり (当たり)
    cells, _, _ = run(f)
    c = cell(cells, pair, pt, st)
    check('(6) 有効 2 票で 1-1 の同数 -> セルは外れ', c['n_valid'] == 2 and c['cyc_hits']['K1'] == [False, True] and c['vote']['K1'] is False)

    # ---------- (7) 得 (損<0) → 予測が損なしなら外れ ----------
    kn = find_cell(PRED1, cat='損なし', confirmed=True, novel=True, nontrivial=True, min_nst=2)
    pair7, pt7, st7 = kn
    arm7, pod7 = sp.PAIR_POD[pair7]
    p7 = PRED1[kn]
    f = Fake()
    for cy in (1, 2, 3):
        f.set(cy, arm7, pt7, st7, counts={pod7: 1})                    # n_st=1 < n_s,n_t のどちらかが 2 以上 -> 得
    f.build()
    cells, _, _ = run(f)
    c = cell(cells, pair7, pt7, st7)
    check('(7) 得 (損<0) と区分され、予測が損なしでも外れ',
          all(m['cat'] == '得' and m['loss'] < 0 for _, m in c['recs']) and c['vote']['K1'] is False,
          '(%s n_s,n_t=%s,%s n_st=1 -> loss=%s)' % (kn, p7['n_s'], p7['n_t'], c['recs'][0][1]['loss']))

    # ---------- (8) Ready 落ち → 無効 ----------
    f = Fake()
    f.set(1, arm, pt, st, series={'cartservice': {WARM + 45: (2 if False else normal_counts(pt, st)['cartservice'],
                                                              max(normal_counts(pt, st)['cartservice'] - 1, 0))}})
    f.build()
    cells, runs, w = run(f)
    c = cell(cells, pair, pt, st)
    check('(8a) ready_replicas が current より減った (Ready 落ち) -> 無効', c['recs'][0][1]['valid'] is False
          and any('ready落ち' in x for x in c['recs'][0][1]['reasons']), str(c['recs'][0][1]['reasons']))
    cells, _, _ = run(f, ready_ignore=['cartservice'])
    check('(8b) --ready-ignore で除外できる', cell(cells, pair, pt, st)['recs'][0][1]['valid'])
    # スケールアウト直後の「まだ Ready でない」(ready < current だが減少でない) は Ready 落ちにしない
    f = Fake()
    ser = {pod: {WARM - 15: (nst, nst - 1 if nst > 1 else 1)}}
    f.set(1, arm, pt, st, series={'cartservice': {t: (normal_counts(pt, st)['cartservice'], max(normal_counts(pt, st)['cartservice'] - 1, 0))
                                                  for t in range(WARM - 30, WARM + 30, STEP)}})
    f.build()
    cells, _, _ = run(f)
    check('(8c) 窓の前から ready<current が続くだけ (減少なし) は Ready 落ちにしない (既知の限界)',
          cell(cells, pair, pt, st)['recs'][0][1]['valid'])

    # ---------- (9) Pending → 無効 ----------
    f = Fake()
    f.set(1, arm, pt, st, pending_at={('adservice', WARM + 60): 1})
    f.set(2, arm, pt, st, res={'pending': 2})
    f.build()
    cells, _, _ = run(f)
    c = cell(cells, pair, pt, st)
    check('(9) Pending (timeline の pending_pods / results の pending) -> 無効', [m['valid'] for _, m in c['recs']] == [False, False, True])

    # ---------- (10) 再実行: 有効な最後の行を使う ----------
    f = Fake()
    f.set(1, arm, pt, st, reruns_bad=1)
    f.build()
    cells, runs, w = run(f)
    c = cell(cells, pair, pt, st)
    check('(10) 再実行 (先の行は無効・後の行は有効) -> 後の行を使い有効', c['recs'][0][1]['valid'] and not w)

    # ---------- (11) CLI でも通る ----------
    out = os.path.join(FAKE, 'cells.csv')
    r = subprocess.run([sys.executable, os.path.join(HERE, 'score_pairval.py'),
                        '--results', os.path.join(FAKE, 'results.csv'), '--timeline', os.path.join(FAKE, 'timeline.csv'),
                        '--events', os.path.join(FAKE, 'events.csv'), '--log', os.path.join(FAKE, 'fake.log'),
                        '--pred', os.path.join(HERE, 'predictions-pairval-K1.csv'),
                        '--pred2', os.path.join(HERE, 'predictions-pairval-K2.csv'), '--out', out],
                       capture_output=True, text=True)
    check('(11) CLI が正常終了し判定が出る', r.returncode == 0 and '判定: 合格' in r.stdout, r.stderr[-300:])
    with open(out) as fh:
        n = sum(1 for _ in fh)
    check('(11) セル CSV の行数 = 1 + 9ペア×3点×2開始 = 55', n == 55, '(%d)' % n)

    ng = [n for n, ok in RESULTS if not ok]
    print('\nテスト: %d 件中 %d 件 OK' % (len(RESULTS), len(RESULTS) - len(ng)))
    if ng:
        print('NG:', ng)
        sys.exit(1)


if __name__ == '__main__':
    main()
