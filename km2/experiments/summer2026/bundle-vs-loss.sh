#!/usr/bin/env bash
# 【夏休み実験1】束ねの「通信の得」と「台数の損」を対決させ、どちらのルールが正しいか決着をつける。
#
# 問い: frontend の相方として recommendation と cart のどちらを束ねるべきか。
#   * 通信量だけのルール(先行研究 ICTer=通信量Knapsack)の予測: reco > cart (recoの方が通信が重い)
#   * 2軸ルール(本研究)の予測:                                cart >= reco
#     理由: 2026-08-18 の利用率カーブ測定([[perservice-utilization-curves]])より、frontend は1台90周/s、
#           catalog 95・reco 147・cart 166。負荷200周/sなら frontend 3台に対し reco/cart は2台で足りるのに
#           同じPodなので3台にされる。無駄になる枠は reco 1200m、cart 560m = recoはcartの2倍以上損する。
#           catalog は元々3台必要なので損ゼロ(=両軸一致で最良のはず)。
#
# アーム(frontend の相方だけを変える。他サービスは全アーム共通で別Pod):
#   normal       … 全部バラバラ(基準)
#   frontcatalog … frontend + productcatalog を1Pod
#   frontreco    … frontend + recommendation を1Pod
#   frontcart    … frontend + cartservice を1Pod (redisはPod外へ出した専用マニフェストを使う。
#                  同居したままHPAで増やすとカートの保管場所が分裂して実験が壊れるため)
#
# 条件: HPA 有り(redis以外の全Deployment, コンテナ別しきい値70%, 1〜8台)。枠(requests/limits)はマニフェストのまま。
#   コンテナ別(ContainerResource)にする理由: Pod平均だと束ねたPodで熱いコンテナが冷たいコンテナに薄められ
#   「増えるべき時に増えない」別の病気が混ざる。ここで見たいのは「増えた時に冷たい方が無駄になる」損なので、
#   熱いコンテナが70%を超えたら増える=理論(n_J = max n_s)と一致する形にそろえる。
#
# 主指標: 捌けた周/秒 ÷ 予約枠の合計[コア] = 「1コアあたり何周捌けたか」= 資源効率。
#   (たくさん捌けても枠を大量に確保していれば効率が良いとは言えないので割り算にする)
#
# 出力: km2/experiments/summer2026/results-bundle-vs-loss.csv
set -u
NS=exp
REPO=/home/mizuki/ダウンロード/msa
DIR=$REPO/km2/experiments/summer2026
K6DIR=$REPO/km2/experiments/k6
ARMS=${ARMS:-"normal frontcatalog frontreco frontcart"}
RATES=${RATES:-"200 260"}     # 周/秒。ノード16コアに枠合計が収まる帯(高くすると Pending が出る)
HPA_MIN=${HPA_MIN:-1}
HPA_MAX=${HPA_MAX:-8}
HPA_TARGET=${HPA_TARGET:-70}
WARM=${WARM:-150}             # HPAが台数を決め切るまで待つ(捨てる)
MEAS=${MEAS:-240}             # 記録する秒
PRE_VUS=${PRE_VUS:-600}
MAX_VUS=${MAX_VUS:-4000}
CYCLES=${CYCLES:-1}
CSV=${CSV:-$DIR/results-bundle-vs-loss.csv}
LOG=${LOG:-$DIR/bundle-vs-loss.log}
PROM="http://prometheus-grafana-kube-pr-prometheus.monitoring.svc:9090"
ROLLOUT=300s

exec > >(tee -a "$LOG") 2>&1
echo "================ BUNDLE-VS-LOSS START $(date -Is) arms=[$ARMS] rates=[$RATES] cycles=$CYCLES HPA=${HPA_TARGET}%/${HPA_MIN}-${HPA_MAX}台 warm=${WARM}s meas=${MEAS}s ================"
[ -s "$CSV" ] || echo "cycle,arm,target_rate,iter_rate,dropped,failed_rate,p50,p99,reserved_cores,eff_iter_per_core,pods,pending,node_cores,softirq_mc_per_iter,replicas" > "$CSV"

ensure_promq(){ [ "$(kubectl get pod promq -n $NS -o jsonpath='{.status.phase}' 2>/dev/null)" = Running ] && return
  kubectl delete pod promq -n $NS --ignore-not-found >/dev/null 2>&1
  kubectl run promq -n $NS --image=curlimages/curl:latest --restart=Never --command -- sleep 86400 >/dev/null 2>&1
  for i in $(seq 1 30);do [ "$(kubectl get pod promq -n $NS -o jsonpath='{.status.phase}' 2>/dev/null)" = Running ]&&break;sleep 2;done; }
