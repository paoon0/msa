#!/usr/bin/env bash
# ============================================================================
# outpy(paymentservice を checkout の Pod 内へ同居し localhost で到達) の softirq を測る(単独)。
# normal / mega は測り直さず、本走 results-cpu.csv(compare.sh, USERS=80: normal≈1.18 / mega≈0.56)と並べる。
# outpy: payment を checkout の Pod に同居し、checkout は PAYMENT_SERVICE_ADDR=localhost:50051 で到達
#   (=payment1ホップだけ loopback)。email等は依然 ClusterIP。outmail の対(email でなく payment を localhost化)。
#   軽ホップ(checkout→payment 1req1回)の localhost 化で softirq が減るか(用量反応の検証, 予想:減らない)。
# 公平のため Istio無しに揃える(normal/mega と同条件)。条件は本走(compare.sh)に一致:
#   CYCLES=3 WARMUP=3m MEASURE=5m USERS=80 RATE=1(rps≈208)、基線 settle30s/窓2m。
# 念のため結果CSVは毎回新規。出力: km2/experiments/results-outpy.csv
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
ALL=$REPO/km2/all/all.yaml
LOAD=$REPO/km2/experiments/loadgen-csv.yaml
LOADGEN=/tmp/loadgen-outpy.yaml
CSV=${CSV:-$REPO/km2/experiments/results-outpy.csv}
LOG=${LOG:-$REPO/km2/experiments/outpy.log}
ROLLOUT_TIMEOUT=300s
LOAD_WAIT_MAX=120
MARKER_POLL_MAX=${MARKER_POLL_MAX:-160}

NORMAL=(frontend checkoutservice cartservice productcatalogservice currencyservice \
        paymentservice shippingservice emailservice recommendationservice adservice)
OUTPY_DEPLOYS=(frontend checkoutservice cartservice redis-cart productcatalogservice \
        currencyservice emailservice shippingservice recommendationservice adservice)
PROM="http://prometheus-grafana-kube-pr-prometheus.monitoring.svc:9090"

CYCLES=${CYCLES:-3}
exec > >(tee -a "$LOG") 2>&1
echo "================ OUTPY START $(date -Is) ns=$NS users=$LG_USERS rate=$LG_RATE warmup=$WARMUP measure=$MEASURE cycles=$CYCLES ================"
echo "cycle,arm,reqcount,fails,p50_ms,p90_ms,p99_ms,avg_ms,rps,softirq_cores,base_softirq,system_cores,base_system,app_cores,base_app,node_cores,base_node,softirq_mc_per_req,system_mc_per_req,app_mc_per_req,node_mc_per_req" > "$CSV"

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

# 既存(normal/mega)の残骸を全消ししてから outpy を張る
echo "---- 既存トポロジを全削除 ----"
kubectl delete -f "$ALL" -n "$NS" --ignore-not-found >/dev/null 2>&1
for f in "${NORMAL[@]}"; do kubectl delete -f "$REPO/km2/normal/$f.yaml" -n "$NS" --ignore-not-found >/dev/null 2>&1; done
for i in $(seq 1 40); do [ -z "$(kubectl get deploy -n "$NS" -o name 2>/dev/null)" ] && break; sleep 3; done

