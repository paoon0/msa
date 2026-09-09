#!/usr/bin/env bash
# B測定 = 各サービスの「CPU利用率カーブ(素の高さ)」を録る。判定平面の【縦軸】を作るための測定。
#
# 何のためか:
#   HPA は「利用率 = 使用CPU ÷ 予約枠(requests)」が目標値(既定70%)を超えると台数を増やす。
#   同じ負荷で一緒に70%へ届く2サービス(=高さが揃う)は一緒に増える → 束ねても粒度損ゼロ。
#   高さがズレる(例 checkout 65% / email 20%)と、熱い方に合わせて冷たい方まで複製 → それが損。
#   ★狙いは「先行研究(通信量が重い所を束ねる)の再確認」ではなく、
#     ★通信量の順位と高さの順位が“食い違う”ペアを探すこと。食い違いがあれば通信量だけでは決められない。
#
# 測り方の約束(重要):
#   * HPA は必ず切る。入れると全サービスが70%に均されて高さの差が消える。
#   * 枠(requests/limits)はマニフェストの値から一切変更しない(つまみは固定)。
#   * 台数も固定(既定1台)。台数は全サービス共通の割り算なので高さの相対関係は変わらず、
#     横軸(何 checkouts/s で70%を横切るか)の目盛りだけが変わる。
#   * スロットリング率を毎点記録し、「limits の天井で絞られていない=カーブが寝ていない」ことを確認する。
#     (絞られ始めるのは 利用率 = limits/requests 倍 = 本アプリでは133%以上。測定帯70%前後では起きない想定)
#
# 出力: km2/experiments/results-perservice-cpu.csv
#   cycle,arm,target_rate,iter_rate,dropped,failed_rate,p99,pod,container,usage_mc,req_mc,util_pct,mc_per_iter,throttle_pct
#
# 使い方:
#   bash km2/experiments/perservice-cpu.sh                                  # 本走(5レート)
#   RATES="40 80" WARM=15 MEAS=60 CSV=/tmp/x.csv bash ...                   # スモーク
#   ARMS="normal bundle" bash ...                                           # 束ね側の高さも見たい時
set -u
NS=exp
REPO=/home/mizuki/ダウンロード/msa
DIR=$REPO/km2/experiments
K6DIR=$DIR/k6
ARMS=${ARMS:-"normal"}                 # 素の高さは分離(normal)で測る
RATES=${RATES:-"20 40 60 80 100"}      # 周/秒(=checkouts/s)。実HTTPは約4req/周
REPLICAS=${REPLICAS:-1}                # 台数固定(HPAが見る「Pod1台あたりの利用率」そのもの)
# --- 枠の一律化(2026-09-01 追加) ---
#   UNIFORM_REQ_M > 0 で、全コンテナの requests を同じ値にする。
#   狙い: 利用率 = 使用量 ÷ 枠 の「分母を定数」にして、高さの違いをそのまま使用量の違いとして読む。
#   ※ 使用量そのものは requests を変えても変わらない(アプリが使うCPUは枠に依存しない)。
#     一律化の利点は「比較が直接できる」ことと、下の UNIFORM_LIM_M と組で「絞りに当たらない」こと。
#   UNIFORM_LIM_M > 0 で、全コンテナの limits も同じ値にする。
#   これが重要: 既存測定(2026-08-18)は frontend の上限1000mに対し150周/sで1054m必要になり頭打ちだった。
#   上限を十分大きく一律にすれば、絞られずに高い負荷まで素の使用量カーブを測れる。
UNIFORM_REQ_M=${UNIFORM_REQ_M:-0}
UNIFORM_LIM_M=${UNIFORM_LIM_M:-0}
WARM=${WARM:-30}                       # 捨てる秒(VU立ち上げ過渡)
MEAS=${MEAS:-180}                      # 記録する秒
PRE_VUS=${PRE_VUS:-300}
MAX_VUS=${MAX_VUS:-3000}
CYCLES=${CYCLES:-1}
CSV=${CSV:-$DIR/results-perservice-cpu.csv}
LOG=${LOG:-$DIR/perservice-cpu.log}
PROM="http://prometheus-grafana-kube-pr-prometheus.monitoring.svc:9090"
ROLLOUT=300s
NORMAL=(frontend checkoutservice cartservice productcatalogservice currencyservice \
        paymentservice shippingservice emailservice recommendationservice adservice)
