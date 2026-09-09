#!/usr/bin/env python3
"""「どのサービスが、いつ台数を増やしたか」を時系列CSVから取り出す。

なぜこれを見るか:
  粒度損は「束ねた2つのサービスの必要台数が揃わない」ときに出る。
  必要台数が揃うかどうかは、突き詰めると「HPAのしきい値に同じタイミングで到達するか」。
  だから各サービスが N台目を立てた時刻を並べれば、揃っている組/ズレている組が直接見える。
  (これまでは1台固定・HPA無しで利用率カーブを描いて間接的に推定していた。これは直接測る版)

使い方: python3 scale_timing.py timeline-xxx.csv [timeline-yyy.csv ...]
"""
import csv, sys, collections

def blocks_of(path):
    """1ファイルに複数測定が入っているので、t_rel が戻る所で切る"""
    rows=list(csv.DictReader(open(path)))
    out=[]; cur=[]; prev=None
    for r in rows:
        t=float(r['t_rel'])
        if prev is not None and t<prev: out.append(cur); cur=[]
        cur.append(r); prev=t
    if cur: out.append(cur)
    return out

for path in sys.argv[1:]:
    print("\n######## %s" % path)
    for bi, b in enumerate(blocks_of(path), 1):
        head=b[0]
        # deploy ごとに (時刻, 台数) の推移を作る。同じ deploy がコンテナ数だけ重複するので除く
        seen=set(); series=collections.defaultdict(list)
        for r in b:
            k=(r['t_rel'], r['deploy'])
            if k in seen: continue
            seen.add(k)
            try: n=int(r['current_replicas'])
            except (ValueError, TypeError): continue
            series[r['deploy']].append((float(r['t_rel']), n))
        # 各 deploy が「N台目に到達した最初の時刻」
        first={}
        for dep, v in series.items():
            v.sort()
            start=v[0][1]
            marks={}
            peak=start
            for t,n in v:
                if n>peak:
                    for m in range(peak+1, n+1): marks.setdefault(m, t)
                    peak=n
            first[dep]=(start, peak, marks)
        lbl=f"[{head.get('arm','?')} {head.get('target_rate','?')}周/s cyc{head.get('cycle','?')}"
        if 'limit_x' in head: lbl+=f" lx={head['limit_x']}"
        print(f"\n{lbl}]  (ウォームアップ180秒 → 計測240秒)")
        print(f"  {'サービス':<24}{'開始':>4}{'最終':>5}   {'2台目':>7}{'3台目':>7}{'4台目':>7}{'5台目':>7}  [秒]")
        for dep in sorted(first, key=lambda d: first[d][2].get(2, 9e9)):
            start, peak, m = first[dep]
            cells="".join(f"{(('%.0f'%m[k]) if k in m else '-'):>7}" for k in (2,3,4,5))
            print(f"  {dep:<24}{start:>4}{peak:>5}   {cells}")
        # 揃い具合の要約: 2台目・3台目に到達した時刻のばらつき
        for k in (2,3):
            ts=[m[k] for _,_,m in first.values() if k in m]
            if len(ts)>=2:
                print(f"    → {k}台目に到達した時刻: 最早{min(ts):.0f}秒 〜 最遅{max(ts):.0f}秒 (幅 {max(ts)-min(ts):.0f}秒, {len(ts)}サービス)")
