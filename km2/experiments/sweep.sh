#!/usr/bin/env bash
# ============================================================================
# 負荷スイープ: normal(分離) vs mega(全部入り) を、複数の負荷レベル(USERS)で測り、
# softirq CPU/req(主指標)が負荷で一定か・絶対節約(cores)が rps に比例して育つか・飽和点 を見る。
#
# 各レベル・各アームで: デプロイ → ウォームアップ(捨) → 温まったアイドル基線 → 本計測(記録)
# 主指標 softirq_mc_per_req =(負荷時softirq − 無負荷softirq)/rps×1000。app は対照群。
#
# 使い方:  SWEEP_USERS="80 160 240 360" LG_RATE=40 bash km2/experiments/sweep.sh
#   env: SWEEP_USERS(負荷レベル列), LG_RATE(spawn rate,高負荷は大きく=即ramp),
#        WARMUP, MEASURE, BASE_SETTLE, BASE_WIN
# 念のため: 実験ごとに結果CSVは毎回新規作成する(追記しない)。
# 出力 CSV: km2/experiments/results-sweep.csv
# ============================================================================
set -u
NS=exp
REPO=/home/mizuki/ダウンロード/msa
SWEEP_USERS=${SWEEP_USERS:-"80 160 240 360"}  # 負荷レベル(locust ユーザ数)の列
LG_RATE=${LG_RATE:-40}                   # spawn rate(即ramp。低いと立ち上げに時間がかかり平均が汚れる)
WARMUP=${WARMUP:-2m}
MEASURE=${MEASURE:-3m}
BASE_SETTLE=${BASE_SETTLE:-30}
BASE_WIN=${BASE_WIN:-2m}
ALL=$REPO/km2/all/all.yaml
LOAD=$REPO/km2/experiments/loadgen-csv.yaml
LOADGEN=/tmp/loadgen-sweep.yaml
CSV=${CSV:-$REPO/km2/experiments/results-sweep.csv}
LOG=${LOG:-$REPO/km2/experiments/sweep.log}
ROLLOUT_TIMEOUT=300s
LOAD_WAIT_MAX=120
MARKER_POLL_MAX=${MARKER_POLL_MAX:-160}

NORMAL=(frontend checkoutservice cartservice productcatalogservice currencyservice \
        paymentservice shippingservice emailservice recommendationservice adservice)
NORMAL_DEPLOYS=(frontend checkoutservice cartservice redis-cart productcatalogservice \
        currencyservice paymentservice shippingservice emailservice recommendationservice adservice)
ISTIO_SVCS=(checkoutservice paymentservice emailservice)
PROM="http://prometheus-grafana-kube-pr-prometheus.monitoring.svc:9090"

LG_USERS=80   # ループ内で各レベルに差し替え

exec > >(tee -a "$LOG") 2>&1
echo "================ SWEEP START $(date -Is) ns=$NS levels=[$SWEEP_USERS] rate=$LG_RATE warmup=$WARMUP measure=$MEASURE ================"
# 念のため: 実験ごとに必ず新規作成(追記しない)
echo "users,arm,reqcount,fails,p50_ms,p90_ms,p99_ms,avg_ms,rps,softirq_cores,base_softirq,system_cores,base_system,app_cores,base_app,node_cores,base_node,softirq_mc_per_req,system_mc_per_req,app_mc_per_req,node_mc_per_req" > "$CSV"

setup_promq() {
  kubectl delete pod promq -n "$NS" --ignore-not-found >/dev/null 2>&1
  kubectl run promq -n "$NS" --image=curlimages/curl:latest --restart=Never --command -- sleep 86400 >/dev/null 2>&1
  for i in $(seq 1 30); do
    [ "$(kubectl get pod promq -n "$NS" -o jsonpath='{.status.phase}' 2>/dev/null)" = "Running" ] && break
    sleep 2
  done
}
prom_scalar() {
  kubectl exec promq -n "$NS" -- curl -s "$PROM/api/v1/query" --data-urlencode "query=$1" 2>/dev/null \
    | python3 -c "import sys,json;r=json.load(sys.stdin).get('data',{}).get('result',[]);print(r[0]['value'][1] if r else 'NA')" 2>/dev/null
}
setup_promq

