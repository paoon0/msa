#!/usr/bin/env bash
# 枠(requests)適正化の第2版 — 手順 STEP 1/2 の測定: リクエストのクラスごとの CPU カーブ
#
# 何を測るか:
#   各サービスを台数固定(HPA無し)にして、リクエストのクラス(buy / view …)を「1つずつ」流し、
#   負荷を段階的に変えたときの各コンテナの CPU 使用量[m]を録る。
#   混ぜて流すと、増えた CPU がどのクラスのせいか分けられないので、必ず1クラスずつ。
#
# 第1版(perservice-cpu.sh, 2026-08-18)からの変更点 — 手順書 km2/approach/rightsizing-procedure.md の §2:
#   * クラスごとに測る(第1版は buy だけ → view が混ざると 60〜80% 過小評価した)
#   * 設計点 k の周辺に点を集める(既定 buy は 60〜140 に5点。第1版は 10〜150 に均等6点)
#   * 3サイクル既定 + サイクルごとに順番をシャッフル(第1版は1サイクルで、ばらつきが分からなかった)
#   * アイドル分 c0 を「台数を変えた差」で測る(C0_REPLICAS)。第1版は直線の切片で、過大に出ていた
#   * ウォームアップ既定 60s(JVM 等の立ち上がりを捨てる。Sock Shop の Java サービスはさらに長く)
#   * 第1版の壊れ(存在しない perservice-cpu/k6/ を参照、__BROWSE__ を埋めていない)を修正
# 2026-10-07 の修正 (手順書の修正項目 3 と gRPC 振り分け):
#   * デプロイごとに慣らし負荷 PREWARM 秒 (既定 180s) を流して捨てる。起動直後の跳ね上がりを測定点に入れない
#   * c0 の対 (2台と1台) は、測る順番をサイクルごとに入れ替える (奇数サイクル=2台が先、偶数=1台が先)
#   * GRPC_LB=1 (既定) で bundle-vs-loss2.sh と同じ gRPC 振り分けを入れる (summer2026/grpc_lb_patch.py)。
#     1台の点では振り分け先が1つなので変わらないが、c0 の2台点と、以後の実験 (既定 GRPC_LB=1) に条件を揃える
#
# 測り方の約束(第1版と同じ):
#   * HPA は必ず切る / 台数固定 / requests・limits はマニフェストのまま(使用量は requests に依存しない)
#   * スロットリング率を毎点記録する(limits の天井で絞られた点はカーブが寝るので解析で捨てる)
#
# 出力 CSV (1行 = 1測定点 × 1コンテナ。複数台のときは同じ deploy の Pod を合計した値):
#   cycle,class,replicas,target_rate,achieved_rate,dropped_win,failed_rate,p99,deploy,container,usage_mc,req_mc,util_pct,throttle_pct,node_cores
#
# 使い方 (リポジトリ直下から):
#   bash km2/experiments/rightsizing/measure-class-cpu.sh                       # 本走(既定)
#   CLASSES=buy RATES_buy="60 100" CYCLES=1 WARM=20 MEAS=60 C0_REPLICAS= \
#     CSV=km2/experiments/rightsizing/smoke.csv bash km2/experiments/rightsizing/measure-class-cpu.sh   # スモーク
#
# 他アプリ(Sock Shop 等)に移すとき書き換えるのは「アプリ固有の設定」の節だけ。
set -u
NS=exp
REPO=/home/mizuki/ダウンロード/msa
DIR=$REPO/km2/experiments/rightsizing
K6DIR=$REPO/km2/experiments/k6

# ===================== アプリ固有の設定 (Online Boutique) =====================
# 台数を固定するサービス(状態を持つ redis-cart は常に1台)
SERVICES=(frontend checkoutservice cartservice productcatalogservice currencyservice \
          paymentservice shippingservice emailservice recommendationservice adservice)
