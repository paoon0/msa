#!/usr/bin/env bash
# ============================================================================
# 通常版(分離: 1 Pod 1 サービス) vs 全部入り(megapod: 11コンテナ1 Pod) を交互に走らせ、
# locust の "1リクエストにかかる時間"(エンドツーエンド応答時間)を CSV で比較する。
#
# 各アーム・各サイクルで:
#   1) デプロイ → 2) ウォームアップ負荷 WARMUP 分(捨て) → 3) 本計測負荷 MEASURE 分(記録)
# ウォームアップで JIT・キャッシュ・接続を温め、コールドスタートのノイズ(特に p99)を排除する。
#
# 計測源: loadgen ログ末尾の locust _stats.csv "Aggregated" 行(クライアント側エンドツーエンド)。
# 出力 CSV 列: cycle,arm,reqcount,fails,p50_ms,p90_ms,p99_ms,avg_ms,rps
#
# 使い方:  bash km2/all/compare.sh
#   env で上書き可: CYCLES, WARMUP, MEASURE  (例: CYCLES=1 WARMUP=30s MEASURE=1m bash ...)
# 注意: ノイズ対策で normal↔mega を交互に CYCLES 回。p50 だけでなく裾(p99)も両アームで比較。
# ============================================================================
set -u

# -------- 設定(環境に合わせて変更 / env で上書き可) --------
NS=exp
REPO=/home/mizuki/ダウンロード/msa
CYCLES=${CYCLES:-3}                      # normal/mega を交互に何サイクル
WARMUP=${WARMUP:-5m}                     # 捨てるウォームアップ負荷の長さ
MEASURE=${MEASURE:-10m}                  # 記録する本計測負荷の長さ
ALL=$REPO/km2/all/all.yaml
LOAD=$REPO/km2/all/loadgen-csv.yaml      # テンプレ(RUN_TIME はここから差し替える)
LOADGEN=/tmp/loadgen-gen.yaml            # RUN_TIME を差し込んだ実行用マニフェスト
CSV=${CSV:-$REPO/km2/all/results-compare.csv}
LOG=${LOG:-$REPO/km2/all/compare.log}
ROLLOUT_TIMEOUT=300s
LOAD_WAIT_MAX=120                        # main 起動待ちの最大ループ(×5s)
MARKER_POLL_MAX=${MARKER_POLL_MAX:-220}  # マーカー待ちの最大ループ(×5s ≈ 18分。MEASURE=10m を十分カバー)

NORMAL=(frontend checkoutservice cartservice productcatalogservice currencyservice \
        paymentservice shippingservice emailservice recommendationservice adservice)
NORMAL_DEPLOYS=(frontend checkoutservice cartservice redis-cart productcatalogservice \
        currencyservice paymentservice shippingservice emailservice recommendationservice adservice)
ISTIO_SVCS=(checkoutservice paymentservice emailservice)   # megapod と公平にするため false 化
# -------------------------------------------

PROM="http://prometheus-grafana-kube-pr-prometheus.monitoring.svc:9090"

exec > >(tee -a "$LOG") 2>&1
echo "================ START $(date -Is) ns=$NS cycles=$CYCLES warmup=$WARMUP measure=$MEASURE ================"
[ -f "$CSV" ] || echo "cycle,arm,reqcount,fails,p50_ms,p90_ms,p99_ms,avg_ms,rps,node_cores,app_cores,node_mc_per_req,app_mc_per_req" > "$CSV"

# Prometheus を叩く常駐 curl Pod を立てる(port-forward はこの環境で落ちるため exec 方式)
setup_promq() {
  kubectl delete pod promq -n "$NS" --ignore-not-found >/dev/null 2>&1
  kubectl run promq -n "$NS" --image=curlimages/curl:latest --restart=Never \
    --command -- sleep 86400 >/dev/null 2>&1
  for i in $(seq 1 30); do
    [ "$(kubectl get pod promq -n "$NS" -o jsonpath='{.status.phase}' 2>/dev/null)" = "Running" ] && break
    sleep 2
  done
}
# PromQL スカラーを返す(失敗時 NA)
prom_scalar() {
  kubectl exec promq -n "$NS" -- curl -s "$PROM/api/v1/query" --data-urlencode "query=$1" 2>/dev/null \
    | python3 -c "import sys,json;r=json.load(sys.stdin).get('data',{}).get('result',[]);print(r[0]['value'][1] if r else 'NA')" 2>/dev/null
}
setup_promq

deploy_normal() {
  echo "---- deploy NORMAL (分離・Istio無し) ----"
  kubectl delete -f "$ALL" -n "$NS" --ignore-not-found
  for f in "${NORMAL[@]}"; do kubectl apply -f "$REPO/km2/$f.yaml" -n "$NS"; done
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
  for f in "${NORMAL[@]}"; do kubectl delete -f "$REPO/km2/$f.yaml" -n "$NS" --ignore-not-found; done
  kubectl apply -f "$ALL" -n "$NS"
  kubectl rollout status deploy/megapod -n "$NS" --timeout="$ROLLOUT_TIMEOUT" || true
}

# RUN_TIME を差し込んだ loadgen マニフェストを生成
gen_loadgen() { # run_time
  sed -E "s/(name: RUN_TIME, value: )\"[^\"]*\"/\1\"$1\"/" "$LOAD" > "$LOADGEN"
}

