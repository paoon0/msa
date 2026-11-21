#!/usr/bin/env bash
# Sock Shop: HPA 下で同居させたときの台数 (引きずり) を測る (2026-11-10 作成)。OB の pdist-k3 (summer2026/bundle-vs-loss2.sh の
# RESET_EACH_POINT=1) と同じ手順を SS 用に書いたもの。
#
# 手順 (サイクル × アーム ごと):
#   1. 全部消して立て直す (アームのマニフェスト)。枠 (requests) を RSTABLE の値にする (limits はマニフェストのまま 2000m)
#   2. HPA 無し・1 台で慣らし負荷 (PREWARM 秒、PREWARM_POINT) を流して捨てる。利用者 NUSERS 人をここで登録
#   3. 点 (POINTS) ごとに: 冷却待ち → HPA を消して全アプリを 1 台に戻す (DB 等は常に 1 台) → 全台 Ready を待つ →
#      枠を確かめる → HPA を作る → k6 (WARM + MEAS 秒、登録済みの利用者) → SAMPLE 秒ごとに HPA と台数を記録 → CPU を Prometheus から
# HPA: アプリ (状態を持たないもの) だけ。ContainerResource (コンテナ別) で目標 HPA_TARGET%、HPA_MIN〜HPA_MAX 台、
#      様子見 増 SU_WIN 秒 / 減 SD_WIN 秒 (pdist-k3 と同じ値が既定)。
# アーム: normal = 分離 (sockshop/normal/)、arm1 = 購入型 6 つを 1 Pod (sockshop/variants/arm1/buygroup.yaml、
#         呼び出しは Service 名のまま = 通信の近さの得は入らない)。
# 台数の時系列の t_rel は k6 自身の開始時刻 (@@@K6_START@@@) から (OB は k6 の Pod が Running になった時刻から)。
#
# 出力: $CSV (1 行 = 1 点 × 1 コンテナ、_write_hpapoint_ss.py)、$TL (台数の時系列、km2/.../sample_hpa.py の形式)、$LOG
# 使い方 (スモーク): ARMS="normal arm1" CYCLES=3 CSV=.../smoke/smoke-hpa-arm1.csv bash .../hpa-pair-ss.sh
set -u
NS=exp
REPO=/home/mizuki/ダウンロード/msa
DIR=$REPO/sockshop
EXP=$DIR/experiments
SAMPLER=$REPO/km2/experiments/summer2026/sample_hpa.py
WRITER=$EXP/_write_hpapoint_ss.py
STATEFUL=(carts-db catalogue-db orders-db session-db user-db rabbitmq)
ARMS=${ARMS:-"normal arm1"}
POINTS=${POINTS:-"b48 b32v160 b16v160 b48v240"}   # 2026-11-10 案 (購入だけ・基準・閲覧寄り・総量最大)。すべて mix-cpu3b の格子の点
CYCLES=${CYCLES:-3}
WARM=${WARM:-180}
MEAS=${MEAS:-240}
SAMPLE=${SAMPLE:-15}
PREWARM=${PREWARM:-300}
PREWARM_POINT=${PREWARM_POINT:-b20v100}
PRE_VUS=${PRE_VUS:-50}
MAX_VUS=${MAX_VUS:-400}
NUSERS=${NUSERS:-200}
HPA_MIN=${HPA_MIN:-1}; HPA_MAX=${HPA_MAX:-12}; HPA_TARGET=${HPA_TARGET:-70}; SU_WIN=${SU_WIN:-30}; SD_WIN=${SD_WIN:-60}
RSTABLE=${RSTABLE:-$EXP/rightsize-ss-k3.csv}
# 2026-11-10 案 3: Java のコンテナだけ readinessProbe の initialDelaySeconds をこの秒数にする (空 = マニフェストのまま 10 s)。
#   スモーク smoke-hpa-arm1 で、新しく立った Java の Pod が最初の 1〜3 分に 0.7〜1.4 コア使い、それを HPA が見て暴走したため。
#   HPA は Ready でない Pod の CPU を判断に入れない。マニフェストは変えず、apply の後に Deployment を書き換える
JAVA_READY_DELAY=${JAVA_READY_DELAY:-}
JAVA_CONTAINERS=${JAVA_CONTAINERS:-"carts orders shipping queue-master"}
POINT_SETTLE=${POINT_SETTLE:-30}
REST_POINT=${REST_POINT:-60}
COOL_TEMP=${COOL_TEMP:-70}; COOL_MAX_WAIT=${COOL_MAX_WAIT:-600}
SHUFFLE_SEED=${SHUFFLE_SEED:-1}
CSV=${CSV:-$EXP/results-hpa-ss.csv}
TL=${TL:-${CSV%.csv}-timeline.csv}
LOG=${LOG:-${CSV%.csv}.log}
PROM="http://prometheus-grafana-kube-pr-prometheus.monitoring.svc:9090"
exec > >(tee -a "$LOG") 2>&1
echo "================ SOCKSHOP HPA-PAIR START $(date -Is) arms=[$ARMS] points=[$POINTS] cycles=$CYCLES warm=${WARM}s meas=${MEAS}s HPA=${HPA_TARGET}%/${HPA_MIN}-${HPA_MAX}台 増${SU_WIN}s/減${SD_WIN}s 開始1台 prewarm=${PREWARM}s@$PREWARM_POINT cool=${COOL_TEMP}℃ java_ready_delay=${JAVA_READY_DELAY:-マニフェストのまま} ================"
echo "  版: commit=$(git -C $REPO rev-parse --short HEAD 2>/dev/null) dirty=$(git -C $REPO status --porcelain -- sockshop/experiments/hpa-pair-ss.sh sockshop/experiments/_write_hpapoint_ss.py sockshop/experiments/rightsize-ss-k3.csv sockshop/variants sockshop/k6 sockshop/normal km2/experiments/summer2026/sample_hpa.py 2>/dev/null | wc -l)  枠=$RSTABLE  VU=${PRE_VUS}/${MAX_VUS}  CSV=$CSV"
REQ=$(awk -F, 'NR>1{printf "%s=%s ",$1,$2}' $RSTABLE); echo "  枠: $REQ"
[ -s "$TL" ] || echo "cycle,arm,target_rate,limit_x,browse_rate,t_rel,deploy,container,hpa_util_pct,current_replicas,desired_replicas,ready_replicas,pending_pods,ns_running_cores,ns_pending_cores,point,start_replicas" > "$TL"

