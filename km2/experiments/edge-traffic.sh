#!/usr/bin/env bash
# サービス間の通信量を Pod 単位のネットワークカウンタで実測する(2026-09-08 作成)。
#
# 何のためか:
#   これまで「エッジの太さ」は softirq の削減量から間接的に推定していた。
#   ここでは cAdvisor の container_network_{receive,transmit}_{bytes,packets}_total を
#   Pod 単位で読み、呼び出しグラフと突き合わせてエッジごとのバイト数/パケット数を出す。
#
# 測り方の約束:
#   * 台数は全サービス1台に固定・HPA は作らない  → Pod のカウンタ = そのサービスの総通信量
#   * 枠(requests/limits)はマニフェストのまま    → 通信量は枠に依存しないので触る必要がない
#   * 分離(normal)で測る                          → 全エッジがネットワークを通る
#   * 「購入型のみ」と「閲覧型のみ」を別々に流す  → 呼ばれるエッジの集合が変わるので連立できる
#       - 閲覧型(GET /product/x)は checkout/email/payment/shipping を一切呼ばない
#       - よってそれらの Pod がゼロになることが、測定が効いていることの確認にもなる
#
# 出力: results-edge-traffic.csv
#   cycle,arm,rate,browse,iter_rate,browse_rate,pod,rx_bytes,tx_bytes,rx_pkts,tx_pkts
set -u
NS=exp
REPO=/home/mizuki/ダウンロード/msa
DIR=$REPO/km2/experiments
K6DIR=$DIR/k6
ARM=${ARM:-normal}
CASES=${CASES:-"100:0 0:100 0:200"}    # 「購入:閲覧」の組。周/秒
WARM=${WARM:-30}
MEAS=${MEAS:-180}
PRE_VUS=${PRE_VUS:-300}
MAX_VUS=${MAX_VUS:-3000}
CYCLES=${CYCLES:-1}
CSV=${CSV:-$DIR/results-edge-traffic.csv}
LOG=${LOG:-$DIR/edge-traffic.log}
PROM="http://prometheus-grafana-kube-pr-prometheus.monitoring.svc:9090"
NORMAL=(frontend checkoutservice cartservice productcatalogservice currencyservice \
        paymentservice shippingservice emailservice recommendationservice adservice)

exec > >(tee -a "$LOG") 2>&1
echo "================ EDGE-TRAFFIC START $(date -Is) arm=$ARM cases=[$CASES] cycles=$CYCLES warm=${WARM}s meas=${MEAS}s (1台固定/HPA無し/枠はマニフェストのまま) ================"
[ -s "$CSV" ] || echo "cycle,arm,rate,browse,iter_rate,browse_rate,pod,rx_bytes,tx_bytes,rx_pkts,tx_pkts" > "$CSV"

ensure_promq(){ [ "$(kubectl get pod promq -n $NS -o jsonpath='{.status.phase}' 2>/dev/null)" = Running ] && return
  kubectl delete pod promq -n $NS --ignore-not-found >/dev/null 2>&1
  kubectl run promq -n $NS --image=curlimages/curl:latest --restart=Never --command -- sleep 86400 >/dev/null 2>&1
  for i in $(seq 1 30);do [ "$(kubectl get pod promq -n $NS -o jsonpath='{.status.phase}' 2>/dev/null)" = Running ]&&break;sleep 2;done; }
promq(){ local q="$1" i out; for i in 1 2 3 4 5;do ensure_promq
  out=$(kubectl exec promq -n $NS -- curl -s --max-time 25 "$PROM/api/v1/query" --data-urlencode "query=$q" 2>/dev/null)
  [ -n "$out" ]&&{ echo "$out"; return; }; sleep 4; done; echo ""; }

