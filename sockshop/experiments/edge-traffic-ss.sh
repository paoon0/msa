#!/usr/bin/env bash
# Sock Shop: サービスペアごとの通信量 (通信の太さ) を基準の負荷で実測する (2026-11-10 作成)。
#
# OB の km2/experiments/edge-traffic/edge-pairs.sh と同じ目的。違い:
#   * OB は各 Pod で ss -tin の累計を窓の前後で引き算した (gRPC は接続が張りっぱなし)。SS は HTTP で接続が開いて閉じるので、
#     窓の途中で閉じた接続を取りこぼさないよう、各 Pod の eth0 のパケットを窓のあいだ丸ごと録って (tcpdump) 数える。
#     数え方は edge_pairs_ss.py (1 つのパケットは送り手の Pod でだけ数える)。
#   * 窓は k6 自身の開始時刻 (@@@K6_START@@@) から決める: 開始 + WARM + 10 秒から MEAS − 20 秒 (measure-mix-cpu.sh の CPU と同じ内側の区間)。
#   * 立て方は measure-mix-cpu.sh と同じ (分離・全部 1 台・HPA 無し、慣らし 300 s で利用者を登録、各回は登録済みの利用者を使う)。
# Pod の netns へはエフェメラルコンテナ (nicolaka/netshoot, netadmin) で入る。エフェメラルコンテナは消せないので、最初に立て直す。
# tcpdump は Pod の中で CPU を使うので、この測定の CPU は使わない (バイト数だけを見る)。
#
# 出力: $CSV (1 行 = 1 回 × 送り手 × 宛先 × プロトコル)、$TIMES (1 回 1 行: k6 の窓と録った区間、k6 の集計)、$LOG、
#       pcap は $PCAP_DIR/<ラベル>/<pod>.pcap (大きいのでコミットしない)
# 使い方:
#   bash /home/mizuki/ダウンロード/msa/sockshop/experiments/edge-traffic-ss.sh                          # 本走 (b32v160 × 3 回)
#   REPEATS=1 MEAS=60 PREWARM=60 CSV=.../smoke/smoke-edge-ss.csv bash .../edge-traffic-ss.sh             # スモーク
set -u
NS=exp
REPO=/home/mizuki/ダウンロード/msa
DIR=$REPO/sockshop
EXP=$DIR/experiments
MANIFEST_DIR=$DIR/normal
SERVICES=(front-end catalogue carts orders payment shipping user queue-master)
STATEFUL=(carts-db catalogue-db orders-db session-db user-db rabbitmq)
PROBE_IMG=${PROBE_IMG:-nicolaka/netshoot}
POINT=${POINT:-b32v160}          # 基準の負荷 (2026-11-10 提案。ρ の格子の真ん中)
REPEATS=${REPEATS:-3}
WARM=${WARM:-60}
MEAS=${MEAS:-180}
PREWARM=${PREWARM:-300}
PREWARM_POINT=${PREWARM_POINT:-b20v100}
PRE_VUS=${PRE_VUS:-50}
MAX_VUS=${MAX_VUS:-400}
NUSERS=${NUSERS:-200}
REST=${REST:-60}
SNAPLEN=${SNAPLEN:-96}
CSV=${CSV:-$EXP/results-edge-ss.csv}
TIMES=${TIMES:-${CSV%.csv}-times.csv}
LOG=${LOG:-${CSV%.csv}.log}
PCAP_DIR=${PCAP_DIR:-$EXP/pcap-$(basename ${CSV%.csv})}
ROLLOUT=300s
mkdir -p "$PCAP_DIR"
exec > >(tee -a "$LOG") 2>&1
echo "================ SOCKSHOP EDGE-TRAFFIC START $(date -Is) point=$POINT repeats=$REPEATS warm=${WARM}s meas=${MEAS}s prewarm=${PREWARM}s@$PREWARM_POINT snaplen=$SNAPLEN (分離・1 台・HPA無し) ================"
echo "  版: commit=$(git -C $REPO rev-parse --short HEAD 2>/dev/null) dirty=$(git -C $REPO status --porcelain -- sockshop/experiments/edge-traffic-ss.sh sockshop/experiments/edge_pairs_ss.py sockshop/k6 sockshop/normal 2>/dev/null | wc -l)  VU=${PRE_VUS}/${MAX_VUS}  CSV=$CSV"

bv(){ local p=$1 b=0 v=0; [[ $p =~ ^b([0-9]+) ]] && b=${BASH_REMATCH[1]}; [[ $p =~ v([0-9]+)$ ]] && v=${BASH_REMATCH[1]}; echo "$b $v"; }

