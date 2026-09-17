#!/usr/bin/env python3
"""FOSE2026 表1「必要台数の食い違い」を results-mix.csv / results-mix2.csv から再現する。

定義 (論文 §2, §4):
  必要台数 n(s) = サービス s を単独 Pod で配置 (arm=normal) したとき HPA が到達した台数
               = results-*.csv の normal 行の replicas 列 (計測窓終了時点)。
  組 (A, B) について、同じ (cycle, view レート) の n(A) と n(B) を比べ、
    n(A) < n(B) なら「A が引きずられる」= 表の n<
    n(A) > n(B) なら「B が引きずられる」= 表の n>
  を cycle 1..5 で数える。view レート 4 段階 × 5 サイクル = 20 点。
  計 = 食い違った点数 / 観測できた点数。同じ (cycle, view) に同居アームの行も存在する点だけを数える
  (frontcart の cycle1 view300 は同居アームの測定が欠けているため除外 → frontend+cart の分母が 19)。

使い方: python3 table1_mismatch.py   (summer2026/ で実行)
"""
import csv, collections

CYCLES = {'1', '2', '3', '4', '5'}
VIEWS = ['0', '100', '200', '300']
PAIRS = [  # (表の行名, 左サービス, 右サービス, 同居アーム名, 出典CSV)
    ('frontend+reco',     'frontend',        'recommendationservice', 'frontreco',     'results-mix.csv'),
    ('frontend+catalog',  'frontend',        'productcatalogservice', 'frontcatalog',  'results-mix.csv'),
    ('checkout+email',    'checkoutservice', 'emailservice',          'checkoutemail', 'results-mix2.csv'),
    ('frontend+checkout', 'frontend',        'checkoutservice',       'frontcheckout', 'results-mix2.csv'),
    ('frontend+cart',     'frontend',        'cartservice',           'frontcart',     'results-mix.csv'),
    ('frontend+email',    'frontend',        'emailservice',          'frontemail',    'results-mix2.csv'),
    # 7 組目。測定はあるが論文の表1からは除外 (ユーザ判断 2026-09-13)。参考として出す
    ('(catalog+checkout)', 'productcatalogservice', 'checkoutservice', 'catalogcheckout', 'results-mix2.csv'),
]


def parse(s):
    d = {}
    for t in s.split():
        k, _, v = t.rpartition(':')
        d[k] = int(v)
    return d


def load(path):
    """arm -> {(cycle, view): {service: replicas}}。同じキーが複数あれば最後 (やり直した方) を採る。"""
    out = collections.defaultdict(dict)
    for r in csv.DictReader(open(path, encoding='utf-8')):
        if r['cycle'] not in CYCLES:
            continue
        out[r['arm']][(r['cycle'], r['browse_rate_target'])] = parse(r['replicas'])
    return out


cache = {}
print(f"{'組み合わせ':18s} " + ' '.join(f"{'v'+v:>5s}" for v in VIEWS) + '   計')
for name, a, b, arm, path in PAIRS:
    if path not in cache:
        cache[path] = load(path)
    rep, bundle = cache[path]['normal'], cache[path][arm]
    cells, mism, seen = [], 0, 0
    for v in VIEWS:
        lt = gt = 0
        for c in sorted(CYCLES):
            r = rep.get((c, v))
            if not r or a not in r or b not in r or (c, v) not in bundle:
                continue
            seen += 1
            if r[a] < r[b]:
                lt += 1
            elif r[a] > r[b]:
                gt += 1
        mism += lt + gt
        cells.append(f"{lt}<" if lt else (f"{gt}>" if gt else '---'))
        if lt and gt:
            cells[-1] = f"{lt}<{gt}>"   # 両向きが混在した場合 (表では起きていない)
    print(f"{name:18s} " + ' '.join(f"{x:>5s}" for x in cells) + f"   {mism}/{seen}")
