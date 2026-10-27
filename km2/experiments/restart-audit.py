#!/usr/bin/env python3
"""MicroK8s の夜間自動再起動と、実験の各点 (慣らし・計測窓を含む) の時間帯の重なりを洗い出す。

何を再計算するか
  2026-09-16 以降に走った実験すべてについて、各点の時間帯 [開始, 終わり] を実験ログ (*.log) の
  開始時刻行から復元し、k8s-restarts-20260916.txt の再起動時刻 (journalctl の apiserver-kicker
  "cert change detected" の時刻、61 行) とどう重なるかを分類する。結果は restart-audit.md に書く。

入力 (どれも読み取り専用。このスクリプトは何も書き換えない。出力の md だけ新規に作る)
  km2/experiments/k8s-restarts-20260916.txt         再起動時刻 (ISO 8601, +09:00)
  km2/experiments/**/*.log, sockshop/experiments/*.log  各実験のログ (点ごとの開始時刻行)
  上と同じ場所の results-*.csv                        各点の結果 (ログに対応する CSV)

点の時間帯の復元 (ドライバ .sh を読んで決めた規則。ログの時刻行は「点の開始直前」に出る)
  measure-mix-cpu.sh (OB: rightsizing/、SS: sockshop/experiments/)
    行: "==== [cycN][×R台] 点 (...) 時刻 ===="。そのあと k6 を起動 (約 8 秒) → 慣らし WARM → 計測窓 MEAS
        → 窓の終わり +15 秒まで待って Prometheus を引く。点の後に REST_POINT 秒休む。
    ブロック = (cycle, 台数) ごとに全 Deployment を消して立て直す ("---- deploy" 行)。
        立て直し後に慣らし負荷 PREWARM 秒 (SS はここで利用者 200 人を登録)。点どうしの間では立て直さない。
  bundle-vs-loss2.sh (OB: summer2026/)
    行: "==== [cycN][アーム] 購入=.. 閲覧=.. [点=.. 開始n台] 時刻 ===="。k6 起動 (約 10 秒) → WARM → MEAS
        → 窓の終わり +25 秒まで待つ。RESET_EACH_POINT=1 のときは、点の前に "---- 点のリセット" 行
        (HPA 全削除 → 全 Deployment を開始台数に scale → 全台 Ready 待ち → 引き直し待ち)。
        Pod の作り直しはアーム×サイクルに 1 回 ("---- deploy" 行) で、リセットは scale だけ。
  どちらも「k6 起動までの秒数」は推定 (約 ±20 秒の誤差)。窓の境界の近くは断定しない。

再起動の効果の見積もり (実測値ではなく仮定。md にも書く)
  - Pod が戻るまで 150 秒 (依頼: 1〜2 分) を見る。点の開始が再起動の 150 秒以内なら「直後に開始」とする。
  - 再起動が点の [開始, 終わり] の中なら「当たった」。慣らし/計測窓/窓後 (回収中) に分ける。

分類
  (a)  欠けた       当たった点 (または直後に開始した点) で CSV に行が無い
  (b)  値が入った   同上で CSV に行がある → 同じ条件の他サイクルと比べる
  (b') 後続         点ごとに作り直さない実験 (mix 系・固定台数) で、再起動の後に同じブロックで続く点
  (b'弱) bundle-vs-loss2 の RESET_EACH_POINT: 再起動後の点はリセットで台数だけ戻す (Pod は作り直さない)
  (c)  休憩中       点と点の間 (休憩・冷却待ち・リセット・デプロイ/慣らし) で再起動、次の点の開始が 150 秒より後
  比較は「同じ条件 (mix: 点×台数 / bvl: アーム×点×開始台数) の他サイクル」のうち、
  上のどれにも当たっていない点だけを peers にする。peers の最小〜最大の外なら * を付ける。
  peers が n<3 のときは外れの判定をしない。

使い方: リポジトリ直下で
  python3 km2/experiments/restart-audit.py                       # 標準出力に md を出す
  python3 km2/experiments/restart-audit.py --md km2/experiments/restart-audit.md   # md を書く
標準ライブラリのみ。何度実行しても同じ結果 (乱数なし)。
"""
import argparse
import csv
import datetime as dt
import glob
import os
import re
import statistics
import sys
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))          # リポジトリ直下
RESTARTS_FILE = os.path.join(HERE, 'k8s-restarts-20260916.txt')
SINCE = dt.datetime.fromisoformat('2026-09-16T00:00:00+09:00')
RECOVER_S = 150          # Pod が戻るまで見る秒数
STAMP = r'(2026-\d\d-\d\dT\d\d:\d\d:\d\d\+09:00)'

# ドライバごとの「k6 起動までの秒数」と「窓の終わりの後に待つ秒数」 (ドライバ .sh から。上の docstring 参照)
LEAD = {'mix': 8, 'bvl': 10}
TAIL = {'mix': 15, 'bvl': 25}

