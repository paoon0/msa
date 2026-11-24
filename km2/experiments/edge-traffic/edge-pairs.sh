#!/usr/bin/env bash
# サービス「ペア」単位の通信量を実測する(2026-09-08 作成)。
#
# cAdvisor の Pod 単位カウンタでは、呼び出し元が複数あるサービス
# (productcatalog は frontend / recommendation / checkout の3つから呼ばれる)を分解できない。
# ここでは各 Pod のネットワーク名前空間に入って `ss -tin` を読み、
# TCP 接続ごと = サービスペアごとの送受信バイト・セグメント数・RTT を取る。
#
# Pod の netns へは「エフェメラルコンテナ」で入る(sudo 不要。kubectl だけで済む)。
#   ※ エフェメラルコンテナは後から削除できない。Pod を作り直すまで残る。
#     この測定専用の走りとして使うこと。
#
# gRPC は HTTP/2 の長寿命接続なのでカウンタは積算値。窓の前後で差分を取る。
set -u
NS=exp
REPO=/home/mizuki/ダウンロード/msa
DIR=$REPO/km2/experiments/edge-traffic
K6DIR=$REPO/km2/experiments/k6   # 2026-11-23 修正: 9/18 の整理で k6/ は km2/experiments/k6 へ移った (旧 $DIR/k6 は存在しない)
PROBE_IMG=${PROBE_IMG:-nicolaka/netshoot}
CASES=${CASES:-"100:0 0:200"}
WARM=${WARM:-30}
MEAS=${MEAS:-180}
PRE_VUS=${PRE_VUS:-300}
MAX_VUS=${MAX_VUS:-3000}
# 2026-11-23 追加 (ρ を測った mix-cpu5 と同じ条件で測り直すため)。既定は 9/08 の測定と同じ (何もしない)
NO_REUSE=${NO_REUSE:-0}            # k6/checkout.js の NO_REUSE
CLOSE_EVERY=${CLOSE_EVERY:-0}      # k6/checkout.js の CLOSE_EVERY (要求 N 回に 1 回接続を閉じる)。mix-cpu5 は 20
LIMIT_OVERRIDE=${LIMIT_OVERRIDE-""}  # 例 "frontend=3000m productcatalogservice=3000m adservice=1000m" (mix-cpu5 と同じ)。requests はマニフェストのまま
GRPC_LB=${GRPC_LB:-0}              # 1 = round_robin + headless (mix-cpu5 と同じ、measure-mix-cpu.sh と同じ処理)。0 = 9/08 と同じ
GRPC_RESOLVE_EVERY=${GRPC_RESOLVE_EVERY:-30}
LB_IMG_FRONTEND=${LB_IMG_FRONTEND:-mizuki0118/mygo:frontend-lb}
LB_IMG_CHECKOUT=${LB_IMG_CHECKOUT:-mizuki0118/mygo:checkout-lb}
LB_IMG_RECO=${LB_IMG_RECO:-mizuki0118/mygo:reco-lb}
CSV=${CSV:-$DIR/results-edge-pairs.csv}
LOG=${LOG:-$DIR/edge-pairs.log}
WORK=${WORK:-/tmp/edge-pairs-$$}
NORMAL=(frontend checkoutservice cartservice productcatalogservice currencyservice \
        paymentservice shippingservice emailservice recommendationservice adservice)
mkdir -p "$WORK"
exec > >(tee -a "$LOG") 2>&1
echo "================ EDGE-PAIRS START $(date -Is) cases=[$CASES] warm=${WARM}s meas=${MEAS}s no_reuse=$NO_REUSE close_every=$CLOSE_EVERY limits=[${LIMIT_OVERRIDE:-マニフェスト}] grpc_lb=$GRPC_LB ================"
[ -s "$CSV" ] || echo "case,src,dst,bytes_sent,bytes_received,segs_out,segs_in,rtt_ms,minrtt_ms,conns" > "$CSV"

