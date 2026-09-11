#!/usr/bin/env bash
# 【2026-09-10】ICTer 2022 と同じ指標(communication affinity)で co-location の効果を測る。
#
# ICTer の定義: affinity = サービス間でやり取りされた「オンザワイヤの総バイト量」
#   (= アプリレベルのデータ量 + ネットワークのカプセル化オーバーヘッド)。tcpdump で計測。
#   アプリレベル量は配置を変えても不変で、減るのはカプセル化分だけ、と原典が明言している。
#   ICTer の3配置: Spreaded(overlay) / Colocated(bridge) / Merged(loopback)
#   本研究(単一ノード)には overlay が無いので、対応は:
#     normal = 別Pod・bridge 経由        → ICTer の Colocated 相当
#     front3 = frontend+reco+catalog 同居 → 一部が loopback(部分的 Merged)
#     mega   = 全部入り1Pod              → ほぼ全部 loopback(Merged 相当)
#
# 測り方: tcpdump の代わりに Pod の netns のインタフェース・カウンタ(/proc/net/dev)を読む。
#   デバイス層のバイト数なのでヘッダを含む = ICTer の「カプセル化込み」と同じ意味。
#   eth0 = Pod をまたぐ通信(veth+bridge)、lo = Pod 内の localhost 通信。
#   ※ cAdvisor は eth0 しか出さない(lo を集計しない)ため、netns を直接読む必要がある。
#   netns へはエフェメラルコンテナで入る(sudo 不要)。消せないが、アーム毎に Pod を作り直すので問題ない。
#
# 出力: results-icter-affinity.csv (cycle,arm,pod,iface,rx_bytes,tx_bytes,rx_pkts,tx_pkts,iters)
set -u
NS=exp
REPO=/home/mizuki/ダウンロード/msa
DIR=$REPO/km2/experiments
K6DIR=$DIR/k6
PROBE_IMG=${PROBE_IMG:-nicolaka/netshoot}
ARMS=${ARMS:-"normal front3 mega"}
RATE=${RATE:-100}
BROWSE=${BROWSE:-0}
REPLICAS=${REPLICAS:-1}
WARM=${WARM:-30}
MEAS=${MEAS:-180}
CYCLES=${CYCLES:-2}
PRE_VUS=${PRE_VUS:-300}
MAX_VUS=${MAX_VUS:-3000}
CSV=${CSV:-$DIR/results-icter-affinity.csv}
LOG=${LOG:-$DIR/icter-affinity.log}
WORK=${WORK:-/tmp/icter-aff-$$}
NORMAL=(frontend checkoutservice cartservice productcatalogservice currencyservice \
        paymentservice shippingservice emailservice recommendationservice adservice)
mkdir -p "$WORK"
exec > >(tee -a "$LOG") 2>&1
echo "================ ICTER-AFFINITY START $(date -Is) arms=[$ARMS] rate=${RATE}周/s reps=$REPLICAS warm=${WARM}s meas=${MEAS}s cycles=$CYCLES ================"
[ -s "$CSV" ] || echo "cycle,arm,pod,iface,rx_bytes,tx_bytes,rx_pkts,tx_pkts,iter_rate,meas" > "$CSV"

