#!/usr/bin/env python3
"""いま確保されている CPU 枠を、Pod の実体から直接数える。

標準入力: kubectl get pods -n <ns> -o json
標準出力: running_cores pending_cores running_pods pending_pods  (空白区切り1行)

Prometheus の kube_pod_container_resource_requests を使う方法は、
  * `== 1` の掛かる位置を間違えると別物を数える(第2版1回目: 3.00固定)
  * join に失敗すると空を返す(第2版2回目: 0.00)
という事故を2回起こしたので、Pod の spec から直接数える方式に変更した。
Pending の Pod(=ノードに載れず動いていない)は必ず分けて数える。
"""
import sys, json, re

SKIP = re.compile(r'^(k6load|promq)')


def cpu_m(v):
    """'500m' / '1' / '1.5' → ミリコア"""
    if not v:
        return 0.0
    v = str(v)
    if v.endswith('m'):
        return float(v[:-1])
    return float(v) * 1000.0


try:
    d = json.load(sys.stdin)
except Exception as e:
    print("0 0 0 0")
    print("reserved.py: JSON読み取り失敗 %s" % e, file=sys.stderr)
    sys.exit(0)

run_m = pend_m = 0.0
run_n = pend_n = 0
for p in d.get('items', []):
    name = p['metadata']['name']
    if SKIP.match(name):
        continue
    phase = p.get('status', {}).get('phase')
    total = 0.0
    for c in p['spec']['containers']:
        if c['name'] == 'istio-proxy':
            continue
        total += cpu_m(((c.get('resources') or {}).get('requests') or {}).get('cpu'))
    if phase == 'Running':
        run_m += total; run_n += 1
    elif phase == 'Pending':
        pend_m += total; pend_n += 1

print("%.3f %.3f %d %d" % (run_m / 1000.0, pend_m / 1000.0, run_n, pend_n))
