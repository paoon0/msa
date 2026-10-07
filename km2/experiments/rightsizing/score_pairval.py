#!/usr/bin/env python3
"""同居ペアの台数・損の前向き検証 (pairval) の採点スクリプト。

何を再計算するか:
  事前登録 prereg-pairval.md の §4 (採点の規則) を、そのまま機械的に実装する。
  予測表 (predictions-pairval-K1.csv = 主評価 / -K2.csv = 副評価) と、本走の実測
  (results / timeline / events / log) を突き合わせ、
    * 台数の3つ組 (n_s, n_t, n_st) の完全一致率
    * 損の区分 (損あり / 損なし / 得) の一致率
    * 対照の単純な規則 R1, R2 の正解率
    * §4-7 の合格条件 (i) (ii) の判定
  を出す。結果を見てから規則を変えないために、本走の結果を開く前に書いて固定する。

入力 (既定は本走のファイル。テストでは偽データのパスを --results 等で渡す):
  --results   results-pairval.csv   (bundle-vs-loss2.sh, RESET_EACH_POINT=1 形式。1行 = 1アーム×1点×1開始台数×1サイクル)
  --timeline  timeline-pairval.csv  (sample_hpa.py の出力。15秒ごとに Deployment 単位 (コンテナ別 HPA ならコンテナ数ぶん) 1行)
  --events    events-pairval.csv    (collect_events.py。HPA の SuccessfulRescale イベント)
  --log       pairval.log           (冒頭の 'warm=180s meas=240s' を読む。--warm / --meas で直接指定も可)
  --pred      predictions-pairval-K1.csv (主評価)。副評価の K=2 は --pred2 (既定 -K2.csv)
  --out       セル単位の採点 CSV (既定 score-pairval-cells.csv)
使い方 (km2/experiments/rightsizing/ で実行。標準ライブラリのみ):
  python3 score_pairval.py
  python3 score_pairval.py --results R --timeline T --events E --log L --out O   # 偽データなど

規則の解釈 (規則の文言を優先し、曖昧なところだけここで固定した。報告にも同じことを書く):
  * 窓 = 時系列の t_rel >= WARM (t_rel は k6 の Pod が Running になってからの秒数。ドライバは WARM 秒待ってから
    MEAS 秒だけ採取を続けて止めるので、上限は付けない。--meas を渡したときだけ t_rel <= WARM+MEAS も課す)。
  * 実測の台数 = 窓内サンプル (t_rel ごとに 1 回数える。同居 Pod はコンテナが2つあり行が2行出るため重複を除く) の
    current_replicas の最頻値。最頻値の割合 < 80% か、窓内で台数の値が2種類以上 → 「不安定」(外れ)。
    不安定の判定は n_s (normal の s), n_t (normal の t), n_st (同居アームの同居 Pod) の3つのどれか。
    current_replicas が空のサンプルは飛ばす。1つも無ければ「無効 (窓データなし)」。
  * 無効 (行単位。normal 行か同居アーム行のどちらかが無効ならそのサイクルは無効):
      dropped_win > 0 / results の pending > 0 / 窓内の timeline の pending_pods > 0 /
      Ready 落ち / frames_ok が 0 / start_ok が 0。
    ★Ready 落ちの検出: events には SuccessfulRescale しか入らないので events からは検出できない。
      timeline の ready_replicas が、直前サンプルより減り (ready_t < ready_{t-1})、かつ HPA の台数が減っていない
      (current_t >= current_{t-1}) 場合を「Ready 落ち」とする (Pod が NotReady に落ちた)。比較の起点に窓の直前の
      1サンプルを含める。スケールアウト直後の「まだ Ready でない新 Pod」は減少でないので数えない。
      欠点: 窓の前から ready<current のまま続いていた状態は検出しない (推測: ウォームアップで解消済みのはず)。
      対象は全 Deployment (adservice 含む)。ad だけの Ready 落ちを無視したいときは --ready-ignore adservice。
      events に NotReady/Unhealthy/FailedScheduling を含む行があれば、そのキーの result 行が1行だけのときに限り無効とする。
    browse_dropped_win > 0 は規則の文言 (dropped_win) に無いので無効にはせず、件数を別に報告する
    (--strict-browse で無効扱いにできる)。
  * 同じ (サイクル, アーム, 点, 開始台数) の results 行が複数 (再実行) あるとき、有効な最後の行を使う。
    1つも有効でなければ最後の行を使い「無効」とする。results の n 番目の行と timeline の n 番目のブロック
    (t_rel が戻る位置で区切る) を対応させる。個数が違うときは末尾から対応させ警告を出す。
  * 採点単位 (ペア, 点, 開始台数) = 3サイクルの多数決。無効サイクルは票から外す (分母が 2 なら 2/2 だけ多数、1-1 は同数=外れ)。
    有効サイクルが 0 のセルは「無効セル」として正解率の分母から外す。同数は外れ。
  * 実測の損 = n_st(r_s+r_t) - (n_s r_s + n_t r_t) [ミリコア]。r_s, r_t は予測表の列。>0 損あり / =0 損なし / <0 得。
    得は予測が「損なし」でも外れ。
  * 主指標の対象 = 予測が「不明」でなく bistable=no のセル。(a) 3つ組の完全一致 (b) 損の区分の一致。Wilson 95% 区間。
  * R1 (クラス規則): s と t の片方だけが {checkout, payment, shipping, email} (buy だけで呼ばれる側) に属し、かつ buy=100 なら
    「損あり」、それ以外 (同じクラス同士、または buy≠100) は「損なし」。★「組」を「クラスをまたぐ組」と解釈した。
  * R2 (利用率比の規則): u1_s, u1_t (予測表のその点の 1 台時利用率) の max/min > 1.2 なら「損あり」、それ以外「損なし」。
  * 合格 (§4-7, K=1, 新規ペア = front+checkout 以外のみ):
      (i)  中心値 (n_s,n_t,n_st) が全員 1 台でない確定セルで、損の区分の一致率 >= 90% (セル単位多数決)
      (ii) 判定式と R1 または R2 の予測が食い違う確定セル (識別セル) で、判定式が正解のセルが過半数 (> 50%)
    確定セル = 予測が不明でなく bistable=no。
"""
import argparse
import csv
import math
import re
import sys
from collections import Counter, defaultdict

