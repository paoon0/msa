#!/usr/bin/env bash
# ============================================================================
# 「HPA 利用時に softirq がどうなるか」の第一歩:
#   normal(分離)構成で 全アプリ Deployment を 1→2→3 レプリカにスイープし、softirq/req を測る。
#   =HPA がやること(レプリカ増)を手動で制御し、softirq がレプリカ数でどう動くかを観察。
#   予想: 総パケットは同(同リクエスト)だが、エンドポイント/コネクション/conntrack が増える
#         → softirq/req 横ばい〜微増 のどちらか。
# 負荷は固定 USERS=80 RATE=1(rps≈208)、他条件は本走に一致(WARMUP3m/MEASURE5m, 基線settle30s/窓2m)。
# redis-cart はステートフルなので 1 のまま(スケールしない)。
# 出力: km2/experiments/results-replicasweep.csv (列頭 replicas)
# ============================================================================
set -u
NS=exp
REPO=/home/mizuki/ダウンロード/msa
LG_USERS=${LG_USERS:-80}
LG_RATE=${LG_RATE:-1}
WARMUP=${WARMUP:-3m}
MEASURE=${MEASURE:-5m}
BASE_SETTLE=${BASE_SETTLE:-30}
BASE_WIN=${BASE_WIN:-2m}
REPLICAS_LIST=${REPLICAS_LIST:-"1 2 3"}
LOAD=$REPO/km2/experiments/loadgen-csv.yaml
LOADGEN=/tmp/loadgen-replicasweep.yaml
CSV=${CSV:-$REPO/km2/experiments/results-replicasweep.csv}
LOG=${LOG:-$REPO/km2/experiments/replicasweep.log}
ROLLOUT_TIMEOUT=300s
LOAD_WAIT_MAX=120
MARKER_POLL_MAX=${MARKER_POLL_MAX:-160}

# 分離(normal)の全サービス。redis-cart は cartservice.yaml 内(スケール対象外)。
NORMAL=(frontend checkoutservice cartservice productcatalogservice currencyservice \
        paymentservice shippingservice emailservice recommendationservice adservice)
# スケールするステートレスApp(redis除く)
SCALE=(frontend checkoutservice cartservice productcatalogservice currencyservice \
       paymentservice shippingservice emailservice recommendationservice adservice)
PROM="http://prometheus-grafana-kube-pr-prometheus.monitoring.svc:9090"

exec > >(tee -a "$LOG") 2>&1
echo "================ REPLICASWEEP START $(date -Is) ns=$NS users=$LG_USERS rate=$LG_RATE warmup=$WARMUP measure=$MEASURE replicas=[$REPLICAS_LIST] ================"
echo "replicas,arm,reqcount,fails,p50_ms,p90_ms,p99_ms,avg_ms,rps,softirq_cores,base_softirq,system_cores,base_system,app_cores,base_app,node_cores,base_node,softirq_mc_per_req,system_mc_per_req,app_mc_per_req,node_mc_per_req" > "$CSV"

setup_promq() {
  kubectl delete pod promq -n "$NS" --ignore-not-found >/dev/null 2>&1
  kubectl run promq -n "$NS" --image=curlimages/curl:latest --restart=Never --command -- sleep 86400 >/dev/null 2>&1
  for i in $(seq 1 30); do [ "$(kubectl get pod promq -n "$NS" -o jsonpath='{.status.phase}' 2>/dev/null)" = "Running" ] && break; sleep 2; done
}
prom_scalar() {
  kubectl exec promq -n "$NS" -- curl -s "$PROM/api/v1/query" --data-urlencode "query=$1" 2>/dev/null \
    | python3 -c "import sys,json;r=json.load(sys.stdin).get('data',{}).get('result',[]);print(r[0]['value'][1] if r else 'NA')" 2>/dev/null
}
setup_promq

echo "---- 既存トポロジ全削除 → normal(分離) を張る ----"
kubectl delete -f "$REPO/km2/all/all.yaml" -n "$NS" --ignore-not-found >/dev/null 2>&1
for f in "${NORMAL[@]}"; do kubectl delete -f "$REPO/km2/normal/$f.yaml" -n "$NS" --ignore-not-found >/dev/null 2>&1; done
for i in $(seq 1 40); do [ -z "$(kubectl get deploy -n "$NS" -o name 2>/dev/null)" ] && break; sleep 3; done
for f in "${NORMAL[@]}"; do kubectl apply -f "$REPO/km2/normal/$f.yaml" -n "$NS" >/dev/null; done
for d in "${NORMAL[@]}" redis-cart; do
  kubectl patch deploy/"$d" -n "$NS" --type=merge -p '{"spec":{"template":{"metadata":{"annotations":{"sidecar.istio.io/inject":"false"}}}}}' >/dev/null 2>&1 || true
done
for d in "${NORMAL[@]}" redis-cart; do kubectl rollout status deploy/"$d" -n "$NS" --timeout="$ROLLOUT_TIMEOUT" >/dev/null 2>&1 || true; done