deploy(){ local arm=$1
  echo "---- deploy $arm (${REPLICAS}台固定, HPA無し, 枠はマニフェストのまま) ----"
  kubectl delete hpa --all -n $NS >/dev/null 2>&1
  kubectl delete deploy --all -n $NS >/dev/null 2>&1
  for i in $(seq 1 40);do [ -z "$(kubectl get deploy -n $NS -o name 2>/dev/null)" ]&&break;sleep 3;done
  case "$arm" in
    normal) for f in "${NORMAL[@]}"; do kubectl apply -f $REPO/km2/normal/$f.yaml -n $NS >/dev/null; done ;;
    front3) for y in $REPO/km2/frontrecocatalogcart/*.yaml; do
              case "$y" in *kustomization*|*loadgenerator*|*hpa-percontainer*) continue;; esac
              kubectl apply -f "$y" -n $NS >/dev/null; done ;;
    mega)   # 1台なので redis を外に出す必要が無い = ICTer の Merged に最も近い形
            kubectl apply -f $REPO/km2/all/all.yaml -n $NS >/dev/null ;;
  esac
  kubectl delete hpa --all -n $NS >/dev/null 2>&1
  for d in $(kubectl get deploy -n $NS -o jsonpath='{range .items[*]}{.metadata.name}{" "}{end}'); do
    kubectl patch deploy/$d -n $NS --type=merge -p '{"spec":{"template":{"metadata":{"annotations":{"sidecar.istio.io/inject":"false"}}}}}' >/dev/null 2>&1||true
    kubectl scale deploy/$d -n $NS --replicas=$REPLICAS >/dev/null 2>&1||true; done
  kubectl scale deploy/redis-cart -n $NS --replicas=1 >/dev/null 2>&1||true
  for d in $(kubectl get deploy -n $NS -o jsonpath='{range .items[*]}{.metadata.name}{" "}{end}'); do
    kubectl rollout status deploy/$d -n $NS --timeout=300s >/dev/null 2>&1||echo "  !! rollout 未完了: $d"; done
  echo "  deploy: $(kubectl get deploy -n $NS --no-headers 2>/dev/null | awk '{printf "%s=%s ",$1,$2}')"
}

ensure_promq(){ [ "$(kubectl get pod promq -n $NS -o jsonpath='{.status.phase}' 2>/dev/null)" = Running ] && return
  kubectl delete pod promq -n $NS --ignore-not-found >/dev/null 2>&1
  kubectl run promq -n $NS --image=curlimages/curl:latest --restart=Never --command -- sleep 86400 >/dev/null 2>&1
  for i in $(seq 1 30);do [ "$(kubectl get pod promq -n $NS -o jsonpath='{.status.phase}' 2>/dev/null)" = Running ]&&break;sleep 2;done; }
promq(){ local q="$1" i out; for i in 1 2 3;do ensure_promq
  out=$(kubectl exec promq -n $NS -- curl -s --max-time 25 "http://prometheus-grafana-kube-pr-prometheus.monitoring.svc:9090/api/v1/query" --data-urlencode "query=$q" 2>/dev/null)
  [ -n "$out" ]&&{ echo "$out"; return; }; sleep 4; done; echo ""; }
scalar(){ python3 -c "import sys,json;r=json.load(sys.stdin).get('data',{}).get('result',[]);print(round(float(r[0]['value'][1]),1) if r else 0)" 2>/dev/null; }

PODS=()
add_probes(){
  echo "---- 各Podに観測用エフェメラルコンテナを追加 ----"
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
    [ "$ready" -eq "${#PODS[@]}" ] && { echo "  起動 $ready/${#PODS[@]}"; return 0; }
    sleep 10
  done
  echo "  !! 全部は起動しなかった($ready/${#PODS[@]})。取れた分で続行"
}

# /proc/net/dev をそのまま保存(kubectl exec の出力は必ずパイプを1段挟む: 直接リダイレクトだと空になる)
snap(){ local out=$1
  : > "$out"
  for p in "${PODS[@]}"; do
    echo "### $p" >> "$out"
    kubectl exec -n $NS "$p" -c netprobe -- cat /proc/net/dev 2>/dev/null | cat >> "$out" || true
  done
  # k6 Pod は netprobe を入れていないので cAdvisor 側で拾う(クライアント辺の切り分け用)
}

run_case(){ local cyc=$1 arm=$2
  echo "==== [cyc$cyc][$arm] 購入=${RATE}周/s $(date -Is) ===="
  kubectl create configmap k6-script -n $NS --from-file=checkout.js=$K6DIR/checkout.js --dry-run=client -o yaml | kubectl apply -f - >/dev/null 2>&1
  kubectl delete job k6load -n $NS --ignore-not-found --wait=true >/dev/null 2>&1
  sed -e "s/__RATE__/$RATE/" -e "s/__BROWSE__/$BROWSE/" -e "s/__WARM__/$WARM/" -e "s/__MEAS__/$MEAS/" \
      -e "s/__PRE__/$PRE_VUS/" -e "s/__MAX__/$MAX_VUS/" "$K6DIR/k6-job.yaml" | kubectl apply -f - -n $NS >/dev/null
  local pod=""
  for i in $(seq 1 40);do pod=$(kubectl get pods -n $NS -l app=k6load --sort-by=.metadata.creationTimestamp -o jsonpath='{.items[-1].metadata.name}' 2>/dev/null)
    [ -n "$pod" ]&&[ "$(kubectl get pod $pod -n $NS -o jsonpath='{.status.phase}' 2>/dev/null)" = Running ]&&break; sleep 3;done
  sleep $WARM
  echo "  スナップショットA $(date -Is)"; snap "$WORK/A-$cyc-$arm.txt"
  sleep $MEAS
  echo "  スナップショットB $(date -Is)"; snap "$WORK/B-$cyc-$arm.txt"
  # k6 の実測レート(周/s)を回収
  local it=""
  for i in $(seq 1 60); do
    logs=$(kubectl logs "$pod" -n $NS 2>/dev/null)
    echo "$logs" | grep -q '@@@K6_END@@@' && { it=$(echo "$logs" | sed -n 's/.*"m_started_rate"[: ]*\([0-9.]*\).*/\1/p' | head -1); break; }
    sleep 5
  done
  [ -z "$it" ] && it=$RATE
  CYC="$cyc" ARM="$arm" ITER="$it" MEAS="$MEAS" python3 "$DIR/icter_affinity.py" "$WORK/A-$cyc-$arm.txt" "$WORK/B-$cyc-$arm.txt" "$CSV"
  # k6 Pod の通信量(= クライアント辺)。normal では eth0 にサービス間通信と混ざるので、
  # これを差し引かないと ICTer の「サービス間 affinity」にならない。cAdvisor から取る。
  local KRX KTX KRP KTP
  KRX=$(promq "sum(increase(container_network_receive_bytes_total{namespace=\"$NS\",pod=~\"k6load.*\"}[${MEAS}s]))" | scalar)
  KTX=$(promq "sum(increase(container_network_transmit_bytes_total{namespace=\"$NS\",pod=~\"k6load.*\"}[${MEAS}s]))" | scalar)
  KRP=$(promq "sum(increase(container_network_receive_packets_total{namespace=\"$NS\",pod=~\"k6load.*\"}[${MEAS}s]))" | scalar)
  KTP=$(promq "sum(increase(container_network_transmit_packets_total{namespace=\"$NS\",pod=~\"k6load.*\"}[${MEAS}s]))" | scalar)
  echo "$cyc,$arm,k6load,eth0,${KRX:-0},${KTX:-0},${KRP:-0},${KTP:-0},$it,$MEAS" >> "$CSV"
  echo "  k6(クライアント辺): rx=$(python3 -c "print(f'{float('${KRX:-0}')/1e6:.1f}')")MB tx=$(python3 -c "print(f'{float('${KTX:-0}')/1e6:.1f}')")MB"
  kubectl delete job k6load -n $NS --ignore-not-found >/dev/null 2>&1
}

for c in $(seq 1 $CYCLES); do
  for arm in $ARMS; do
    deploy "$arm"; add_probes; run_case "$c" "$arm"
  done
done
echo "作業ディレクトリ: $WORK"
echo "================ ICTER-AFFINITY DONE $(date -Is) ================"