# 温まったアイドル基線(ウォームアップ後・無負荷)。起動スパイクを避け本計測と同条件で測る。
measure_baseline() { # arm
  local arm=$1
  echo "---- $(date -Is) arm=$arm users=$LG_USERS アイドル基線(温まったアイドル: ドレイン ${BASE_SETTLE}s + 窓 ${BASE_WIN}) ----"
  sleep "$BASE_SETTLE"
  local win_s=$BASE_WIN; case "$win_s" in *m) win_s=$(( ${win_s%m} * 60 ));; *s) win_s=${win_s%s};; esac
  sleep "$win_s"
  BASE_SOFTIRQ=$(prom_scalar "sum(rate(node_cpu_seconds_total{mode=\"softirq\"}[$BASE_WIN]))")
  BASE_SYSTEM=$(prom_scalar "sum(rate(node_cpu_seconds_total{mode=\"system\"}[$BASE_WIN]))")
  BASE_APP=$(prom_scalar "sum(rate(container_cpu_usage_seconds_total{namespace=\"$NS\",container!=\"\",container!=\"POD\",pod!~\"loadgenerator.*\",pod!~\"promq.*\"}[$BASE_WIN]))")
  BASE_NODE=$(prom_scalar "sum(rate(node_cpu_seconds_total{mode!=\"idle\"}[$BASE_WIN]))")
  echo "  $(date -Is) base: softirq=${BASE_SOFTIRQ} system=${BASE_SYSTEM} app=${BASE_APP} node=${BASE_NODE} cores"
}

deploy_normal() {
  echo "---- deploy NORMAL (分離・Istio無し) ----"
  kubectl delete -f "$ALL" -n "$NS" --ignore-not-found
  for f in "${NORMAL[@]}"; do kubectl apply -f "$REPO/km2/normal/$f.yaml" -n "$NS"; done
  for d in "${ISTIO_SVCS[@]}"; do
    kubectl patch deploy/"$d" -n "$NS" --type=merge \
      -p '{"spec":{"template":{"metadata":{"annotations":{"sidecar.istio.io/inject":"false"}}}}}' || true
  done
  for d in "${NORMAL_DEPLOYS[@]}"; do
    kubectl rollout status deploy/"$d" -n "$NS" --timeout="$ROLLOUT_TIMEOUT" || true
  done
}
deploy_mega() {
  echo "---- deploy MEGA (全部入り) ----"
  for f in "${NORMAL[@]}"; do kubectl delete -f "$REPO/km2/normal/$f.yaml" -n "$NS" --ignore-not-found; done
  kubectl apply -f "$ALL" -n "$NS"
  kubectl rollout status deploy/megapod -n "$NS" --timeout="$ROLLOUT_TIMEOUT" || true
}

# RUN_TIME / USERS / RATE を差し込んだ loadgen マニフェスト生成
gen_loadgen() { # run_time
  sed -E "s/(name: RUN_TIME, value: )\"[^\"]*\"/\1\"$1\"/; \
          s/(name: USERS,[[:space:]]*value: )\"[^\"]*\"/\1\"$LG_USERS\"/; \
          s/(name: RATE,[[:space:]]*value: )\"[^\"]*\"/\1\"$LG_RATE\"/" "$LOAD" > "$LOADGEN"
}