start_k6(){ local b=$1 v=$2 warm=$3 meas=$4 prefix=$5 reg=$6
  kubectl create configmap k6-script -n $NS --from-file=sockshop.js=$DIR/k6/sockshop.js --dry-run=client -o yaml | kubectl apply -n $NS -f - >/dev/null 2>&1
  kubectl delete job k6load -n $NS --ignore-not-found --wait=true >/dev/null 2>&1
  sed -e "s/__RATE__/$b/;s/__BROWSE__/$v/;s/__WARM__/$warm/;s/__MEAS__/$meas/;s/__PRE__/$PRE_VUS/;s/__MAX__/$MAX_VUS/;s/__NUSERS__/$NUSERS/;s/__PREFIX__/$prefix/;s/__REGISTER__/$reg/" \
    $DIR/k6/k6-job.yaml | kubectl apply -n $NS -f - >/dev/null; }
wait_k6(){ local t0=$(date +%s); until kubectl logs -n $NS job/k6load 2>/dev/null | grep -q K6_DONE; do
    [ $(( $(date +%s) - t0 )) -gt 1500 ] && { echo "  !! k6 が終わらない"; break; }; sleep 5; done; }

# --- 立て直し (measure-mix-cpu.sh の deploy と同じ、1 台) ---
echo "---- deploy 分離 (全部 1 台、HPA無し) ----"
kubectl delete hpa --all -n $NS >/dev/null 2>&1
kubectl delete job k6load -n $NS --ignore-not-found >/dev/null 2>&1
kubectl delete deploy --all -n $NS >/dev/null 2>&1
for i in $(seq 1 60);do [ -z "$(kubectl get pods -n $NS -o name 2>/dev/null | grep -v promq)" ]&&break;sleep 3;done
kubectl apply -n $NS -f $MANIFEST_DIR/ >/dev/null
for d in "${SERVICES[@]}";do kubectl scale deploy/$d -n $NS --replicas=1 >/dev/null 2>&1||true;done
for d in "${SERVICES[@]}" "${STATEFUL[@]}";do kubectl rollout status deploy/$d -n $NS --timeout=$ROLLOUT >/dev/null 2>&1||echo "  !! rollout 未完: $d";done
sleep 30
echo "  deploy: $(kubectl get deploy -n $NS --no-headers 2>/dev/null | awk '{printf "%s=%s ",$1,$2}')"
PREFIX="ss$(date +%s)"
read b v <<< "$(bv $PREWARM_POINT)"
echo "  慣らし負荷 ${PREWARM}s ($PREWARM_POINT, 捨てる)。利用者 $NUSERS 人をここで登録 (接頭辞 $PREFIX)"
start_k6 $b $v 0 $PREWARM "$PREFIX" 1; wait_k6
st=$(kubectl logs -n $NS job/k6load 2>/dev/null | grep -oE 'setup: [^"]*' | head -1); echo "  $st"
echo "$st" | grep -q "setup: $NUSERS/$NUSERS users registered" || { echo "  !! 登録がそろわない。中止"; exit 1; }
kubectl delete job k6load -n $NS --ignore-not-found --wait=true >/dev/null 2>&1

# --- 観測用のエフェメラルコンテナ ---
echo "---- 各 Pod に観測用のエフェメラルコンテナを追加 ($PROBE_IMG) ----"
PODS=($(kubectl get pods -n $NS -o jsonpath='{range .items[*]}{.metadata.name}{"\n"}{end}' | grep -Ev 'k6load|promq'))
for p in "${PODS[@]}"; do
  kubectl debug -n $NS "$p" --image=$PROBE_IMG --profile=netadmin -c netprobe --attach=false -q -- sleep 21600 >/dev/null 2>&1 || echo "  !! debug 失敗: $p"
done
for i in $(seq 1 60); do ready=0
  for p in "${PODS[@]}"; do case "$(kubectl get pod -n $NS "$p" -o jsonpath='{range .status.ephemeralContainerStatuses[?(@.name=="netprobe")]}{.state}{end}' 2>/dev/null)" in *running*) ready=$((ready+1));; esac; done
  [ "$ready" -eq "${#PODS[@]}" ] && break; sleep 10; done
echo "  起動 $ready/${#PODS[@]}"; [ "$ready" -eq "${#PODS[@]}" ] || { echo "  !! 全部は起動しなかった。中止"; exit 1; }

# --- IP 対応表 (Pod IP → deploy 名、ClusterIP → Service 名、送り手判定用に pod:<名前> IP) ---
MAP=$PCAP_DIR/ipmap.txt; : > $MAP
kubectl get pods -n $NS -o jsonpath='{range .items[*]}{.status.podIP}{" "}{.metadata.name}{"\n"}{end}' | grep -v '^ ' | \
  while read ip pod; do echo "$ip $(echo $pod | sed -E 's/-[a-f0-9]{6,}-[a-z0-9]+$//')"; echo "pod:$pod $ip"; done >> $MAP