BUNDLE_SCALE=(frontend checkoutservice cartservice currencyservice paymentservice shippingservice emailservice adservice)

exec > >(tee -a "$LOG") 2>&1
echo "================ PERSERVICE-CPU START $(date -Is) arms=[$ARMS] rates=[$RATES] cycles=$CYCLES reps=$REPLICAS warm=${WARM}s meas=${MEAS}s (枠=req:${UNIFORM_REQ_M}m/lim:${UNIFORM_LIM_M}m 0はマニフェストのまま, HPA無し) ================"
[ -s "$CSV" ] || echo "cycle,arm,target_rate,iter_rate,dropped,failed_rate,p99,pod,container,usage_mc,req_mc,util_pct,mc_per_iter,throttle_pct" > "$CSV"

ensure_promq(){ [ "$(kubectl get pod promq -n $NS -o jsonpath='{.status.phase}' 2>/dev/null)" = Running ] && return
  kubectl delete pod promq -n $NS --ignore-not-found >/dev/null 2>&1
  kubectl run promq -n $NS --image=curlimages/curl:latest --restart=Never --command -- sleep 86400 >/dev/null 2>&1
  for i in $(seq 1 30);do [ "$(kubectl get pod promq -n $NS -o jsonpath='{.status.phase}' 2>/dev/null)" = Running ]&&break;sleep 2;done; }
promq(){ local q="$1" i out; for i in 1 2 3 4 5;do ensure_promq
  out=$(kubectl exec promq -n $NS -- curl -s --max-time 25 "$PROM/api/v1/query" --data-urlencode "query=$q" 2>/dev/null)
  [ -n "$out" ]&&{ echo "$out"; return; }; sleep 4; done; echo ""; }

