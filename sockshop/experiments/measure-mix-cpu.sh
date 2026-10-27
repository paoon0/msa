#!/usr/bin/env bash
# Sock Shop: 配合 (購入 + 閲覧) ごとの各サービスの CPU — ρ (閲覧 1 周 ÷ 購入 1 周の CPU) を求める本測定 (2026-10-19)
#
# km2/experiments/rightsizing/measure-mix-cpu.sh (Online Boutique の mix-cpu2) と同じ手順。違い:
#   * アプリ固有の設定 (サービス一覧・マニフェスト・k6 シナリオ sockshop.js)。gRPC の振り分けは無い
#   * 状態を持つもの (DB・rabbitmq) も CPU は記録するが、台数は常に 1
#   * 負荷の開始時刻を k6 のログ (@@@K6_START@@@ <ms>) から取り、計測窓 = 開始 + WARM 〜 + MEAS を出す
#     (Pod の起動時刻からは出さない。k6 の setup() の時間ぶんずれるため)
#   * サイクルごとに全 Deployment を消して立て直す (DB の中身も初期化される)。立て直し後に慣らし負荷を流して捨てる (Java の JIT)
#   * 利用者の登録はサイクルの慣らしで 1 回だけ (2026-10-19)。各点は REGISTER=0 で登録済みの利用者を使い回す。
#     点ごとに登録すると、計測の直前に user・user-db へ OB には無い仕事が入り、user-db も点ごとに 200 人ずつ大きくなるため。
#     慣らしの登録が NUSERS 人そろわなかったときは、そのサイクルだけ従来どおり点ごとに登録する (ログに !! を出す)
#   * 冷却待ちと休憩は OB の mix-cpu2 と同じ (各点の前に CPU 温度 70℃ 以下まで待つ・最長 600 s、各点の後に 60 s 休む)
# HPA 無し・全サービス 1 台固定 (既定)。枠は sockshop/normal/ の測定用の仮のまま (HPA が無いので CPU 使用量には効かない)。
#
# 出力 (CSV の列は OB の results-mix-cpu2.csv と同じ。_write_mixpoint.py を共用):
#   $CSV    1 行 = 1 点 × 1 コンテナ
#   $SERIES 1 行 = 1 点 × 1 コンテナ × 10 秒 (計測窓の中だけ)
#
# 使い方:
#   bash /home/mizuki/ダウンロード/msa/sockshop/experiments/measure-mix-cpu.sh                       # 本走 (既定)
#   POINTS="b10v50" CYCLES=1 WARM=20 MEAS=60 PREWARM=30 CSV=/tmp/smoke.csv bash .../measure-mix-cpu.sh   # スモーク
set -u
NS=exp
REPO=/home/mizuki/ダウンロード/msa
DIR=$REPO/sockshop
MANIFEST_DIR=$DIR/normal
WRITER=$REPO/km2/experiments/rightsizing/_write_mixpoint.py

SERVICES=(front-end catalogue carts orders payment shipping user queue-master)
STATEFUL=(carts-db catalogue-db orders-db session-db user-db rabbitmq)