# 予測表のペア → (アーム, 同居 Pod の Deployment 名)。manifests/pairs{X,Y,Y2}.yaml による。
PAIR_POD = {
    'catalog+reco': ('pairsX', 'productcatalogservice'),
    'checkout+payment': ('pairsX', 'checkoutservice'),
    'shipping+email': ('pairsX', 'shippingservice'),
    'catalog+payment': ('pairsY', 'productcatalogservice'),
    'shipping+reco': ('pairsY', 'shippingservice'),
    'front+checkout': ('pairsY', 'frontend'),
    'catalog+email': ('pairsY2', 'productcatalogservice'),
    'payment+reco': ('pairsY2', 'paymentservice'),
    'front+shipping': ('pairsY2', 'frontend'),
}
OLD_PAIRS = {'front+checkout'}                       # 2026-09 に結果を見ているので新規に数えない
POINTS = ('b100v0', 'b100v100', 'b100v150')           # 採点対象の点
STARTS = ('1', '2')
BUY_ONLY = {'checkoutservice', 'paymentservice', 'shippingservice', 'emailservice'}   # R1 の「buy だけで呼ばれる側」
STABLE_FRAC = 0.80
BAD_EVENT = re.compile(r'NotReady|Unhealthy|FailedScheduling|Readiness', re.I)


def wilson(k, n, z=1.96):
    """Wilson 95% 区間 (割合の信頼区間。n が小さくても 0〜1 からはみ出さない)。"""
    if n == 0:
        return (float('nan'), float('nan'))
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (c - h, c + h)


def fnum(x, default=0.0):
    try:
        return float(x)
    except (TypeError, ValueError):
        return default


def point_of(row):
    return row.get('point', '')


def read_csv(path):
    with open(path, newline='') as fh:
        return list(csv.DictReader(fh))


def read_log_params(path):
    """ログ冒頭の 'warm=180s meas=240s' を読む。無ければ (None, None)。"""
    warm = meas = None
    try:
        with open(path) as fh:
            for line in fh:
                m = re.search(r'warm=(\d+)s', line)
                if m:
                    warm = int(m.group(1))
                    m2 = re.search(r'meas=(\d+)s', line)
                    meas = int(m2.group(1)) if m2 else None
                    break
    except OSError:
        pass
    return warm, meas


def run_key(r):
    return (r['cycle'], r['arm'], r['point'], r['start_replicas'])