run_load() { # arm run_time capture(1=記録/0=捨て)
  local arm=$1 rt=$2 capture=$3 pod run logs i st
  local phase; [ "$capture" = "1" ] && phase="本計測" || phase="ウォームアップ"
  echo "---- $(date -Is) arm=$arm users=$LG_USERS $phase (負荷 $rt, rate $LG_RATE) ----"
  gen_loadgen "$rt"
  kubectl delete job loadgenerator -n "$NS" --ignore-not-found --wait=true
  for i in $(seq 1 24); do
    [ -z "$(kubectl get pods -n "$NS" -l job-name=loadgenerator -o jsonpath='{.items[*].metadata.name}' 2>/dev/null)" ] && break
    sleep 2
  done
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
    echo "$logs" | grep -q '@@@CSV_END@@@' && { echo "  $(date -Is) 負荷完了・マーカー検出(試行 $i)"; break; }
    st=$(kubectl get pod "$pod" -n "$NS" -o jsonpath='{.status.phase}' 2>/dev/null)
    [ "$st" = "Failed" ] && { echo "  loadgen FAILED"; break; }
    sleep 5
  done
  if [ "$capture" = "1" ]; then
    local softirq_cores system_cores app_cores node_cores
    softirq_cores=$(prom_scalar "sum(rate(node_cpu_seconds_total{mode=\"softirq\"}[$rt]))")
    system_cores=$(prom_scalar "sum(rate(node_cpu_seconds_total{mode=\"system\"}[$rt]))")
    app_cores=$(prom_scalar "sum(rate(container_cpu_usage_seconds_total{namespace=\"$NS\",container!=\"\",container!=\"POD\",pod!~\"loadgenerator.*\",pod!~\"promq.*\"}[$rt]))")
    node_cores=$(prom_scalar "sum(rate(node_cpu_seconds_total{mode!=\"idle\"}[$rt]))")
    echo "  $(date -Is) CPU: softirq=${softirq_cores} system=${system_cores} app=${app_cores} node=${node_cores} cores (window=$rt)"
  fi
  kubectl delete job loadgenerator -n "$NS" --ignore-not-found >/dev/null 2>&1
  if [ "$capture" != "1" ]; then echo "  ウォームアップ完了(捨て)"; return; fi
  local logfile="$REPO/km2/experiments/last-logs-sweep-$arm.txt"
  printf '%s\n' "$logs" > "$logfile"
  python3 - "$LG_USERS" "$arm" "$CSV" "$logfile" \
           "$softirq_cores" "${BASE_SOFTIRQ:-NA}" "$system_cores" "${BASE_SYSTEM:-NA}" \
           "$app_cores" "${BASE_APP:-NA}" "$node_cores" "${BASE_NODE:-NA}" <<'PY'
import sys,csv,io
users,arm,out,logfile,sc,bsi,syc,bsy,ac,ba,nc,bn=sys.argv[1:13]
data=open(logfile,encoding='utf-8',errors='replace').read()
b,e="@@@CSV_BEGIN@@@","@@@CSV_END@@@"
def fnum(x):
    try: return float(x)
    except: return None
if b in data and e in data:
    block=data.split(b,1)[1].split(e,1)[0].strip()
    rows=list(csv.reader(io.StringIO(block)))
    hdr=rows[0]
    def idx(name): return hdr.index(name) if name in hdr else None
    agg=[r for r in rows[1:] if len(r)>1 and r[1]=="Aggregated"]
    if agg:
        r=agg[0]
        def g(name,default="NA"):
            i=idx(name); return r[i] if i is not None and i<len(r) else default
        rps=fnum(g("Requests/s"))
        def mc(load,base):
            l=fnum(load); bb=fnum(base)
            return round((l-bb)/rps*1000,3) if (l is not None and bb is not None and rps) else "NA"
        softirq_mc=mc(sc,bsi); system_mc=mc(syc,bsy); app_mc=mc(ac,ba); node_mc=mc(nc,bn)
        rec=[users,arm,g("Request Count"),g("Failure Count"),
             g("50%"),g("90%"),g("99%"),g("Average Response Time"),g("Requests/s"),
             sc,bsi,syc,bsy,ac,ba,nc,bn,softirq_mc,system_mc,app_mc,node_mc]
        with open(out,"a",newline="") as f: csv.writer(f).writerow(rec)
        print("  -> 記録:", ",".join(map(str,rec)))
    else:
        print("  !! Aggregated 行が見つからない")
else:
    print("  !! CSVマーカーがログに無い(loadgen失敗?)")
PY
}

run_arm() { # arm
  run_load "$1" "$WARMUP"  0
  measure_baseline "$1"
  run_load "$1" "$MEASURE" 1
}

for U in $SWEEP_USERS; do
  LG_USERS=$U
  echo "######## $(date -Is) SWEEP level USERS=$U (rate=$LG_RATE) ########"
  deploy_normal; run_arm normal
  deploy_mega;   run_arm mega
done

kubectl delete pod promq -n "$NS" --ignore-not-found >/dev/null 2>&1
echo "================ SWEEP DONE $(date -Is) ================"
column -s, -t "$CSV" 2>/dev/null || cat "$CSV"