# 2026-10-20 (mix-cpu2b) 購入 {0,16,32,48} × 閲覧 {0,80,160,240} から b0v0 を除いた 15 点 (ユーザ確定)。
#   初回 (10/19) は {0,8,16,24} × {0,40,80,120} で「front-end は 1 コアで頭打ち」と見て選んだが、耐久試験
#   (measure-stress.sh、b100 / v400 / b40v200 まで取りこぼし ≤1%、front-end 約 1 コア) で外れたので 2 倍に広げた。
#   基準 b24v120 が格子の内側に入る (OB の基準 b50v150 も格子の内側)。
#   重い角 b48v240 も残して 15 点 (2026-10-20 ユーザ決定: 外した場合と外さない場合で ρ がどれだけ変わるかを解析で比べる)。
#   注意 (スモーク smoke-mix2b*.csv の観察): 1 台の b48v240 では front-end が 1027〜1055m に張り付き (10 秒値の揺れがほぼ無い、
#   絞り 0%、limits 2000m に未達、Node.js は 1 プロセス)、取りこぼし 購入 0.12%・閲覧 0.04%。同じ点の 2 台では合計 1.2〜1.5 コア使えた。
#   → 1 台のこの点の front-end の CPU は必要量より少なく記録されている (頭打ち)。隣の b48v160・b32v240 は平均 957・968m で揺れあり・取りこぼし 0。
POINTS=${POINTS:-"b16 b32 b48 v80 v160 v240 b16v80 b16v160 b16v240 b32v80 b32v160 b32v240 b48v80 b48v160 b48v240"}
REPLICAS=${REPLICAS:-"1 2"}     # 2026-10-20 OB の mix-cpu2 と同じく 1 台と 2 台 (ユーザ確定)
CYCLES=${CYCLES:-6}               # 2026-10-19 測り直し (mix-cpu2b) で OB の mix-cpu2 と同じ 6 に (初回は 4)
WARM=${WARM:-60}
MEAS=${MEAS:-180}
SETTLE=${SETTLE:-30}
PREWARM=${PREWARM:-300}           # 2026-10-19 180→300 s (probe10 試験で Java が落ち着くまで約 3 分)
PREWARM_POINT=${PREWARM_POINT:-b20v100}
PRE_VUS=${PRE_VUS:-50}
MAX_VUS=${MAX_VUS:-400}
NUSERS=${NUSERS:-200}
REST_POINT=${REST_POINT:-60}        # 2026-10-19 OB の mix-cpu2 と同じに (初回は 0)
COOL_TEMP=${COOL_TEMP:-70}          # 各点の前に coretemp の最高値がこの値以下になるまで待つ ("" で無効)
COOL_MAX_WAIT=${COOL_MAX_WAIT:-600}
# 段を下から上げる測定用 (2026-10-19、km2/experiments/rightsizing/measure-mix-cpu.sh と同じ。既定は従来どおり)。measure-stress.sh が使う
#   ORDER=asc 書いた順に流す / STOP_DROP_PCT=1 取りこぼしがこの % を超えたら残りを流さない / CYCLE_START=n サイクル番号の始まり
ORDER=${ORDER:-shuffle}
STOP_DROP_PCT=${STOP_DROP_PCT:-""}
CYCLE_START=${CYCLE_START:-1}
CSV=${CSV:-$DIR/experiments/results-mix-cpu2b.csv}   # 2026-10-20 測り直し。初回 (B′ 前) は results-mix-cpu.csv
SERIES=${SERIES:-${CSV%.csv}-series.csv}
LOG=${LOG:-${CSV%.csv}.log}
PROM="http://prometheus-grafana-kube-pr-prometheus.monitoring.svc:9090"
ROLLOUT=300s

exec > >(tee -a "$LOG") 2>&1
echo "================ SOCKSHOP MIX-CPU START $(date -Is) points=[$POINTS] replicas=[$REPLICAS] cycles=$CYCLES warm=${WARM}s meas=${MEAS}s prewarm=${PREWARM}s@$PREWARM_POINT nusers=$NUSERS rest=${REST_POINT}s cool=${COOL_TEMP:-なし}℃ (HPA無し、登録はサイクルに 1 回) ================"

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
promq(){ local q="$1" t="$2" i out; for i in 1 2 3 4 5;do ensure_promq
  out=$(kubectl exec promq -n $NS -- curl -s --max-time 25 "$PROM/api/v1/query" --data-urlencode "query=$q" --data-urlencode "time=$t" 2>/dev/null)
  [ -n "$out" ]&&{ echo "$out"; return; }; sleep 4; done; echo ""; }
promr(){ local q="$1" s="$2" e="$3" i out; for i in 1 2 3 4 5;do ensure_promq
  out=$(kubectl exec promq -n $NS -- curl -s --max-time 40 "$PROM/api/v1/query_range" --data-urlencode "query=$q" \
        --data-urlencode "start=$s" --data-urlencode "end=$e" --data-urlencode "step=10" 2>/dev/null)
  [ -n "$out" ]&&{ echo "$out"; return; }; sleep 4; done; echo ""; }

# k6 を流して終わるまで待つ。echo する値 = k6 Pod 名。prefix が空なら k6 が名前を作って登録、reg=0 なら登録を省く
run_k6(){ local b=$1 v=$2 warm=$3 meas=$4 prefix=${5:-} reg=${6:-1} pod i
  kubectl create configmap k6-script -n $NS --from-file=sockshop.js=$DIR/k6/sockshop.js --dry-run=client -o yaml | kubectl apply -n $NS -f - >/dev/null 2>&1
  kubectl delete job k6load -n $NS --ignore-not-found --wait=true >/dev/null 2>&1
  sed -e "s/__RATE__/$b/;s/__BROWSE__/$v/;s/__WARM__/$warm/;s/__MEAS__/$meas/;s/__PRE__/$PRE_VUS/;s/__MAX__/$MAX_VUS/;s/__NUSERS__/$NUSERS/;s/__PREFIX__/$prefix/;s/__REGISTER__/$reg/" \
    $DIR/k6/k6-job.yaml | kubectl apply -n $NS -f - >/dev/null
  local t0=$(date +%s)
  until kubectl logs -n $NS job/k6load 2>/dev/null | grep -q K6_DONE; do
    [ $(( $(date +%s) - t0 )) -gt $(( warm + meas + 900 )) ] && { echo "  !! k6 が終わらない" >&2; break; }
    sleep 5; done
  kubectl get pods -n $NS -l app=k6load --sort-by=.metadata.creationTimestamp -o jsonpath='{.items[-1].metadata.name}' 2>/dev/null; }