kubectl get svc -n $NS -o jsonpath='{range .items[*]}{.spec.clusterIP}{" "}{.metadata.name}{"\n"}{end}' | grep -v '^None' >> $MAP
kubectl get svc -n kube-system -o jsonpath='{range .items[*]}{.spec.clusterIP}{" kube-system/"}{.metadata.name}{"\n"}{end}' >> $MAP
echo "  IP 対応表 $(wc -l < $MAP) 行"
[ -s "$TIMES" ] || echo "label,point,k6_start,cap_from,cap_to,k6_meas_from,k6_meas_to,margin_start_s,margin_end_s,buy_achieved,view_achieved,buy_dropped_win,view_dropped_win,failed_rate,view_failed" > "$TIMES"

# --- 本測定 ---
read b v <<< "$(bv $POINT)"
WIN=$(( MEAS - 20 ))
for r in $(seq 1 $REPEATS); do
  label="${POINT}-r$r"; pd=$PCAP_DIR/$label; mkdir -p $pd
  echo "==== $label (購入=$b 閲覧=$v 周/秒) $(date -Is) ===="
  start_k6 $b $v $WARM $MEAS "$PREFIX" 0
  start_ms=""; for i in $(seq 1 120); do start_ms=$(kubectl logs -n $NS job/k6load 2>/dev/null | grep -oE '@@@K6_START@@@ [0-9]+' | awk '{print $2}' | tail -1); [ -n "$start_ms" ] && break; sleep 2; done
  [ -z "$start_ms" ] && { echo "  !! k6 の開始時刻が取れない。この回は飛ばす"; kubectl delete job k6load -n $NS --ignore-not-found >/dev/null 2>&1; continue; }
  cap_from=$(( start_ms / 1000 + WARM + 10 + 1 ))     # 秒の切り上げぶん 1 秒足して、確実に k6 の窓の内側から始める
  echo "  k6 開始 $start_ms ms → 録る区間 $cap_from から ${WIN}s"
  while [ "$(date +%s)" -lt $cap_from ]; do sleep 0.5; done
  # k6 の Pod の IP も対応表に足す (対応表を作った後に立つので。無いと front-end → k6 の応答が other になる。2026-11-10 スモークで判明)
  k6ip=$(kubectl get pods -n $NS -l app=k6load -o jsonpath='{.items[-1].status.podIP}' 2>/dev/null); [ -n "$k6ip" ] && echo "$k6ip k6load" >> $MAP
  pids=()
  for p in "${PODS[@]}"; do
    ( kubectl exec -n $NS "$p" -c netprobe -- timeout $WIN tcpdump -i eth0 -nn -s $SNAPLEN -U -w - ip 2>/dev/null | cat > $pd/$p.pcap ) &
    pids+=($!)
  done
  # 引数なしの wait は exec > >(tee) のプロセス置換まで待って止まる (bash 5.2、2026-11-10 スモークで踏んだ)。PID を名指しで待つ
  wait "${pids[@]}"
  cap_to=$(date +%s)
  wait_k6
  summary=$(kubectl logs -n $NS job/k6load 2>/dev/null | sed -n '/@@@K6_BEGIN@@@/,/@@@K6_END@@@/p' | grep '{')
  python3 - "$label" "$POINT" "$start_ms" "$cap_from" "$cap_to" "$WARM" "$MEAS" "$summary" >> "$TIMES" <<'PY'
import sys, json
lab, pt, k6s, cf, ct, warm, meas, sm = sys.argv[1:9]
d = json.loads(sm) if sm.strip() else {}
kf = int(k6s) / 1000 + int(warm); kt = kf + int(meas)
print(','.join(map(str, [lab, pt, round(int(k6s) / 1000, 3), cf, ct, round(kf, 3), round(kt, 3), round(int(cf) - kf, 3), round(kt - int(ct), 3),
      round(d.get('iter_rate', 0), 2), round(d.get('browse_rate', 0), 2), d.get('dropped_win', 'NA'), d.get('browse_dropped_win', 'NA'),
      round(d.get('failed_rate', 0), 4), d.get('browse_failed', 'NA')])))
PY
  echo "  時刻と k6: $(tail -1 $TIMES)"
  python3 $EXP/edge_pairs_ss.py $pd $MAP "$CSV" "$label"
  kubectl get pods -n $NS --no-headers | awk '$4>0{print "  !! 再起動:",$1,$4}'
  kubectl delete job k6load -n $NS --ignore-not-found >/dev/null 2>&1
  [ $r -lt $REPEATS ] && { echo "  休憩 ${REST}s"; sleep $REST; }
done
echo "================ SOCKSHOP EDGE-TRAFFIC DONE $(date -Is) ================"