def split_blocks(rows):
    """timeline の行を (cycle,arm,point,start) ごとに集め、t_rel が戻る位置でブロックに分ける (再実行の区別)。"""
    by = defaultdict(list)
    for r in rows:
        by[run_key(r)].append(r)
    out = {}
    for k, rs in by.items():
        blocks, cur, prev = [], [], None
        for r in rs:
            t = fnum(r['t_rel'], -1)
            if prev is not None and t < prev:
                blocks.append(cur)
                cur = []
            cur.append(r)
            prev = t
        if cur:
            blocks.append(cur)
        out[k] = blocks
    return out


def window_samples(block, warm, meas, with_prev=True):
    """ブロックを Deployment ごとの [(t_rel, current, ready, pending)] (t_rel 重複除去・時刻順) にする。
    with_prev=True なら窓の直前の1サンプルを先頭に付ける (Ready 落ちの起点。戻り値の 2 番目が窓の開始位置)。"""
    per = defaultdict(dict)
    for r in block:
        t = fnum(r['t_rel'], -1)
        d = r['deploy']
        if t not in per[d]:
            cur = r['current_replicas']
            per[d][t] = (t, int(float(cur)) if cur != '' else None,
                         int(float(r['ready_replicas'])) if r['ready_replicas'] != '' else None,
                         int(float(r['pending_pods'])) if r['pending_pods'] != '' else 0)
    res = {}
    for d, m in per.items():
        ts = sorted(m)
        inwin = [t for t in ts if t >= warm and (meas is None or t <= warm + meas)]
        pre = [t for t in ts if t < warm]
        start = inwin[0] if inwin else None
        seq = ([pre[-1]] if (with_prev and pre and inwin) else []) + inwin
        res[d] = ([m[t] for t in seq], 1 if (with_prev and pre and inwin) else 0)
    return res


def eval_run(row, block, events_for_key, n_rows_for_key, args, warm, meas):
    """1 回の測定 (results 1行 + timeline 1ブロック) を評価する。valid / 理由 / Deployment 別の台数統計。"""
    reasons = []
    if fnum(row.get('dropped_win')) > 0:
        reasons.append('dropped_win>0')
    if fnum(row.get('pending')) > 0:
        reasons.append('pending(results)>0')
    if row.get('frames_ok', '') in ('0', 'no', 'false', 'False'):
        reasons.append('frames_ok=0')
    if row.get('start_ok', '') in ('0', 'no', 'false', 'False'):
        reasons.append('start_ok=0')
    if args.strict_browse and fnum(row.get('browse_dropped_win')) > 0:
        reasons.append('browse_dropped_win>0')
    stats = {}
    ready_drop = []
    if block is None:
        reasons.append('timeline なし')
    else:
        ws = window_samples(block, warm, meas)
        pend = False
        for d, (seq, off) in ws.items():
            win = seq[off:]
            if any(s[3] > 0 for s in win):
                pend = True
            vals = [s[1] for s in win if s[1] is not None]
            if vals:
                cnt = Counter(vals)
                mode, c = sorted(cnt.items(), key=lambda kv: (-kv[1], kv[0]))[0]
                stats[d] = {'mode': mode, 'frac': c / len(vals), 'nvals': len(set(vals)), 'n': len(vals)}
            # Ready 落ち: 直前サンプルより ready が減り、HPA 台数は減っていない
            if d not in args.ready_ignore:
                for a, b in zip(seq, seq[1:]):
                    if None in (a[1], a[2], b[1], b[2]):
                        continue
                    if b[2] < a[2] and b[1] >= a[1]:
                        ready_drop.append(d)
                        break
        if pend:
            reasons.append('pending(timeline)>0')
        if ready_drop:
            reasons.append('ready落ち:' + '/'.join(sorted(ready_drop)))
    if events_for_key and n_rows_for_key == 1:
        if any(BAD_EVENT.search(m) for m in events_for_key):
            reasons.append('events に NotReady/Unhealthy 等')
    return {'valid': not reasons, 'reasons': reasons, 'stats': stats}