deploy(){
  echo "---- deploy $ARM (1台固定, HPA無し, 枠はマニフェストのまま) ----"
  kubectl delete hpa --all -n $NS >/dev/null 2>&1
  kubectl delete deploy --all -n $NS >/dev/null 2>&1
  for i in $(seq 1 40);do [ -z "$(kubectl get deploy -n $NS -o name 2>/dev/null)" ]&&break;sleep 3;done
  for f in "${NORMAL[@]}"; do kubectl apply -f $REPO/km2/normal/$f.yaml -n $NS >/dev/null; done
  kubectl apply -f $REPO/km2/normal/redis-cart.yaml -n $NS >/dev/null 2>&1 || true
  for d in $(kubectl get deploy -n $NS -o jsonpath='{range .items[*]}{.metadata.name}{" "}{end}'); do
    kubectl patch deploy/$d -n $NS --type=merge -p '{"spec":{"template":{"metadata":{"annotations":{"sidecar.istio.io/inject":"false"}}}}}' >/dev/null 2>&1||true
    kubectl scale deploy/$d -n $NS --replicas=1 >/dev/null 2>&1||true
  done
  for d in $(kubectl get deploy -n $NS -o jsonpath='{range .items[*]}{.metadata.name}{" "}{end}'); do
    kubectl rollout status deploy/$d -n $NS --timeout=300s >/dev/null 2>&1||echo "  !! rollout 未完了: $d"; done
  kubectl get deploy -n $NS --no-headers | awk '{printf "  %s=%s ",$1,$2}'; echo
}

run_case(){ local rate=$1 brw=$2 cyc=$3
  echo "==== [cyc$cyc] 購入=${rate}周/秒 閲覧=${brw}周/秒 $(date -Is) ===="
  kubectl create configmap k6-script -n $NS --from-file=checkout.js=$K6DIR/checkout.js --dry-run=client -o yaml | kubectl apply -f - >/dev/null 2>&1
  kubectl delete job k6load -n $NS --ignore-not-found --wait=true >/dev/null 2>&1
  sed -e "s/__RATE__/$rate/" -e "s/__BROWSE__/$brw/" -e "s/__WARM__/$WARM/" -e "s/__MEAS__/$MEAS/" \
      -e "s/__PRE__/$PRE_VUS/" -e "s/__MAX__/$MAX_VUS/" "$K6DIR/k6-job.yaml" | kubectl apply -f - -n $NS >/dev/null
  local pod=""
  for i in $(seq 1 40);do pod=$(kubectl get pods -n $NS -l app=k6load --sort-by=.metadata.creationTimestamp -o jsonpath='{.items[-1].metadata.name}' 2>/dev/null)
    [ -n "$pod" ]&&[ "$(kubectl get pod $pod -n $NS -o jsonpath='{.status.phase}' 2>/dev/null)" = Running ]&&break; sleep 3;done
  sleep $((WARM + MEAS))
  # 計測窓ぴったりのバイト数/パケット数。increase なら「この窓で流れた量」そのもの。
  local F="namespace=\"$NS\",pod!~\"k6load.*|promq.*\""
  RX=$(promq "sum by(pod)(increase(container_network_receive_bytes_total{$F}[${MEAS}s]))")
  TX=$(promq "sum by(pod)(increase(container_network_transmit_bytes_total{$F}[${MEAS}s]))")
  RP=$(promq "sum by(pod)(increase(container_network_receive_packets_total{$F}[${MEAS}s]))")
  TP=$(promq "sum by(pod)(increase(container_network_transmit_packets_total{$F}[${MEAS}s]))")
  local done_at=$(( $(date +%s) + 25 ))
  while [ "$(date +%s)" -lt "$done_at" ]; do sleep 5; done
  local logs summary
  logs=$(kubectl logs job/k6load -n $NS --tail=400 2>/dev/null)
  summary=$(printf '%s\n' "$logs" | sed -n '/@@@K6_BEGIN@@@/,/@@@K6_END@@@/p' | grep '{')
  [ -z "$summary" ] && echo "  !! summary回収失敗"
  SUMMARY="$summary" RX="$RX" TX="$TX" RP="$RP" TP="$TP" \
    python3 "$DIR/edge_traffic_row.py" "$ARM" "$CSV" "$cyc" "$rate" "$brw" "$MEAS"
}

ensure_promq
deploy
for c in $(seq 1 $CYCLES); do
  echo "################ CYCLE $c / $CYCLES $(date -Is) ################"
  for cs in $CASES; do run_case "${cs%%:*}" "${cs##*:}" "$c"; done
done
kubectl delete job k6load -n $NS --ignore-not-found >/dev/null 2>&1
echo "================ EDGE-TRAFFIC DONE $(date -Is) ================"