# 論文・修論での位置づけ (出所: FOSE2026-TeX-UTF8/fose2026-data-provenance.md、km2/experiments/summer2026/EXPERIMENTS.md、
#   km2/approach/related_work.md §9)。FOSE2026 の本文・provenance にはこの期間 (9/16 以降) のデータは一つも入っていない。
ROLE = {
    'rightsizing/results-mix-cpu2': ('修論の主結果 (OB の ρ 本測定)', 'FOSE2026 には無し'),
    'rightsizing/results-mix-cpu': ('OB の ρ 初回測定 (mix-cpu2 の前段)', 'FOSE2026 には無し'),
    'rightsizing/smoke/smoke-mix': ('スモーク', ''),
    'rightsizing/results-limit-coarse': ('OB の限界の粗い測定 (補足)', 'FOSE2026 には無し'),
    'summer2026/fixed4-lb': ('4 台固定の振り分けあり再実行 (基本帯 150-300)', 'FOSE2026 には無し (FOSE の §3.1 は 9/9-10 の fixed4 = 振り分けなし)'),
    'summer2026/fixed4b-lb': ('4 台固定の振り分けあり再実行 (飽和帯 350-450)', 'FOSE2026 には無し'),
    'summer2026/pairval': ('同居ペアの台数予測の前向き検証 (pairval)', 'FOSE2026 には無し。修論候補'),
    'summer2026/pdist': ('P の近さと引きずり (pdist)', 'FOSE2026 には無し。修論候補'),
    'summer2026/pdistk3n': ('pdist-k3 の開始 3/4 台の試し (中断、本集計に使わない)', '使わない'),
    'summer2026/pdistk3sep': ('pdist-k3 分離 12 サイクル', 'FOSE2026 には無し。修論の主結果'),
    'summer2026/pdistk3pair': ('pdist-k3 同居ペア', 'FOSE2026 には無し。修論の主結果'),
    'sockshop/results-mix-cpu': ('SS の ρ 初回測定 (B′ 前、4 サイクル)', '置き換え済み (mix-cpu2b が正)'),
    'sockshop/results-mix-cpu2b': ('修論の主結果 (SS の ρ 本測定)', 'FOSE2026 には無し'),
    'sockshop/results-stress': ('SS の耐久試験 (補足)', 'FOSE2026 には無し'),
    'sockshop/probe-cpu': ('SS のプローブ試験 (補足)', ''),
    'sockshop/probe10': ('SS のプローブ試験 (readiness 10 s、補足)', ''),
    'sockshop/probe10b': ('SS のプローブ試験 (readiness 10 s、補足)', ''),
}

# 当たった実験への手書きの注 (ログ・CSV を読んで確かめた事実だけ。推測は「推測:」と書く)
NOTES = {
    'km2/experiments/summer2026/fixed4b-lb.log': (
        '所見 (事実): 欠けた 2 点 (front3@350 の cyc3、mega@400 の cyc3) は、`summer2026/EXPERIMENTS.md` が「k6 summary 回収失敗で '
        'front3@350 と mega@400 が1点ずつ欠け」と書いている 2 点と同じ点で、時刻が 2 回の再起動と合う (cyc3 のみ、他サイクルは欠けなし)。'
        '(b\') の 3 点は飽和帯 (400/450 周/s) で、peers 自体のばらつきが大きく (例: front3@450 の取りこぼし peers sd 350)、'
        '再起動の影響と分けられない。FOSE2026 の §3.1 は 9/9-10 の振り分けなし fixed4/fixed4b を使っており、この -lb の再実行は載っていない。'),
    'km2/experiments/rightsizing/results-mix-cpu2.log': (
        '所見 (事実): (1) 欠けたのは cyc2 ×1台 b100v75 の 1 点 (203/204 点の欠けの原因、`EXPERIMENTS.md` は「summary 回収失敗」とだけ書いている)。'
        '(2) 22:57:41 の再起動は cyc2 ×2台 b50v300 の開始の 22 秒前 (点の間の休憩中)。この点の値は peers の範囲に収まる指標がほとんどで、'
        '外れは購入 p99 504 ms (peers 516〜707) と CPU 合計 4127 m (peers 4066〜4124、差は peers 平均比 +0.5%) だけ。'
        '推測: この時刻の再起動でこの点の Pod が実際に落ちたかは OB ログから分からない (再起動回数を記録していない)。値には影響が見えない。'
        '(3) 23:17:39 以降の cyc2 ×1台の 15 点 (b\') は CPU 合計が peers 平均比 -2.1%〜+1.7% の範囲 (最大 |z|=2.9, n=5)。'
        '取りこぼし・失敗率に異常なし。ρ への影響の目安: cyc2 ×1台の全点と cyc2 ×2台 b50v300 を除いた CSV で既存の analyze_rho2.py を回すと、'
        'front/catalog/reco の ρ は 1台 0.35/0.34/0.36、2台 0.34/0.34/0.34 のまま (小数第2位まで同じ)。ad の ρ だけ 1台 1.19→1.17。'
        '再現: `python3 km2/experiments/restart-audit.py --write-excl-csv <出力CSV>` で除外版を作り、'
        '`cd km2/experiments/rightsizing && python3 analyze_rho2.py <出力CSV> results-mix-cpu.csv` を、元の CSV の出力と比べる。'),
    'km2/experiments/summer2026/pdistk3sep.log': (
        '所見 (事実): 欠けたのは cyc12 の b50v300 の 1 点 (12 サイクル × 4 点 = 48 回のうち 47 行)。'
        '22:17:53 の 2 回目の再起動は DONE 行 (22:17:28) の 25 秒後で、点には当たっていない。'
        '(b\'弱) の cyc12 b100v200 は終了時の台数が recommendationservice:4 (他 11 サイクルは 5) で、'
        '確保コア 8.67 は peers 8.81〜9.14 の外 (z=-3.3、n=11)。この台数差が再起動の後遺症か偶然かは未確認 (推測: HPA の境目の揺らぎもありうる)。'
        '最頻値 (reco:5) は cyc12 を除いても変わらない。'),
    'sockshop/experiments/results-mix-cpu2b.log': (
        '所見 (事実): cyc2 の 2 台ブロック (15 点) のうち、再起動 (21:08:04) の前に終わった 6 点は失敗率 0。'
        '当たった 2 点と後続 7 点の計 9 点のうち、購入を含む 7 点 (b16v160, b48v240, b16v240, b48v160, b32v160, b32, b32v240) は buy_failed_rate=0.5 '
        '(CPU 合計が peers 平均比 -16%〜-43%)、閲覧のみの 2 点 (v80, v160) は失敗率 0 で CPU 合計も peers 比 -1.7% / +0.9% (ただし peers の sd が小さく z=-2.7 / +2.9)。'
        '`sockshop/experiments/analyze_rho_ss.py` は既にこのブロック (cyc2 ×2台) を丸ごと除く設計 (INCIDENT)。'
        '1台ブロックと他サイクルの 2台ブロックは、失敗率>0 の点が 0 点 (本表の「対照」節)。'),
}