def build_runs(results, timeline, events, args, warm, meas):
    """(cycle,arm,point,start) → 採用する測定 (有効な最後 / 無ければ最後) を返す。"""
    blocks = split_blocks(timeline)
    ev = defaultdict(list)
    for e in events:
        ev[(e['cycle'], e['arm'], e.get('point', ''), e.get('start_replicas', ''))].append(e['message'])
    rows_by = defaultdict(list)
    for r in results:
        rows_by[run_key(r)].append(r)
    runs, warnings = {}, []
    for k, rs in rows_by.items():
        bl = blocks.get(k, [])
        if len(bl) != len(rs):
            warnings.append('results %d 行 / timeline %d ブロック (対応は末尾から): %s' % (len(rs), len(bl), k))
        evaluated = []
        for i, r in enumerate(rs):
            j = i - (len(rs) - len(bl))
            blk = bl[j] if 0 <= j < len(bl) else None
            e = eval_run(r, blk, ev.get(k), len(rs), args, warm, meas)
            e['row'] = r
            e['n_events'] = len(ev.get(k, []))
            evaluated.append(e)
        valid = [e for e in evaluated if e['valid']]
        chosen = valid[-1] if valid else evaluated[-1]
        chosen['n_runs'] = len(rs)
        runs[k] = chosen
    return runs, warnings


def categorize(loss):
    return '損あり' if loss > 0 else ('損なし' if loss == 0 else '得')


def r1_pred(row):
    cross = (row['s'] in BUY_ONLY) != (row['t'] in BUY_ONLY)
    return '損あり' if (cross and fnum(row['buy']) == 100) else '損なし'


def r2_pred(row):
    a, b = fnum(row['u1_s']), fnum(row['u1_t'])
    if min(a, b) <= 0:
        return '損あり'
    return '損あり' if max(a, b) / min(a, b) > 1.2 else '損なし'


def triple_of(row):
    return (int(float(row['n_s'])), int(float(row['n_t'])), int(float(row['n_st'])))


def vote(hits):
    """hits = 有効サイクルごとの True/False。多数決 (同数は外れ)。有効0なら None。"""
    n = len(hits)
    if n == 0:
        return None
    return sum(hits) * 2 > n


def load_pred(path):
    out = {}
    for r in read_csv(path):
        pt = 'b%dv%d' % (int(float(r['buy'])), int(float(r['view'])))
        if r['pair'] in PAIR_POD and pt in POINTS and r['start'] in STARTS:
            out[(r['pair'], pt, r['start'])] = r
    return out


def measure_cycles(pred1, runs, cycles):
    """(ペア,点,開始) × サイクル の実測 (台数・損・区分・無効理由) を作る。"""
    meas = {}
    for (pair, pt, st), p in pred1.items():
        arm, pod = PAIR_POD[pair]
        for c in cycles:
            rn = runs.get((c, 'normal', pt, st))
            rp = runs.get((c, arm, pt, st))
            rec = {'valid': False, 'unstable': False, 'reasons': [], 'triple': None, 'loss': None, 'cat': None}
            if rn is None or rp is None:
                rec['reasons'].append('測定なし(%s)' % ('normal' if rn is None else arm))
                meas[(pair, pt, st, c)] = rec
                continue
            rec['reasons'] += ['normal:' + x for x in rn['reasons']] + [arm + ':' + x for x in rp['reasons']]
            sn_s, sn_t, sp = rn['stats'].get(p['s']), rn['stats'].get(p['t']), rp['stats'].get(pod)
            if not (sn_s and sn_t and sp):
                rec['reasons'].append('窓データなし')
            if rec['reasons']:
                meas[(pair, pt, st, c)] = rec
                continue
            rec['valid'] = True
            rec['unstable'] = any(s['frac'] < STABLE_FRAC or s['nvals'] > 1 for s in (sn_s, sn_t, sp))
            rec['triple'] = (sn_s['mode'], sn_t['mode'], sp['mode'])
            rs_, rt_ = fnum(p['r_s']), fnum(p['r_t'])
            n_s, n_t, n_st = rec['triple']
            rec['loss'] = n_st * (rs_ + rt_) - (n_s * rs_ + n_t * rt_)
            rec['cat'] = categorize(rec['loss'])
            meas[(pair, pt, st, c)] = rec
    return meas