deploy(){ local reps=$1
  echo "---- deploy 分離 (アプリ ${reps} 台・状態を持つもの 1 台、HPA無し) ----"
  kubectl delete hpa --all -n $NS >/dev/null 2>&1
  kubectl delete job k6load -n $NS --ignore-not-found >/dev/null 2>&1
  kubectl delete deploy --all -n $NS >/dev/null 2>&1
  for i in $(seq 1 60);do [ -z "$(kubectl get pods -n $NS -o name 2>/dev/null | grep -v promq)" ]&&break;sleep 3;done
  kubectl apply -n $NS -f $MANIFEST_DIR/ >/dev/null
  for d in "${SERVICES[@]}";do kubectl scale deploy/$d -n $NS --replicas=$reps >/dev/null 2>&1||true;done
  for d in "${SERVICES[@]}" "${STATEFUL[@]}";do kubectl rollout status deploy/$d -n $NS --timeout=$ROLLOUT >/dev/null 2>&1||echo "  !! rollout 未完: $d";done
  sleep $SETTLE
  ensure_promq
  local code; code=$(kubectl exec promq -n $NS -- curl -s -o /dev/null -w '%{http_code}' --max-time 10 http://front-end:80/catalogue 2>/dev/null)
  echo "  front-end /catalogue → $code"
  echo "  deploy: $(kubectl get deploy -n $NS --no-headers 2>/dev/null | awk '{printf "%s=%s ",$1,$2}')"
  CYCLE_PREFIX=""
  if [ "$PREWARM" -gt 0 ]; then
    local bv; bv=$(parse_point $PREWARM_POINT)
    local pre="ss$(date +%s)"
    echo "  慣らし負荷 ${PREWARM}s ($PREWARM_POINT, 結果は捨てる)。利用者 $NUSERS 人をここで登録 (接頭辞 $pre)"
    local pod; pod=$(run_k6 ${bv% *} ${bv#* } 0 $PREWARM "$pre" 1)
    local st; st=$(kubectl logs $pod -n $NS 2>/dev/null | grep -oE 'setup: [^"]*' | head -1)
    echo "  $st"
    if echo "$st" | grep -q "setup: $NUSERS/$NUSERS users registered"; then CYCLE_PREFIX=$pre
    else echo "  !! 慣らしでの登録がそろわない。このサイクルは点ごとに登録する"; fi
    kubectl delete job k6load -n $NS --ignore-not-found --wait=true >/dev/null 2>&1
  else
    echo "  !! 慣らし無し (PREWARM=0) なので点ごとに登録する"
  fi
}

# 冷却待ちと休憩 (km2/experiments/rightsizing/measure-mix-cpu.sh と同じ)
cpu_temp(){ local m=0 f v; for f in /sys/class/hwmon/hwmon*/; do [ "$(cat ${f}name 2>/dev/null)" = coretemp ] || continue
  for v in $(cat ${f}temp*_input 2>/dev/null); do [ $(( v / 1000 )) -gt $m ] && m=$(( v / 1000 )); done; done
  [ $m -gt 0 ] && echo $m; }
cool_down(){ [ -z "$COOL_TEMP" ] && return; local t0=$(date +%s) t
  while :; do t=$(cpu_temp); [ -z "$t" ] && { echo "  (温度が読めないので冷却待ちなし)"; return; }
    [ "$t" -le "$COOL_TEMP" ] && break
    [ $(( $(date +%s) - t0 )) -ge "$COOL_MAX_WAIT" ] && { echo "  !! 冷却待ちが上限 ${COOL_MAX_WAIT}s に達した (${t}℃) のまま開始"; break; }
    sleep 10; done
  echo "  冷却待ち $(( $(date +%s) - t0 ))s → ${t}℃"; }
rest(){ [ "${1:-0}" -gt 0 ] && { echo "  休憩 ${1}s ($2)"; sleep "$1"; }; return 0; }

run_point(){ local cyc=$1 pt=$2 reps=$3 bv b v pod
  bv=$(parse_point "$pt"); b=${bv% *}; v=${bv#* }
  echo "==== [cyc$cyc][×${reps}台] $pt (購入=$b 閲覧=$v 周/秒) $(date -Is) ===="
  if [ -n "$CYCLE_PREFIX" ]; then pod=$(run_k6 $b $v $WARM $MEAS "$CYCLE_PREFIX" 0)
  else pod=$(run_k6 $b $v $WARM $MEAS "" 1); fi
  local logs; logs=$(kubectl logs "$pod" -n $NS 2>/dev/null)
  echo "$logs" | grep -oE 'setup: [^"]*' | sed 's/^/  /'
  local start_ms; start_ms=$(echo "$logs" | grep -oE '@@@K6_START@@@ [0-9]+' | tail -1 | awk '{print $2}')
  local summary; summary=$(echo "$logs" | sed -n '/@@@K6_BEGIN@@@/,/@@@K6_END@@@/p' | grep '{')
  if [ -z "$start_ms" ] || ! echo "$summary" | grep -q '{'; then
    echo "  !! 開始時刻か summary の回収に失敗 (pod=$pod)"; kubectl delete job k6load -n $NS --ignore-not-found >/dev/null 2>&1; return; fi
  local t_beg=$(( start_ms / 1000 + WARM ))
  local t_end=$(( t_beg + MEAS ))
  local win=$(( MEAS - 20 ))                       # 両端 10 秒ずつ内側
  local t_q=$(( t_end - 10 ))
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
  SUMMARY="$summary" USAGE="$USAGE" REQJSON="$REQ" LIMJSON="$LIM" THRJSON="$THR" THRTJSON="$THRT" \
    NODEJSON="$NODE" FREQJSON="$FREQ" TEMPJSON="$TEMP" SERJSON="$SER" \
    python3 "$WRITER" "$CSV" "$SERIES" "$cyc" "$pt" "$reps" "$b" "$v" "$t_beg"
  echo "  order_failed=$(echo "$summary" | python3 -c 'import json,sys;print(json.load(sys.stdin).get("order_failed"))')"
  kubectl get pods -n $NS --no-headers | awk '$4>0{print "  !! 再起動:",$1,$4}'
  kubectl delete job k6load -n $NS --ignore-not-found >/dev/null 2>&1
}

CYCLE_PREFIX=""
ensure_promq
for c in $(seq $CYCLE_START $(( CYCLE_START + CYCLES - 1 ))); do
  echo "################ CYCLE $c / $CYCLES $(date -Is) ################"
  # 1 台と 2 台の順番はサイクルごとに入れ替える (奇数 = 書いた順、偶数 = 逆順)。OB の mix-cpu2 と同じ (2026-10-20)
  if [ $(( c % 2 )) = 1 ]; then order=$REPLICAS; else order=$(echo $REPLICAS | tr ' ' '\n' | tac | tr '\n' ' '); fi
  for n in $order; do
    deploy "$n"
    if [ "$ORDER" = asc ]; then plist=$POINTS; else plist=$(echo $POINTS | tr ' ' '\n' | shuf); fi
    for p in $plist; do cool_down; run_point "$c" "$p" "$n"; rest $REST_POINT 点の後
      if [ -n "$STOP_DROP_PCT" ]; then
        dp=$(python3 -c '
import csv,sys
c,p,n,meas=sys.argv[2:6]; best=None
for r in csv.DictReader(open(sys.argv[1])):
    if r["cycle"]==c and r["point"]==p and r["replicas"]==n:
        b,v=float(r["buy_target"]),float(r["view_target"])
        d=[float(r["buy_dropped_win"] or 0)/(b*float(meas)) if b else 0, float(r["view_dropped_win"] or 0)/(v*float(meas)) if v else 0]
        best=100*max(d)
print("NA" if best is None else "%.3f"%best)' "$CSV" "$c" "$p" "$n" "$MEAS")
        echo "  取りこぼし (窓) ${dp}%"
        if [ "$dp" = NA ] || python3 -c "import sys;sys.exit(0 if float('$dp')>float('$STOP_DROP_PCT') else 1)"; then
          echo "  >> ${STOP_DROP_PCT}% 超 (または回収失敗) なので、このブロックの残りの点は流さない"; break; fi
      fi
    done
  done
done
kubectl delete job k6load -n $NS --ignore-not-found >/dev/null 2>&1
echo "================ SOCKSHOP MIX-CPU DONE $(date -Is) ================"
