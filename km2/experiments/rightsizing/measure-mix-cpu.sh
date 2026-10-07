#!/usr/bin/env bash
# 混合負荷 (buy + view) での各サービスの CPU — 同居の相手選びの式の入力 (2026-10-07)
#
# 何を測るか:
#   分離構成・HPA 無し・台数固定で、buy と view の配合を変えた負荷を流し、各コンテナの CPU 使用量[m]を録る。
#   同じ点を「全サービス1台固定」と「全サービス2台固定」の両方で測る。
#     - 2台 − 1台 の差 = Pod が1つ増えたぶんのアイドル CPU (c0)。全点で出る
#     - 配合ごとの CPU の比から、サービスどうしの「高さの比」が配合でどう動くかを出す
#   解析で HPA の判断規則に入れて、同居したときの台数と損を予測する (予測は同居実験の前に固定する)。
#
# measure-class-cpu.sh (第2版の手順 STEP 1、1クラスずつ) との違い:
#   * 1点で buy と view を同時に流せる (点の名前 b50v100 = buy 50周/秒 + view 100周/秒)
#   * buy と view それぞれの達成率・取りこぼし・p50/p99 を記録 (片方だけ取りこぼしても見逃さない)
#   * CPU 周波数の平均・最高温度・k6 の CPU・絞られた時間の割合も記録 (ノード負荷の影響を後で確かめるため)
#   * Prometheus は k6 の計測窓の終わりの時刻を指定して問い合わせる (窓を一意にする)
#   * 計測窓の 10 秒刻みの系列も別 CSV に残す (HPA は短い窓で判断するので、ばらつきが要る)
#   * 1台ブロックと2台ブロックの順番はサイクルごとに入れ替える (奇数=1台が先、偶数=2台が先)
#   アヌビス査読 (2026-10-07) の必須修正のうち、記録の追加・c0・limits の対処をここに入れた。
#
# 出力:
#   $CSV    1行 = 1点 × 1コンテナ (同じ Deployment の Pod は合計)
#   $SERIES 1行 = 1点 × 1コンテナ × 10秒 (計測窓の中だけ)
#
# 使い方 (リポジトリ直下から):
#   bash km2/experiments/rightsizing/measure-mix-cpu.sh                                     # 本走 (既定)
#   POINTS="b100 b100v150" REPLICAS="1" CYCLES=1 WARM=20 MEAS=60 PREWARM=30 \
#     CSV=km2/experiments/rightsizing/smoke-mix.csv bash km2/experiments/rightsizing/measure-mix-cpu.sh   # スモーク
set -u
NS=exp
REPO=/home/mizuki/ダウンロード/msa
DIR=$REPO/km2/experiments/rightsizing
K6DIR=$REPO/km2/experiments/k6

# ===================== アプリ固有の設定 (Online Boutique) =====================
SERVICES=(frontend checkoutservice cartservice productcatalogservice currencyservice \
          paymentservice shippingservice emailservice recommendationservice adservice)
STATEFUL=(redis-cart)
MANIFEST_DIR=$REPO/km2/normal
# ==============================================================================

# 点の名前: b<buy周/秒>v<view周/秒>。片方だけなら b100 / v200
POINTS=${POINTS:-"b50 b100 v100 v200 b50v50 b50v100 b50v150 b100v50 b100v100 b100v150"}
REPLICAS=${REPLICAS:-"1 2"}        # 測る台数 (全サービス同じ台数。redis-cart は常に1台)
CYCLES=${CYCLES:-3}
WARM=${WARM:-60}
MEAS=${MEAS:-180}
SETTLE=${SETTLE:-30}
PREWARM=${PREWARM:-180}            # デプロイごとに流して捨てる慣らし負荷の秒数
PREWARM_POINT=${PREWARM_POINT:-b100}
PRE_VUS=${PRE_VUS:-300}
MAX_VUS=${MAX_VUS:-3000}
# 測定中だけ limits を上書き。requests は触らない
LIMIT_OVERRIDE=${LIMIT_OVERRIDE-"frontend=3000m productcatalogservice=3000m adservice=1000m"}
# ↑ 2026-10-07 ユーザ了承 (frontend)。スモークで catalog が 660m/上限1000m で絞り 17%、ad が 2台で 4.5% だったので同じ扱いに広げた。
#   Go は GOMAXPROCS=16 で瞬間的に CPU を使うので、平均が上限の半分程度でも 100ms 周期で絞られる。空文字を渡すとマニフェストのまま
GRPC_LB=${GRPC_LB:-1}
GRPC_RESOLVE_EVERY=${GRPC_RESOLVE_EVERY:-30}
LB_IMG_FRONTEND=${LB_IMG_FRONTEND:-mizuki0118/mygo:frontend-lb}
LB_IMG_CHECKOUT=${LB_IMG_CHECKOUT:-mizuki0118/mygo:checkout-lb}
LB_IMG_RECO=${LB_IMG_RECO:-mizuki0118/mygo:reco-lb}
CSV=${CSV:-$DIR/results-mix-cpu.csv}
SERIES=${SERIES:-${CSV%.csv}-series.csv}
LOG=${LOG:-${CSV%.csv}.log}
PROM="http://prometheus-grafana-kube-pr-prometheus.monitoring.svc:9090"
ROLLOUT=300s