bv(){ local p=$1 b=0 v=0; [[ $p =~ ^b([0-9]+) ]] && b=${BASH_REMATCH[1]}; [[ $p =~ v([0-9]+)$ ]] && v=${BASH_REMATCH[1]}; echo "$b $v"; }
apps_of(){ case $1 in normal) echo "front-end catalogue carts orders payment shipping user queue-master";; arm1) echo "front-end catalogue buygroup";; *) echo "!! 不明なアーム $1" >&2; exit 1;; esac; }
ensure_promq(){ [ "$(kubectl get pod promq -n $NS -o jsonpath='{.status.phase}' 2>/dev/null)" = Running ] && return
  kubectl delete pod promq -n $NS --ignore-not-found >/dev/null 2>&1
  kubectl run promq -n $NS --image=curlimages/curl:latest --restart=Never --command -- sleep 86400 >/dev/null 2>&1
  for i in $(seq 1 30);do [ "$(kubectl get pod promq -n $NS -o jsonpath='{.status.phase}' 2>/dev/null)" = Running ]&&break;sleep 2;done; }
promq(){ local q="$1" t="$2" i out; for i in 1 2 3 4 5;do ensure_promq
  out=$(kubectl exec promq -n $NS -- curl -s --max-time 25 "$PROM/api/v1/query" --data-urlencode "query=$q" --data-urlencode "time=$t" 2>/dev/null)
  [ -n "$out" ]&&{ echo "$out"; return; }; sleep 4; done; echo ""; }
start_k6(){ local b=$1 v=$2 warm=$3 meas=$4 prefix=$5 reg=$6
  kubectl create configmap k6-script -n $NS --from-file=sockshop.js=$DIR/k6/sockshop.js --dry-run=client -o yaml | kubectl apply -n $NS -f - >/dev/null 2>&1
  kubectl delete job k6load -n $NS --ignore-not-found --wait=true >/dev/null 2>&1
  sed -e "s/__RATE__/$b/;s/__BROWSE__/$v/;s/__WARM__/$warm/;s/__MEAS__/$meas/;s/__PRE__/$PRE_VUS/;s/__MAX__/$MAX_VUS/;s/__NUSERS__/$NUSERS/;s/__PREFIX__/$prefix/;s/__REGISTER__/$reg/" \
    $DIR/k6/k6-job.yaml | kubectl apply -n $NS -f - >/dev/null; }
