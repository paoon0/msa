#!/usr/bin/env bash
# 基線の再現性チェック: 今デプロイ中(温まって無負荷)のアームの基線を 2分窓で N 回連続測定。
# 各窓を独立にするため SPACING 秒あけて測る。本走の基線が1回測定でどれだけ信頼できるかを定量化。
set -u
NS=exp
PROM="http://prometheus-grafana-kube-pr-prometheus.monitoring.svc:9090"
WIN=${WIN:-2m}; N=${N:-3}; SPACING=${SPACING:-120}
OUT=/home/mizuki/ダウンロード/msa/km2/all/baseline-repeat.csv
kubectl delete pod promq -n "$NS" --ignore-not-found >/dev/null 2>&1
kubectl run promq -n "$NS" --image=curlimages/curl:latest --restart=Never --command -- sleep 86400 >/dev/null 2>&1
for i in $(seq 1 30); do [ "$(kubectl get pod promq -n "$NS" -o jsonpath='{.status.phase}' 2>/dev/null)" = "Running" ] && break; sleep 2; done
q() { kubectl exec promq -n "$NS" -- curl -s "$PROM/api/v1/query" --data-urlencode "query=$1" 2>/dev/null \
  | python3 -c "import sys,json;r=json.load(sys.stdin).get('data',{}).get('result',[]);print(r[0]['value'][1] if r else 'NA')" 2>/dev/null; }
echo "sample,ts,node_cores,app_cores" > "$OUT"
echo "==== 基線再現性チェック N=$N win=$WIN spacing=${SPACING}s ===="
for s in $(seq 1 "$N"); do
  nc=$(q "sum(rate(node_cpu_seconds_total{mode!=\"idle\"}[$WIN]))")
  ac=$(q "sum(rate(container_cpu_usage_seconds_total{namespace=\"$NS\",container!=\"\",container!=\"POD\",pod!~\"loadgenerator.*\",pod!~\"promq.*\"}[$WIN]))")
  ts=$(date -Is); echo "  $ts sample $s: node=$nc app=$ac"; echo "$s,$ts,$nc,$ac" >> "$OUT"
  [ "$s" -lt "$N" ] && sleep "$SPACING"
done
kubectl delete pod promq -n "$NS" --ignore-not-found >/dev/null 2>&1
python3 - "$OUT" <<'PY'
import sys,csv,statistics as st
rows=list(csv.DictReader(open(sys.argv[1])))
v=[float(r['node_cores']) for r in rows if r['node_cores'] not in ('NA','')]
if len(v)>=2:
    m=st.mean(v); sd=st.pstdev(v); rng=max(v)-min(v)
    print(f"node 基線: mean={m:.3f} sd={sd:.3f} range={rng:.3f} cores (n={len(v)})")
    print(f"  → rps=92 換算ばらつき: sd={sd/92*1000:.2f} range={rng/92*1000:.2f} mc/req")
    print(f"  → rps=215換算ばらつき: sd={sd/215*1000:.2f} range={rng/215*1000:.2f} mc/req")
PY