deploy(){ local arm=$1
  echo "---- deploy $arm (固定${REPLICAS}台, HPA無し, 枠は変更しない) ----"
  kubectl delete hpa --all -n $NS >/dev/null 2>&1
  kubectl delete deploy --all -n $NS >/dev/null 2>&1
  for i in $(seq 1 40);do [ -z "$(kubectl get deploy -n $NS -o name 2>/dev/null)" ]&&break;sleep 3;done
  if [ "$arm" = normal ];then
    for f in "${NORMAL[@]}";do kubectl apply -f $REPO/km2/normal/$f.yaml -n $NS >/dev/null;done
    SCALE=("${NORMAL[@]}")
  elif [ "$arm" = mega ];then
    kubectl apply -f $REPO/km2/all/all.yaml -n $NS >/dev/null
    SCALE=(megapod)
  else
    for y in $REPO/km2/frontrecocatalogcart/*.yaml;do case "$y" in *kustomization*|*loadgenerator*|*hpa-percontainer*)continue;;esac;kubectl apply -f "$y" -n $NS >/dev/null;done
    SCALE=("${BUNDLE_SCALE[@]}")
  fi
  kubectl delete hpa --all -n $NS >/dev/null 2>&1   # 束ね側に同梱されたHPAを必ず消す(高さが均されるのを防ぐ)
  for d in "${SCALE[@]}" redis-cart;do kubectl patch deploy/$d -n $NS --type=merge -p '{"spec":{"template":{"metadata":{"annotations":{"sidecar.istio.io/inject":"false"}}}}}' >/dev/null 2>&1||true;done
  if [ "$UNIFORM_REQ_M" != 0 ] || [ "$UNIFORM_LIM_M" != 0 ]; then
    fl=""
    [ "$UNIFORM_REQ_M" != 0 ] && fl="$fl --requests=cpu=${UNIFORM_REQ_M}m"
    [ "$UNIFORM_LIM_M" != 0 ] && fl="$fl --limits=cpu=${UNIFORM_LIM_M}m"
    echo "  枠を一律化:$fl (全コンテナ)"
    for d in $(kubectl get deploy -n $NS -o jsonpath='{range .items[*]}{.metadata.name}{" "}{end}'); do
      for c in $(kubectl get deploy/$d -n $NS -o jsonpath='{range .spec.template.spec.containers[*]}{.name}{" "}{end}'); do
        case "$c" in istio-proxy) continue;; esac
        kubectl set resources deploy/$d -n $NS --containers=$c $fl >/dev/null 2>&1||true
      done
    done
  fi
  for d in "${SCALE[@]}";do kubectl scale deploy/$d -n $NS --replicas=$REPLICAS >/dev/null 2>&1||true;done
  kubectl scale deploy/redis-cart -n $NS --replicas=1 >/dev/null 2>&1||true
  for d in "${SCALE[@]}" redis-cart;do kubectl rollout status deploy/$d -n $NS --timeout=$ROLLOUT >/dev/null 2>&1||true;done
  echo "  deploy: $(kubectl get deploy -n $NS --no-headers 2>/dev/null | awk '{printf "%s=%s ",$1,$2}')"
}

run_rate(){ local arm=$1 rate=$2 cyc=${3:-1}
  echo "==== [cyc$cyc][$arm] target=${rate}周/秒 $(date -Is) ===="
  kubectl create configmap k6-script -n $NS --from-file=checkout.js=$K6DIR/checkout.js --dry-run=client -o yaml | kubectl apply -f - >/dev/null 2>&1
  kubectl delete job k6load -n $NS --ignore-not-found --wait=true >/dev/null 2>&1
  sed -e "s/__RATE__/$rate/" -e "s/__WARM__/$WARM/" -e "s/__MEAS__/$MEAS/" -e "s/__PRE__/$PRE_VUS/" -e "s/__MAX__/$MAX_VUS/" "$K6DIR/k6-job.yaml" | kubectl apply -f - -n $NS >/dev/null
  local pod=""
  for i in $(seq 1 40);do pod=$(kubectl get pods -n $NS -l app=k6load --sort-by=.metadata.creationTimestamp -o jsonpath='{.items[-1].metadata.name}' 2>/dev/null)
    [ -n "$pod" ]&&[ "$(kubectl get pod $pod -n $NS -o jsonpath='{.status.phase}' 2>/dev/null)" = Running ]&&break; sleep 3;done
  local t_run=$(date +%s)
  # 計測窓の終わりで、窓の大半をカバーする rate() 幅で採取(瞬間値でなく窓平均にする)
  local win=$(( MEAS*5/6 )); [ $win -lt 60 ] && win=60
  sleep $(( WARM + MEAS ))
  local USAGE REQ THR NODE
  USAGE=$(promq "sum by(pod,container)(rate(container_cpu_usage_seconds_total{namespace=\"$NS\",container!=\"\",container!=\"POD\",pod!~\"k6load.*|promq.*\"}[${win}s]))")
  REQ=$(promq   "sum by(pod,container)(kube_pod_container_resource_requests{namespace=\"$NS\",resource=\"cpu\",pod!~\"k6load.*|promq.*\"})")
  # スロットリング率 = 絞られた期間 ÷ 全期間。0 なら limits の天井に当たっていない=カーブは寝ていない。
  THR=$(promq   "sum by(pod,container)(rate(container_cpu_cfs_throttled_periods_total{namespace=\"$NS\",container!=\"\",container!=\"POD\",pod!~\"k6load.*|promq.*\"}[${win}s])) / sum by(pod,container)(rate(container_cpu_cfs_periods_total{namespace=\"$NS\",container!=\"\",container!=\"POD\",pod!~\"k6load.*|promq.*\"}[${win}s]))")
  NODE=$(promq  "sum(rate(node_cpu_seconds_total{mode!=\"idle\"}[${win}s]))" | python3 -c "import sys,json;r=json.load(sys.stdin).get('data',{}).get('result',[]);print(round(float(r[0]['value'][1]),2) if r else 'NA')" 2>/dev/null)
  # k6 の集計が出るまで待ってからログを一度だけ読む(ポーリング競合を排除)
  local done_at=$(( t_run + WARM + MEAS + 25 ))
  while [ "$(date +%s)" -lt "$done_at" ]; do sleep 5; done
  local logs summary; logs=$(kubectl logs "$pod" -n $NS 2>/dev/null)
  summary=$(printf '%s\n' "$logs" | sed -n '/@@@K6_BEGIN@@@/,/@@@K6_END@@@/p' | grep '{')
  echo "$summary" | grep -q '{' || { echo "  !! summary回収失敗(pod=$pod)"; kubectl delete job k6load -n $NS --ignore-not-found >/dev/null 2>&1; return; }
  echo "  node_cores=$NODE"
  SUMMARY="$summary" USAGE="$USAGE" REQJSON="$REQ" THRJSON="$THR" python3 - "$arm" "$CSV" "$cyc" <<'PY'
import sys,json,csv,os,re
arm,out,cyc=sys.argv[1:4]
d=json.loads(os.environ['SUMMARY'])
def series(env):
    try: r=json.loads(os.environ[env]).get('data',{}).get('result',[])
    except Exception: r=[]
    o={}
    for x in r:
        try: v=float(x['value'][1])
        except Exception: continue
        if v!=v: continue                      # NaN(分母0)は捨てる
        o[(x['metric'].get('pod','?'),x['metric'].get('container','?'))]=v
    return o
usage=series('USAGE'); req=series('REQJSON'); thr=series('THRJSON')
iters=d.get('iter_rate') or 0
rows=[]
for k,v in sorted(usage.items(), key=lambda kv:-kv[1]):
    pod,cont=k
    mc=v*1000.0                        # 使用 mコア
    rq=req.get(k,0.0)*1000.0           # 枠 mコア
    util=(mc/rq*100.0) if rq>0 else 0.0
    per=(mc/iters) if iters>0 else 0.0  # 1周(=1checkout)あたり mコア秒
    tp=thr.get(k,0.0)*100.0
    rows.append([cyc,arm,d.get('target_rate'),round(iters,1),d.get('dropped'),
                 round(d.get('failed_rate') or 0,4),round(d.get('p99') or 0,1),
                 re.sub(r'-[a-f0-9]{6,}-\w+$','',pod),cont,
                 round(mc,1),round(rq,1),round(util,1),round(per,2),round(tp,1)])
with open(out,'a',newline='') as f:
    w=csv.writer(f)
    for r in rows: w.writerow(r)
print("  -> iter_rate=%.1f/%s dropped=%s p99=%.0f failed=%.3f"%(iters,d.get('target_rate'),d.get('dropped'),d.get('p99') or 0,d.get('failed_rate') or 0))
print("     %-24s %-20s %8s %7s %8s %10s %8s"%("pod","container","使用m","枠m","利用率%","mc秒/周","絞り%"))
for r in rows[:14]:
    print("     %-24s %-20s %8.1f %7.0f %8.1f %10.2f %8.1f"%(r[7],r[8],r[9],r[10],r[11],r[12],r[13]))
hot=[r for r in rows if r[13]>1.0]
if hot: print("     !! スロットリング検出(カーブが寝ている可能性): "+", ".join("%s/%s=%.0f%%"%(r[7],r[8],r[13]) for r in hot))
PY
  kubectl delete job k6load -n $NS --ignore-not-found >/dev/null 2>&1
}

ensure_promq
for c in $(seq 1 $CYCLES); do
  echo "################ CYCLE $c / $CYCLES $(date -Is) ################"
  for arm in $ARMS; do
    deploy "$arm"; sleep 15
    for r in $RATES; do run_rate "$arm" "$r" "$c"; done
  done
done
kubectl delete job k6load -n $NS --ignore-not-found >/dev/null 2>&1
echo "================ PERSERVICE-CPU DONE $(date -Is) ================"