k6_done(){ kubectl logs -n $NS job/k6load 2>/dev/null | grep -q K6_DONE; }
cpu_temp(){ local m=0 f v; for f in /sys/class/hwmon/hwmon*/; do [ "$(cat ${f}name 2>/dev/null)" = coretemp ] || continue
  for v in $(cat ${f}temp*_input 2>/dev/null); do [ $(( v / 1000 )) -gt $m ] && m=$(( v / 1000 )); done; done; [ $m -gt 0 ] && echo $m; }
cool_down(){ [ -z "$COOL_TEMP" ] && return; local t0=$(date +%s) t
  while :; do t=$(cpu_temp); [ -z "$t" ] && { echo "  (温度が読めない)"; return; }; [ "$t" -le "$COOL_TEMP" ] && break
    [ $(( $(date +%s) - t0 )) -ge "$COOL_MAX_WAIT" ] && { echo "  !! 冷却待ちが上限 (${t}℃)"; break; }; sleep 10; done
  echo "  冷却待ち $(( $(date +%s) - t0 ))s → ${t}℃"; }

set_frames(){ local d c v
  for d in $APPS; do for c in $(kubectl get deploy/$d -n $NS -o jsonpath='{range .spec.template.spec.containers[*]}{.name}{" "}{end}'); do
    v=$(echo " $REQ" | grep -oE " $c=[0-9]+" | cut -d= -f2); [ -z "$v" ] && { echo "  !! 枠の表に $c が無い"; continue; }
    kubectl set resources deploy/$d -n $NS -c $c --requests=cpu=${v}m >/dev/null || echo "  !! 枠の設定に失敗: $d/$c"; done; done; }
set_java_delay(){ local d
  for d in $APPS; do
    kubectl get deploy/$d -n $NS -o json | python3 -c "
import sys,json; d=json.load(sys.stdin); n=0
for c in d['spec']['template']['spec']['containers']:
  if c['name'] in '''$JAVA_CONTAINERS'''.split() and 'readinessProbe' in c:
    c['readinessProbe']['initialDelaySeconds']=int('$JAVA_READY_DELAY'); n+=1
for k in ('resourceVersion','uid','creationTimestamp','generation','managedFields'): d['metadata'].pop(k,None)
d.pop('status',None); print(json.dumps(d)); print('$d: %d コンテナ' % n, file=sys.stderr)" 2>>"$LOG" | kubectl apply -n $NS -f - >/dev/null || echo "  !! Ready の遅らせ方の設定に失敗: $d"
  done
  echo "  Java ($JAVA_CONTAINERS) の readinessProbe を ${JAVA_READY_DELAY} s 後からに"; }