deploy(){
  echo "---- deploy normal (1台固定, HPA無し) ----"
  kubectl delete hpa --all -n $NS >/dev/null 2>&1
  kubectl delete deploy --all -n $NS >/dev/null 2>&1
  for i in $(seq 1 40);do [ -z "$(kubectl get deploy -n $NS -o name 2>/dev/null)" ]&&break;sleep 3;done
  for f in "${NORMAL[@]}"; do kubectl apply -f $REPO/km2/normal/$f.yaml -n $NS >/dev/null; done
  kubectl apply -f $REPO/km2/normal/redis-cart.yaml -n $NS >/dev/null 2>&1 || true
  for d in $(kubectl get deploy -n $NS -o jsonpath='{range .items[*]}{.metadata.name}{" "}{end}'); do
    kubectl patch deploy/$d -n $NS --type=merge -p '{"spec":{"template":{"metadata":{"annotations":{"sidecar.istio.io/inject":"false"}}}}}' >/dev/null 2>&1||true
    kubectl scale deploy/$d -n $NS --replicas=1 >/dev/null 2>&1||true; done
  # 2026-11-23 追加: limits の上書きと gRPC 振り分け (measure-mix-cpu.sh の deploy と同じ処理)
  for kv in $LIMIT_OVERRIDE; do
    kubectl set resources deploy/${kv%%=*} -n $NS --limits=cpu=${kv#*=} >/dev/null && echo "  limits 上書き: ${kv%%=*} cpu=${kv#*=} (requests はそのまま)"
  done
  if [ "$GRPC_LB" = 1 ]; then
    echo "  gRPC 負荷分散: round_robin + headless Service (引き直し ${GRPC_RESOLVE_EVERY}s)"
    { printf '{"deploy":'; kubectl get deploy -n $NS -o json; printf ',"svc":'; kubectl get svc -n $NS -o json; printf '}'; } \
      | NS="$NS" GRPC_RESOLVE_EVERY="$GRPC_RESOLVE_EVERY" LB_IMG_FRONTEND="$LB_IMG_FRONTEND" \
        LB_IMG_CHECKOUT="$LB_IMG_CHECKOUT" LB_IMG_RECO="$LB_IMG_RECO" LB_IMAGES_ONLY=0 \
        python3 "$REPO/km2/experiments/summer2026/grpc_lb_patch.py" > "$WORK/lb.sh"
    bash "$WORK/lb.sh"
  fi
  for d in $(kubectl get deploy -n $NS -o jsonpath='{range .items[*]}{.metadata.name}{" "}{end}'); do
    kubectl rollout status deploy/$d -n $NS --timeout=300s >/dev/null 2>&1||echo "  !! rollout 未完了: $d"; done
  # 2026-11-23 追加: 振り分けの差し替えで古い Pod が Terminating のまま残ると、観測コンテナの追加対象に混ざるので消えるまで待つ
  for i in $(seq 1 60); do kubectl get pods -n $NS --no-headers 2>/dev/null | grep -q Terminating || break; sleep 5; done
  echo "  枠(req/上限lim): $(kubectl get deploy -n $NS -o jsonpath='{range .items[*]}{.metadata.name}={range .spec.template.spec.containers[*]}{.name}:{.resources.requests.cpu}/{.resources.limits.cpu}{","}{end}{" "}{end}')"
}

# IP → サービス名の対応表(Pod IP と ClusterIP の両方)
make_map(){
  : > "$WORK/ipmap.txt"
  kubectl get pods -n $NS -o jsonpath='{range .items[*]}{.status.podIP}{" "}{.metadata.labels.app}{"\n"}{end}' \
    | grep -v '^ ' >> "$WORK/ipmap.txt"
  kubectl get svc -n $NS -o jsonpath='{range .items[*]}{.spec.clusterIP}{" "}{.metadata.name}{"\n"}{end}' \
    | grep -v '^None' >> "$WORK/ipmap.txt"
  echo "  IP対応表 $(wc -l < "$WORK/ipmap.txt") 件"
}

PODS=()
add_probes(){
  echo "---- 各Podにネットワーク観測用のエフェメラルコンテナを追加 ----"
  PODS=($(kubectl get pods -n $NS -o jsonpath='{range .items[*]}{.metadata.name}{"\n"}{end}' | grep -Ev 'k6load|promq'))
  for p in "${PODS[@]}"; do
    kubectl debug -n $NS "$p" --image=$PROBE_IMG --profile=netadmin -c netprobe --attach=false -q -- sleep 7200 >/dev/null 2>&1 || echo "  !! debug失敗: $p"
  done
  for i in $(seq 1 60); do
    local ready=0
    for p in "${PODS[@]}"; do
      st=$(kubectl get pod -n $NS "$p" -o jsonpath='{range .status.ephemeralContainerStatuses[?(@.name=="netprobe")]}{.state}{end}' 2>/dev/null)
      case "$st" in *running*) ready=$((ready+1));; esac
    done
    echo "  起動 $ready/${#PODS[@]}"
    [ "$ready" -eq "${#PODS[@]}" ] && return 0
    sleep 10
  done
  echo "  !! 全部は起動しなかった。取れた分だけで続行"
}