STATEFUL=(redis-cart)
MANIFEST_DIR=$REPO/km2/normal
# クラス名 → k6 の環境変数(RATE=購入型, BROWSE_RATE=閲覧型)。$1 = 負荷[周/秒]
class_env(){ case "$1" in
  buy)  echo "$2 0";;      # RATE=$2  BROWSE_RATE=0
  view) echo "0 $2";;      # RATE=0   BROWSE_RATE=$2  (checkout.js は RATE<=0 で閲覧型だけを流す)
  *) echo "!! 未知のクラス $1" >&2; return 1;; esac; }
# k6 の集計 JSON から、そのクラスの「計測窓で開始できた周/秒」を取り出すキー
class_started_key(){ case "$1" in buy) echo started;; view) echo browse_started;; esac; }
# ==============================================================================

CLASSES=${CLASSES:-"buy view"}
RATES_buy=${RATES_buy:-"20 60 80 100 120 140"}     # 設計点 k=100 の周辺に集める
RATES_view=${RATES_view:-"50 100 150 200 250 300"}
C0_REPLICAS=${C0_REPLICAS-2}       # アイドル分 c0 を測るための追加台数(空にすると測らない)
C0_CLASS=${C0_CLASS:-buy}          # c0 を測るときのクラスと負荷(1台の点と同じ負荷で比べる)
C0_RATE=${C0_RATE:-100}
WARM=${WARM:-60}
MEAS=${MEAS:-180}
SETTLE=${SETTLE:-30}               # デプロイ後、負荷を入れる前に待つ秒
PRE_VUS=${PRE_VUS:-300}
MAX_VUS=${MAX_VUS:-3000}
CYCLES=${CYCLES:-3}
SHUFFLE=${SHUFFLE:-1}              # 1 = サイクルごとに (クラス, 負荷) の順番をシャッフル(時間ドリフト対策)
PREWARM=${PREWARM:-180}            # デプロイ直後に流して捨てる慣らし負荷の秒数 (0 で無し)
PREWARM_CLASS=${PREWARM_CLASS:-buy}
PREWARM_RATE=${PREWARM_RATE:-100}
GRPC_LB=${GRPC_LB:-1}              # 1 = gRPC 振り分けあり (2026-10-07 からの既定)、0 = 無し
GRPC_RESOLVE_EVERY=${GRPC_RESOLVE_EVERY:-30}
LB_IMG_FRONTEND=${LB_IMG_FRONTEND:-mizuki0118/mygo:frontend-lb}
LB_IMG_CHECKOUT=${LB_IMG_CHECKOUT:-mizuki0118/mygo:checkout-lb}
LB_IMG_RECO=${LB_IMG_RECO:-mizuki0118/mygo:reco-lb}
CSV=${CSV:-$DIR/results-class-cpu.csv}
LOG=${LOG:-${CSV%.csv}.log}
PROM="http://prometheus-grafana-kube-pr-prometheus.monitoring.svc:9090"
ROLLOUT=300s

exec > >(tee -a "$LOG") 2>&1
echo "================ MEASURE-CLASS-CPU START $(date -Is) classes=[$CLASSES] buy=[$RATES_buy] view=[$RATES_view] c0=[${C0_REPLICAS:-なし}台@$C0_CLASS:$C0_RATE] cycles=$CYCLES warm=${WARM}s meas=${MEAS}s shuffle=$SHUFFLE prewarm=${PREWARM}s@$PREWARM_CLASS:$PREWARM_RATE grpc_lb=$GRPC_LB (HPA無し, 枠はマニフェストのまま) ================"
[ -s "$CSV" ] || echo "cycle,class,replicas,target_rate,achieved_rate,dropped_win,failed_rate,p99,deploy,container,usage_mc,req_mc,util_pct,throttle_pct,node_cores" > "$CSV"

ensure_promq(){ [ "$(kubectl get pod promq -n $NS -o jsonpath='{.status.phase}' 2>/dev/null)" = Running ] && return
  kubectl delete pod promq -n $NS --ignore-not-found >/dev/null 2>&1
  kubectl run promq -n $NS --image=curlimages/curl:latest --restart=Never --command -- sleep 86400 >/dev/null 2>&1
  for i in $(seq 1 30);do [ "$(kubectl get pod promq -n $NS -o jsonpath='{.status.phase}' 2>/dev/null)" = Running ]&&break;sleep 2;done; }
