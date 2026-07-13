#!/usr/bin/env bash
# ============================================================================
# 束ねPodのHPAしきい値方式の比較(3アーム):
#   f3avg  = 束ね(front3) + Pod平均HPA(Resource cpu, 全コンテナ合計÷requests合計, 70%)
#   f3perc = 束ね(front3) + コンテナ別HPA(ContainerResource, server/reco/catalog を個別70%)
#   normal = 分離(1Pod1サービス) + frontend/reco/catalog を個別HPA(Resource cpu 70%)
#   問い: 束ねると Pod平均HPA は熱いfrontendが冷たいreco/catalogに薄められて失速する(落とし穴#8)。
#         コンテナ別しきい値にすると失速が直り、分離(normal)並みにスケール&スループットが出るか。
# 各アームで scale_replicas / rps / softirq/req に加え、コンテナ別の実効CPU(cont_mc)も記録して
#   「なぜ平均だと薄まるか」を実測で裏取りする。
# 出力: km2/experiments/results-hpapercont.csv
# ============================================================================
set -u
NS=exp
REPO=/home/mizuki/ダウンロード/msa
SWEEP_USERS=${SWEEP_USERS:-"240 480"}
CYCLES=${CYCLES:-3}
LG_RATE=${LG_RATE:-40}
WARMUP=${WARMUP:-3m}
MEASURE=${MEASURE:-3m}
BASE_SETTLE=${BASE_SETTLE:-30}
BASE_WIN=${BASE_WIN:-2m}
HPA_TARGET=${HPA_TARGET:-70}
HPA_MIN=${HPA_MIN:-1}
HPA_MAX=${HPA_MAX:-4}
ARMS=${ARMS:-"f3avg f3perc normal"}
LOAD=$REPO/km2/experiments/loadgen-csv.yaml
LOADGEN=/tmp/loadgen-hpapc.yaml
CSV=${CSV:-$REPO/km2/experiments/results-hpapercont.csv}
LOG=${LOG:-$REPO/km2/experiments/hpapercont.log}
PC_HPA=$REPO/km2/frontrecocatalogcart/hpa-percontainer.yaml
ROLLOUT_TIMEOUT=300s
LOAD_WAIT_MAX=120
MARKER_POLL_MAX=${MARKER_POLL_MAX:-220}
PROM="http://prometheus-grafana-kube-pr-prometheus.monitoring.svc:9090"

NORMAL=(frontend checkoutservice cartservice productcatalogservice currencyservice \
        paymentservice shippingservice emailservice recommendationservice adservice)
# 束ね(front3)で個別に立つ(スケールしない固定1)Deployment群。
FRONT3_DEPLOYS=(frontend checkoutservice cartservice redis-cart currencyservice paymentservice emailservice shippingservice adservice)
SCALE_NORMAL=(frontend recommendationservice productcatalogservice)
SCALE_FRONT3=(frontend)
# SCALE_ALL=1 のとき、両アーム共通の固定サービスにも個別HPAを付ける(redisは除外=ステートフル)。
# email(300m/1replica)がu480のボトルネックなので、これを外して真のスループット差を測る。
COMMON_SCALE=(checkoutservice cartservice currencyservice paymentservice shippingservice emailservice adservice)
SCALE_ALL=${SCALE_ALL:-0}
LG_USERS=80

exec > >(tee -a "$LOG") 2>&1
echo "================ HPAPERCONT START $(date -Is) arms=[$ARMS] levels=[$SWEEP_USERS] rate=$LG_RATE warmup=$WARMUP measure=$MEASURE HPA=${HPA_TARGET}%/${HPA_MIN}-${HPA_MAX} SCALE_ALL=$SCALE_ALL ================"
echo "cycle,arm,users,reqcount,fails,p50_ms,p90_ms,p99_ms,avg_ms,rps,softirq_cores,base_softirq,app_cores,base_app,node_cores,base_node,softirq_mc_per_req,app_mc_per_req,node_mc_per_req,scale_replicas,scale_detail,cont_mc" > "$CSV"

