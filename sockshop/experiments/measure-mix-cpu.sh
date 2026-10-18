#!/usr/bin/env bash
# Sock Shop: 配合 (購入 + 閲覧) ごとの各サービスの CPU — ρ (閲覧 1 周 ÷ 購入 1 周の CPU) を求める本測定 (2026-10-19)
#
# km2/experiments/rightsizing/measure-mix-cpu.sh (Online Boutique の mix-cpu2) と同じ手順。違い:
#   * アプリ固有の設定 (サービス一覧・マニフェスト・k6 シナリオ sockshop.js)。gRPC の振り分けは無い
#   * 状態を持つもの (DB・rabbitmq) も CPU は記録するが、台数は常に 1
#   * k6 の setup() で利用者を登録するので、負荷の開始時刻を k6 のログ (@@@K6_START@@@ <ms>) から取り、
#     計測窓 = 開始 + WARM 〜 + MEAS を出す (Pod の起動時刻からは出さない。登録にかかる時間ぶんずれるため)
#   * サイクルごとに全 Deployment を消して立て直す (DB の中身も初期化される)。立て直し後に慣らし負荷を流して捨てる (Java の JIT)
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

# 購入 {0,8,16,24} × 閲覧 {0,40,80,120} から b0v0 を除いた 15 点。Node の front-end は 1 コアで頭打ちになるので、
# 最も重い b24v120 でも 1 コアを下回るように選んだ (スモーク b10v50 で front-end 460m。予備測定からの足し算より高く出た)
POINTS=${POINTS:-"b8 b16 b24 v40 v80 v120 b8v40 b8v80 b8v120 b16v40 b16v80 b16v120 b24v40 b24v80 b24v120"}
REPLICAS=${REPLICAS:-1}
CYCLES=${CYCLES:-4}
WARM=${WARM:-60}
MEAS=${MEAS:-180}
SETTLE=${SETTLE:-30}
PREWARM=${PREWARM:-180}
PREWARM_POINT=${PREWARM_POINT:-b20v100}
PRE_VUS=${PRE_VUS:-50}
MAX_VUS=${MAX_VUS:-400}
NUSERS=${NUSERS:-200}
REST_POINT=${REST_POINT:-0}
CSV=${CSV:-$DIR/experiments/results-mix-cpu.csv}
SERIES=${SERIES:-${CSV%.csv}-series.csv}
LOG=${LOG:-${CSV%.csv}.log}
PROM="http://prometheus-grafana-kube-pr-prometheus.monitoring.svc:9090"
ROLLOUT=300s

exec > >(tee -a "$LOG") 2>&1
echo "================ SOCKSHOP MIX-CPU START $(date -Is) points=[$POINTS] replicas=[$REPLICAS] cycles=$CYCLES warm=${WARM}s meas=${MEAS}s prewarm=${PREWARM}s@$PREWARM_POINT nusers=$NUSERS (HPA無し) ================"

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

# k6 を流して終わるまで待つ。echo する値 = k6 Pod 名
run_k6(){ local b=$1 v=$2 warm=$3 meas=$4 pod i
  kubectl create configmap k6-script -n $NS --from-file=sockshop.js=$DIR/k6/sockshop.js --dry-run=client -o yaml | kubectl apply -n $NS -f - >/dev/null 2>&1
  kubectl delete job k6load -n $NS --ignore-not-found --wait=true >/dev/null 2>&1
  sed -e "s/__RATE__/$b/;s/__BROWSE__/$v/;s/__WARM__/$warm/;s/__MEAS__/$meas/;s/__PRE__/$PRE_VUS/;s/__MAX__/$MAX_VUS/;s/__NUSERS__/$NUSERS/" \
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
  if [ "$PREWARM" -gt 0 ]; then
    local bv; bv=$(parse_point $PREWARM_POINT)
    echo "  慣らし負荷 ${PREWARM}s ($PREWARM_POINT, 結果は捨てる)"
    local pod; pod=$(run_k6 ${bv% *} ${bv#* } 0 $PREWARM)
    kubectl logs $pod -n $NS 2>/dev/null | grep -E 'setup:' | sed 's/^/  /'
    kubectl delete job k6load -n $NS --ignore-not-found --wait=true >/dev/null 2>&1
  fi
}

run_point(){ local cyc=$1 pt=$2 reps=$3 bv b v pod
  bv=$(parse_point "$pt"); b=${bv% *}; v=${bv#* }
  echo "==== [cyc$cyc][×${reps}台] $pt (購入=$b 閲覧=$v 周/秒) $(date -Is) ===="
  pod=$(run_k6 $b $v $WARM $MEAS)
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

ensure_promq
for c in $(seq 1 $CYCLES); do
  echo "################ CYCLE $c / $CYCLES $(date -Is) ################"
  for n in $REPLICAS; do
    deploy "$n"
    for p in $(echo $POINTS | tr ' ' '\n' | shuf); do
      run_point "$c" "$p" "$n"
      [ "$REST_POINT" -gt 0 ] && sleep "$REST_POINT"
    done
  done
done
kubectl delete job k6load -n $NS --ignore-not-found >/dev/null 2>&1
echo "================ SOCKSHOP MIX-CPU DONE $(date -Is) ================"