def score_cells(pred1, pred2, meas, cycles):
    """セル (ペア,点,開始) ごとに各予測者のサイクル別・多数決の正誤を出す。"""
    cells = []
    for key in sorted(pred1, key=lambda k: (k[0], POINTS.index(k[1]), k[2])):
        pair, pt, st = key
        p1, p2 = pred1[key], pred2.get(key)
        recs = [(c, meas[(pair, pt, st, c)]) for c in cycles]
        vrecs = [(c, m) for c, m in recs if m['valid']]
        n_inv = len(recs) - len(vrecs)
        cell = {'pair': pair, 'point': pt, 'start': st, 'p1': p1, 'p2': p2,
                'n_valid': len(vrecs), 'n_invalid': n_inv,
                'n_unstable': sum(1 for _, m in vrecs if m['unstable']),
                'recs': recs, 'reasons': sorted({x for _, m in recs for x in m['reasons']})}
        ptriple = triple_of(p1)
        preds = {'K1': p1['category'], 'K2': p2['category'] if p2 else None, 'R1': r1_pred(p1), 'R2': r2_pred(p1)}
        cell['pred'] = preds
        cell['ptriple'] = ptriple
        hits = {}
        hits['triple'] = [(not m['unstable']) and m['triple'] == ptriple for _, m in vrecs]
        hits['triple2'] = None
        if p2:
            hits['triple2'] = [(not m['unstable']) and m['triple'] == triple_of(p2) for _, m in vrecs]
        for nm, pc in preds.items():
            hits[nm] = [(not m['unstable']) and m['cat'] == pc for _, m in vrecs] if pc in ('損あり', '損なし') else None
        cell['cyc_hits'] = hits
        cell['vote'] = {k: (vote(v) if v is not None else None) for k, v in hits.items()}
        cell['valid_cell'] = len(vrecs) > 0
        cell['confirmed1'] = p1['category'] != '不明' and p1['bistable'] == 'no'
        cell['confirmed2'] = bool(p2) and p2['category'] != '不明' and p2['bistable'] == 'no'
        cell['nontrivial'] = ptriple != (1, 1, 1)
        cell['novel'] = pair not in OLD_PAIRS
        cells.append(cell)
    return cells


def agg(cells, sel, name):
    """sel(cell) で選んだ有効セルについて、予測者 name の正解セル数 / 総数 (セル単位) と、サイクル単位。"""
    ks = vn = cn = ck = 0
    for c in cells:
        if not (c['valid_cell'] and sel(c)):
            continue
        v = c['vote'].get(name)
        if v is None:
            continue
        vn += 1
        ks += 1 if v else 0
        h = c['cyc_hits'][name]
        cn += len(h)
        ck += sum(h)
    return ks, vn, ck, cn


def fmt(k, n):
    if n == 0:
        return 'n/a (n=0)'
    lo, hi = wilson(k, n)
    return '%d/%d = %.1f%% [Wilson95 %.1f-%.1f%%]' % (k, n, 100 * k / n, 100 * lo, 100 * hi)