echo "---- deploy OUTPY (payment を checkout に同居・localhost・Istio無し) ----"
for y in "$REPO"/km2/outpy/*.yaml; do
  case "$y" in *kustomization.yaml|*loadgenerator.yaml) continue;; esac
  kubectl apply -f "$y" -n "$NS"
done
for d in "${OUTPY_DEPLOYS[@]}"; do
  kubectl patch deploy/"$d" -n "$NS" --type=merge -p '{"spec":{"template":{"metadata":{"annotations":{"sidecar.istio.io/inject":"false"}}}}}' || true
done
for d in "${OUTPY_DEPLOYS[@]}"; do kubectl rollout status deploy/"$d" -n "$NS" --timeout="$ROLLOUT_TIMEOUT" || true; done

measure_baseline() {
  echo "---- $(date -Is) アイドル基線(温まったアイドル: ドレイン ${BASE_SETTLE}s + 窓 ${BASE_WIN}) ----"
  sleep "$BASE_SETTLE"
  local win_s=$BASE_WIN; case "$win_s" in *m) win_s=$(( ${win_s%m} * 60 ));; *s) win_s=${win_s%s};; esac
  sleep "$win_s"
  BASE_SOFTIRQ=$(prom_scalar "sum(rate(node_cpu_seconds_total{mode=\"softirq\"}[$BASE_WIN]))")
  BASE_SYSTEM=$(prom_scalar "sum(rate(node_cpu_seconds_total{mode=\"system\"}[$BASE_WIN]))")
  BASE_APP=$(prom_scalar "sum(rate(container_cpu_usage_seconds_total{namespace=\"$NS\",container!=\"\",container!=\"POD\",pod!~\"loadgenerator.*\",pod!~\"promq.*\"}[$BASE_WIN]))")
  BASE_NODE=$(prom_scalar "sum(rate(node_cpu_seconds_total{mode!=\"idle\"}[$BASE_WIN]))")
  echo "  $(date -Is) base: softirq=${BASE_SOFTIRQ} system=${BASE_SYSTEM} app=${BASE_APP} node=${BASE_NODE} cores"
}
gen_loadgen() {
  sed -E "s/(name: RUN_TIME, value: )\"[^\"]*\"/\1\"$1\"/; \
          s/(name: USERS,[[:space:]]*value: )\"[^\"]*\"/\1\"$LG_USERS\"/; \
          s/(name: RATE,[[:space:]]*value: )\"[^\"]*\"/\1\"$LG_RATE\"/" "$LOAD" > "$LOADGEN"
}
run_load() { # run_time capture
  local rt=$1 capture=$2 pod run logs i st
  local phase; [ "$capture" = "1" ] && phase="本計測" || phase="ウォームアップ"
  echo "---- $(date -Is) $phase (負荷 $rt, users $LG_USERS rate $LG_RATE) ----"
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
  echo "  $(date -Is) loadgen pod=$pod main開始=$run"
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
    echo "  $(date -Is) CPU: softirq=${softirq_cores} system=${system_cores} app=${app_cores} node=${node_cores} cores"
  fi
  kubectl delete job loadgenerator -n "$NS" --ignore-not-found >/dev/null 2>&1
  [ "$capture" != "1" ] && { echo "  ウォームアップ完了(捨て)"; return; }
  local logfile="$REPO/km2/experiments/last-logs-outpy.txt"
  printf '%s\n' "$logs" > "$logfile"
  python3 - "${CYC:-1}" "outpy" "$CSV" "$logfile" \
           "$softirq_cores" "${BASE_SOFTIRQ:-NA}" "$system_cores" "${BASE_SYSTEM:-NA}" \
           "$app_cores" "${BASE_APP:-NA}" "$node_cores" "${BASE_NODE:-NA}" <<'PY'
import sys,csv,io
cyc,arm,out,logfile,sc,bsi,syc,bsy,ac,ba,nc,bn=sys.argv[1:13]
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
        rec=[cyc,arm,g("Request Count"),g("Failure Count"),g("50%"),g("90%"),g("99%"),
             g("Average Response Time"),g("Requests/s"),
             sc,bsi,syc,bsy,ac,ba,nc,bn,mc(sc,bsi),mc(syc,bsy),mc(ac,ba),mc(nc,bn)]
        with open(out,"a",newline="") as f: csv.writer(f).writerow(rec)
        print("  -> 記録:", ",".join(map(str,rec)))
    else: print("  !! Aggregated行なし")
else: print("  !! CSVマーカー無し")
PY
}

for CYC in $(seq 1 "$CYCLES"); do
  echo "================ CYCLE $CYC/$CYCLES $(date -Is) ================"
  run_load "$WARMUP" 0
  measure_baseline
  run_load "$MEASURE" 1
done

kubectl delete pod promq -n "$NS" --ignore-not-found >/dev/null 2>&1
echo "================ OUTPY DONE $(date -Is) ================"
column -s, -t "$CSV" 2>/dev/null || cat "$CSV"
