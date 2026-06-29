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
BASE_SETTLE=${BASE_SETTLE:-30}           # デプロイ後、起動CPUスパイクが収まるまでの待ち(秒・無負荷)
BASE_WIN=${BASE_WIN:-2m}                 # アイドル基線の rate 窓(node-exporter のスクレイプ間隔を十分カバー)
ALL=$REPO/km2/all/all.yaml
LOAD=$REPO/km2/all/loadgen-csv.yaml      # テンプレ(RUN_TIME はここから差し替える)
LOADGEN=/tmp/loadgen-gen.yaml            # RUN_TIME を差し込んだ実行用マニフェスト
CSV=${CSV:-$REPO/km2/all/results-cpu.csv}
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
[ -f "$CSV" ] || echo "cycle,arm,reqcount,fails,p50_ms,p90_ms,p99_ms,avg_ms,rps,node_cores,app_cores,base_node,base_app,node_mc_per_req,app_mc_per_req,comm_mc_per_req,softirq_cores,system_cores,base_softirq,base_system,softirq_mc_per_req,system_mc_per_req" > "$CSV"

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

# 無負荷のアイドル基線CPUを測る(アーム別)。本計測の (負荷時CPU − 基線CPU)/req に使う。
# 低負荷では基線ドリフトが per-req 信号を覆うため必須。重要: 呼び出しは "ウォームアップ後" に行う。
# デプロイ直後(冷えた状態)で測ると起動CPUスパイクが基線を膨らませ、アーム間ドリフトが出て
# 信号(数 mc/req)を覆う。実証(baseline-probe): normal の基線は settle10s=0.914→settle30s=0.560
# →5分温め後=0.389 と落ち着くほど下がり、温め後は mega(0.401)とほぼ一致(差0.012)=ドリフト消失。
# 結果は BASE_NODE / BASE_APP に格納。
measure_baseline() { # arm
  local arm=$1
  echo "---- $(date -Is) arm=$arm アイドル基線測定 (ウォームアップ後の温まったアイドル: ドレイン ${BASE_SETTLE}s + 窓 ${BASE_WIN}) ----"
  sleep "$BASE_SETTLE"          # 直前ウォームアップ負荷のドレイン(in-flight/conntrack)を待つ
  # rate 窓ぶん無負荷で寝かせてからクエリ(窓全体が無負荷データになるように)
  local win_s=$BASE_WIN; case "$win_s" in *m) win_s=$(( ${win_s%m} * 60 ));; *s) win_s=${win_s%s};; esac
  sleep "$win_s"
  BASE_NODE=$(prom_scalar "sum(rate(node_cpu_seconds_total{mode!=\"idle\"}[$BASE_WIN]))")
  BASE_APP=$(prom_scalar "sum(rate(container_cpu_usage_seconds_total{namespace=\"$NS\",container!=\"\",container!=\"POD\",pod!~\"loadgenerator.*\",pod!~\"promq.*\"}[$BASE_WIN]))")
  # 主指標 softirq(通信kernel)・副指標 system。背景ノイズは user モードに居るので両者は影響を受けない。
  # softirq の無負荷基線は ~0.005cores と微小・安定(=基線ドリフト問題が無い)。
  BASE_SOFTIRQ=$(prom_scalar "sum(rate(node_cpu_seconds_total{mode=\"softirq\"}[$BASE_WIN]))")
  BASE_SYSTEM=$(prom_scalar "sum(rate(node_cpu_seconds_total{mode=\"system\"}[$BASE_WIN]))")
  echo "  $(date -Is) base: node=${BASE_NODE} app=${BASE_APP} softirq=${BASE_SOFTIRQ} system=${BASE_SYSTEM} cores (無負荷)"
}

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
    local node_cores app_cores softirq_cores system_cores
    node_cores=$(prom_scalar "sum(rate(node_cpu_seconds_total{mode!=\"idle\"}[$rt]))")
    app_cores=$(prom_scalar "sum(rate(container_cpu_usage_seconds_total{namespace=\"$NS\",container!=\"\",container!=\"POD\",pod!~\"loadgenerator.*\",pod!~\"promq.*\"}[$rt]))")
    softirq_cores=$(prom_scalar "sum(rate(node_cpu_seconds_total{mode=\"softirq\"}[$rt]))")
    system_cores=$(prom_scalar "sum(rate(node_cpu_seconds_total{mode=\"system\"}[$rt]))")
    echo "  $(date -Is) CPU: node=${node_cores} app=${app_cores} softirq=${softirq_cores} system=${system_cores} cores (window=$rt) / base softirq=${BASE_SOFTIRQ:-NA} system=${BASE_SYSTEM:-NA}"
  fi
  kubectl delete job loadgenerator -n "$NS" --ignore-not-found >/dev/null 2>&1
  if [ "$capture" != "1" ]; then
    echo "  ウォームアップ完了(結果は捨てる)"
    return
  fi
  # 本計測のみ CSV へ記録(ファイル渡し: python3 - のヒアドキュメントが stdin を占有するため)
  local logfile="$REPO/km2/all/last-logs-$arm.txt"
  printf '%s\n' "$logs" > "$logfile"
  python3 - "$cyc" "$arm" "$CSV" "$logfile" "$node_cores" "$app_cores" "${BASE_NODE:-NA}" "${BASE_APP:-NA}" \
           "$softirq_cores" "$system_cores" "${BASE_SOFTIRQ:-NA}" "${BASE_SYSTEM:-NA}" <<'PY'
