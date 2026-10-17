#!/bin/bash
# Sock Shop: 枠を決めるための予備測定 (2026-10-17)。HPA なし・全サービス 1 台・枠は測定用の仮 (normal/ のまま)。
# 点 (購入 周/s, 閲覧 周/s) ごとに k6 を WARM+MEAS 秒流し、計測窓の終わりに Prometheus で
# コンテナ別 CPU = rate(container_cpu_usage_seconds_total[MEAS s]) を取る。
# 使い方: POINTS="b10v0 b20v0 b0v50" WARM=60 MEAS=120 OUT=probe-cpu.csv bash probe-cpu.sh
set -u
NS=${NS:-exp}
DIR=/home/mizuki/ダウンロード/msa/sockshop
POINTS=${POINTS:-"b5v0 b10v0 b20v0 b40v0 b0v25 b0v50 b0v100 b0v200"}
WARM=${WARM:-60}; MEAS=${MEAS:-120}
OUT=${OUT:-$DIR/experiments/probe-cpu.csv}
PROM="http://prometheus-grafana-kube-pr-prometheus.monitoring.svc:9090"

ensure_promq(){ [ "$(kubectl get pod promq -n $NS -o jsonpath='{.status.phase}' 2>/dev/null)" = Running ] && return
  kubectl delete pod promq -n $NS --ignore-not-found >/dev/null 2>&1
  kubectl run promq -n $NS --image=curlimages/curl:latest --restart=Never --command -- sleep 86400 >/dev/null 2>&1
  for i in $(seq 1 30); do [ "$(kubectl get pod promq -n $NS -o jsonpath='{.status.phase}' 2>/dev/null)" = Running ] && break; sleep 2; done; }
promq(){ ensure_promq; kubectl exec promq -n $NS -- curl -s --max-time 25 "$PROM/api/v1/query" --data-urlencode "query=$1"; }

[ -f "$OUT" ] || echo "point,buy,browse,pod,container,cpu_m,iter_rate,dropped_win,failed_rate,order_failed,browse_rate,browse_dropped_win,browse_failed,p50,order_p50,browse_p50" > "$OUT"
kubectl create configmap k6-script -n $NS --from-file=sockshop.js=$DIR/k6/sockshop.js --dry-run=client -o yaml | kubectl apply -n $NS -f - >/dev/null 2>&1
for pt in $POINTS; do
  b=${pt#b}; b=${b%v*}; v=${pt#*v}
  echo "==== $pt (buy=$b browse=$v) $(date -Is)"
  kubectl delete job k6load -n $NS --ignore-not-found --wait=true >/dev/null 2>&1
  sed -e "s/__RATE__/$b/;s/__BROWSE__/$v/;s/__WARM__/$WARM/;s/__MEAS__/$MEAS/;s/__PRE__/50/;s/__MAX__/400/;s/__NUSERS__/400/" \
    $DIR/k6/k6-job.yaml | kubectl apply -n $NS -f - >/dev/null
  until kubectl logs -n $NS job/k6load 2>/dev/null | grep -q K6_DONE; do sleep 5; done
  sum=$(kubectl logs -n $NS job/k6load | sed -n '/K6_BEGIN/{n;p}')
  echo "  k6: $sum"
  # k6 終了直後 = 計測窓の終わり。窓 MEAS 秒の平均 CPU
  promq "sum by (pod,container) (rate(container_cpu_usage_seconds_total{namespace=\"$NS\",container!=\"\",container!=\"POD\"}[${MEAS}s]))" \
  | python3 -c "
import json,sys
d=json.load(sys.stdin)['data']['result']; s=json.loads('''$sum''' or '{}')
g=lambda k: s.get(k,'')
for r in sorted(d,key=lambda r:r['metric']['pod']):
    m=r['metric']
    if m['pod'].startswith(('k6load','promq')): continue
    print(','.join(map(str,['$pt',$b,$v,m['pod'],m['container'],round(float(r['value'][1])*1000,1),g('iter_rate'),g('dropped_win'),g('failed_rate'),g('order_failed'),g('browse_rate'),g('browse_dropped_win'),g('browse_failed'),g('p50'),g('order_p50'),g('browse_p50')])))
" | tee -a "$OUT" | awk -F, '{printf "  %-16s %7.1fm\n",$5,$6}'
  kubectl get pods -n $NS --no-headers | awk '$4>0{print "  !! restart:",$1,$4}'
done
kubectl delete job k6load -n $NS --ignore-not-found >/dev/null 2>&1
echo "DONE $(date -Is)"