check_frames(){ local bad
  bad=$(kubectl get deploy -n $NS -o json | python3 -c "
import sys,json; req=dict(kv.split('=') for kv in '''$REQ'''.split()); bad=[]
for it in json.load(sys.stdin)['items']:
  for c in it['spec']['template']['spec']['containers']:
    if c['name'] in req:
      v=str(((c.get('resources') or {}).get('requests') or {}).get('cpu',''))
      if v!=req[c['name']]+'m': bad.append('%s/%s=%s' % (it['metadata']['name'],c['name'],v))
print(' '.join(bad))")
  [ -z "$bad" ] || { echo "  !! 枠が表と違う: $bad"; return 1; }; }
wait_ready(){ local i nr term
  for i in $(seq 1 60); do
    nr=$(kubectl get deploy -n $NS --no-headers 2>/dev/null | awk '{split($2,r,"/"); if(r[1]!=r[2]||r[2]!=1) printf "%s(%s) ",$1,$2}')
    term=$(kubectl get pods -n $NS --no-headers 2>/dev/null | grep -c Terminating)
    [ -z "$nr" ] && [ "$term" = 0 ] && return 0; sleep 5; done
  echo "  !! 全台 Ready (1 台) にならない: $nr Terminating=$term"; return 1; }

deploy_arm(){ local arm=$1
  echo "---- deploy $arm (アプリ: $APPS) $(date -Is) ----"
  kubectl delete hpa --all -n $NS >/dev/null 2>&1
  kubectl delete job k6load -n $NS --ignore-not-found >/dev/null 2>&1
  kubectl delete deploy --all -n $NS >/dev/null 2>&1
  for i in $(seq 1 60);do [ -z "$(kubectl get pods -n $NS -o name 2>/dev/null | grep -v promq)" ]&&break;sleep 3;done
  kubectl apply -n $NS -f $DIR/normal/ >/dev/null
  if [ "$arm" = arm1 ]; then
    kubectl delete deploy -n $NS carts orders payment shipping user queue-master >/dev/null 2>&1
    kubectl apply -n $NS -f $DIR/variants/arm1/buygroup.yaml >/dev/null
  fi
  set_frames
  [ -n "$JAVA_READY_DELAY" ] && set_java_delay
  for d in $(kubectl get deploy -n $NS -o jsonpath='{range .items[*]}{.metadata.name}{" "}{end}'); do
    kubectl scale deploy/$d -n $NS --replicas=1 >/dev/null 2>&1; done
  for d in $APPS "${STATEFUL[@]}"; do kubectl rollout status deploy/$d -n $NS --timeout=300s >/dev/null 2>&1 || echo "  !! rollout 未完: $d"; done
  wait_ready; check_frames
  sleep 30; ensure_promq
  echo "  front-end /catalogue → $(kubectl exec promq -n $NS -- curl -s -o /dev/null -w '%{http_code}' --max-time 10 http://front-end:80/catalogue 2>/dev/null)"
  echo "  deploy: $(kubectl get deploy -n $NS --no-headers | awk '{printf "%s=%s ",$1,$2}')"
  PREFIX="ss$(date +%s)"; read b v <<< "$(bv $PREWARM_POINT)"
  echo "  慣らし負荷 ${PREWARM}s ($PREWARM_POINT、HPA 無し、捨てる)。利用者 $NUSERS 人を登録 (接頭辞 $PREFIX)"
  start_k6 $b $v 0 $PREWARM "$PREFIX" 1
  local t0=$(date +%s); until k6_done; do [ $(( $(date +%s) - t0 )) -gt $(( PREWARM + 900 )) ] && { echo "  !! 慣らしが終わらない"; break; }; sleep 5; done
  local st; st=$(kubectl logs -n $NS job/k6load 2>/dev/null | grep -oE 'setup: [^"]*' | head -1); echo "  $st"
  kubectl delete job k6load -n $NS --ignore-not-found --wait=true >/dev/null 2>&1
  echo "$st" | grep -q "setup: $NUSERS/$NUSERS users registered" || { echo "  !! 登録がそろわない。このアームのこのサイクルは飛ばす"; return 1; }
}

make_hpa(){ local d cs c yaml
  for d in $APPS; do
    cs=$(kubectl get deploy/$d -n $NS -o jsonpath='{range .spec.template.spec.containers[*]}{.name}{"\n"}{end}')
    yaml="apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: $d
spec:
  scaleTargetRef: {apiVersion: apps/v1, kind: Deployment, name: $d}
  minReplicas: $HPA_MIN
  maxReplicas: $HPA_MAX
  behavior:
    scaleUp:   {stabilizationWindowSeconds: $SU_WIN}
    scaleDown: {stabilizationWindowSeconds: $SD_WIN}
  metrics:"
    for c in $cs; do yaml="$yaml
  - type: ContainerResource
    containerResource:
      name: cpu
      container: $c
      target: {type: Utilization, averageUtilization: $HPA_TARGET}"; done
    printf '%s\n' "$yaml" | kubectl apply -f - -n $NS >/dev/null || echo "  !! HPA 作成失敗: $d"
  done; }

run_point(){ local cyc=$1 arm=$2 pt=$3 b v start_ms
  read b v <<< "$(bv $pt)"
  echo "==== [cyc$cyc][$arm] $pt (購入=$b 閲覧=$v 周/秒) $(date -Is) ===="
  cool_down
  kubectl delete hpa --all -n $NS >/dev/null 2>&1
  for d in $APPS; do kubectl scale deploy/$d -n $NS --replicas=1 >/dev/null 2>&1; done
  wait_ready || { echo "  !! 点中止 [$arm][$pt]: 1 台に戻らない"; return; }
  check_frames || { echo "  !! 点中止 [$arm][$pt]: 枠不一致"; return; }
  sleep $POINT_SETTLE
  make_hpa
  start_k6 $b $v $WARM $MEAS "$PREFIX" 0
  start_ms=""; for i in $(seq 1 120); do start_ms=$(kubectl logs -n $NS job/k6load 2>/dev/null | grep -oE '@@@K6_START@@@ [0-9]+' | awk '{print $2}' | tail -1); [ -n "$start_ms" ] && break; sleep 2; done
  [ -z "$start_ms" ] && { echo "  !! k6 の開始時刻が取れない。点中止"; kubectl delete job k6load -n $NS --ignore-not-found >/dev/null 2>&1; return; }
  local t0=$(( start_ms / 1000 )) t_end=$(( start_ms / 1000 + WARM + MEAS ))
  local win=$(( MEAS - 20 )) t_q=$(( t_end - 10 ))
  echo "  k6 開始 $t0。窓 $(( t0 + WARM ))〜$t_end、Prometheus の区間 $(( t_q - win ))〜$t_q"
  # 台数の時系列: k6 が終わるまで SAMPLE 秒ごと (パイプで JSON を渡す。sample_hpa.py は標準入力を読む)
  while ! k6_done; do
    kubectl get hpa,deploy,pods -n $NS -o json 2>/dev/null | CYC="$cyc" ARM="$arm" RATE="$b" LX=0 BRW="$v" T0="$t0" TL_POINT="$pt" TL_N0=1 python3 "$SAMPLER" >> "$TL" 2>/dev/null
    [ $(( $(date +%s) - t0 )) -gt $(( WARM + MEAS + 600 )) ] && { echo "  !! k6 が終わらない"; break; }
    sleep $SAMPLE; done
  while [ "$(date +%s)" -lt $(( t_end + 15 )) ]; do sleep 5; done
  local summary; summary=$(kubectl logs -n $NS job/k6load 2>/dev/null | sed -n '/@@@K6_BEGIN@@@/,/@@@K6_END@@@/p' | grep '{')
  local SEL="namespace=\"$NS\",container!=\"\",container!=\"POD\",pod!~\"promq.*|k6load.*\""
  SUMMARY="$summary" K6_START_MS="$start_ms" WARM=$WARM MEAS=$MEAS T_Q=$t_q WIN=$win REQ="$REQ" \
    USAGE="$(promq "sum by(pod,container)(rate(container_cpu_usage_seconds_total{$SEL}[${win}s]))" $t_q)" \
    NODEJSON="$(promq "sum(rate(node_cpu_seconds_total{mode!=\"idle\"}[${win}s]))" $t_q)" \
    FREQJSON="$(promq "avg(avg_over_time(node_cpu_scaling_frequency_hertz[${win}s]))" $t_q)" \
    TEMPJSON="$(promq "max(max_over_time(node_hwmon_temp_celsius[${win}s]))" $t_q)" \
    python3 "$WRITER" "$CSV" "$TL" "$cyc" "$arm" "$pt" "$b" "$v"
  kubectl get pods -n $NS --no-headers | awk '$4>0 && $1!~/^k6load/{print "  !! 再起動:",$1,$4}'
  kubectl delete job k6load -n $NS --ignore-not-found >/dev/null 2>&1
  echo "  休憩 ${REST_POINT}s"; sleep $REST_POINT
}

ensure_promq
read -r -a ARR <<< "$ARMS"
for cyc in $(seq 1 $CYCLES); do
  echo "################ CYCLE $cyc / $CYCLES $(date -Is) ################"
  n=${#ARR[@]}; order=""; for ((i=0;i<n;i++)); do order="$order ${ARR[$(( (i + cyc - 1) % n ))]}"; done   # アームの順番をサイクルごとに回す
  for arm in $order; do
    APPS=$(apps_of $arm)
    deploy_arm $arm || continue
    pts=$(python3 -c "import random,sys; p=sys.argv[1].split(); random.Random('%s-%s-%s'%(sys.argv[2],sys.argv[3],sys.argv[4])).shuffle(p); print(' '.join(p))" "$POINTS" "$SHUFFLE_SEED" "$cyc" "$arm")
    echo "  点の順番: $pts"
    for pt in $pts; do run_point $cyc $arm $pt; done
  done
done
kubectl delete hpa --all -n $NS >/dev/null 2>&1
echo "================ SOCKSHOP HPA-PAIR DONE $(date -Is) ================"