run_load() { # cycle arm run_time capture(1=記録/0=捨て)
  local cyc=$1 arm=$2 rt=$3 capture=$4 pod run logs i st
  local phase; [ "$capture" = "1" ] && phase="本計測" || phase="ウォームアップ"
  echo "---- $(date -Is) cycle $cyc arm=$arm $phase (負荷 $rt) ----"
  gen_loadgen "$rt"
  # 前段(ウォームアップ等)の残存Podを掴まないよう、loadgen Pod が完全に消えるまで待ってから apply。
  kubectl delete job loadgenerator -n "$NS" --ignore-not-found --wait=true
  for i in $(seq 1 24); do
    [ -z "$(kubectl get pods -n "$NS" -l job-name=loadgenerator -o jsonpath='{.items[*].metadata.name}' 2>/dev/null)" ] && break
    sleep 2
  done
  kubectl apply -f "$LOADGEN" -n "$NS"
  pod=""; run=""
  for i in $(seq 1 $LOAD_WAIT_MAX); do
    # 念のため最新作成のPodを採用(items を creationTimestamp 昇順にして末尾)
    pod=$(kubectl get pods -n "$NS" -l job-name=loadgenerator --sort-by=.metadata.creationTimestamp -o jsonpath='{.items[-1].metadata.name}' 2>/dev/null)
    [ -n "$pod" ] || { sleep 5; continue; }
    run=$(kubectl get pod "$pod" -n "$NS" -o jsonpath='{.status.containerStatuses[?(@.name=="main")].state.running.startedAt}' 2>/dev/null)
    [ -n "$run" ] && break
    st=$(kubectl get pod "$pod" -n "$NS" -o jsonpath='{.status.phase}' 2>/dev/null)
    { [ "$st" = "Succeeded" ] || [ "$st" = "Failed" ]; } && break
    sleep 5
  done
  echo "  $(date -Is) loadgen pod=$pod main開始=$run"
  # loadgen は CSV 出力後 sleep で生存。生存中の Pod をポーリングし END マーカーで読み取る。
  logs=""
  for i in $(seq 1 $MARKER_POLL_MAX); do
    logs=$(kubectl logs "$pod" -n "$NS" -c main --tail=-1 2>/dev/null)
    echo "$logs" | grep -q '@@@CSV_END@@@' && { echo "  $(date -Is) 負荷完了・マーカー検出(試行 $i)"; break; }
    st=$(kubectl get pod "$pod" -n "$NS" -o jsonpath='{.status.phase}' 2>/dev/null)
    [ "$st" = "Failed" ] && { echo "  loadgen FAILED"; break; }
    sleep 5
  done
  if [ "$capture" = "1" ]; then
    # 本計測窓のCPUを取得(rate窓 = 本計測長 $rt)。loadgen/promq 自身は app から除外。
    local node_cores app_cores
    node_cores=$(prom_scalar "sum(rate(node_cpu_seconds_total{mode!=\"idle\"}[$rt]))")
    app_cores=$(prom_scalar "sum(rate(container_cpu_usage_seconds_total{namespace=\"$NS\",container!=\"\",container!=\"POD\",pod!~\"loadgenerator.*\",pod!~\"promq.*\"}[$rt]))")
    echo "  $(date -Is) CPU: node=${node_cores} cores / app=${app_cores} cores (window=$rt)"
  fi
  kubectl delete job loadgenerator -n "$NS" --ignore-not-found >/dev/null 2>&1
  if [ "$capture" != "1" ]; then
    echo "  ウォームアップ完了(結果は捨てる)"
    return
  fi
  # 本計測のみ CSV へ記録(ファイル渡し: python3 - のヒアドキュメントが stdin を占有するため)
  local logfile="$REPO/km2/all/last-logs-$arm.txt"
  printf '%s\n' "$logs" > "$logfile"
  python3 - "$cyc" "$arm" "$CSV" "$logfile" "$node_cores" "$app_cores" <<'PY'
import sys,csv,io
cyc,arm,out,logfile,node_cores,app_cores=sys.argv[1:7]
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
        rps=fnum(g("Requests/s")); nc=fnum(node_cores); ac=fnum(app_cores)
        # CPU/req = cores / (req/s) * 1000 = ミリコア秒/リクエスト
        node_mc=round(nc/rps*1000,3) if (nc and rps) else "NA"
        app_mc =round(ac/rps*1000,3) if (ac and rps) else "NA"
        rec=[cyc,arm,g("Request Count"),g("Failure Count"),
             g("50%"),g("90%"),g("99%"),g("Average Response Time"),g("Requests/s"),
             node_cores,app_cores,node_mc,app_mc]
        with open(out,"a",newline="") as f: csv.writer(f).writerow(rec)
        print("  -> 記録:", ",".join(map(str,rec)))
    else:
        print("  !! Aggregated 行が見つからない")
else:
    print("  !! CSVマーカーがログに無い(loadgen失敗?)")
PY
}

run_arm() { # cycle arm
  run_load "$1" "$2" "$WARMUP"  0   # ウォームアップ(捨て)
  run_load "$1" "$2" "$MEASURE" 1   # 本計測(記録)
}

for c in $(seq 1 $CYCLES); do
  deploy_normal; run_arm "$c" normal
  deploy_mega;   run_arm "$c" mega
done

kubectl delete pod promq -n "$NS" --ignore-not-found >/dev/null 2>&1
echo "================ DONE $(date -Is) ================"
column -s, -t "$CSV" 2>/dev/null || cat "$CSV"