promq(){ local q="$1" i out; for i in 1 2 3 4 5;do ensure_promq
  out=$(kubectl exec promq -n $NS -- curl -s --max-time 25 "$PROM/api/v1/query" --data-urlencode "query=$q" 2>/dev/null)
  [ -n "$out" ]&&{ echo "$out"; return; }; sleep 4; done; echo ""; }

deploy(){ local reps=$1
  echo "---- deploy 分離 (固定${reps}台, HPA無し, 枠はマニフェストのまま) ----"
  kubectl delete hpa --all -n $NS >/dev/null 2>&1
  kubectl delete deploy --all -n $NS >/dev/null 2>&1
  for i in $(seq 1 40);do [ -z "$(kubectl get deploy -n $NS -o name 2>/dev/null)" ]&&break;sleep 3;done
  for f in "${SERVICES[@]}" "${STATEFUL[@]}";do [ -f $MANIFEST_DIR/$f.yaml ] && kubectl apply -f $MANIFEST_DIR/$f.yaml -n $NS >/dev/null;done   # redis-cart は cartservice.yaml の中
  kubectl delete hpa --all -n $NS >/dev/null 2>&1
  for d in "${SERVICES[@]}";do kubectl scale deploy/$d -n $NS --replicas=$reps >/dev/null 2>&1||true;done
  for d in "${STATEFUL[@]}";do kubectl scale deploy/$d -n $NS --replicas=1 >/dev/null 2>&1||true;done
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
  sleep $SETTLE
  [ "$PREWARM" -gt 0 ] && prewarm
}

# 慣らし負荷: 結果は捨てる (起動直後の JIT・接続確立・キャッシュの跳ね上がりを測定点に入れない)
prewarm(){ local ev; ev=$(class_env "$PREWARM_CLASS" "$PREWARM_RATE") || return
  echo "  慣らし負荷 ${PREWARM}s ($PREWARM_CLASS ${PREWARM_RATE}周/秒, 結果は捨てる)"
  kubectl create configmap k6-script -n $NS --from-file=checkout.js=$K6DIR/checkout.js --dry-run=client -o yaml | kubectl apply -f - >/dev/null 2>&1
  kubectl delete job k6load -n $NS --ignore-not-found --wait=true >/dev/null 2>&1
  sed -e "s/__RATE__/${ev% *}/" -e "s/__BROWSE__/${ev#* }/" -e "s/__WARM__/0/" -e "s/__MEAS__/$PREWARM/" \
      -e "s/__PRE__/$PRE_VUS/" -e "s/__MAX__/$MAX_VUS/" "$K6DIR/k6-job.yaml" | kubectl apply -f - -n $NS >/dev/null
  kubectl wait --for=condition=complete job/k6load -n $NS --timeout=$(( PREWARM + 120 ))s >/dev/null 2>&1 || true
  kubectl delete job k6load -n $NS --ignore-not-found --wait=true >/dev/null 2>&1
}