ensure_promq() {
  [ "$(kubectl get pod promq -n "$NS" -o jsonpath='{.status.phase}' 2>/dev/null)" = "Running" ] && return
  kubectl delete pod promq -n "$NS" --ignore-not-found >/dev/null 2>&1
  kubectl run promq -n "$NS" --image=curlimages/curl:latest --restart=Never --command -- sleep 86400 >/dev/null 2>&1
  for i in $(seq 1 30); do [ "$(kubectl get pod promq -n "$NS" -o jsonpath='{.status.phase}' 2>/dev/null)" = "Running" ] && break; sleep 2; done
}
prom_scalar() { # リトライ付き
  local q="$1" out i
  for i in 1 2 3 4 5; do
    ensure_promq
    out=$(kubectl exec promq -n "$NS" -- curl -s --max-time 20 "$PROM/api/v1/query" --data-urlencode "query=$q" 2>/dev/null \
      | python3 -c "import sys,json;r=json.load(sys.stdin).get('data',{}).get('result',[]);print(r[0]['value'][1] if r else '')" 2>/dev/null)
    [ -n "$out" ] && { echo "$out"; return; }
    sleep 5
  done
  echo "NA"
}
scale_info() { # $@=deploys -> "総数|d1=n d2=n..."
  local t=0 r detail=""
  for d in "$@"; do r=$(kubectl get deploy "$d" -n "$NS" -o jsonpath='{.status.replicas}' 2>/dev/null); [ -n "$r" ] && t=$((t+r)); detail="$detail$d=$r "; done
  echo "$t|$detail"
}
cont_mc() { # 束ねPod(app=frontend)のコンテナ別 平均millicores を "server=..;reco=..;catalog=.." で。best-effort
  kubectl top pod -n "$NS" -l app=frontend --containers --no-headers 2>/dev/null \
    | python3 -c '
import sys,collections
s=collections.defaultdict(list)
for ln in sys.stdin:
    p=ln.split()
    if len(p)>=3:
        c=p[1]; v=p[2].rstrip("m")
        try: s[c].append(float(v))
        except: pass
print(";".join("%s=%.0f"%(k,sum(v)/len(v)) for k,v in s.items()) or "NA")
' 2>/dev/null || echo "NA"
}

wait_empty() { for i in $(seq 1 40); do [ -z "$(kubectl get deploy -n "$NS" -o name 2>/dev/null)" ] && break; sleep 3; done; }
patch_noistio() { for d in "$@"; do kubectl patch deploy/"$d" -n "$NS" --type=merge -p '{"spec":{"template":{"metadata":{"annotations":{"sidecar.istio.io/inject":"false"}}}}}' >/dev/null 2>&1 || true; done; }