def summarize(cells, runs, warnings, out):
    P = lambda *a: print(*a, file=out)
    # ---- 合格条件 (K=1, 新規ペア) ----
    nov1 = lambda c: c['novel'] and c['confirmed1']
    k_i, n_i, _, _ = agg(cells, lambda c: nov1(c) and c['nontrivial'], 'K1')
    ok_i = n_i > 0 and k_i / n_i >= 0.9
    ident = [c for c in cells if c['valid_cell'] and nov1(c) and
             (c['pred']['K1'] != c['pred']['R1'] or c['pred']['K1'] != c['pred']['R2'])]
    k_ii = sum(1 for c in ident if c['vote']['K1'])
    n_ii = len(ident)
    ok_ii = n_ii > 0 and k_ii * 2 > n_ii
    P('=' * 78)
    P('pairval 採点 (事前登録 §4)')
    P('=' * 78)
    P('【合格条件 §4-7】(主評価 K=1・新規ペアのみ = front+checkout を除く、セル単位の多数決)')
    P('  (i)  自明でない確定セルの損の区分の一致率 >= 90%%: %s -> %s' % (fmt(k_i, n_i), '満たす' if ok_i else '満たさない'))
    P('  (ii) 識別セル (判定式が R1 または R2 と食い違う確定セル) で判定式が過半数正解: %s -> %s'
      % (fmt(k_ii, n_ii), '満たす' if ok_ii else '満たさない'))
    P('  => 判定: %s' % ('合格' if (ok_i and ok_ii) else '不合格'))
    if n_i == 0 or n_ii == 0:
        P('  (注意: 対象セルが 0 のため判定不能。無効が多すぎる可能性)')
    P('')

    def block(title, K, sel):
        nm = 'K%d' % K
        tn = 'triple' if K == 1 else 'triple2'
        P('【%s】' % title)
        for lab, s2 in (('全確定セル', lambda c: True), ('うち自明でない(中心値が全員1台でない)', lambda c: c['nontrivial'])):
            s = lambda c: sel(c) and s2(c)
            P('  <%s>' % lab)
            for who, nmx in (('(a) 3つ組の完全一致', tn), ('(b) 損の区分の一致  [判定式]', nm),
                             ('    対照 R1 (クラス規則)', 'R1'), ('    対照 R2 (利用率比の規則)', 'R2')):
                kc, nc, ck, cn = agg(cells, s, nmx)
                P('    %-28s セル: %-42s サイクル: %s' % (who, fmt(kc, nc), fmt(ck, cn)))
        P('')

    ck1 = lambda c: c['confirmed1']
    ck2 = lambda c: c['confirmed2']
    block('主評価 K=1・新規ペア (対象 = 予測が不明でなく bistable=no)', 1, lambda c: ck1(c) and c['novel'])
    block('副評価 K=2・新規ペア', 2, lambda c: ck2(c) and c['novel'])
    block('副: front+checkout (新規に数えない) K=1', 1, lambda c: ck1(c) and not c['novel'])
    block('副: front+checkout K=2', 2, lambda c: ck2(c) and not c['novel'])
    # ---- 件数 ----
    tot = len(cells)
    inv_cells = [c for c in cells if not c['valid_cell']]
    n_cyc = sum(len(c['recs']) for c in cells)
    n_inv = sum(c['n_invalid'] for c in cells)
    n_unst = sum(c['n_unstable'] for c in cells)
    P('【件数】セル (ペア×点×開始台数) %d 個、サイクル単位 %d 個' % (tot, n_cyc))
    P('  無効セル (有効サイクル0) = %d (正解率の分母から外した) / 無効サイクル = %d / 有効サイクルのうち不安定 (=外れ) = %d'
      % (len(inv_cells), n_inv, n_unst))
    rc = Counter(x.split(':', 1)[-1].split(':')[0] if x.startswith(('normal:', 'pairs')) else x
                 for c in cells for _, m in c['recs'] for x in m['reasons'])
    P('  無効理由の内訳 (サイクル単位、同じ測定が複数ペアに数えられる): %s' % dict(rc))
    for w in warnings:
        P('  警告: ' + w)
    P('')
    # ---- 双安定・不明セルの内訳 ----
    P('【副: bistable=yes または 予測「不明」(K=1) のセルの実測内訳】 実測は (n_s,n_t,n_st)/区分 を各サイクル並べる (! = 不安定, x = 無効)')
    for c in cells:
        p1 = c['p1']
        if c['confirmed1']:
            continue
        why = []
        if p1['bistable'] == 'yes':
            why.append('bistable')
        if p1['category'] == '不明':
            why.append('不明')
        obs = []
        for cy, m in c['recs']:
            if not m['valid']:
                obs.append('x')
            else:
                obs.append('%s%s/%s' % ('!' if m['unstable'] else '', ','.join(map(str, m['triple'])), m['cat']))
        P('  %-17s %-9s 開始%s [%s] 予測中心 %s %s | 実測: %s' % (
            c['pair'], c['point'], c['start'], '+'.join(why), ','.join(map(str, c['ptriple'])), p1['category'], '  '.join(obs)))
    P('')
    # ---- 得 ----
    gains = [(c['pair'], c['point'], c['start'], cy) for c in cells for cy, m in c['recs'] if m['valid'] and m['cat'] == '得']
    P('【得 (損<0) のサイクル】 %d 件 %s' % (len(gains), gains[:20]))
    bd = sum(1 for k, r in runs.items() if fnum(r['row'].get('browse_dropped_win')) > 0)
    P('【参考】browse_dropped_win>0 の測定 (規則外のため無効にしていない): %d 件' % bd)


