#!/usr/bin/env bash
# ============================================================================
# HPA比較: 「同じ3サービス(frontend/reco/catalog, cart+redisは分離固定)をスケールさせる」を
#   束ね(front3: 1Pod同居, HPAは束ねPodのみ) vs 分離(normal: 4サービス個別HPA) で比較。
#   colocation以外(checkout/currency/payment/shipping/email/ad)は両arm固定1(HPAなし)。
#   各負荷(80/240/480 rate40)で softirq/req と スケール対象の総レプリカ数 を記録。
#   問い: HPAスケール下でも束ねが softirq/req を低く保つか。粒度(何Pod必要か)はどう違うか。
# prom_scalar はリトライ付き(前回=高負荷でタイムアウト全NAの再発防止)。promqも都度死活確認。
# 出力: km2/experiments/results-hpacompare.csv (arm, users, ..., scale_replicas, scale_detail)
# ============================================================================
set -u
NS=exp
REPO=/home/mizuki/ダウンロード/msa
SWEEP_USERS=${SWEEP_USERS:-"240 480"}
CYCLES=${CYCLES:-3}
LG_RATE=${LG_RATE:-40}
WARMUP=${WARMUP:-3m}
MEASURE=${MEASURE:-3m}
BASE_SETTLE=${BASE_SETTLE:-30}
BASE_WIN=${BASE_WIN:-2m}
HPA_TARGET=${HPA_TARGET:-70}
HPA_MIN=${HPA_MIN:-1}
HPA_MAX=${HPA_MAX:-4}
LOAD=$REPO/km2/experiments/loadgen-csv.yaml
LOADGEN=/tmp/loadgen-hpacmp.yaml
CSV=${CSV:-$REPO/km2/experiments/results-hpacompare.csv}
LOG=${LOG:-$REPO/km2/experiments/hpacompare.log}
ROLLOUT_TIMEOUT=300s
LOAD_WAIT_MAX=120
MARKER_POLL_MAX=${MARKER_POLL_MAX:-220}
PROM="http://prometheus-grafana-kube-pr-prometheus.monitoring.svc:9090"

NORMAL=(frontend checkoutservice cartservice productcatalogservice currencyservice \
        paymentservice shippingservice emailservice recommendationservice adservice)
# 束ね(front3)=frontend+reco+catalog の3ステートレスのみ。cart+redis は分離(別Pod,固定1,スケールなし)。
FRONT3_DEPLOYS=(frontend checkoutservice cartservice redis-cart currencyservice paymentservice emailservice shippingservice adservice)
# スケール対象(=束ねている3サービス)。normalでは個別、front3では frontend Pod に同居。
SCALE_NORMAL=(frontend recommendationservice productcatalogservice)
SCALE_FRONT3=(frontend)
LG_USERS=80

exec > >(tee -a "$LOG") 2>&1
echo "================ HPACOMPARE START $(date -Is) levels=[$SWEEP_USERS] rate=$LG_RATE warmup=$WARMUP measure=$MEASURE HPA=${HPA_TARGET}%/${HPA_MIN}-${HPA_MAX} ================"
echo "cycle,arm,users,reqcount,fails,p50_ms,p90_ms,p99_ms,avg_ms,rps,softirq_cores,base_softirq,app_cores,base_app,node_cores,base_node,softirq_mc_per_req,app_mc_per_req,node_mc_per_req,scale_replicas,scale_detail" > "$CSV"

ensure_promq() {
  [ "$(kubectl get pod promq -n "$NS" -o jsonpath='{.status.phase}' 2>/dev/null)" = "Running" ] && return
  kubectl delete pod promq -n "$NS" --ignore-not-found >/dev/null 2>&1
  kubectl run promq -n "$NS" --image=curlimages/curl:latest --restart=Never --command -- sleep 86400 >/dev/null 2>&1
  for i in $(seq 1 30); do [ "$(kubectl get pod promq -n "$NS" -o jsonpath='{.status.phase}' 2>/dev/null)" = "Running" ] && break; sleep 2; done
}
prom_scalar() { # リトライ付き
  local q="$1" out i
  for i in 1 2 3 4 5; do
    ensure_promq
    out=$(kubectl exec promq -n "$NS" -- curl -s --max-time 20 "$PROM/api/v1/query" --data-urlencode "query=$q" 2>/dev/null \
      | python3 -c "import sys,json;r=json.load(sys.stdin).get('data',{}).get('result',[]);print(r[0]['value'][1] if r else '')" 2>/dev/null)
    [ -n "$out" ] && { echo "$out"; return; }
    sleep 5
  done
  echo "NA"
}
scale_info() { # $@=deploys -> "総数|d1=n d2=n..."
  local t=0 r detail=""
  for d in "$@"; do r=$(kubectl get deploy "$d" -n "$NS" -o jsonpath='{.status.replicas}' 2>/dev/null); [ -n "$r" ] && t=$((t+r)); detail="$detail$d=$r "; done
  echo "$t|$detail"
}