deploy_arm() { # $1=arm  -> グローバル SCALESET を設定
  local arm=$1
  echo "---- deploy $arm ----"
  kubectl delete hpa --all -n "$NS" >/dev/null 2>&1
  kubectl delete -f "$REPO/km2/all/all.yaml" -n "$NS" --ignore-not-found >/dev/null 2>&1
  for f in "${NORMAL[@]}"; do kubectl delete -f "$REPO/km2/$f.yaml" -n "$NS" --ignore-not-found >/dev/null 2>&1; done
  wait_empty
  if [ "$arm" = normal ]; then
    for f in "${NORMAL[@]}"; do kubectl apply -f "$REPO/km2/$f.yaml" -n "$NS" >/dev/null; done
    patch_noistio "${NORMAL[@]}" redis-cart
    for d in "${NORMAL[@]}" redis-cart; do kubectl rollout status deploy/"$d" -n "$NS" --timeout="$ROLLOUT_TIMEOUT" >/dev/null 2>&1 || true; done
    kubectl delete hpa --all -n "$NS" >/dev/null 2>&1
    for d in "${SCALE_NORMAL[@]}"; do kubectl autoscale deploy/"$d" -n "$NS" --cpu-percent="$HPA_TARGET" --min="$HPA_MIN" --max="$HPA_MAX" >/dev/null 2>&1 || true; done
    SCALESET=("${SCALE_NORMAL[@]}")
    if [ "$SCALE_ALL" = 1 ]; then
      for d in "${COMMON_SCALE[@]}"; do kubectl autoscale deploy/"$d" -n "$NS" --cpu-percent="$HPA_TARGET" --min="$HPA_MIN" --max="$HPA_MAX" >/dev/null 2>&1 || true; done
      SCALESET=("${SCALE_NORMAL[@]}" "${COMMON_SCALE[@]}")
    fi
  else
    # f3avg / f3perc は同じ束ねトポロジ。HPAだけ変える。
    for y in "$REPO"/km2/frontrecocatalogcart/*.yaml; do
      case "$y" in *kustomization.yaml|*loadgenerator.yaml|*hpa-percontainer.yaml) continue;; esac
      kubectl apply -f "$y" -n "$NS" >/dev/null
    done
    patch_noistio "${FRONT3_DEPLOYS[@]}"
    for d in "${FRONT3_DEPLOYS[@]}"; do kubectl rollout status deploy/"$d" -n "$NS" --timeout="$ROLLOUT_TIMEOUT" >/dev/null 2>&1 || true; done
    kubectl delete hpa --all -n "$NS" >/dev/null 2>&1   # yaml同梱HPAを消す
    if [ "$arm" = f3perc ]; then
      kubectl apply -f "$PC_HPA" -n "$NS" >/dev/null
    else # f3avg
      kubectl autoscale deploy/frontend -n "$NS" --cpu-percent="$HPA_TARGET" --min="$HPA_MIN" --max="$HPA_MAX" >/dev/null 2>&1 || true
    fi
    SCALESET=("${SCALE_FRONT3[@]}")
    if [ "$SCALE_ALL" = 1 ]; then
      for d in "${COMMON_SCALE[@]}"; do kubectl autoscale deploy/"$d" -n "$NS" --cpu-percent="$HPA_TARGET" --min="$HPA_MIN" --max="$HPA_MAX" >/dev/null 2>&1 || true; done
      SCALESET=("${SCALE_FRONT3[@]}" "${COMMON_SCALE[@]}")
    fi
  fi
}

measure_baseline() {
  echo "---- $(date -Is) 基線(ドレイン ${BASE_SETTLE}s + 窓 ${BASE_WIN}) ----"
  sleep "$BASE_SETTLE"
  local win_s=$BASE_WIN; case "$win_s" in *m) win_s=$(( ${win_s%m} * 60 ));; *s) win_s=${win_s%s};; esac
  sleep "$win_s"
  BASE_SOFTIRQ=$(prom_scalar "sum(rate(node_cpu_seconds_total{mode=\"softirq\"}[$BASE_WIN]))")
  BASE_APP=$(prom_scalar "sum(rate(container_cpu_usage_seconds_total{namespace=\"$NS\",container!=\"\",container!=\"POD\",pod!~\"loadgenerator.*\",pod!~\"promq.*\"}[$BASE_WIN]))")
  BASE_NODE=$(prom_scalar "sum(rate(node_cpu_seconds_total{mode!=\"idle\"}[$BASE_WIN]))")
  echo "  base: softirq=${BASE_SOFTIRQ} app=${BASE_APP} node=${BASE_NODE}"
}
gen_loadgen() {
  sed -E "s/(name: RUN_TIME, value: )\"[^\"]*\"/\1\"$1\"/; \
          s/(name: USERS,[[:space:]]*value: )\"[^\"]*\"/\1\"$LG_USERS\"/; \
          s/(name: RATE,[[:space:]]*value: )\"[^\"]*\"/\1\"$LG_RATE\"/" "$LOAD" > "$LOADGEN"
}
run_load() { # run_time capture arm scaleset...
  local rt=$1 capture=$2 arm=$3; shift 3; local SCALESET=("$@")
  local pod run logs i st
  local phase; [ "$capture" = "1" ] && phase="本計測" || phase="ウォームアップ"
  echo "---- $(date -Is) [$arm] users=$LG_USERS $phase (負荷 $rt) ----"
  gen_loadgen "$rt"
  kubectl delete job loadgenerator -n "$NS" --ignore-not-found --wait=true
  for i in $(seq 1 24); do [ -z "$(kubectl get pods -n "$NS" -l job-name=loadgenerator -o jsonpath='{.items[*].metadata.name}' 2>/dev/null)" ] && break; sleep 2; done
  kubectl apply -f "$LOADGEN" -n "$NS"
  pod=""; run=""
  for i in $(seq 1 $LOAD_WAIT_MAX); do
    pod=$(kubectl get pods -n "$NS" -l job-name=loadgenerator --sort-by=.metadata.creationTimestamp -o jsonpath='{.items[-1].metadata.name}' 2>/dev/null)
    [ -n "$pod" ] || { sleep 5; continue; }
    run=$(kubectl get pod "$pod" -n "$NS" -o jsonpath='{.status.containerStatuses[?(@.name=="main")].state.running.startedAt}' 2>/dev/null)
    [ -n "$run" ] && break
    st=$(kubectl get pod "$pod" -n "$NS" -o jsonpath='{.status.phase}' 2>/dev/null)
    { [ "$st" = "Succeeded" ] || [ "$st" = "Failed" ]; } && break
    sleep 5
  done
  # 本計測窓の終盤で scale/CPU を採取(スケールが落ち着いた状態)
  logs=""
  for i in $(seq 1 $MARKER_POLL_MAX); do
    logs=$(kubectl logs "$pod" -n "$NS" -c main --tail=-1 2>/dev/null)
    echo "$logs" | grep -q '@@@CSV_END@@@' && { echo "  $(date -Is) 負荷完了(試行 $i)"; break; }
    st=$(kubectl get pod "$pod" -n "$NS" -o jsonpath='{.status.phase}' 2>/dev/null)
    [ "$st" = "Failed" ] && { echo "  loadgen FAILED"; break; }
    sleep 5
  done
  if [ "$capture" = "1" ]; then
    softirq_cores=$(prom_scalar "sum(rate(node_cpu_seconds_total{mode=\"softirq\"}[$rt]))")
    app_cores=$(prom_scalar "sum(rate(container_cpu_usage_seconds_total{namespace=\"$NS\",container!=\"\",container!=\"POD\",pod!~\"loadgenerator.*\",pod!~\"promq.*\"}[$rt]))")
    node_cores=$(prom_scalar "sum(rate(node_cpu_seconds_total{mode!=\"idle\"}[$rt]))")
    SI=$(scale_info "${SCALESET[@]}"); SREPS=${SI%%|*}; SDET=${SI#*|}
    CMC=$(cont_mc)
    echo "  $(date -Is) CPU: softirq=${softirq_cores} app=${app_cores} node=${node_cores} | scale_replicas=${SREPS} [${SDET}] cont_mc=[${CMC}]"
    echo "  HPA: $(kubectl get hpa -n "$NS" --no-headers 2>/dev/null | tr '\n' '|')"
  fi
  kubectl delete job loadgenerator -n "$NS" --ignore-not-found >/dev/null 2>&1
  [ "$capture" != "1" ] && { echo "  ウォームアップ完了(捨て)"; return; }
  local logfile="$REPO/km2/experiments/last-logs-hpapc.txt"
  printf '%s\n' "$logs" > "$logfile"
  python3 - "${CYC:-1}" "$arm" "$LG_USERS" "$CSV" "$logfile" \
           "$softirq_cores" "${BASE_SOFTIRQ:-NA}" "$app_cores" "${BASE_APP:-NA}" "$node_cores" "${BASE_NODE:-NA}" \
           "$SREPS" "$SDET" "$CMC" <<'PY'
import sys,csv,io
cyc,arm,users,out,logfile,sc,bsi,ac,ba,nc,bn,sreps,sdet,cmc=sys.argv[1:15]
data=open(logfile,encoding='utf-8',errors='replace').read()
b,e="@@@CSV_BEGIN@@@","@@@CSV_END@@@"
def fnum(x):
    try: return float(x)
    except: return None
if b in data and e in data:
    block=data.split(b,1)[1].split(e,1)[0].strip()
    rows=list(csv.reader(io.StringIO(block))); hdr=rows[0]
    def idx(n): return hdr.index(n) if n in hdr else None
    agg=[r for r in rows[1:] if len(r)>1 and r[1]=="Aggregated"]
    if agg:
        r=agg[0]
        def g(n,d="NA"):
            i=idx(n); return r[i] if i is not None and i<len(r) else d
        rps=fnum(g("Requests/s"))
        def mc(load,base):
            l=fnum(load); bb=fnum(base)
            return round((l-bb)/rps*1000,3) if (l is not None and bb is not None and rps) else "NA"
        rec=[cyc,arm,users,g("Request Count"),g("Failure Count"),g("50%"),g("90%"),g("99%"),
             g("Average Response Time"),g("Requests/s"),
             sc,bsi,ac,ba,nc,bn,mc(sc,bsi),mc(ac,ba),mc(nc,bn),sreps,sdet.strip(),cmc]
        with open(out,"a",newline="") as f: csv.writer(f).writerow(rec)
        print("  -> 記録:", "cyc"+cyc, arm, "users",users, "softirq/req",mc(sc,bsi), "scale_reps",sreps, "cont_mc",cmc)
    else: print("  !! Aggregated行なし")
else: print("  !! CSVマーカー無し")
PY
}

ensure_promq
for CYC in $(seq 1 "$CYCLES"); do
for ARM in $ARMS; do
  echo "################ CYCLE $CYC/$CYCLES ARM=$ARM $(date -Is) ################"
  deploy_arm "$ARM"   # 毎回デプロイし直す=レプリカを1にリセット
  sleep 15; echo "  HPA: $(kubectl get hpa -n "$NS" --no-headers 2>/dev/null | tr '\n' '|')"
  for U in $SWEEP_USERS; do
    LG_USERS=$U
    echo "======== [cyc$CYC $ARM] USERS=$U $(date -Is) ========"
    run_load "$WARMUP" 0 "$ARM" "${SCALESET[@]}"
    measure_baseline
    run_load "$MEASURE" 1 "$ARM" "${SCALESET[@]}"
  done
done
done

kubectl delete hpa --all -n "$NS" >/dev/null 2>&1
kubectl delete pod promq -n "$NS" --ignore-not-found >/dev/null 2>&1
echo "================ HPAPERCONT DONE $(date -Is) ================"
column -s, -t "$CSV" 2>/dev/null || cat "$CSV"
