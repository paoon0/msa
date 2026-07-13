#!/usr/bin/env bash
# ============================================================================
# ボトルネック特定: 束ね(f3perc)を u480 で回し、負荷中に全コンテナの
#   CPU使用量(mc) / CPU制限(mc) / 利用率(usage/limit) / スロットリング率 を採取。
#   スロットリング率(=CPU制限に当たって待たされたCFS周期の割合)が高い＝そのサービスが律速。
#   スケール対象(frontend/reco/catalog)は52%で余裕・ノードも空き→固定1レプリカのどれが詰まるかを暴く。
# 出力: km2/experiments/bottleneck-diag.txt (ランキング表)
# ============================================================================
set -u
NS=exp
REPO=/home/mizuki/ダウンロード/msa
USERS=${USERS:-480}
RATE=${RATE:-40}
WARMUP=${WARMUP:-3m}
MEASURE=${MEASURE:-3m}
LOAD=$REPO/km2/experiments/loadgen-csv.yaml
LOADGEN=/tmp/loadgen-diag.yaml
PC_HPA=$REPO/km2/frontrecocatalogcart/hpa-percontainer.yaml
OUT=$REPO/km2/experiments/bottleneck-diag.txt
PROM="http://prometheus-grafana-kube-pr-prometheus.monitoring.svc:9090"
ROLLOUT_TIMEOUT=300s
NORMAL=(frontend checkoutservice cartservice productcatalogservice currencyservice \
        paymentservice shippingservice emailservice recommendationservice adservice)
FRONT3_DEPLOYS=(frontend checkoutservice cartservice redis-cart currencyservice paymentservice emailservice shippingservice adservice)

exec > >(tee -a "${OUT%.txt}.log") 2>&1
echo "================ BOTTLENECK-DIAG START $(date -Is) users=$USERS ================"