measure_baseline() {
  echo "---- $(date -Is) アイドル基線(ドレイン ${BASE_SETTLE}s + 窓 ${BASE_WIN}) ----"
  sleep "$BASE_SETTLE"
  local win_s=$BASE_WIN; case "$win_s" in *m) win_s=$(( ${win_s%m} * 60 ));; *s) win_s=${win_s%s};; esac
  sleep "$win_s"
  BASE_SOFTIRQ=$(prom_scalar "sum(rate(node_cpu_seconds_total{mode=\"softirq\"}[$BASE_WIN]))")
  BASE_SYSTEM=$(prom_scalar "sum(rate(node_cpu_seconds_total{mode=\"system\"}[$BASE_WIN]))")
  BASE_APP=$(prom_scalar "sum(rate(container_cpu_usage_seconds_total{namespace=\"$NS\",container!=\"\",container!=\"POD\",pod!~\"loadgenerator.*\",pod!~\"promq.*\"}[$BASE_WIN]))")
  BASE_NODE=$(prom_scalar "sum(rate(node_cpu_seconds_total{mode!=\"idle\"}[$BASE_WIN]))")
  echo "  $(date -Is) base: softirq=${BASE_SOFTIRQ} system=${BASE_SYSTEM} app=${BASE_APP} node=${BASE_NODE}"
}
gen_loadgen() {
  sed -E "s/(name: RUN_TIME, value: )\"[^\"]*\"/\1\"$1\"/; \
          s/(name: USERS,[[:space:]]*value: )\"[^\"]*\"/\1\"$LG_USERS\"/; \
          s/(name: RATE,[[:space:]]*value: )\"[^\"]*\"/\1\"$LG_RATE\"/" "$LOAD" > "$LOADGEN"
}
run_load() { # run_time capture replicas
  local rt=$1 capture=$2 reps=$3 pod run logs i st
  local phase; [ "$capture" = "1" ] && phase="本計測" || phase="ウォームアップ"
  echo "---- $(date -Is) rep=$reps $phase (負荷 $rt) ----"
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
  echo "  $(date -Is) loadgen pod=$pod"
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
    system_cores=$(prom_scalar "sum(rate(node_cpu_seconds_total{mode=\"system\"}[$rt]))")
    app_cores=$(prom_scalar "sum(rate(container_cpu_usage_seconds_total{namespace=\"$NS\",container!=\"\",container!=\"POD\",pod!~\"loadgenerator.*\",pod!~\"promq.*\"}[$rt]))")
    node_cores=$(prom_scalar "sum(rate(node_cpu_seconds_total{mode!=\"idle\"}[$rt]))")
    echo "  $(date -Is) CPU: softirq=${softirq_cores} app=${app_cores} node=${node_cores}"
  fi
  kubectl delete job loadgenerator -n "$NS" --ignore-not-found >/dev/null 2>&1
  [ "$capture" != "1" ] && { echo "  ウォームアップ完了(捨て)"; return; }
  local logfile="$REPO/km2/experiments/last-logs-replicasweep.txt"
  printf '%s\n' "$logs" > "$logfile"
  python3 - "$reps" "r$reps" "$CSV" "$logfile" \
           "$softirq_cores" "${BASE_SOFTIRQ:-NA}" "$system_cores" "${BASE_SYSTEM:-NA}" \
           "$app_cores" "${BASE_APP:-NA}" "$node_cores" "${BASE_NODE:-NA}" <<'PY'
import sys,csv,io
reps,arm,out,logfile,sc,bsi,syc,bsy,ac,ba,nc,bn=sys.argv[1:13]
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
        rec=[reps,arm,g("Request Count"),g("Failure Count"),g("50%"),g("90%"),g("99%"),
             g("Average Response Time"),g("Requests/s"),
             sc,bsi,syc,bsy,ac,ba,nc,bn,mc(sc,bsi),mc(syc,bsy),mc(ac,ba),mc(nc,bn)]
        with open(out,"a",newline="") as f: csv.writer(f).writerow(rec)
        print("  -> 記録:", ",".join(map(str,rec)))
    else: print("  !! Aggregated行なし")
else: print("  !! CSVマーカー無し")
PY
}

for REPS in $REPLICAS_LIST; do
  echo "================ REPLICAS=$REPS $(date -Is) ================"
  for d in "${SCALE[@]}"; do kubectl scale deploy/"$d" -n "$NS" --replicas="$REPS" >/dev/null 2>&1 || true; done
  for d in "${SCALE[@]}"; do kubectl rollout status deploy/"$d" -n "$NS" --timeout="$ROLLOUT_TIMEOUT" >/dev/null 2>&1 || true; done
  run_load "$WARMUP" 0 "$REPS"
  measure_baseline
  run_load "$MEASURE" 1 "$REPS"
done

kubectl delete pod promq -n "$NS" --ignore-not-found >/dev/null 2>&1
echo "================ REPLICASWEEP DONE $(date -Is) ================"
column -s, -t "$CSV" 2>/dev/null || cat "$CSV"