exec > >(tee -a "$LOG") 2>&1
echo "================ MEASURE-MIX-CPU START $(date -Is) points=[$POINTS] replicas=[$REPLICAS] cycles=$CYCLES warm=${WARM}s meas=${MEAS}s prewarm=${PREWARM}s@$PREWARM_POINT limits=[${LIMIT_OVERRIDE:-マニフェスト}] grpc_lb=$GRPC_LB (HPA無し) ================"

# 点の名前 → "buy view"
parse_point(){ local p=$1 b=0 v=0
  [[ $p =~ ^b([0-9]+) ]] && b=${BASH_REMATCH[1]}
  [[ $p =~ v([0-9]+)$ ]] && v=${BASH_REMATCH[1]}
  [[ $p =~ ^(b[0-9]+)?(v[0-9]+)?$ ]] && [ -n "$p" ] || { echo "!! 点の名前が不正: $p" >&2; return 1; }
  echo "$b $v"; }
for p in $POINTS $PREWARM_POINT; do parse_point "$p" >/dev/null || exit 1; done

ensure_promq(){ [ "$(kubectl get pod promq -n $NS -o jsonpath='{.status.phase}' 2>/dev/null)" = Running ] && return
  kubectl delete pod promq -n $NS --ignore-not-found >/dev/null 2>&1
  kubectl run promq -n $NS --image=curlimages/curl:latest --restart=Never --command -- sleep 86400 >/dev/null 2>&1
  for i in $(seq 1 30);do [ "$(kubectl get pod promq -n $NS -o jsonpath='{.status.phase}' 2>/dev/null)" = Running ]&&break;sleep 2;done; }
# promq <PromQL> <評価時刻(unix秒)>
promq(){ local q="$1" t="$2" i out; for i in 1 2 3 4 5;do ensure_promq
  out=$(kubectl exec promq -n $NS -- curl -s --max-time 25 "$PROM/api/v1/query" --data-urlencode "query=$q" --data-urlencode "time=$t" 2>/dev/null)
  [ -n "$out" ]&&{ echo "$out"; return; }; sleep 4; done; echo ""; }
# promr <PromQL> <開始> <終了> : 10秒刻みの系列
promr(){ local q="$1" s="$2" e="$3" i out; for i in 1 2 3 4 5;do ensure_promq
  out=$(kubectl exec promq -n $NS -- curl -s --max-time 40 "$PROM/api/v1/query_range" --data-urlencode "query=$q" \
        --data-urlencode "start=$s" --data-urlencode "end=$e" --data-urlencode "step=10" 2>/dev/null)
  [ -n "$out" ]&&{ echo "$out"; return; }; sleep 4; done; echo ""; }

start_k6(){ local b=$1 v=$2 warm=$3 meas=$4
  kubectl create configmap k6-script -n $NS --from-file=checkout.js=$K6DIR/checkout.js --dry-run=client -o yaml | kubectl apply -f - >/dev/null 2>&1
  kubectl delete job k6load -n $NS --ignore-not-found --wait=true >/dev/null 2>&1
  sed -e "s/__RATE__/$b/" -e "s/__BROWSE__/$v/" -e "s/__WARM__/$warm/" -e "s/__MEAS__/$meas/" \
      -e "s/__PRE__/$PRE_VUS/" -e "s/__MAX__/$MAX_VUS/" "$K6DIR/k6-job.yaml" | kubectl apply -f - -n $NS >/dev/null; }