ensure_promq() {
  [ "$(kubectl get pod promq -n "$NS" -o jsonpath='{.status.phase}' 2>/dev/null)" = "Running" ] && return
  kubectl delete pod promq -n "$NS" --ignore-not-found >/dev/null 2>&1
  kubectl run promq -n "$NS" --image=curlimages/curl:latest --restart=Never --command -- sleep 86400 >/dev/null 2>&1
  for i in $(seq 1 30); do [ "$(kubectl get pod promq -n "$NS" -o jsonpath='{.status.phase}' 2>/dev/null)" = "Running" ] && break; sleep 2; done
}
prom_vec() { # $1=query -> "container<TAB>value" 行(リトライ付き)
  local q="$1" out i
  for i in 1 2 3 4 5; do
    ensure_promq
    out=$(kubectl exec promq -n "$NS" -- curl -s --max-time 25 "$PROM/api/v1/query" --data-urlencode "query=$q" 2>/dev/null \
      | python3 -c "
import sys,json
try: r=json.load(sys.stdin).get('data',{}).get('result',[])
except: r=[]
for x in r:
    c=x['metric'].get('container','?'); print(c+'\t'+x['value'][1])
" 2>/dev/null)
    [ -n "$out" ] && { echo "$out"; return; }
    sleep 5
  done
  echo ""
}

# ---- deploy 束ね f3perc ----
echo "---- deploy f3perc(束ね) ----"
kubectl delete hpa --all -n "$NS" >/dev/null 2>&1
kubectl delete -f "$REPO/km2/all/all.yaml" -n "$NS" --ignore-not-found >/dev/null 2>&1
for f in "${NORMAL[@]}"; do kubectl delete -f "$REPO/km2/$f.yaml" -n "$NS" --ignore-not-found >/dev/null 2>&1; done
for i in $(seq 1 40); do [ -z "$(kubectl get deploy -n "$NS" -o name 2>/dev/null)" ] && break; sleep 3; done
for y in "$REPO"/km2/frontrecocatalogcart/*.yaml; do
  case "$y" in *kustomization.yaml|*loadgenerator.yaml|*hpa-percontainer.yaml) continue;; esac
  kubectl apply -f "$y" -n "$NS" >/dev/null
done
for d in "${FRONT3_DEPLOYS[@]}"; do kubectl patch deploy/"$d" -n "$NS" --type=merge -p '{"spec":{"template":{"metadata":{"annotations":{"sidecar.istio.io/inject":"false"}}}}}' >/dev/null 2>&1 || true; done
for d in "${FRONT3_DEPLOYS[@]}"; do kubectl rollout status deploy/"$d" -n "$NS" --timeout="$ROLLOUT_TIMEOUT" >/dev/null 2>&1 || true; done
kubectl delete hpa --all -n "$NS" >/dev/null 2>&1
kubectl apply -f "$PC_HPA" -n "$NS" >/dev/null

ensure_promq
# ---- 負荷(warmup+measure を連続で。合計で採取窓を確保) ----
sed -E "s/(name: RUN_TIME, value: )\"[^\"]*\"/\1\"$WARMUP\"/; s/(name: USERS,[[:space:]]*value: )\"[^\"]*\"/\1\"$USERS\"/; s/(name: RATE,[[:space:]]*value: )\"[^\"]*\"/\1\"$RATE\"/" "$LOAD" > "$LOADGEN"
run_one() { # $1=runtime
  local rt=$1 pod i st logs
  sed -E "s/(name: RUN_TIME, value: )\"[^\"]*\"/\1\"$rt\"/" "$LOADGEN" > "$LOADGEN.tmp" && mv "$LOADGEN.tmp" "$LOADGEN"
  kubectl delete job loadgenerator -n "$NS" --ignore-not-found --wait=true >/dev/null 2>&1
  for i in $(seq 1 24); do [ -z "$(kubectl get pods -n "$NS" -l job-name=loadgenerator -o name 2>/dev/null)" ] && break; sleep 2; done
  kubectl apply -f "$LOADGEN" -n "$NS" >/dev/null
  pod=""
  for i in $(seq 1 220); do
    pod=$(kubectl get pods -n "$NS" -l job-name=loadgenerator --sort-by=.metadata.creationTimestamp -o jsonpath='{.items[-1].metadata.name}' 2>/dev/null)
    [ -n "$pod" ] || { sleep 5; continue; }
    logs=$(kubectl logs "$pod" -n "$NS" -c main --tail=-1 2>/dev/null)
    echo "$logs" | grep -q '@@@CSV_END@@@' && { echo "  $(date -Is) 負荷完了"; break; }
    st=$(kubectl get pod "$pod" -n "$NS" -o jsonpath='{.status.phase}' 2>/dev/null)
    [ "$st" = "Failed" ] && { echo "  loadgen FAILED"; break; }
    sleep 5
  done
}
echo "---- $(date -Is) ウォームアップ $WARMUP (users=$USERS) ----"
run_one "$WARMUP"
echo "---- $(date -Is) 本計測 $MEASURE (この窓で採取) ----"
kubectl delete job loadgenerator -n "$NS" --ignore-not-found --wait=true >/dev/null 2>&1
sed -E "s/(name: RUN_TIME, value: )\"[^\"]*\"/\1\"$MEASURE\"/" "$LOADGEN" > "$LOADGEN.tmp" && mv "$LOADGEN.tmp" "$LOADGEN"
kubectl apply -f "$LOADGEN" -n "$NS" >/dev/null
# measure窓の中盤〜終盤(=定常)で採取。窓長の8割ほど待つ。
win=$MEASURE; case "$win" in *m) win=$(( ${win%m}*60 ));; *s) win=${win%s};; esac
sleep $(( win*8/10 ))

echo "---- $(date -Is) Prometheus採取 ----"
USE=$(prom_vec "sum by(container)(rate(container_cpu_usage_seconds_total{namespace=\"$NS\",container!=\"\",container!=\"POD\",pod!~\"loadgenerator.*\",pod!~\"promq.*\"}[2m]))")
THN=$(prom_vec "sum by(container)(rate(container_cpu_cfs_throttled_periods_total{namespace=\"$NS\"}[2m]))")
THD=$(prom_vec "sum by(container)(rate(container_cpu_cfs_periods_total{namespace=\"$NS\"}[2m]))")
LIM=$(prom_vec "max by(container)(kube_pod_container_resource_limits{namespace=\"$NS\",resource=\"cpu\"})")
REQ=$(prom_vec "max by(container)(kube_pod_container_resource_requests{namespace=\"$NS\",resource=\"cpu\"})")
RPS_LINE=$(kubectl logs -n "$NS" -l job-name=loadgenerator -c main --tail=-1 2>/dev/null | grep -A3 '@@@CSV_BEGIN@@@' | grep Aggregated | head -1)

python3 - "$USE" "$THN" "$THD" "$LIM" "$REQ" <<'PY'
import sys
def d(s):
    m={}
    for ln in s.strip().splitlines():
        if '\t' in ln:
            k,v=ln.split('\t',1)
            try:m[k]=float(v)
            except:pass
    return m
use,thn,thd,lim,req=[d(a) for a in sys.argv[1:6]]
rows=[]
for c in sorted(set(list(use)+list(lim))):
    u=use.get(c,0)*1000            # mc
    l=lim.get(c,0)*1000; r=req.get(c,0)*1000
    thr=(thn.get(c,0)/thd[c]*100) if thd.get(c,0) else 0
    ulim=(u/l*100) if l else 0
    ureq=(u/r*100) if r else 0
    rows.append((thr,ulim,c,u,l,r,ureq))
rows.sort(reverse=True)
print("\n%-22s %8s %8s %8s %8s %10s"%("container","use_mc","limit_mc","%oflim","%ofreq","throttle%"))
print("-"*74)
for thr,ulim,c,u,l,r,ureq in rows:
    print("%-22s %8.0f %8.0f %7.0f%% %7.0f%% %9.1f%%"%(c,u,l,ulim,ureq,thr))
print("\n※ throttle% が高い or %oflim が100%近い = そのサービスがCPU制限に張り付く=律速候補")
PY
echo "---- loadgen Aggregated ----"; echo "$RPS_LINE"
kubectl delete job loadgenerator -n "$NS" --ignore-not-found >/dev/null 2>&1
kubectl delete hpa --all -n "$NS" >/dev/null 2>&1
echo "================ BOTTLENECK-DIAG DONE $(date -Is) ================"
