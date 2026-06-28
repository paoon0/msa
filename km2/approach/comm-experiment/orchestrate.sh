#!/usr/bin/env bash
# 自動本走: 分離(ClusterIP) <-> 同居(localhost) を交互に6分走、各完了後に分布をPrometheusから取得しCSV追記。
set -u
SP=/tmp/claude-1000/-home-mizuki--------msa/2180ecd9-490c-40b3-8a03-47e2819257f7/scratchpad
REPO=/home/mizuki/ダウンロード/msa
SEP=$REPO/km2/checkoutservice.yaml          # 分離: EMAIL=emailservice:5000 (ClusterIP)
COLO=$REPO/km2/outmail/outmail.yaml         # 同居: EMAIL=localhost:8080
LOAD=$SP/loadgen-run.yaml
CSV=$SP/results.csv
LOG=$SP/orchestrate.log
NS=exp
PROMPORT=9091
WINDOW=4m
CYCLES=4

exec >>"$LOG" 2>&1
echo "================ START $(date -Is) ================"
echo "cycle,arm,emailaddr,dst,p50_ms,p90_ms,p99_ms,mean_ms,reqps" > "$CSV"

# 専用 port-forward
pkill -f "port-forward.*$PROMPORT:9090" 2>/dev/null
kubectl port-forward -n monitoring svc/prometheus-grafana-kube-pr-prometheus $PROMPORT:9090 >/dev/null 2>&1 &
PF=$!
trap 'kill $PF 2>/dev/null' EXIT
sleep 5

pq() { # promql -> scalar
  curl -s "http://localhost:$PROMPORT/api/v1/query" --data-urlencode "query=$1" \
   | python3 -c "import sys,json;r=json.load(sys.stdin)['data']['result'];print(r[0]['value'][1] if r else 'NA')" 2>/dev/null
}
ms() { python3 -c "print(round(float('$1')*1000,3))" 2>/dev/null || echo NA; }

snapshot() { # cycle arm emailaddr
  local cyc=$1 arm=$2 addr=$3 dst p50 p90 p99 mean rps
  for dst in emailservice paymentservice; do
    p50=$(ms "$(pq "histogram_quantile(0.5, sum by (le) (rate(grpc_client_latency_seconds_bucket{destination=\"$dst\"}[$WINDOW])))")")
    p90=$(ms "$(pq "histogram_quantile(0.9, sum by (le) (rate(grpc_client_latency_seconds_bucket{destination=\"$dst\"}[$WINDOW])))")")
    p99=$(ms "$(pq "histogram_quantile(0.99, sum by (le) (rate(grpc_client_latency_seconds_bucket{destination=\"$dst\"}[$WINDOW])))")")
    mean=$(ms "$(pq "rate(grpc_client_latency_seconds_sum{destination=\"$dst\"}[$WINDOW])/rate(grpc_client_latency_seconds_count{destination=\"$dst\"}[$WINDOW])")")
    rps=$(pq "rate(grpc_client_latency_seconds_count{destination=\"$dst\"}[$WINDOW])")
    echo "$cyc,$arm,$addr,$dst,$p50,$p90,$p99,$mean,$rps" >> "$CSV"
    echo "  [$arm c$cyc] $dst p50=$p50 p90=$p90 p99=$p99 mean=$mean rps=$rps"
  done
}

run_arm() { # cycle arm manifest emailaddr
  local cyc=$1 arm=$2 manifest=$3 addr=$4
  echo "---- $(date -Is) cycle $cyc arm=$arm apply ----"
  kubectl apply -f "$manifest" -n $NS
  kubectl rollout status deploy/checkoutservice -n $NS --timeout=180s
  sleep 5
  kubectl delete job loadgenerator -n $NS --ignore-not-found
  sleep 2
  kubectl apply -f "$LOAD" -n $NS
  # wait completion (max 9min)
  for i in $(seq 1 108); do
    st=$(kubectl get pods -n $NS 2>/dev/null | grep loadgen | awk '{print $3}')
    [ "$st" = "Completed" ] && break
    [ "$st" = "Error" ] && { echo "  loadgen ERROR"; break; }
    sleep 5
  done
  echo "  $(date -Is) loadgen status=$st -> snapshot"
  snapshot "$cyc" "$arm" "$addr"
}

for c in $(seq 1 $CYCLES); do
  run_arm "$c" separated "$SEP"  "clusterip"
  run_arm "$c" colocated "$COLO" "localhost"
done

echo "================ DONE $(date -Is) ================"
cat "$CSV"