import sys,csv,io
cyc,arm,out,logfile,node_cores,app_cores,base_node,base_app,softirq_cores,system_cores,base_softirq,base_system=sys.argv[1:13]
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
        bn=fnum(base_node); ba=fnum(base_app)
        sc=fnum(softirq_cores); syc=fnum(system_cores); bsi=fnum(base_softirq); bsy=fnum(base_system)
        # アイドル基線を差し引いた「負荷由来の増分CPU」を req で割る = ミリコア秒/リクエスト
        # 主指標 softirq_mc(通信kernel/req)・副 system_mc。node_mc/app_mc は参考(app=対照群)。
        def mc(load,base):
            return round((load-base)/rps*1000,3) if (load is not None and base is not None and rps) else "NA"
        node_mc=mc(nc,bn); app_mc=mc(ac,ba); softirq_mc=mc(sc,bsi); system_mc=mc(syc,bsy)
        comm_mc=round(node_mc-app_mc,3) if (node_mc!="NA" and app_mc!="NA") else "NA"
        rec=[cyc,arm,g("Request Count"),g("Failure Count"),
             g("50%"),g("90%"),g("99%"),g("Average Response Time"),g("Requests/s"),
             node_cores,app_cores,base_node,base_app,node_mc,app_mc,comm_mc,
             softirq_cores,system_cores,base_softirq,base_system,softirq_mc,system_mc]
        with open(out,"a",newline="") as f: csv.writer(f).writerow(rec)
        print("  -> 記録:", ",".join(map(str,rec)))
    else:
        print("  !! Aggregated 行が見つからない")
else:
    print("  !! CSVマーカーがログに無い(loadgen失敗?)")
PY
}

run_arm() { # cycle arm
  run_load "$1" "$2" "$WARMUP"  0   # ウォームアップ(捨て): JIT/キャッシュ/接続を温める
  measure_baseline "$2"             # 温まったアイドル基線(負荷ドレイン後) → BASE_NODE/BASE_APP
  run_load "$1" "$2" "$MEASURE" 1   # 本計測(記録, 基線差引でCPU/req算出)
}

for c in $(seq 1 $CYCLES); do
  deploy_normal; run_arm "$c" normal
  deploy_mega;   run_arm "$c" mega
done

kubectl delete pod promq -n "$NS" --ignore-not-found >/dev/null 2>&1
echo "================ DONE $(date -Is) ================"
column -s, -t "$CSV" 2>/dev/null || cat "$CSV"