def pstamp(s):
    return dt.datetime.fromisoformat(s)


def fmt(t):
    return t.strftime('%m-%d %H:%M:%S')


def short_dur(sec):
    sec = int(round(sec))
    return '%d分%02d秒' % (sec // 60, sec % 60) if abs(sec) >= 60 else '%d秒' % sec


class Point:
    def __init__(self):
        self.cyc = None
        self.arm = ''
        self.pt = ''
        self.reps = None       # mix: 台数 / bvl: 開始台数
        self.rate = None       # bvl 非リセット: 購入レート
        self.brw = None
        self.t_h = None        # ヘッダ時刻 (点の開始直前)
        self.reset_t = None    # bvl リセット行の時刻
        self.block = None
        self.first_in_block = False
        self.flags = []        # ログ中の "!!" 行
        self.restart_pods = 0  # SS: "!! 再起動:" 行の数 (Pod 数)
        self.warm = self.meas = 0
        self.family = ''

    @property
    def warm_end(self):
        return self.t_h + dt.timedelta(seconds=LEAD[self.family] + self.warm)

    @property
    def meas_end(self):
        return self.warm_end + dt.timedelta(seconds=self.meas)

    @property
    def end(self):
        return self.meas_end + dt.timedelta(seconds=TAIL[self.family])

    def label(self):
        if self.family == 'mix':
            return 'cyc%s ×%s台 %s' % (self.cyc, self.reps, self.pt)
        if self.pt:
            return 'cyc%s %s %s 開始%s台' % (self.cyc, self.arm, self.pt, self.reps)
        return 'cyc%s %s 購入%s 閲覧%s' % (self.cyc, self.arm, self.rate, self.brw)

    def key(self):
        return (self.cyc, self.arm, self.pt, self.reps, self.rate, self.brw)


class Run:
    def __init__(self, path):
        self.path = path
        self.rel = os.path.relpath(path, ROOT)
        self.family = None     # 'mix' / 'bvl' / 'probe'
        self.reset_each = False
        self.warm = self.meas = 0
        self.t_start = self.t_end = None
        self.interrupted = False
        self.points = []
        self.csv = None
        self.rows = {}
        self.smoke = False
        self.blocks = {}       # block id -> [Point]
        self.setup_start = {}  # block id -> 推定のブロック開始時刻
        self.n_headers = 0
        self.first_ts = self.last_ts = None


def parse_log(path):
    run = Run(path)
    base = os.path.basename(path)[:-4]
    run.smoke = ('/smoke/' in path) or base.startswith('smoke')
    text = open(path, errors='replace').read().splitlines()
    cur = None
    block = 0
    last_event_end = None
    cyc_stamp = None
    pending_reset = {}
    stamps_all = []
    for ln in text:
        m_all = re.findall(STAMP, ln)
        for s in m_all:
            stamps_all.append(pstamp(s))
        m = re.search(r'(BUNDLE-VS-LOSS2|MEASURE-MIX-CPU|SOCKSHOP MIX-CPU) START ' + STAMP, ln)
        if m:
            run.family = 'bvl' if m.group(1) == 'BUNDLE-VS-LOSS2' else 'mix'
            ts = pstamp(m.group(2))
            if run.t_start is None:
                run.t_start = ts
            mw = re.search(r'warm=(\d+)s meas=(\d+)s', ln)
            if mw:
                run.warm, run.meas = int(mw.group(1)), int(mw.group(2))
            continue
        if run.family is None and re.search(r'START ' + STAMP, ln):
            m2 = re.search(r'START ' + STAMP, ln)
            run.family = 'probe'
            run.t_start = pstamp(m2.group(1))
        if '点ごとリセット:' in ln:
            run.reset_each = True
        m = re.search(r'CYCLE \d+ / \d+ ' + STAMP, ln)
        if m:
            cyc_stamp = pstamp(m.group(1))
            continue
        if ln.startswith('---- deploy'):
            block += 1
            if cur is not None:
                last_event_end = cur.end
            run.setup_start[block] = max([t for t in (last_event_end, cyc_stamp) if t is not None] or [run.t_start])
            cur = None
            continue
        m = re.match(r'---- 点のリセット \[(\S+)\]\[(\S+)\] 開始(\d+)台 ' + STAMP, ln)
        if m:
            pending_reset[(m.group(1), m.group(2), int(m.group(3)))] = pstamp(m.group(4))
            continue
        p = None
        m = re.match(r'==== \[cyc(\d+)\]\[×(\d+)台\] (\S+) \(.*?\) ' + STAMP + r' ====', ln)
        if m:
            p = Point()
            p.family = 'mix'
            p.cyc, p.reps, p.pt, p.t_h = int(m.group(1)), int(m.group(2)), m.group(3), pstamp(m.group(4))
        else:
            m = re.match(r'==== \[cyc(\d+)\]\[(\S+)\] 購入=(\S+)周/秒 閲覧=(\S+)周/秒(?: 点=(\S+) 開始(\d+)台)? ' + STAMP + r' ====', ln)
            if m:
                p = Point()
                p.family = 'bvl'
                p.cyc, p.arm = int(m.group(1)), m.group(2)
                p.rate, p.brw = float(m.group(3)), float(m.group(4))
                p.pt = m.group(5) or ''
                p.reps = int(m.group(6)) if m.group(6) else None
                p.t_h = pstamp(m.group(7))
                p.reset_t = pending_reset.pop((p.arm, p.pt, p.reps), None) if p.pt else None
        if p is not None:
            p.warm, p.meas = run.warm, run.meas
            p.block = block
            if cur is not None and cur.block == block:
                last_event_end = cur.end
            p.first_in_block = not any(q.block == block for q in run.points)
            run.points.append(p)
            run.blocks.setdefault(block, []).append(p)
            cur = p
            continue
        if cur is not None:
            if '!!' in ln:
                if '再起動:' in ln:
                    cur.restart_pods += 1
                else:
                    cur.flags.append(ln.strip())
            if ln.startswith('  (この点は記録なし'):
                cur.flags.append(ln.strip())
        m = re.search(r'(DONE|BUNDLE-VS-LOSS2 DONE|MIX-CPU DONE) ' + STAMP, ln)
        if m:
            run.t_end = pstamp(m.group(2))
    if run.family is None:
        run.family = 'probe'
    if stamps_all:
        run.first_ts, run.last_ts = min(stamps_all), max(stamps_all)
        if run.t_start is None:
            run.t_start = run.first_ts
    if run.t_end is None:
        run.interrupted = True
        run.t_end = run.last_ts
    if run.points:
        run.t_end = max(run.t_end, run.points[-1].end) if run.interrupted else run.t_end
    # CSV
    d = os.path.dirname(path)
    stem = base[len('results-'):] if base.startswith('results-') else base
    for cand in ('results-%s.csv' % stem, '%s.csv' % base, 'results-%s.csv' % base):
        if os.path.exists(os.path.join(d, cand)):
            run.csv = os.path.join(d, cand)
            break
    return run


# ---------------------------------------------------------------- CSV
def num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


MIX_METRICS = [('buy_dropped_win', '購入 取りこぼし(窓)'), ('view_dropped_win', '閲覧 取りこぼし(窓)'),
               ('buy_failed_rate', '購入 失敗率'), ('view_failed_rate', '閲覧 失敗率'),
               ('buy_p99', '購入 p99[ms]'), ('view_p99', '閲覧 p99[ms]'), ('total_usage_mc', 'CPU 合計[m]')]
BVL_METRICS = [('dropped_win', '取りこぼし(窓)'), ('failed_rate', '失敗率'), ('p50', 'p50[ms]'), ('p99', 'p99[ms]'),
               ('iter_rate', '捌けた周/s'), ('reserved_avg_cores', '確保コア(窓平均)'), ('softirq_cpu_sec', 'softirq[コア秒]')]


def load_rows(run):
    """CSV を (点のキー) -> 指標 dict にする。キーは Point.key() と同じ並びで作る。"""
    out = {}
    if not run.csv:
        return out
    rows = list(csv.DictReader(open(run.csv, newline='')))
    if run.family == 'mix':
        grp = defaultdict(list)
        for r in rows:
            grp[(int(r['cycle']), r['point'], int(r['replicas']))].append(r)
        for (c, pt, n), rs in grp.items():
            r0 = rs[0]
            d = {k: num(r0.get(k)) for k, _ in MIX_METRICS if k != 'total_usage_mc'}
            d['total_usage_mc'] = sum(num(r['usage_mc']) or 0 for r in rs if r['deploy'] != 'k6load')
            d['_ok'] = r0.get('buy_achieved', '') != '' or r0.get('view_achieved', '') != ''
            d['_failed_any'] = (num(r0.get('buy_failed_rate')) or 0) > 0 or (num(r0.get('view_failed_rate')) or 0) > 0
            out[(c, '', pt, n, None, None)] = d
    elif run.family == 'bvl':
        for r in rows:
            d = {k: num(r.get(k)) for k, _ in BVL_METRICS}
            d['_ok'] = True
            d['_rep'] = r.get('replicas', '')                 # 窓の終わりの台数 (文字列)
            d['_failed_any'] = (num(r.get('failed_rate')) or 0) > 0
            if r.get('point'):
                key = (int(r['cycle']), r['arm'], r['point'], int(r['start_replicas']), None, None)
            else:
                key = (int(r['cycle']), r['arm'], '', None, float(r['target_rate']), float(r['browse_rate_target'] or 0))
            out[key] = d
    return out


def csv_key(p):
    if p.family == 'mix':
        return (p.cyc, '', p.pt, p.reps, None, None)
    if p.pt:
        return (p.cyc, p.arm, p.pt, p.reps, None, None)
    return (p.cyc, p.arm, '', None, p.rate, p.brw)


def cond_key(p):
    """同じ条件 (サイクルだけ違う) を表すキー。"""
    k = csv_key(p)
    return k[1:]


# ---------------------------------------------------------------- 割り当て
def locate(run, T):
    """再起動 T が run のどこに当たるか。(zone, 点, 次の点, 秒) を返す。"""
    pts = run.points
    for i, p in enumerate(pts):
        if p.t_h <= T < p.end:
            if T < p.warm_end:
                z = '慣らし中'
            elif T < p.meas_end:
                z = '計測窓の中'
            else:
                z = '窓の後 (回収中)'
            return z, p, None, (T - p.t_h).total_seconds()
        nxt = pts[i + 1] if i + 1 < len(pts) else None
        if nxt is not None and p.end <= T < nxt.t_h:
            if nxt.first_in_block and nxt.block != p.block:
                zone = 'デプロイ/慣らし中 (ブロック先頭の前)'
            elif nxt.reset_t is not None and T >= nxt.reset_t:
                zone = '点のリセット中'
            else:
                zone = '点の間 (休憩・冷却待ち)'
            return zone, None, nxt, (nxt.t_h - T).total_seconds()
    if pts and run.t_start <= T < pts[0].t_h:
        return 'デプロイ/慣らし中 (ブロック先頭の前)', None, pts[0], (pts[0].t_h - T).total_seconds()
    if pts and T >= pts[-1].end:
        return '最終点の後', None, None, (T - pts[-1].end).total_seconds()
    return '点なし(span内)', None, None, 0


def stats(vals):
    n = len(vals)
    if n == 0:
        return None
    m = statistics.mean(vals)
    sd = statistics.stdev(vals) if n > 1 else 0.0
    return n, m, sd, min(vals), max(vals)


def g(x, nd=1):
    if x is None:
        return '-'
    if abs(x) >= 100:
        return '%.0f' % x
    return ('%.' + str(nd) + 'f') % x


def compare(run, rows, p, peers_pts, metrics):
    """点 p の指標を、peers_pts (同条件の清浄な点) と比べる。(行のリスト, 外れた指標名のリスト)。"""
    me = rows.get(csv_key(p))
    lines, outs = [], []
    if me is None:
        return lines, outs
    for k, name in metrics:
        x = me.get(k)
        vs = [rows[csv_key(q)][k] for q in peers_pts if csv_key(q) in rows and rows[csv_key(q)].get(k) is not None]
        st = stats(vs)
        if x is None:
            lines.append((name, '(空)', '', '', ''))
            continue
        if st is None or st[0] < 3:
            lines.append((name, g(x, 2), 'peers n=%d' % (st[0] if st else 0), '', ''))
            continue
        n, m, sd, lo, hi = st
        out = x < lo or x > hi
        z = ('%.1f' % ((x - m) / sd)) if sd > 0 else '-'
        lines.append((name, g(x, 2) + (' *' if out else ''), '%s ± %s (n=%d)' % (g(m, 2), g(sd, 2), n),
                      '%s 〜 %s' % (g(lo, 2), g(hi, 2)), z))
        if out:
            outs.append(name)
    if run.family == 'bvl' and me.get('_rep'):
        reps = [rows[csv_key(q)].get('_rep') for q in peers_pts if csv_key(q) in rows]
        if len(reps) >= 3:
            cnt = defaultdict(int)
            for x in reps:
                cnt[x] += 1
            mode, mc = max(cnt.items(), key=lambda kv: kv[1])
            same = (me['_rep'] == mode)
            if not same:
                diff = []
                dm = dict(t.split(':') for t in mode.split())
                dx = dict(t.split(':') for t in me['_rep'].split())
                for a in dm:
                    if a in dx and dm[a] != dx[a]:
                        diff.append('%s 最頻 %s → この点 %s' % (a, dm[a], dx[a]))
                lines.append(('台数(窓の終わり)', '最頻値と不一致 *', 'peers の最頻値は %d/%d 点' % (mc, len(reps)), '; '.join(diff), ''))
                if mc / float(len(reps)) >= 0.7:
                    outs.append('台数')
            else:
                lines.append(('台数(窓の終わり)', '最頻値と一致', 'peers の最頻値は %d/%d 点' % (mc, len(reps)), '', ''))
    return lines, outs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--md', help='md の書き出し先 (省略時は標準出力)')
    ap.add_argument('--write-excl-csv', help='OB の results-mix-cpu2.csv から、再起動が当たったブロック (cyc2 ×1台 全点) と直後に始まった点 (cyc2 ×2台 b50v300) を除いた CSV を書く (ρ への影響の目安用)')
    args = ap.parse_args()

    restarts = [pstamp(l.strip()) for l in open(RESTARTS_FILE) if l.strip()]
    logs = sorted(set(glob.glob(os.path.join(ROOT, 'km2/experiments/**/*.log'), recursive=True)
                      + glob.glob(os.path.join(ROOT, 'sockshop/experiments/*.log'))))
    runs = []
    for p in logs:
        if os.path.basename(p) in ('texput.log',) or 'FOSE2026' in p:
            continue
        r = parse_log(p)
        if r.first_ts is None or r.first_ts < SINCE:
            continue
        r.rows = load_rows(r)
        runs.append(r)
    runs.sort(key=lambda r: r.t_start)

    if args.write_excl_csv:
        r2 = [r for r in runs if r.rel.endswith('rightsizing/results-mix-cpu2.log')][0]
        drop = set()
        for T in restarts:
            if not (r2.t_start <= T <= r2.t_end):
                continue
            zone, p, nxt, sec = locate(r2, T)
            if p is not None:
                drop.update((q.cyc, q.reps) for q in r2.blocks[p.block])          # 当たった点のブロックを丸ごと
            elif nxt is not None and sec < RECOVER_S:
                drop.add((nxt.cyc, nxt.reps, nxt.pt))                              # 直後に始まった点だけ
        rows_in = list(csv.reader(open(r2.csv, newline='')))
        h = rows_in[0]
        ic, ir, ip = h.index('cycle'), h.index('replicas'), h.index('point')
        n_drop = 0
        with open(args.write_excl_csv, 'w', newline='') as f:
            w = csv.writer(f)
            w.writerow(h)
            for r in rows_in[1:]:
                k2, k3 = (int(r[ic]), int(r[ir])), (int(r[ic]), int(r[ir]), r[ip])
                if k2 in drop or k3 in drop:
                    n_drop += 1
                    continue
                w.writerow(r)
        print('除外ブロック/点: %s、除いた CSV 行 %d (1 点 = 12 行) → %s' % (sorted(drop, key=str), n_drop, args.write_excl_csv))
        return

    out = []
    W = out.append
    W('# MicroK8s 夜間自動再起動 と 実験の重なり (2026-09-16 以降)')
    W('')
    W('生成: `python3 km2/experiments/restart-audit.py --md km2/experiments/restart-audit.md` (標準ライブラリのみ、毎回同じ結果)。')
    W('再起動時刻: `km2/experiments/k8s-restarts-20260916.txt` (%d 行、%s 〜 %s)。' % (len(restarts), fmt(restarts[0]), fmt(restarts[-1])))
    W('')
    W('## 0. 読み方と前提')
    W('')
    W('- 点の時間帯は、ログの開始時刻行 + ドライバ .sh の待ち秒数から復元した **推定** (k6 起動までの秒数は mix 系 8 秒・bundle-vs-loss2 10 秒と仮定、±20 秒の誤差)。')
    W('  慣らし = k6 起動〜WARM、計測窓 = WARM〜WARM+MEAS、窓の後 = 回収待ち (mix 15 秒 / bvl 25 秒)。')
    W('- 再起動の効果は「Pod が戻るまで %d 秒」と仮定。**OB のログには Pod の再起動回数が残っていない** (SS のログだけ `!! 再起動:` 行がある) ので、'
      'OB で実際に Pod が再起動したかは未確認。journalctl の時刻と、点の値が崩れているかどうかだけが根拠。' % RECOVER_S)
    W('- 「peers」= 同じ条件の他サイクルで、再起動の影響を受けていない点。最小〜最大の外を `*`。n<3 は判定しない。標準偏差は n-1 で割る。')
    W('- FOSE2026 の本文 (`fose2026.tex`) と `fose2026-data-provenance.md` には、9/16 以降のデータは出てこない (grep で確認: pdist / mix-cpu / pairval / -lb / limit / stress / k3 いずれもヒット 0)。'
      'よって FOSE2026 の数値は影響を受けない。影響は修論用の主結果にだけ及ぶ。')
    W('- 再起動一覧は 9/30 → 10/05 の間が空いている (10/01〜10/04 の再起動行が無い)。journal の欠けか再起動が無かったのかは **未確認**。'
      'この間に走った実験はログから見つからなかった (後述の全実験一覧)。')
    W('')

    # ---- 再起動ごとの割り当て
    hits = []   # (restart, run, zone, p, nxt, sec)
    W('## 1. 再起動ごとの割り当て (全 %d 回)' % len(restarts))
    W('')
    W('| 再起動 | 実験 (ログ) | 位置 | 点 | 備考 |')
    W('|---|---|---|---|---|')
    per_restart = {}
    for T in restarts:
        cands = [r for r in runs if r.t_start <= T <= r.t_end]
        if not cands:
            # 近い実験
            near = [r for r in runs if abs((r.t_start - T).total_seconds()) < 3600 or abs((r.t_end - T).total_seconds()) < 3600]
            nb = ''
            if near:
                rr = min(near, key=lambda r: min(abs((r.t_start - T).total_seconds()), abs((r.t_end - T).total_seconds())))
                gap = min(abs((rr.t_start - T).total_seconds()), abs((rr.t_end - T).total_seconds()))
                nb = '最寄り: %s まで %s' % (rr.rel, short_dur(gap))
            W('| %s | (どの実験も走っていなかった) | | | %s |' % (fmt(T), nb))
            continue
        for r in cands:
            zone, p, nxt, sec = locate(r, T)
            hits.append((T, r, zone, p, nxt, sec))
            per_restart[T] = hits[-1]
            tgt = p or nxt
            lab = tgt.label() if tgt else ''
            if p:
                note = '点の開始から %s' % short_dur(sec)
            elif nxt:
                note = '次の点の開始の %s 前' % short_dur(sec)
            else:
                note = ''
            W('| %s | `%s` | %s | %s | %s |' % (fmt(T), r.rel, zone, lab, note))
    W('')

    # ---- 全実験一覧
    W('## 2. 9/16 以降に走った全実験 (ログの時刻から。smoke は区別)')
    W('')
    W('| 実験ログ | 種別 | 走った区間 | 点数(ヘッダ) | CSV 行のある点 | 再起動が重なった回数 | 論文・修論での位置づけ | 備考 |')
    W('|---|---|---|---|---|---|---|---|')
    for r in runs:
        nh = sum(1 for h in hits if h[1] is r)
        key = os.path.relpath(r.path[:-4], os.path.join(ROOT, 'km2/experiments'))
        if key.startswith('..'):
            key = os.path.relpath(r.path[:-4], os.path.join(ROOT, 'sockshop/experiments'))
            key = 'sockshop/' + key
        role = ROLE.get(key, (('スモーク/予備' if r.smoke else '(未分類)'), ''))
        nrows = sum(1 for p in r.points if csv_key(p) in r.rows)
        kind = {'mix': 'mix-cpu 系', 'bvl': 'bundle-vs-loss2' + (' (点ごとリセット)' if r.reset_each else ' (リセットなし)'),
                'probe': 'プローブ系'}[r.family]
        note = '中断 (DONE 行なし)' if r.interrupted else ''
        W('| `%s`%s | %s | %s 〜 %s | %d | %s | %d | %s / %s | %s |' % (
            r.rel, ' (smoke)' if r.smoke else '', kind, fmt(r.t_start), fmt(r.t_end), len(r.points),
            ('%d' % nrows) if r.family != 'probe' else '-', nh, role[0], role[1], note))
    W('')

    # ---- 当たった実験の詳細
    W('## 3. 再起動が重なった実験の詳細')
    W('')
    done_runs = []
    affected_all = {}
    for r in runs:
        rh = [h for h in hits if h[1] is r]
        if not rh:
            continue
        done_runs.append(r)
        metrics = MIX_METRICS if r.family == 'mix' else BVL_METRICS
        W('### 3.%d `%s`' % (len(done_runs), r.rel))
        W('')
        W('- 種別: %s、WARM=%ds MEAS=%ds、区間 %s 〜 %s、CSV: `%s` (点の行 %d)' % (
            {'mix': 'mix-cpu 系 (ブロックごとに立て直し、点の間は立て直さない)',
             'bvl': 'bundle-vs-loss2' + (' RESET_EACH_POINT=1 (アーム×サイクルで 1 回デプロイ、点ごとは scale によるリセットのみ)' if r.reset_each else '、リセットなし')}[r.family],
            r.warm, r.meas, fmt(r.t_start), fmt(r.t_end), os.path.relpath(r.csv, ROOT) if r.csv else 'なし',
            len(r.rows)))
        # 影響を受けた点の集合 (peers から除く)
        affected = {}   # id(point) -> (class, 再起動, 説明)
        for T, _, zone, p, nxt, sec in rh:
            if p is not None:
                has = csv_key(p) in r.rows
                affected[id(p)] = ('(a) 欠けた' if not has else '(b) 値が入った', T, zone)
            elif nxt is not None and sec < RECOVER_S:
                has = csv_key(nxt) in r.rows
                affected[id(nxt)] = ('(a) 欠けた(直後に開始)' if not has else '(b) 値が入った(直後に開始)', T, '再起動の %s 後に開始' % short_dur(sec))
            nb = nxt if p is None else p
            if nb is not None:
                for q in r.blocks.get(nb.block, []):
                    if q.t_h > T and id(q) not in affected:
                        cls = "(b'弱) 後続" if (r.family == 'bvl' and r.reset_each) else "(b') 後続"
                        affected[id(q)] = (cls, T, 'ブロック内で再起動の後')
            elif zone.startswith('デプロイ') and nxt is not None:
                pass
        affected_all.update({k: v[0] for k, v in affected.items()})
        # (c) 休憩中だけで影響のない点は別に記録
        peers_by_cond = defaultdict(list)
        for p in r.points:
            if id(p) not in affected:
                peers_by_cond[cond_key(p)].append(p)
        W('')
        W('| 再起動 | 位置 | 当たった点 | 分類 | CSV の行 | 値の外れ (peers の範囲外) |')
        W('|---|---|---|---|---|---|')
        detail = []
        for T, _, zone, p, nxt, sec in rh:
            tgt = p if p is not None else nxt
            if tgt is None:
                W('| %s | %s | - | (c) 点なし | - | - |' % (fmt(T), zone))
                continue
            if p is None and sec >= RECOVER_S:
                cls = '(c) 休憩中 (次の点まで %s)' % short_dur(sec)
                nxt_has = csv_key(nxt) in r.rows
                W('| %s | %s | 次: %s | %s | %s | (次の点は再起動後 %s 以上経過; 値は peers と別途比較 → 下の後続表) |' % (
                    fmt(T), zone, nxt.label(), cls, '有' if nxt_has else '無', short_dur(sec)))
                continue
            cls = affected[id(tgt)][0]
            has = csv_key(tgt) in r.rows
            peers = [q for q in peers_by_cond[cond_key(tgt)] if q is not tgt]
            lines, outs = compare(r, r.rows, tgt, peers, metrics)
            W('| %s | %s (%s) | %s | %s | %s | %s |' % (
                fmt(T), zone, ('開始から %s' % short_dur(sec)) if p else ('再起動の %s 後に開始' % short_dur(sec)),
                tgt.label(), cls, '有' if has else '無 ' + ('; '.join(tgt.flags) if tgt.flags else '(ログに理由行なし)'),
                ', '.join(outs) if outs else ('範囲内' if has else '-')))
            if has:
                detail.append((T, tgt, lines, len(peers)))
        W('')
        for T, tgt, lines, npeers in detail:
            W('**値の比較: %s (再起動 %s)** — peers = 同条件の清浄な他サイクル %d 点' % (tgt.label(), fmt(T), npeers))
            W('')
            W('| 指標 | この点 | peers 平均 ± 標準偏差 | peers 最小〜最大 | z |')
            W('|---|---|---|---|---|')
            for ln in lines:
                W('| %s | %s | %s | %s | %s |' % ln)
            W('')
        # 後続 (b')
        bp = [(q, v) for q in r.points for v in [affected.get(id(q))] if v and v[0].startswith("(b'")]
        if bp:
            W("**(b') 後続の点 (再起動の後、同じブロックで続く点)** — 件数 %d。CSV の値を peers と比べた結果" % len(bp))
            W('')
            W('| 再起動 | 点 | 開始(再起動から) | CSV | 範囲外の指標 | 主な値 | ' + ('CPU 合計の peers 比' if r.family == 'mix' else 'peers 数') + ' |')
            W('|---|---|---|---|---|---|---|')
            n_out = 0
            bdetail = []
            for q, v in bp:
                peers = [x for x in peers_by_cond[cond_key(q)] if x is not q]
                lines, outs = compare(r, r.rows, q, peers, metrics)
                has = csv_key(q) in r.rows
                if outs:
                    n_out += 1
                me = r.rows.get(csv_key(q), {})
                if r.family == 'mix':
                    mv = '購入失敗 %s / 閲覧失敗 %s / 取りこぼし(窓) 購入 %s 閲覧 %s / CPU合計 %s m' % (
                        g(me.get('buy_failed_rate'), 3), g(me.get('view_failed_rate'), 3), g(me.get('buy_dropped_win')),
                        g(me.get('view_dropped_win')), g(me.get('total_usage_mc'))) if has else '-'
                else:
                    mv = '取りこぼし(窓) %s / 失敗率 %s / p50 %s ms / 確保 %s コア' % (
                        g(me.get('dropped_win')), g(me.get('failed_rate'), 3), g(me.get('p50')), g(me.get('reserved_avg_cores'), 2)) if has else '-'
                extra = ''
                if q.restart_pods:
                    extra = ' [ログ: 再起動回数>0 の Pod %d 個]' % q.restart_pods
                cmp_txt = '%d' % len(peers)
                if r.family == 'mix' and has:
                    vs = [r.rows[csv_key(x)]['total_usage_mc'] for x in peers if csv_key(x) in r.rows]
                    if len(vs) >= 3:
                        mm, sd = statistics.mean(vs), statistics.stdev(vs)
                        cmp_txt = '%+.0f m (%+.1f%%, %s sd, n=%d)' % (me['total_usage_mc'] - mm, 100 * (me['total_usage_mc'] - mm) / mm,
                                                                  ('%+.1f' % ((me['total_usage_mc'] - mm) / sd)) if sd > 0 else '-', len(vs))
                    else:
                        cmp_txt = 'peers n=%d' % len(vs)
                W('| %s | %s | %s 後 | %s | %s | %s%s | %s |' % (fmt(v[1]), q.label(), short_dur((q.t_h - v[1]).total_seconds()),
                                                          '有' if has else '無', ', '.join(outs) if outs else ('なし' if has else '-'), mv, extra, cmp_txt))
                if r.family == 'bvl' and has:
                    bdetail.append((q, lines, len(peers)))
            W('')
            W("(b') %d 点中、peers の範囲外の指標が 1 つ以上ある点: %d 点 (peers が n<3 の点は判定不能で「なし」扱い)" % (len(bp), n_out))
            W('')
            for q, lines, npe in bdetail:
                W('**値の比較 (b\'): %s** — peers %d 点' % (q.label(), npe))
                W('')
                W('| 指標 | この点 | peers 平均 ± 標準偏差 | peers 最小〜最大 | z |')
                W('|---|---|---|---|---|')
                for ln in lines:
                    W('| %s | %s | %s | %s | %s |' % ln)
                W('')
        if r.family == 'mix' and any(q.restart_pods for q in r.points):
            W('SS のログの `!! 再起動:` 行 (点の後の `kubectl get pods` で RESTARTS>0 の Pod 数): ' +
              ', '.join('%s=%d' % (q.label(), q.restart_pods) for q in r.points if q.restart_pods))
            W('')
        if r.rel in NOTES:
            W(NOTES[r.rel])
            W('')

    # ---- 対照: 再起動と無関係な欠け・失敗
    W('## 4. 対照: 再起動に当たっていないのに CSV に行が無い点 / 失敗率が正の点')
    W('')
    W('再起動以外の原因で欠けた点や失敗した点がどれだけあるかの目安。各点に最も近い再起動までの時間も付ける。')
    W('')
    W('| 実験 | 点 | 状況 | 最寄りの再起動との差 | 再起動に当たったか |')
    W('|---|---|---|---|---|')
    hit_ids = set()
    for T, rr, zone, p, nxt, sec in hits:
        if p is not None:
            hit_ids.add(id(p))
        elif nxt is not None and sec < RECOVER_S:
            hit_ids.add(id(nxt))
    n_other = 0
    for r in runs:
        if r.family == 'probe':
            continue
        nfail = 0
        for p in r.points:
            has = csv_key(p) in r.rows
            fa = has and r.rows[csv_key(p)].get('_failed_any')
            if has and not fa:
                continue
            near = min(restarts, key=lambda T: abs((T - p.t_h).total_seconds()))
            dsec = (p.t_h - near).total_seconds()
            if r.family == 'bvl' and has and fa:
                nfail += 1
                continue    # bvl の失敗率>0 は件数だけ (飽和帯で普通に出る)
            n_other += 1 if (id(p) not in hit_ids and id(p) not in affected_all) else 0
            W('| `%s` | %s | %s | %s (%s) | %s |' % (
                r.rel, p.label(), ('CSV 行なし: ' + ('; '.join(p.flags) if p.flags else ('ログが途中で終わっている (中断)' if r.interrupted and p is r.points[-1] else 'ログに理由行なし'))) if not has else '失敗率>0',
                fmt(near), ('点の開始が再起動の %s %s' % (short_dur(abs(dsec)), '後' if dsec >= 0 else '前')),
                '当たった' if id(p) in hit_ids else (("後続 " + affected_all[id(p)].split(' ')[0]) if id(p) in affected_all else 'いいえ')))
        if nfail:
            W('| `%s` | (bundle-vs-loss2 の失敗率>0 の点 %d/%d) | 件数のみ | - | - |' % (r.rel, nfail, len(r.points)))
    W('')
    W('再起動の直接の当たり・後続のどちらでもない欠け/失敗 (上の表で「いいえ」): %d 点。' % n_other)
    W('')

    W('## 5. 限界')
    W('')
    W('- 点の時間帯は推定 (±20 秒)。窓の境界のすぐ近くの再起動は、慣らし/窓の分類が入れ替わりうる。')
    W('- 「当たらなかった」ことは、再起動が実験に影響しなかったことの証明ではない (journalctl の cert change 行が再起動の全てとは限らない、'
      'また OB の 10/06 以前は journal の時刻一覧が 9/30 → 10/05 で途切れている)。')
    W('- peers との比較は、サイクル間ばらつき (n=3〜12) の範囲に収まるかを見ているだけで、有意性検定ではない。範囲内でも汚れていないとは言えない。')
    text = '\n'.join(out) + '\n'
    if args.md:
        open(args.md, 'w').write(text)
        print('wrote', args.md, '(%d 行)' % len(out))
    else:
        sys.stdout.write(text)


if __name__ == '__main__':
    main()