promq(){ local q="$1" i out; for i in 1 2 3 4 5;do ensure_promq
  out=$(kubectl exec promq -n $NS -- curl -s --max-time 25 "$PROM/api/v1/query" --data-urlencode "query=$q" 2>/dev/null)
  [ -n "$out" ]&&{ echo "$out"; return; }; sleep 4; done; echo ""; }
scalar(){ python3 -c "import sys,json;r=json.load(sys.stdin).get('data',{}).get('result',[]);print(round(float(r[0]['value'][1]),4) if r else 'NA')" 2>/dev/null; }

apply_arm(){ local arm=$1
  case "$arm" in
    normal)       for f in frontend checkoutservice cartservice productcatalogservice currencyservice \
                            paymentservice shippingservice emailservice recommendationservice adservice; do
                    kubectl apply -f $REPO/km2/normal/$f.yaml -n $NS >/dev/null; done ;;
    frontcatalog) for y in $REPO/km2/frontcatalog/*.yaml;do case "$y" in *kustomization*|*loadgenerator*)continue;;esac
                    kubectl apply -f "$y" -n $NS >/dev/null; done ;;
    frontreco)    for y in $REPO/km2/frontreco/*.yaml;do case "$y" in *kustomization*|*loadgenerator*)continue;;esac
                    kubectl apply -f "$y" -n $NS >/dev/null; done ;;
    frontcart)    # frontend+cart は夏休み用(redis外出し)を使い、redis-cart は単独で立てる
                  kubectl apply -f $DIR/manifests/frontcart.yaml -n $NS >/dev/null
                  kubectl apply -f $DIR/manifests/redis-cart.yaml -n $NS >/dev/null
                  for y in $REPO/km2/frontcart/*.yaml;do case "$y" in *kustomization*|*loadgenerator*|*frontcart.yaml)continue;;esac
                    kubectl apply -f "$y" -n $NS >/dev/null; done ;;
  esac
}

make_hpa(){ # 全Deployment(redis-cart除く)に、コンテナ別しきい値のHPAを作る
  local d cs c yaml
  for d in $(kubectl get deploy -n $NS -o jsonpath='{range .items[*]}{.metadata.name}{"\n"}{end}'); do
    [ "$d" = redis-cart ] && continue
    cs=$(kubectl get deploy/$d -n $NS -o jsonpath='{range .spec.template.spec.containers[*]}{.name}{"\n"}{end}')
    yaml="apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: $d
spec:
  scaleTargetRef: {apiVersion: apps/v1, kind: Deployment, name: $d}
  minReplicas: $HPA_MIN
  maxReplicas: $HPA_MAX
  metrics:"
    for c in $cs; do
      case "$c" in istio-proxy) continue;; esac
      yaml="$yaml
  - type: ContainerResource
    containerResource:
      name: cpu
      container: $c
      target: {type: Utilization, averageUtilization: $HPA_TARGET}"
    done
    printf '%s\n' "$yaml" | kubectl apply -f - -n $NS >/dev/null || echo "  !! HPA作成失敗: $d"
  done
}

deploy(){ local arm=$1
  echo "---- deploy $arm (HPA ${HPA_TARGET}% コンテナ別, ${HPA_MIN}-${HPA_MAX}台, 枠は変更しない) ----"
  kubectl delete hpa --all -n $NS >/dev/null 2>&1
  kubectl delete deploy --all -n $NS >/dev/null 2>&1
  for i in $(seq 1 40);do [ -z "$(kubectl get deploy -n $NS -o name 2>/dev/null)" ]&&break;sleep 3;done
  apply_arm "$arm"
  kubectl delete hpa --all -n $NS >/dev/null 2>&1   # マニフェスト同梱のHPAを消してから自前で作り直す
  for d in $(kubectl get deploy -n $NS -o jsonpath='{range .items[*]}{.metadata.name}{" "}{end}'); do
    kubectl patch deploy/$d -n $NS --type=merge -p '{"spec":{"template":{"metadata":{"annotations":{"sidecar.istio.io/inject":"false"}}}}}' >/dev/null 2>&1||true
    kubectl scale deploy/$d -n $NS --replicas=1 >/dev/null 2>&1||true
  done
  for d in $(kubectl get deploy -n $NS -o jsonpath='{range .items[*]}{.metadata.name}{" "}{end}'); do
    kubectl rollout status deploy/$d -n $NS --timeout=$ROLLOUT >/dev/null 2>&1||true; done
  make_hpa
  echo "  deploy: $(kubectl get deploy -n $NS --no-headers 2>/dev/null | awk '{printf "%s=%s ",$1,$2}')"
  echo "  hpa   : $(kubectl get hpa -n $NS --no-headers 2>/dev/null | awk '{printf "%s ",$1}')"
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
  local win=$(( MEAS*5/6 )); [ $win -lt 60 ] && win=60
  sleep $(( WARM + MEAS ))
  # --- 計測窓の終わりで資源側を採取 ---
  local RES PODS PEND NODE SOFT REPL
  RES=$(promq "sum(kube_pod_container_resource_requests{namespace=\"$NS\",resource=\"cpu\",pod!~\"k6load.*|promq.*\"})" | scalar)
  PODS=$(promq "count(kube_pod_status_phase{namespace=\"$NS\",phase=\"Running\",pod!~\"k6load.*|promq.*\"} == 1)" | scalar)
  PEND=$(promq "count(kube_pod_status_phase{namespace=\"$NS\",phase=\"Pending\",pod!~\"k6load.*|promq.*\"} == 1)" | scalar)
  NODE=$(promq "sum(rate(node_cpu_seconds_total{mode!=\"idle\"}[${win}s]))" | scalar)
  SOFT=$(promq "sum(rate(node_cpu_seconds_total{mode=\"softirq\"}[${win}s]))" | scalar)
  REPL=$(kubectl get deploy -n $NS --no-headers 2>/dev/null | awk '{printf "%s:%s ",$1,$4}')
  # --- k6 の集計 ---
  local done_at=$(( t_run + WARM + MEAS + 25 ))
  while [ "$(date +%s)" -lt "$done_at" ]; do sleep 5; done
  local logs summary; logs=$(kubectl logs "$pod" -n $NS 2>/dev/null)
  summary=$(printf '%s\n' "$logs" | sed -n '/@@@K6_BEGIN@@@/,/@@@K6_END@@@/p' | grep '{')
  echo "$summary" | grep -q '{' || { echo "  !! summary回収失敗(pod=$pod)"; kubectl delete job k6load -n $NS --ignore-not-found >/dev/null 2>&1; return; }
  SUMMARY="$summary" python3 - "$arm" "$CSV" "$cyc" "$RES" "$PODS" "$PEND" "$NODE" "$SOFT" "$REPL" <<'PY'
import sys,json,csv,os
arm,out,cyc,res,pods,pend,node,soft,repl=sys.argv[1:10]
d=json.loads(os.environ['SUMMARY'])
f=lambda x:(float(x) if x not in ('NA','') else 0.0)
it=d.get('iter_rate') or 0
eff=(it/f(res)) if f(res)>0 else 0
softper=(f(soft)*1000/it) if it>0 else 0
row=[cyc,arm,d.get('target_rate'),round(it,1),d.get('dropped'),round(d.get('failed_rate') or 0,4),
     round(d.get('p50') or 0,1),round(d.get('p99') or 0,1),round(f(res),2),round(eff,1),
     int(f(pods)),int(f(pend)),f(node),round(softper,2),repl.strip()]
with open(out,'a',newline='') as fh: csv.writer(fh).writerow(row)
print("  -> 捌けた=%.1f/%s周s drop=%s p50=%.0f p99=%.0f | 予約枠=%.2fコア Pod=%d(Pending %d) 効率=%.1f周/コア softirq=%.2f mc秒/周"
      %(it,d.get('target_rate'),d.get('dropped'),d.get('p50') or 0,d.get('p99') or 0,f(res),f(pods),f(pend),eff,softper))
print("     台数: %s"%repl.strip())
PY
  kubectl delete job k6load -n $NS --ignore-not-found >/dev/null 2>&1
}

ensure_promq
for c in $(seq 1 $CYCLES); do
  echo "################ CYCLE $c / $CYCLES $(date -Is) ################"
  for arm in $ARMS; do
    deploy "$arm"; sleep 10
    for r in $RATES; do run_rate "$arm" "$r" "$c"; done
  done
done
kubectl delete job k6load -n $NS --ignore-not-found >/dev/null 2>&1
echo "================ BUNDLE-VS-LOSS DONE $(date -Is) ================"
column -s, -t "$CSV" 2>/dev/null | cut -c1-190
