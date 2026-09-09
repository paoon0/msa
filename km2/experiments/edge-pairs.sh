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
DIR=$REPO/km2/experiments
K6DIR=$DIR/k6
PROBE_IMG=${PROBE_IMG:-nicolaka/netshoot}
CASES=${CASES:-"100:0 0:200"}
WARM=${WARM:-30}
MEAS=${MEAS:-180}
PRE_VUS=${PRE_VUS:-300}
MAX_VUS=${MAX_VUS:-3000}
CSV=${CSV:-$DIR/results-edge-pairs.csv}
LOG=${LOG:-$DIR/edge-pairs.log}
WORK=${WORK:-/tmp/edge-pairs-$$}
NORMAL=(frontend checkoutservice cartservice productcatalogservice currencyservice \
        paymentservice shippingservice emailservice recommendationservice adservice)
mkdir -p "$WORK"
exec > >(tee -a "$LOG") 2>&1
echo "================ EDGE-PAIRS START $(date -Is) cases=[$CASES] warm=${WARM}s meas=${MEAS}s ================"
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
  for d in $(kubectl get deploy -n $NS -o jsonpath='{range .items[*]}{.metadata.name}{" "}{end}'); do
    kubectl rollout status deploy/$d -n $NS --timeout=300s >/dev/null 2>&1||echo "  !! rollout 未完了: $d"; done
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
      -e "s/__PRE__/$PRE_VUS/" -e "s/__MAX__/$MAX_VUS/" "$K6DIR/k6-job.yaml" | kubectl apply -f - -n $NS >/dev/null
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
