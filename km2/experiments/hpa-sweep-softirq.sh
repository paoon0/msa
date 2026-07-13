#!/usr/bin/env bash
# ============================================================================
# HPA本実験(第一歩): normal(分離)に全アプリHPA(CPU70%,1-4)を付け、負荷を上げて実際にスケールさせ、
#   各負荷レベルで softirq/req と 総レプリカ数 を記録。「HPAがスケールするとき softirq がどうなるか」を観察。
#   予想: レプリカ増→エンドポイント/コネクション/conntrack増→softirq/req 横ばい〜微増 のどちらか。
# 負荷を低→高(80→高)で上げる(scale-upのみ。HPAはscale-up速い/scale-down 5分停留なので低→高が安全)。
# 各レベル: ウォームアップ(HPA settle)→本計測。RATE大=即ramp。
# 出力: km2/experiments/results-hpasweep.csv (列頭 users, 末尾 total_replicas)
# ============================================================================
set -u
NS=exp
REPO=/home/mizuki/ダウンロード/msa
SWEEP_USERS=${SWEEP_USERS:-"80 240 480"}
LG_RATE=${LG_RATE:-40}
WARMUP=${WARMUP:-4m}          # HPA が scale-up して落ち着くまで
MEASURE=${MEASURE:-3m}
BASE_SETTLE=${BASE_SETTLE:-30}
BASE_WIN=${BASE_WIN:-2m}
HPA_TARGET=${HPA_TARGET:-70}
HPA_MIN=${HPA_MIN:-1}
HPA_MAX=${HPA_MAX:-4}
LOAD=$REPO/km2/experiments/loadgen-csv.yaml
LOADGEN=/tmp/loadgen-hpasweep.yaml
CSV=${CSV:-$REPO/km2/experiments/results-hpasweep.csv}
LOG=${LOG:-$REPO/km2/experiments/hpasweep.log}
ROLLOUT_TIMEOUT=300s
LOAD_WAIT_MAX=120
MARKER_POLL_MAX=${MARKER_POLL_MAX:-220}

NORMAL=(frontend checkoutservice cartservice productcatalogservice currencyservice \
        paymentservice shippingservice emailservice recommendationservice adservice)
# HPA を付けるステートレスApp(redis除く)
HPADEPLOYS=(frontend checkoutservice cartservice productcatalogservice currencyservice \
            paymentservice shippingservice emailservice recommendationservice adservice)
PROM="http://prometheus-grafana-kube-pr-prometheus.monitoring.svc:9090"
LG_USERS=80

exec > >(tee -a "$LOG") 2>&1
echo "================ HPASWEEP START $(date -Is) ns=$NS levels=[$SWEEP_USERS] rate=$LG_RATE warmup=$WARMUP measure=$MEASURE HPA=${HPA_TARGET}%/${HPA_MIN}-${HPA_MAX} ================"
echo "users,arm,reqcount,fails,p50_ms,p90_ms,p99_ms,avg_ms,rps,softirq_cores,base_softirq,system_cores,base_system,app_cores,base_app,node_cores,base_node,softirq_mc_per_req,system_mc_per_req,app_mc_per_req,node_mc_per_req,total_replicas" > "$CSV"

setup_promq() {
  kubectl delete pod promq -n "$NS" --ignore-not-found >/dev/null 2>&1
  kubectl run promq -n "$NS" --image=curlimages/curl:latest --restart=Never --command -- sleep 86400 >/dev/null 2>&1
  for i in $(seq 1 30); do [ "$(kubectl get pod promq -n "$NS" -o jsonpath='{.status.phase}' 2>/dev/null)" = "Running" ] && break; sleep 2; done
}
prom_scalar() {
  kubectl exec promq -n "$NS" -- curl -s "$PROM/api/v1/query" --data-urlencode "query=$1" 2>/dev/null \
    | python3 -c "import sys,json;r=json.load(sys.stdin).get('data',{}).get('result',[]);print(r[0]['value'][1] if r else 'NA')" 2>/dev/null
}
total_replicas() { # 全HPA対象の .status.replicas 合計
  local t=0 r
  for d in "${HPADEPLOYS[@]}"; do
    r=$(kubectl get deploy "$d" -n "$NS" -o jsonpath='{.status.replicas}' 2>/dev/null); [ -n "$r" ] && t=$((t+r))
  done
  echo "$t"
}
setup_promq

echo "---- 既存トポロジ全削除(HPAも) → normal(分離) を張る ----"
kubectl delete hpa --all -n "$NS" >/dev/null 2>&1
kubectl delete -f "$REPO/km2/all/all.yaml" -n "$NS" --ignore-not-found >/dev/null 2>&1
for f in "${NORMAL[@]}"; do kubectl delete -f "$REPO/km2/normal/$f.yaml" -n "$NS" --ignore-not-found >/dev/null 2>&1; done
for i in $(seq 1 40); do [ -z "$(kubectl get deploy -n "$NS" -o name 2>/dev/null)" ] && break; sleep 3; done
for f in "${NORMAL[@]}"; do kubectl apply -f "$REPO/km2/normal/$f.yaml" -n "$NS" >/dev/null; done
for d in "${NORMAL[@]}" redis-cart; do
  kubectl patch deploy/"$d" -n "$NS" --type=merge -p '{"spec":{"template":{"metadata":{"annotations":{"sidecar.istio.io/inject":"false"}}}}}' >/dev/null 2>&1 || true
