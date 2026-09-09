#!/usr/bin/env bash
# 既に netprobe が入っている Pod に対して、計測だけを実行する(デプロイと追加を飛ばす)。
set -u
NS=exp; REPO=/home/mizuki/ダウンロード/msa; DIR=$REPO/km2/experiments; K6DIR=$DIR/k6
CASES=${CASES:-"100:0 0:200"}; WARM=${WARM:-30}; MEAS=${MEAS:-180}
PRE_VUS=${PRE_VUS:-300}; MAX_VUS=${MAX_VUS:-3000}
CSV=${CSV:-$DIR/results-edge-pairs.csv}; LOG=${LOG:-$DIR/edge-pairs.log}; WORK=${WORK:-/tmp/edge-pairs}
mkdir -p "$WORK"; exec > >(tee -a "$LOG") 2>&1
echo "================ EDGE-PAIRS(計測のみ)START $(date -Is) cases=[$CASES] ================"
[ -s "$CSV" ] || echo "case,src,dst,bytes_sent,bytes_received,segs_out,segs_in,rtt_ms,minrtt_ms,conns" > "$CSV"
PODS=($(kubectl get pods -n $NS -o jsonpath='{range .items[*]}{.metadata.name}{"\n"}{end}' | grep -Ev 'k6load|promq'))
echo "対象Pod ${#PODS[@]}個"
: > "$WORK/ipmap.txt"
kubectl get pods -n $NS -o jsonpath='{range .items[*]}{.status.podIP}{" "}{.metadata.labels.app}{"\n"}{end}' | grep -v '^ ' >> "$WORK/ipmap.txt"
kubectl get svc  -n $NS -o jsonpath='{range .items[*]}{.spec.clusterIP}{" "}{.metadata.name}{"\n"}{end}' | grep -v '^None' >> "$WORK/ipmap.txt"
echo "IP対応表 $(wc -l < "$WORK/ipmap.txt") 件"
snap(){ local out=$1; : > "$out"
  for p in "${PODS[@]}"; do echo "### $p" >> "$out"
    kubectl exec -n $NS "$p" -c netprobe -- ss -tin state established 2>/dev/null | cat >> "$out" || true; done
  echo "  → $(grep -c bytes_sent "$out") 接続"; }
for cs in $CASES; do
  rate=${cs%%:*}; brw=${cs##*:}; label="購入${rate}_閲覧${brw}"
  echo "==== $label $(date -Is) ===="
  kubectl create configmap k6-script -n $NS --from-file=checkout.js=$K6DIR/checkout.js --dry-run=client -o yaml | kubectl apply -f - >/dev/null 2>&1
  kubectl delete job k6load -n $NS --ignore-not-found --wait=true >/dev/null 2>&1
  sed -e "s/__RATE__/$rate/" -e "s/__BROWSE__/$brw/" -e "s/__WARM__/$WARM/" -e "s/__MEAS__/$MEAS/" \
      -e "s/__PRE__/$PRE_VUS/" -e "s/__MAX__/$MAX_VUS/" "$K6DIR/k6-job.yaml" | kubectl apply -f - -n $NS >/dev/null
  for i in $(seq 1 40);do pod=$(kubectl get pods -n $NS -l app=k6load --sort-by=.metadata.creationTimestamp -o jsonpath='{.items[-1].metadata.name}' 2>/dev/null)
    [ -n "$pod" ]&&[ "$(kubectl get pod $pod -n $NS -o jsonpath='{.status.phase}' 2>/dev/null)" = Running ]&&break; sleep 3;done
  sleep $WARM; echo "  スナップショットA"; snap "$WORK/A-$label.txt"
  sleep $MEAS; echo "  スナップショットB"; snap "$WORK/B-$label.txt"
  python3 "$DIR/edge_pairs.py" "$WORK/A-$label.txt" "$WORK/B-$label.txt" "$WORK/ipmap.txt" "$CSV" "$MEAS" "$label"
done
kubectl delete job k6load -n $NS --ignore-not-found >/dev/null 2>&1
echo "================ DONE $(date -Is) ================"
