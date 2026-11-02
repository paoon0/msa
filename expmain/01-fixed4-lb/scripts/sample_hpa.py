#!/usr/bin/env python3
"""`kubectl get hpa,deploy,pods -o json` を標準入力で受け、時系列1行/コンテナ を CSV で出す。

出力列: cycle,arm,target_rate,t_rel,deploy,container,hpa_util_pct,current_replicas,desired_replicas,ready_replicas,pending_pods
  hpa_util_pct = HPA がその瞬間に判断材料として見ていた利用率(コンテナ別, status.currentMetrics)
  desired_replicas = HPA が「こうしたい」と決めた台数(実際に立つ前の意思が見える)
  pending_pods = そのDeploymentでノードに載れず Pending の Pod 数
環境変数 CYC/ARM/RATE/LX/T0 で文脈を渡す(T0=k6起動時刻のepoch秒, LX=limitsの倍率)。
※ パイプで JSON を渡すため heredoc は使わない(heredocは標準入力を奪ってしまう)。
"""
import sys, json, os, time, csv

try:
    d = json.load(sys.stdin)
except Exception as e:
    print("sample_hpa: JSON読み取り失敗: %s" % e, file=sys.stderr)
    sys.exit(0)

cyc, arm, rate = os.environ.get('CYC', '1'), os.environ.get('ARM', '?'), os.environ.get('RATE', '?')
lx = os.environ.get('LX', '0')   # limits の倍率。これが無いと同じ(cycle,rate)の別条件が混ざる
brw = os.environ.get('BRW', '0') # 閲覧型の到着レート。同上(購入型を固定して閲覧型だけ振ると衝突する)
t = int(time.time()) - int(os.environ.get('T0', time.time()))

def _cpu_m(v):
    """'500m' / '1' / '1.5' → ミリコア"""
    if not v: return 0.0
    v = str(v)
    return float(v[:-1]) if v.endswith('m') else float(v) * 1000.0

hpa, dep, pend = {}, {}, {}
# 名前空間全体の予約枠。reserved.py と同じ数え方(k6load/promq を除外、istio-proxy を除外、
# Running と Pending を分ける)を、15秒ごとのサンプルでも記録する。
# 追加の取得は不要 — Pod の spec は既にこの JSON に入っている。
# これで「計測窓の中で台数が動いた測定」でも、窓の時間平均が事後に計算できる。
ns_run_m = ns_pend_m = 0.0
for it in d.get('items', []):
    kind = it.get('kind')
    name = it.get('metadata', {}).get('name', '?')
    if kind == 'HorizontalPodAutoscaler':
        st = it.get('status', {})
        mets = {}
        for m in (st.get('currentMetrics') or []):
            cr = m.get('containerResource') or {}
            if cr:
                mets[cr.get('container')] = (cr.get('current') or {}).get('averageUtilization')
        hpa[name] = (st.get('currentReplicas'), st.get('desiredReplicas'), mets)
    elif kind == 'Deployment':
        dep[name] = (it.get('spec', {}).get('replicas'), it.get('status', {}).get('readyReplicas') or 0)
    elif kind == 'Pod':
        phase = it.get('status', {}).get('phase')
        if phase == 'Pending':
            base = name.rsplit('-', 2)[0]          # pod名 → deployment名
            pend[base] = pend.get(base, 0) + 1
        if not (name.startswith('k6load') or name.startswith('promq')):
            tot = 0.0
            for c in (it.get('spec', {}).get('containers') or []):
                if c.get('name') == 'istio-proxy':
                    continue
                tot += _cpu_m(((c.get('resources') or {}).get('requests') or {}).get('cpu'))
            if phase == 'Running':
                ns_run_m += tot
            elif phase == 'Pending':
                ns_pend_m += tot

w = csv.writer(sys.stdout)
for name, (spec, ready) in sorted(dep.items()):
    cur, des, mets = hpa.get(name, (spec, spec, {}))
    if not mets:
        mets = {'-': None}
    for c, u in sorted(mets.items()):
        w.writerow([cyc, arm, rate, lx, brw, t, name, c, '' if u is None else u,
                    cur, des, ready, pend.get(name, 0),
                    round(ns_run_m / 1000.0, 3), round(ns_pend_m / 1000.0, 3)])