run_point(){ local cyc=$1 cls=$2 rate=$3 reps=$4
  local ev; ev=$(class_env "$cls" "$rate") || return
  local r_buy=${ev% *} r_view=${ev#* }
  echo "==== [cyc$cyc][$cls ×${reps}台] ${rate}周/秒 (RATE=$r_buy BROWSE_RATE=$r_view) $(date -Is) ===="
  kubectl create configmap k6-script -n $NS --from-file=checkout.js=$K6DIR/checkout.js --dry-run=client -o yaml | kubectl apply -f - >/dev/null 2>&1
  kubectl delete job k6load -n $NS --ignore-not-found --wait=true >/dev/null 2>&1
  sed -e "s/__RATE__/$r_buy/" -e "s/__BROWSE__/$r_view/" -e "s/__WARM__/$WARM/" -e "s/__MEAS__/$MEAS/" \
      -e "s/__PRE__/$PRE_VUS/" -e "s/__MAX__/$MAX_VUS/" "$K6DIR/k6-job.yaml" | kubectl apply -f - -n $NS >/dev/null
  local pod=""
  for i in $(seq 1 40);do pod=$(kubectl get pods -n $NS -l app=k6load --sort-by=.metadata.creationTimestamp -o jsonpath='{.items[-1].metadata.name}' 2>/dev/null)
    [ -n "$pod" ]&&[ "$(kubectl get pod $pod -n $NS -o jsonpath='{.status.phase}' 2>/dev/null)" = Running ]&&break; sleep 3;done
  local t_run=$(date +%s)
  # 計測窓の終わりで、窓の大半をカバーする rate() 幅で採取(瞬間値でなく窓平均)
  local win=$(( MEAS*5/6 )); [ $win -lt 60 ] && win=60
  sleep $(( WARM + MEAS ))
  local SEL="namespace=\"$NS\",container!=\"\",container!=\"POD\",pod!~\"k6load.*|promq.*\""
  local USAGE REQ THR NODE
  USAGE=$(promq "sum by(pod,container)(rate(container_cpu_usage_seconds_total{$SEL}[${win}s]))")
  REQ=$(promq   "sum by(pod,container)(kube_pod_container_resource_requests{namespace=\"$NS\",resource=\"cpu\",pod!~\"k6load.*|promq.*\"})")
  THR=$(promq   "sum by(pod,container)(rate(container_cpu_cfs_throttled_periods_total{$SEL}[${win}s])) / sum by(pod,container)(rate(container_cpu_cfs_periods_total{$SEL}[${win}s]))")
  NODE=$(promq  "sum(rate(node_cpu_seconds_total{mode!=\"idle\"}[${win}s]))" | python3 -c "import sys,json;r=json.load(sys.stdin).get('data',{}).get('result',[]);print(round(float(r[0]['value'][1]),2) if r else 'NA')" 2>/dev/null)
  local done_at=$(( t_run + WARM + MEAS + 25 ))
  while [ "$(date +%s)" -lt "$done_at" ]; do sleep 5; done
  local summary; summary=$(kubectl logs "$pod" -n $NS 2>/dev/null | sed -n '/@@@K6_BEGIN@@@/,/@@@K6_END@@@/p' | grep '{')
  echo "$summary" | grep -q '{' || { echo "  !! summary回収失敗(pod=$pod)"; kubectl delete job k6load -n $NS --ignore-not-found >/dev/null 2>&1; return; }
  SUMMARY="$summary" USAGE="$USAGE" REQJSON="$REQ" THRJSON="$THR" SKEY="$(class_started_key $cls)" \
    python3 "$DIR/_write_point.py" "$CSV" "$cyc" "$cls" "$reps" "$rate" "$NODE"
  kubectl delete job k6load -n $NS --ignore-not-found >/dev/null 2>&1
}

# (クラス, 負荷) の一覧を作る
points(){ for cls in $CLASSES; do v="RATES_$cls"; for r in ${!v}; do echo "$cls $r"; done; done; }

ensure_promq
for c in $(seq 1 $CYCLES); do
  echo "################ CYCLE $c / $CYCLES $(date -Is) ################"
  deploy 1
  if [ "$SHUFFLE" = 1 ]; then list=$(points | shuf); else list=$(points); fi
  while read -r cls r; do [ -n "$cls" ] && run_point "$c" "$cls" "$r" 1; done <<< "$list"
  # アイドル分 c0: 同じ負荷で台数だけ変える。差 = 1台増えたぶんのアイドル CPU。
  # 1台側も同じサイクル内で測り直して対にする。順番は奇数サイクル=n台が先、偶数=1台が先 (時間ドリフトを相殺)
  for n in $C0_REPLICAS; do
    if [ $(( c % 2 )) = 1 ]; then order="$n 1"; else order="1 $n"; fi
    for m in $order; do
      deploy "$m"
      run_point "$c" "$C0_CLASS" "$C0_RATE" "$m"
    done
  done
done
kubectl delete job k6load -n $NS --ignore-not-found >/dev/null 2>&1
echo "================ MEASURE-CLASS-CPU DONE $(date -Is) ================"