deploy(){ local reps=$1
  echo "---- deploy 分離 (固定${reps}台, HPA無し) ----"
  kubectl delete hpa --all -n $NS >/dev/null 2>&1
  kubectl delete deploy --all -n $NS >/dev/null 2>&1
  for i in $(seq 1 40);do [ -z "$(kubectl get deploy -n $NS -o name 2>/dev/null)" ]&&break;sleep 3;done
  for f in "${SERVICES[@]}" "${STATEFUL[@]}";do [ -f $MANIFEST_DIR/$f.yaml ] && kubectl apply -f $MANIFEST_DIR/$f.yaml -n $NS >/dev/null;done   # redis-cart は cartservice.yaml の中
  kubectl delete hpa --all -n $NS >/dev/null 2>&1
  for d in "${SERVICES[@]}";do kubectl scale deploy/$d -n $NS --replicas=$reps >/dev/null 2>&1||true;done
  for d in "${STATEFUL[@]}";do kubectl scale deploy/$d -n $NS --replicas=1 >/dev/null 2>&1||true;done
  for kv in $LIMIT_OVERRIDE; do
    kubectl set resources deploy/${kv%%=*} -n $NS --limits=cpu=${kv#*=} >/dev/null && echo "  limits 上書き: ${kv%%=*} cpu=${kv#*=} (requests はそのまま)"
  done
  if [ "$GRPC_LB" = 1 ]; then
    echo "  gRPC 負荷分散: round_robin + headless Service (引き直し ${GRPC_RESOLVE_EVERY}s)"
    { printf '{"deploy":'; kubectl get deploy -n $NS -o json; printf ',"svc":'; kubectl get svc -n $NS -o json; printf '}'; } \
      | NS="$NS" GRPC_RESOLVE_EVERY="$GRPC_RESOLVE_EVERY" LB_IMG_FRONTEND="$LB_IMG_FRONTEND" \
        LB_IMG_CHECKOUT="$LB_IMG_CHECKOUT" LB_IMG_RECO="$LB_IMG_RECO" LB_IMAGES_ONLY=0 \
        python3 "$REPO/km2/experiments/summer2026/grpc_lb_patch.py" > /tmp/lb-$$.sh
    bash /tmp/lb-$$.sh; rm -f /tmp/lb-$$.sh
  fi
  for d in "${SERVICES[@]}" "${STATEFUL[@]}";do kubectl rollout status deploy/$d -n $NS --timeout=$ROLLOUT >/dev/null 2>&1||true;done
  echo "  deploy: $(kubectl get deploy -n $NS --no-headers 2>/dev/null | awk '{printf "%s=%s ",$1,$2}')"
  echo "  枠(req/上限lim): $(kubectl get deploy -n $NS -o jsonpath='{range .items[*]}{.metadata.name}={range .spec.template.spec.containers[*]}{.name}:{.resources.requests.cpu}/{.resources.limits.cpu}{","}{end}{" "}{end}')"
  sleep $SETTLE
  if [ "$PREWARM" -gt 0 ]; then
    local bv; bv=$(parse_point $PREWARM_POINT)
    echo "  慣らし負荷 ${PREWARM}s ($PREWARM_POINT, 結果は捨てる)"
    start_k6 ${bv% *} ${bv#* } 0 $PREWARM
    kubectl wait --for=condition=complete job/k6load -n $NS --timeout=$(( PREWARM + 120 ))s >/dev/null 2>&1 || true
    kubectl delete job k6load -n $NS --ignore-not-found --wait=true >/dev/null 2>&1
  fi
}

run_point(){ local cyc=$1 pt=$2 reps=$3 bv b v
  bv=$(parse_point "$pt"); b=${bv% *}; v=${bv#* }
  echo "==== [cyc$cyc][×${reps}台] $pt (buy=$b view=$v 周/秒) $(date -Is) ===="
  start_k6 $b $v $WARM $MEAS
  local pod=""
  for i in $(seq 1 40);do pod=$(kubectl get pods -n $NS -l app=k6load --sort-by=.metadata.creationTimestamp -o jsonpath='{.items[-1].metadata.name}' 2>/dev/null)
    [ -n "$pod" ]&&[ "$(kubectl get pod $pod -n $NS -o jsonpath='{.status.phase}' 2>/dev/null)" = Running ]&&break; sleep 3;done
  local t_run=$(date +%s)
  local t_end=$(( t_run + WARM + MEAS ))          # k6 の計測窓の終わり (k6 の起動遅れ数秒ぶん早め)
  local t_beg=$(( t_end - MEAS ))
  local win=$(( MEAS - 20 ))                       # 両端 10 秒ずつ内側
  local t_q=$(( t_end - 10 ))
  while [ "$(date +%s)" -lt $(( t_end + 15 )) ]; do sleep 5; done
  local SEL="namespace=\"$NS\",container!=\"\",container!=\"POD\",pod!~\"promq.*\""
  local USAGE REQ LIM THR THRT NODE FREQ TEMP SER
  USAGE=$(promq "sum by(pod,container)(rate(container_cpu_usage_seconds_total{$SEL}[${win}s]))" $t_q)
  REQ=$(promq   "sum by(pod,container)(kube_pod_container_resource_requests{namespace=\"$NS\",resource=\"cpu\"})" $t_q)
  LIM=$(promq   "sum by(pod,container)(kube_pod_container_resource_limits{namespace=\"$NS\",resource=\"cpu\"})" $t_q)
  THR=$(promq   "sum by(pod,container)(rate(container_cpu_cfs_throttled_periods_total{$SEL}[${win}s])) / sum by(pod,container)(rate(container_cpu_cfs_periods_total{$SEL}[${win}s]))" $t_q)
  THRT=$(promq  "sum by(pod,container)(rate(container_cpu_cfs_throttled_seconds_total{$SEL}[${win}s]))" $t_q)
  NODE=$(promq  "sum(rate(node_cpu_seconds_total{mode!=\"idle\"}[${win}s]))" $t_q)
  FREQ=$(promq  "avg(avg_over_time(node_cpu_scaling_frequency_hertz[${win}s]))" $t_q)
  TEMP=$(promq  "max(max_over_time(node_hwmon_temp_celsius[${win}s]))" $t_q)
  SER=$(promr   "sum by(pod,container)(rate(container_cpu_usage_seconds_total{$SEL}[30s]))" $(( t_beg + 10 )) $t_q)
  local summary; summary=$(kubectl logs "$pod" -n $NS 2>/dev/null | sed -n '/@@@K6_BEGIN@@@/,/@@@K6_END@@@/p' | grep '{')
  echo "$summary" | grep -q '{' || { echo "  !! summary回収失敗(pod=$pod)"; kubectl delete job k6load -n $NS --ignore-not-found >/dev/null 2>&1; return; }
  SUMMARY="$summary" USAGE="$USAGE" REQJSON="$REQ" LIMJSON="$LIM" THRJSON="$THR" THRTJSON="$THRT" \
    NODEJSON="$NODE" FREQJSON="$FREQ" TEMPJSON="$TEMP" SERJSON="$SER" \
    python3 "$DIR/_write_mixpoint.py" "$CSV" "$SERIES" "$cyc" "$pt" "$reps" "$b" "$v" "$t_beg"
  kubectl delete job k6load -n $NS --ignore-not-found >/dev/null 2>&1
}

ensure_promq
for c in $(seq 1 $CYCLES); do
  echo "################ CYCLE $c / $CYCLES $(date -Is) ################"
  if [ $(( c % 2 )) = 1 ]; then order=$REPLICAS; else order=$(echo $REPLICAS | tr ' ' '\n' | tac | tr '\n' ' '); fi
  for n in $order; do
    deploy "$n"
    for p in $(echo $POINTS | tr ' ' '\n' | shuf); do run_point "$c" "$p" "$n"; done
  done
done
kubectl delete job k6load -n $NS --ignore-not-found >/dev/null 2>&1
echo "================ MEASURE-MIX-CPU DONE $(date -Is) ================"