snap(){ local out=$1
  : > "$out"
  for p in "${PODS[@]}"; do
    echo "### $p" >> "$out"
    # kubectl exec の出力をファイルへ直接リダイレクトすると空になる(2026-09-08 に踏んだ)。
    # パイプを1段挟むと正しくストリームされる。
    kubectl exec -n $NS "$p" -c netprobe -- ss -tin state established 2>/dev/null | cat >> "$out" || true
  done
}

run_case(){ local rate=$1 brw=$2
  local label="購入${rate}_閲覧${brw}"
  echo "==== $label  $(date -Is) ===="
  kubectl create configmap k6-script -n $NS --from-file=checkout.js=$K6DIR/checkout.js --dry-run=client -o yaml | kubectl apply -f - >/dev/null 2>&1
  kubectl delete job k6load -n $NS --ignore-not-found --wait=true >/dev/null 2>&1
  sed -e "s/__RATE__/$rate/" -e "s/__BROWSE__/$brw/" -e "s/__WARM__/$WARM/" -e "s/__MEAS__/$MEAS/" \
      -e "s/__PRE__/$PRE_VUS/" -e "s/__MAX__/$MAX_VUS/" -e "s/__NOREUSE__/$NO_REUSE/" -e "s/__CLOSEEVERY__/$CLOSE_EVERY/" "$K6DIR/k6-job.yaml" | kubectl apply -f - -n $NS >/dev/null
  local pod=""
  for i in $(seq 1 40);do pod=$(kubectl get pods -n $NS -l app=k6load --sort-by=.metadata.creationTimestamp -o jsonpath='{.items[-1].metadata.name}' 2>/dev/null)
    [ -n "$pod" ]&&[ "$(kubectl get pod $pod -n $NS -o jsonpath='{.status.phase}' 2>/dev/null)" = Running ]&&break; sleep 3;done
  sleep $WARM
  echo "  スナップショットA $(date -Is)"; snap "$WORK/A-$label.txt"
  sleep $MEAS
  echo "  スナップショットB $(date -Is)"; snap "$WORK/B-$label.txt"
  python3 "$DIR/edge_pairs.py" "$WORK/A-$label.txt" "$WORK/B-$label.txt" "$WORK/ipmap.txt" "$CSV" "$MEAS" "$label"
}

deploy
add_probes
make_map
for cs in $CASES; do run_case "${cs%%:*}" "${cs##*:}"; done
kubectl delete job k6load -n $NS --ignore-not-found >/dev/null 2>&1
echo "作業ディレクトリ: $WORK"
echo "================ EDGE-PAIRS DONE $(date -Is) ================"