def write_cells_csv(cells, path):
    cols = ['pair', 'point', 'start', 'K1_category', 'K2_category', 'bistable', 'novel', 'nontrivial',
            'pred_triple', 'n_valid_cycles', 'n_invalid_cycles', 'n_unstable_cycles', 'valid_cell',
            'obs_per_cycle', 'obs_loss_m_per_cycle', 'obs_category_per_cycle', 'R1', 'R2',
            'hit_triple_votes', 'hit_K1_vote', 'hit_K2_vote', 'hit_R1_vote', 'hit_R2_vote',
            'hits_triple_cycles', 'hits_K1_cycles', 'hits_R1_cycles', 'hits_R2_cycles', 'invalid_reasons']
    b = lambda x: '' if x is None else ('1' if x else '0')
    hc = lambda c, k: ''.join('1' if x else '0' for x in c['cyc_hits'][k]) if c['cyc_hits'].get(k) is not None else ''
    with open(path, 'w', newline='') as fh:
        w = csv.writer(fh)
        w.writerow(cols)
        for c in cells:
            obs = ['x' if not m['valid'] else ('!' if m['unstable'] else '') + ','.join(map(str, m['triple'])) for _, m in c['recs']]
            los = ['' if not m['valid'] else '%g' % m['loss'] for _, m in c['recs']]
            cat = ['' if not m['valid'] else m['cat'] for _, m in c['recs']]
            w.writerow([c['pair'], c['point'], c['start'], c['pred']['K1'], c['pred']['K2'] or '', c['p1']['bistable'],
                        int(c['novel']), int(c['nontrivial']), ','.join(map(str, c['ptriple'])), c['n_valid'],
                        c['n_invalid'], c['n_unstable'], int(c['valid_cell']), ' | '.join(obs), ' | '.join(los),
                        ' | '.join(cat), c['pred']['R1'], c['pred']['R2'],
                        b(c['vote']['triple']), b(c['vote']['K1']), b(c['vote']['K2']), b(c['vote']['R1']), b(c['vote']['R2']),
                        hc(c, 'triple'), hc(c, 'K1'), hc(c, 'R1'), hc(c, 'R2'), '; '.join(c['reasons'])])


def score(results, timeline, events, pred1, pred2, warm, meas=None, ready_ignore=(), strict_browse=False):
    """API (テスト用)。戻り値 = (cells, runs, warnings)。"""
    args = argparse.Namespace(ready_ignore=set(ready_ignore), strict_browse=strict_browse)
    runs, warnings = build_runs(results, timeline, events, args, warm, meas)
    cycles = sorted({k[0] for k in runs}, key=lambda x: int(x))
    m = measure_cycles(pred1, runs, cycles)
    return score_cells(pred1, pred2, m, cycles), runs, warnings


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--results', default='../summer2026/results-pairval.csv')
    ap.add_argument('--timeline', default='../summer2026/timeline-pairval.csv')
    ap.add_argument('--events', default='../summer2026/events-pairval.csv')
    ap.add_argument('--log', default='../summer2026/pairval.log')
    ap.add_argument('--pred', default='predictions-pairval-K1.csv')
    ap.add_argument('--pred2', default='predictions-pairval-K2.csv')
    ap.add_argument('--out', default='score-pairval-cells.csv')
    ap.add_argument('--warm', type=int, default=None, help='ウォームアップ秒 (既定: ログの warm=)')
    ap.add_argument('--meas', type=int, default=None, help='指定時のみ窓の上限 t_rel<=warm+meas を課す')
    ap.add_argument('--ready-ignore', nargs='*', default=[], help='Ready 落ちの判定から外す Deployment (例: adservice)')
    ap.add_argument('--strict-browse', action='store_true', help='browse_dropped_win>0 も無効にする (規則外)')
    a = ap.parse_args(argv)
    warm = a.warm
    if warm is None:
        warm, _ = read_log_params(a.log)
    if warm is None:
        sys.exit('warm が決まらない: --warm を渡すか、ログ冒頭に warm=...s があること')
    cells, runs, warnings = score(read_csv(a.results), read_csv(a.timeline), read_csv(a.events),
                                  load_pred(a.pred), load_pred(a.pred2), warm, a.meas, a.ready_ignore, a.strict_browse)
    print('入力: results=%s timeline=%s events=%s log=%s pred=%s pred2=%s WARM=%ds' % (
        a.results, a.timeline, a.events, a.log, a.pred, a.pred2, warm))
    summarize(cells, runs, warnings, sys.stdout)
    write_cells_csv(cells, a.out)
    print('セル単位の採点 CSV: %s' % a.out)


if __name__ == '__main__':
    main()
