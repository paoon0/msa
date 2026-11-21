#!/usr/bin/env python3
"""需要モデルの外れを「形のずれ」と「サイクルの揺れ」に分け、周波数固定の前後で比べる (2026-11-19)。

入力 = plot_fit_mix.py が書いた図の HTML (中に当てた結果と各点の残差が入っている)。
  形のずれ   = 配合ごとに 6 サイクルの残差を平均した値の二乗平均平方根 (直線の形が合っていない分)
  サイクルの揺れ = 各点の残差から、その配合の平均を引いた値の二乗平均平方根 (繰り返しの揺れ)
  どちらも b50v150 での直線の値 (枠の元になる D) に対する %。除外した点は使わない。
使い方: python3 fit_shape_compare.py fig-fit-mix-cpu2.html fig-fit-mix-cpu3.html fig-fit-mix-cpu4.html > analysis-fit-shape.txt
"""
import json,re,math,collections,sys
FILES=sys.argv[1:]
rm=lambda xs: math.sqrt(sum(x*x for x in xs)/len(xs))
res={}
for k in FILES:
    d=json.loads(re.search(r'const DATA = (\{.*?\});\n',open(k).read()).group(1))
    for n in '12':
        for sv,f in d[n].items():
            u=[p for p in f['pts'] if not p['ex']]
            g=collections.defaultdict(list)
            for p in u: g[p['pt']].append(100*p['res']/f['dref'])
            shape=rm([sum(v)/len(v) for v in g.values()])
            noise=rm([x-sum(v)/len(v) for v in g.values() for x in v])
            g2=[sum(v)/len(v) for pt,v in g.items() if pt!='b100v150']
            res[(k,n,f['name'])]=(shape,noise,rm(g2),f['n_ex'],f['rho'])
names=[k[2] for k in res if k[0]==FILES[-1] and k[1]=='1']
for n in '12':
    print(f'== {n} 台   形のずれ% (b100v150 抜き) / サイクルの揺れ% / 除外数 / ρ   : ' + ' | '.join(FILES))
    for nm in names:
        print(f'{nm:9}', ' | '.join(f'{res[(k,n,nm)][0]:4.1f} ({res[(k,n,nm)][2]:4.1f}) / {res[(k,n,nm)][1]:3.1f} / {res[(k,n,nm)][3]:2d} / {res[(k,n,nm)][4]:.3f}' for k in FILES))
    for k in FILES:
        v=[res[(k,n,nm)] for nm in names]
        print(f'  {k} 10 サービスの平均: 形 {sum(x[0] for x in v)/10:.2f}%  形(b100v150抜き) {sum(x[2] for x in v)/10:.2f}%  揺れ {sum(x[1] for x in v)/10:.2f}%')
