#!/usr/bin/env bash
# ============================================================================
# 基線ドリフト診断: 「冷えた直後の基線」vs「5分温めた後の基線」を測り、
# normal と mega で温め後の基線が揃うか(=ドリフト解消か)を確認する。
# 本走はしない。compare.sh の基線タイミング修正を入れる前の検証用。
# 出力: km2/experiments/baseline-probe.csv  列: arm,phase,node_cores,app_cores
# ============================================================================
set -u
NS=exp
REPO=/home/mizuki/ダウンロード/msa
ALL=$REPO/km2/all/all.yaml
LOAD=$REPO/km2/experiments/loadgen-csv.yaml
LOADGEN=/tmp/loadgen-probe.yaml
WARM=${WARM:-5m}        # 温め負荷の長さ
SETTLE=${SETTLE:-30}    # 負荷ドレイン待ち(秒)
WIN=${WIN:-2m}          # 基線 rate 窓
OUT=$REPO/km2/experiments/baseline-probe.csv
LOG=$REPO/km2/experiments/baseline-probe.log
PROM="http://prometheus-grafana-kube-pr-prometheus.monitoring.svc:9090"
NORMAL=(frontend checkoutservice cartservice productcatalogservice currencyservice \
        paymentservice shippingservice emailservice recommendationservice adservice)
NORMAL_DEPLOYS=(frontend checkoutservice cartservice redis-cart productcatalogservice \
        currencyservice paymentservice shippingservice emailservice recommendationservice adservice)
ISTIO_SVCS=(checkoutservice paymentservice emailservice)

exec > >(tee -a "$LOG") 2>&1
echo "================ PROBE START $(date -Is) warm=$WARM win=$WIN ================"
echo "arm,phase,node_cores,app_cores" > "$OUT"

kubectl delete pod promq -n "$NS" --ignore-not-found >/dev/null 2>&1
kubectl run promq -n "$NS" --image=curlimages/curl:latest --restart=Never --command -- sleep 86400 >/dev/null 2>&1
for i in $(seq 1 30); do [ "$(kubectl get pod promq -n "$NS" -o jsonpath='{.status.phase}' 2>/dev/null)" = "Running" ] && break; sleep 2; done

prom_scalar() {
  kubectl exec promq -n "$NS" -- curl -s "$PROM/api/v1/query" --data-urlencode "query=$1" 2>/dev/null \
    | python3 -c "import sys,json;r=json.load(sys.stdin).get('data',{}).get('result',[]);print(r[0]['value'][1] if r else 'NA')" 2>/dev/null
}

measure() { # arm phase  -> 無負荷の基線を測って記録(呼ぶ前に負荷は無いこと)
  local arm=$1 phase=$2
  sleep "$SETTLE"
  local win_s=$WIN; case "$win_s" in *m) win_s=$(( ${win_s%m} * 60 ));; *s) win_s=${win_s%s};; esac
  sleep "$win_s"
  local nc ac
  nc=$(prom_scalar "sum(rate(node_cpu_seconds_total{mode!=\"idle\"}[$WIN]))")
  ac=$(prom_scalar "sum(rate(container_cpu_usage_seconds_total{namespace=\"$NS\",container!=\"\",container!=\"POD\",pod!~\"loadgenerator.*\",pod!~\"promq.*\"}[$WIN]))")
  echo "  $(date -Is) [$arm/$phase] base node=$nc app=$ac cores"
  echo "$arm,$phase,$nc,$ac" >> "$OUT"
}

warm_load() { # 温め負荷を WARM 分かけて終わったら消す
  sed -E "s/(name: RUN_TIME, value: )\"[^\"]*\"/\1\"$WARM\"/" "$LOAD" > "$LOADGEN"
  kubectl delete job loadgenerator -n "$NS" --ignore-not-found --wait=true >/dev/null 2>&1
  for i in $(seq 1 24); do [ -z "$(kubectl get pods -n "$NS" -l job-name=loadgenerator -o jsonpath='{.items[*].metadata.name}' 2>/dev/null)" ] && break; sleep 2; done
  echo "  $(date -Is) 温め負荷 $WARM 開始"
  kubectl apply -f "$LOADGEN" -n "$NS" >/dev/null
  local pod="" i
  for i in $(seq 1 120); do
    pod=$(kubectl get pods -n "$NS" -l job-name=loadgenerator --sort-by=.metadata.creationTimestamp -o jsonpath='{.items[-1].metadata.name}' 2>/dev/null)
    [ -n "$pod" ] && break; sleep 5
  done
  for i in $(seq 1 200); do
    kubectl logs "$pod" -n "$NS" -c main --tail=-1 2>/dev/null | grep -q '@@@CSV_END@@@' && { echo "  $(date -Is) 温め完了"; break; }
    [ "$(kubectl get pod "$pod" -n "$NS" -o jsonpath='{.status.phase}' 2>/dev/null)" = "Failed" ] && { echo "  温め負荷FAILED"; break; }
    sleep 5
  done
  kubectl delete job loadgenerator -n "$NS" --ignore-not-found --wait=true >/dev/null 2>&1
}

# ---- mega: 既にデプロイ済み&8分Running=温まっている想定。温まった基線を測る ----
if kubectl get pod -n "$NS" -l app=megapod -o name 2>/dev/null | grep -q pod; then
  echo "---- mega は既稼働。温まった基線を測定 ----"
  measure mega warm
else
  echo "---- mega 未稼働。デプロイ→温め→測定 ----"
  for f in "${NORMAL[@]}"; do kubectl delete -f "$REPO/km2/$f.yaml" -n "$NS" --ignore-not-found >/dev/null 2>&1; done
  kubectl apply -f "$ALL" -n "$NS" >/dev/null
  kubectl rollout status deploy/megapod -n "$NS" --timeout=300s || true
  measure mega cold
  warm_load
  measure mega warm
fi

# ---- normal: デプロイ→冷えた基線→5分温め→温まった基線 ----
echo "---- normal デプロイ(分離・Istio無し) ----"
kubectl delete -f "$ALL" -n "$NS" --ignore-not-found >/dev/null 2>&1
for f in "${NORMAL[@]}"; do kubectl apply -f "$REPO/km2/$f.yaml" -n "$NS" >/dev/null; done
for d in "${ISTIO_SVCS[@]}"; do
  kubectl patch deploy/"$d" -n "$NS" --type=merge \
    -p '{"spec":{"template":{"metadata":{"annotations":{"sidecar.istio.io/inject":"false"}}}}}' >/dev/null 2>&1 || true
done
for d in "${NORMAL_DEPLOYS[@]}"; do kubectl rollout status deploy/"$d" -n "$NS" --timeout=300s || true; done
echo "---- normal 冷えた直後の基線 ----"
measure normal cold
echo "---- normal 5分温め ----"
warm_load
echo "---- normal 温まった基線 ----"
measure normal warm

kubectl delete pod promq -n "$NS" --ignore-not-found >/dev/null 2>&1
echo "================ PROBE DONE $(date -Is) ================"
column -s, -t "$OUT"