deploy_normal() {
  echo "---- deploy NORMAL(分離) ----"
  kubectl delete hpa --all -n "$NS" >/dev/null 2>&1
  kubectl delete -f "$REPO/km2/all/all.yaml" -n "$NS" --ignore-not-found >/dev/null 2>&1
  for f in "${NORMAL[@]}"; do kubectl delete -f "$REPO/km2/$f.yaml" -n "$NS" --ignore-not-found >/dev/null 2>&1; done
  for i in $(seq 1 40); do [ -z "$(kubectl get deploy -n "$NS" -o name 2>/dev/null)" ] && break; sleep 3; done
  for f in "${NORMAL[@]}"; do kubectl apply -f "$REPO/km2/$f.yaml" -n "$NS" >/dev/null; done
  for d in "${NORMAL[@]}" redis-cart; do
    kubectl patch deploy/"$d" -n "$NS" --type=merge -p '{"spec":{"template":{"metadata":{"annotations":{"sidecar.istio.io/inject":"false"}}}}}' >/dev/null 2>&1 || true
  done
  for d in "${NORMAL[@]}" redis-cart; do kubectl rollout status deploy/"$d" -n "$NS" --timeout="$ROLLOUT_TIMEOUT" >/dev/null 2>&1 || true; done
  for d in "${SCALE_NORMAL[@]}"; do kubectl autoscale deploy/"$d" -n "$NS" --cpu-percent="$HPA_TARGET" --min="$HPA_MIN" --max="$HPA_MAX" >/dev/null 2>&1 || true; done
}
deploy_front3() {
  echo "---- deploy FRONT3(束ね=frontend+reco+catalog) ----"
  kubectl delete hpa --all -n "$NS" >/dev/null 2>&1
  kubectl delete -f "$REPO/km2/all/all.yaml" -n "$NS" --ignore-not-found >/dev/null 2>&1
  for f in "${NORMAL[@]}"; do kubectl delete -f "$REPO/km2/$f.yaml" -n "$NS" --ignore-not-found >/dev/null 2>&1; done
  for i in $(seq 1 40); do [ -z "$(kubectl get deploy -n "$NS" -o name 2>/dev/null)" ] && break; sleep 3; done
  for y in "$REPO"/km2/frontrecocatalogcart/*.yaml; do
    case "$y" in *kustomization.yaml|*loadgenerator.yaml) continue;; esac
    kubectl apply -f "$y" -n "$NS" >/dev/null
  done
  for d in "${FRONT3_DEPLOYS[@]}"; do
    kubectl patch deploy/"$d" -n "$NS" --type=merge -p '{"spec":{"template":{"metadata":{"annotations":{"sidecar.istio.io/inject":"false"}}}}}' >/dev/null 2>&1 || true
  done
  for d in "${FRONT3_DEPLOYS[@]}"; do kubectl rollout status deploy/"$d" -n "$NS" --timeout="$ROLLOUT_TIMEOUT" >/dev/null 2>&1 || true; done
  # yaml同梱HPAを消し、normalと同一ポリシで束ねPodのみに付け直す
  kubectl delete hpa --all -n "$NS" >/dev/null 2>&1
  for d in "${SCALE_FRONT3[@]}"; do kubectl autoscale deploy/"$d" -n "$NS" --cpu-percent="$HPA_TARGET" --min="$HPA_MIN" --max="$HPA_MAX" >/dev/null 2>&1 || true; done
}

measure_baseline() {
  echo "---- $(date -Is) 基線(ドレイン ${BASE_SETTLE}s + 窓 ${BASE_WIN}) ----"
  sleep "$BASE_SETTLE"
  local win_s=$BASE_WIN; case "$win_s" in *m) win_s=$(( ${win_s%m} * 60 ));; *s) win_s=${win_s%s};; esac
  sleep "$win_s"
  BASE_SOFTIRQ=$(prom_scalar "sum(rate(node_cpu_seconds_total{mode=\"softirq\"}[$BASE_WIN]))")
  BASE_APP=$(prom_scalar "sum(rate(container_cpu_usage_seconds_total{namespace=\"$NS\",container!=\"\",container!=\"POD\",pod!~\"loadgenerator.*\",pod!~\"promq.*\"}[$BASE_WIN]))")
  BASE_NODE=$(prom_scalar "sum(rate(node_cpu_seconds_total{mode!=\"idle\"}[$BASE_WIN]))")
  echo "  base: softirq=${BASE_SOFTIRQ} app=${BASE_APP} node=${BASE_NODE}"
}
gen_loadgen() {
  sed -E "s/(name: RUN_TIME, value: )\"[^\"]*\"/\1\"$1\"/; \
          s/(name: USERS,[[:space:]]*value: )\"[^\"]*\"/\1\"$LG_USERS\"/; \
          s/(name: RATE,[[:space:]]*value: )\"[^\"]*\"/\1\"$LG_RATE\"/" "$LOAD" > "$LOADGEN"
}
run_load() { # run_time capture arm scaleset...
  local rt=$1 capture=$2 arm=$3; shift 3; local SCALESET=("$@")
  local pod run logs i st
  local phase; [ "$capture" = "1" ] && phase="本計測" || phase="ウォームアップ"
  echo "---- $(date -Is) [$arm] users=$LG_USERS $phase (負荷 $rt) ----"
  gen_loadgen "$rt"
  kubectl delete job loadgenerator -n "$NS" --ignore-not-found --wait=true
  for i in $(seq 1 24); do [ -z "$(kubectl get pods -n "$NS" -l job-name=loadgenerator -o jsonpath='{.items[*].metadata.name}' 2>/dev/null)" ] && break; sleep 2; done
  kubectl apply -f "$LOADGEN" -n "$NS"
  pod=""; run=""
  for i in $(seq 1 $LOAD_WAIT_MAX); do
    pod=$(kubectl get pods -n "$NS" -l job-name=loadgenerator --sort-by=.metadata.creationTimestamp -o jsonpath='{.items[-1].metadata.name}' 2>/dev/null)
    [ -n "$pod" ] || { sleep 5; continue; }
    run=$(kubectl get pod "$pod" -n "$NS" -o jsonpath='{.status.containerStatuses[?(@.name=="main")].state.running.startedAt}' 2>/dev/null)
    [ -n "$run" ] && break
    st=$(kubectl get pod "$pod" -n "$NS" -o jsonpath='{.status.phase}' 2>/dev/null)
    { [ "$st" = "Succeeded" ] || [ "$st" = "Failed" ]; } && break
    sleep 5
  done
  logs=""
  for i in $(seq 1 $MARKER_POLL_MAX); do
    logs=$(kubectl logs "$pod" -n "$NS" -c main --tail=-1 2>/dev/null)
    echo "$logs" | grep -q '@@@CSV_END@@@' && { echo "  $(date -Is) 負荷完了(試行 $i)"; break; }
    st=$(kubectl get pod "$pod" -n "$NS" -o jsonpath='{.status.phase}' 2>/dev/null)
    [ "$st" = "Failed" ] && { echo "  loadgen FAILED"; break; }
    sleep 5
  done
  if [ "$capture" = "1" ]; then
    softirq_cores=$(prom_scalar "sum(rate(node_cpu_seconds_total{mode=\"softirq\"}[$rt]))")
    app_cores=$(prom_scalar "sum(rate(container_cpu_usage_seconds_total{namespace=\"$NS\",container!=\"\",container!=\"POD\",pod!~\"loadgenerator.*\",pod!~\"promq.*\"}[$rt]))")
    node_cores=$(prom_scalar "sum(rate(node_cpu_seconds_total{mode!=\"idle\"}[$rt]))")
    SI=$(scale_info "${SCALESET[@]}"); SREPS=${SI%%|*}; SDET=${SI#*|}
    echo "  $(date -Is) CPU: softirq=${softirq_cores} app=${app_cores} node=${node_cores} | scale_replicas=${SREPS} [${SDET}]"
  fi
  kubectl delete job loadgenerator -n "$NS" --ignore-not-found >/dev/null 2>&1
  [ "$capture" != "1" ] && { echo "  ウォームアップ完了(捨て)"; return; }
  local logfile="$REPO/km2/experiments/last-logs-hpacmp.txt"
  printf '%s\n' "$logs" > "$logfile"
  python3 - "${CYC:-1}" "$arm" "$LG_USERS" "$CSV" "$logfile" \
           "$softirq_cores" "${BASE_SOFTIRQ:-NA}" "$app_cores" "${BASE_APP:-NA}" "$node_cores" "${BASE_NODE:-NA}" \
           "$SREPS" "$SDET" <<'PY'
import sys,csv,io
cyc,arm,users,out,logfile,sc,bsi,ac,ba,nc,bn,sreps,sdet=sys.argv[1:14]
data=open(logfile,encoding='utf-8',errors='replace').read()
b,e="@@@CSV_BEGIN@@@","@@@CSV_END@@@"
def fnum(x):
    try: return float(x)
    except: return None
if b in data and e in data:
    block=data.split(b,1)[1].split(e,1)[0].strip()
    rows=list(csv.reader(io.StringIO(block))); hdr=rows[0]
    def idx(n): return hdr.index(n) if n in hdr else None
    agg=[r for r in rows[1:] if len(r)>1 and r[1]=="Aggregated"]
    if agg:
        r=agg[0]
        def g(n,d="NA"):
            i=idx(n); return r[i] if i is not None and i<len(r) else d
        rps=fnum(g("Requests/s"))
        def mc(load,base):
            l=fnum(load); bb=fnum(base)
            return round((l-bb)/rps*1000,3) if (l is not None and bb is not None and rps) else "NA"
        rec=[cyc,arm,users,g("Request Count"),g("Failure Count"),g("50%"),g("90%"),g("99%"),
             g("Average Response Time"),g("Requests/s"),
             sc,bsi,ac,ba,nc,bn,mc(sc,bsi),mc(ac,ba),mc(nc,bn),sreps,sdet.strip()]
        with open(out,"a",newline="") as f: csv.writer(f).writerow(rec)
        print("  -> 記録:", "cyc"+cyc, arm, "users",users, "softirq/req",mc(sc,bsi), "scale_reps",sreps)
    else: print("  !! Aggregated行なし")
else: print("  !! CSVマーカー無し")
PY
}

ensure_promq
for CYC in $(seq 1 "$CYCLES"); do
for ARM in front3 normal; do
  echo "################ CYCLE $CYC/$CYCLES ARM=$ARM $(date -Is) ################"
  # 毎回デプロイし直す=レプリカを1にリセット(前サイクルのスケールアップ残りを持ち越さない)
  if [ "$ARM" = front3 ]; then deploy_front3; SCALESET=("${SCALE_FRONT3[@]}"); else deploy_normal; SCALESET=("${SCALE_NORMAL[@]}"); fi
  sleep 15; echo "  HPA: $(kubectl get hpa -n "$NS" --no-headers 2>/dev/null | awk '{print $1"("$6")"}' | tr '\n' ' ')"
  for U in $SWEEP_USERS; do
    LG_USERS=$U
    echo "======== [cyc$CYC $ARM] USERS=$U $(date -Is) ========"
    run_load "$WARMUP" 0 "$ARM" "${SCALESET[@]}"
    measure_baseline
    run_load "$MEASURE" 1 "$ARM" "${SCALESET[@]}"
  done
done
done

kubectl delete hpa --all -n "$NS" >/dev/null 2>&1
kubectl delete pod promq -n "$NS" --ignore-not-found >/dev/null 2>&1
echo "================ HPACOMPARE DONE $(date -Is) ================"
column -s, -t "$CSV" 2>/dev/null || cat "$CSV"