done
for d in "${NORMAL[@]}" redis-cart; do kubectl rollout status deploy/"$d" -n "$NS" --timeout="$ROLLOUT_TIMEOUT" >/dev/null 2>&1 || true; done

echo "---- 全アプリに HPA を作成(CPU ${HPA_TARGET}%, ${HPA_MIN}-${HPA_MAX}) ----"
for d in "${HPADEPLOYS[@]}"; do
  kubectl autoscale deploy/"$d" -n "$NS" --cpu-percent="$HPA_TARGET" --min="$HPA_MIN" --max="$HPA_MAX" >/dev/null 2>&1 || true
done
sleep 20; kubectl get hpa -n "$NS" --no-headers 2>/dev/null | awk '{print "  HPA "$1" "$4" "$6"->"$7" cur="$8}'

measure_baseline() {
  echo "---- $(date -Is) アイドル基線(ドレイン ${BASE_SETTLE}s + 窓 ${BASE_WIN}) ----"
  sleep "$BASE_SETTLE"
  local win_s=$BASE_WIN; case "$win_s" in *m) win_s=$(( ${win_s%m} * 60 ));; *s) win_s=${win_s%s};; esac
  sleep "$win_s"
  BASE_SOFTIRQ=$(prom_scalar "sum(rate(node_cpu_seconds_total{mode=\"softirq\"}[$BASE_WIN]))")
  BASE_SYSTEM=$(prom_scalar "sum(rate(node_cpu_seconds_total{mode=\"system\"}[$BASE_WIN]))")
  BASE_APP=$(prom_scalar "sum(rate(container_cpu_usage_seconds_total{namespace=\"$NS\",container!=\"\",container!=\"POD\",pod!~\"loadgenerator.*\",pod!~\"promq.*\"}[$BASE_WIN]))")
  BASE_NODE=$(prom_scalar "sum(rate(node_cpu_seconds_total{mode!=\"idle\"}[$BASE_WIN]))")
  echo "  base: softirq=${BASE_SOFTIRQ} system=${BASE_SYSTEM} app=${BASE_APP} node=${BASE_NODE}"
}
gen_loadgen() {
  sed -E "s/(name: RUN_TIME, value: )\"[^\"]*\"/\1\"$1\"/; \
          s/(name: USERS,[[:space:]]*value: )\"[^\"]*\"/\1\"$LG_USERS\"/; \
          s/(name: RATE,[[:space:]]*value: )\"[^\"]*\"/\1\"$LG_RATE\"/" "$LOAD" > "$LOADGEN"
}
run_load() { # run_time capture
  local rt=$1 capture=$2 pod run logs i st
  local phase; [ "$capture" = "1" ] && phase="本計測" || phase="ウォームアップ"
  echo "---- $(date -Is) users=$LG_USERS $phase (負荷 $rt, rate $LG_RATE) ----"
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
  echo "  loadgen pod=$pod"
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
    TREPS=$(total_replicas)
    echo "  $(date -Is) CPU: softirq=${softirq_cores} app=${app_cores} node=${node_cores} | total_replicas=${TREPS}"
    echo "  レプリカ内訳: $(for d in "${HPADEPLOYS[@]}"; do printf '%s=%s ' "$d" "$(kubectl get deploy $d -n $NS -o jsonpath='{.status.replicas}' 2>/dev/null)"; done)"
  fi
  kubectl delete job loadgenerator -n "$NS" --ignore-not-found >/dev/null 2>&1
  [ "$capture" != "1" ] && { echo "  ウォームアップ完了(捨て)"; return; }
  local logfile="$REPO/km2/experiments/last-logs-hpasweep.txt"
  printf '%s\n' "$logs" > "$logfile"
  python3 - "$LG_USERS" "normal" "$CSV" "$logfile" \
           "$softirq_cores" "${BASE_SOFTIRQ:-NA}" "$system_cores" "${BASE_SYSTEM:-NA}" \
           "$app_cores" "${BASE_APP:-NA}" "$node_cores" "${BASE_NODE:-NA}" "$TREPS" <<'PY'
import sys,csv,io
users,arm,out,logfile,sc,bsi,syc,bsy,ac,ba,nc,bn,treps=sys.argv[1:14]
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
        rec=[users,arm,g("Request Count"),g("Failure Count"),g("50%"),g("90%"),g("99%"),
             g("Average Response Time"),g("Requests/s"),
             sc,bsi,syc,bsy,ac,ba,nc,bn,mc(sc,bsi),mc(syc,bsy),mc(ac,ba),mc(nc,bn),treps]
        with open(out,"a",newline="") as f: csv.writer(f).writerow(rec)
        print("  -> 記録:", ",".join(map(str,rec)))
    else: print("  !! Aggregated行なし")
else: print("  !! CSVマーカー無し")
PY
}

for U in $SWEEP_USERS; do
  LG_USERS=$U
  echo "================ USERS=$U $(date -Is) ================"
  run_load "$WARMUP" 0
  measure_baseline
  run_load "$MEASURE" 1
done

kubectl delete hpa --all -n "$NS" >/dev/null 2>&1
kubectl delete pod promq -n "$NS" --ignore-not-found >/dev/null 2>&1
echo "================ HPASWEEP DONE $(date -Is) ================"
column -s, -t "$CSV" 2>/dev/null || cat "$CSV"
