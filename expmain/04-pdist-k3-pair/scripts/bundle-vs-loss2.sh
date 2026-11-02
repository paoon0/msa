#!/usr/bin/env bash
# 【夏休み実験1・第2版】束ねの「通信の得」と「台数の損」の対決。第1版(bundle-vs-loss.sh)の反省を反映。
#
# 第1版で分かった問題:
#   (a) Pending の Pod(動いていない=CPUを使っていない)を予約枠に数えてしまい、結論を取り違えた。
#   (b) 束ねと無関係なサービス(checkout/payment/shipping)の台数がアームごとに違い、
#       そのノイズ(1.32コア)が束ね起因の差(0.64コア)より大きかった。
#   (c) 「HPA がいつ・何を見て台数を変えたか」が記録されておらず、事後に説明できなかった。
#
# 第2版の変更:
#   1. 15秒ごと(HPAの判断周期と同じ)に時系列を記録する。
#      - HPA が判断に使った利用率(コンテナ別 status.currentMetrics)
#      - 現在の台数 / HPAが望んだ台数(desired) / Ready台数 / Pending Pod数
#   2. 台数変更イベント(SuccessfulRescale)の時刻と理由文を記録。
#   3. 最終行の予約枠は「動いている Pod」と「Pending 込み」の両方を出す(取り違え防止)。
#   4. 反復(CYCLES)を既定3にし、束ね起因の差とノイズを分離できるようにする。
#   ※ 束ねと無関係なサービスの HPA は外さない(ユーザ判断)。代わりに台数を全部記録し、
#     事後に「束ねに関係する部分」だけ抜き出して比較する。
#
# 【2026-10-08 追加】同居ペアの前向き検証用に、新しいつまみを環境変数で足した (既定ではすべて従来どおり)。
#   RESET_EACH_POINT=1 ... 点 (POINTS) × 開始台数 (STARTS) ごとに HPA を消し、全 Deployment を開始台数に戻し、
#                          全 Pod Ready を待ってから k6 を開始し、直後に HPA を作る。results/timeline/events に
#                          point,start_replicas 列 (results には start_ok,frames_ok も) が増える。
#   POINTS / STARTS / SHUFFLE_POINTS / SHUFFLE_SEED / ROTATE_ARMS / POINT_SETTLE / POINT_READY_TIMEOUT
#   RS_STRICT / CHECK_FRAMES / LIMIT_OVERRIDE ... 枠の置換の取り違え防止と、コンテナ単位の limits 上書き
#   アーム pairsX / pairsY / pairsY2 / pairsP1 / pairsP2 / pairsP3 / pairsP1b / pairsQ1 / pairsQ2 / pairsQ3 ... manifests/pairs*.yaml (pairsX/Y/Y2/P1 は 3 Pod、P1b/P2/P3/Q1 は 2 Pod、Q2/Q3 は 1 Pod 同居)
#   各変数の意味は下の変数定義のコメントを見ること。
#
# 出力:
#   results-bundle-vs-loss2.csv  … 1点1行のまとめ
#   timeline-bundle-vs-loss2.csv … 15秒ごとの時系列(コンテナ別利用率・台数)
#   events-bundle-vs-loss2.csv   … 台数変更イベント
set -u
NS=exp
REPO=/home/mizuki/ダウンロード/msa
DIR=$REPO/km2/experiments/summer2026
K6DIR=$REPO/km2/experiments/k6
ARMS=${ARMS:-"normal frontcatalog frontreco frontcart"}
RATES=${RATES:-"200 260"}
HPA_MIN=${HPA_MIN:-1}
HPA_MAX=${HPA_MAX:-8}
HPA_TARGET=${HPA_TARGET:-70}
# HPAの様子見時間。既定(増やす0秒/減らす300秒)だと、立ち上がりの増やしすぎが計測窓(240秒)の間ずっと残るため、
# 増やす側に少し様子見を入れ、減らす側を短くして「落ち着いた台数」に計測窓内で到達させる。
SU_WIN=${SU_WIN:-30}
SD_WIN=${SD_WIN:-60}
# 負荷をいきなり掛けると1台目が過負荷になりHPAが暴走するので、開始時の台数を少し多めにしておく
PRESCALE=${PRESCALE:-2}
WARM=${WARM:-180}
MEAS=${MEAS:-240}
# 閲覧型(商品を見るだけで買わない)利用者の到着レート [周/秒]。0 で従来どおり購入型のみ。
# 目的: 全員が購入型だと全サービスの忙しさが完全に連動し、需要のズレ(=粒度損の源)が作れない。
# 空白区切りで複数指定できる(例 "0 100 200 300")。RATES と同じく1回のデプロイで連続測定する。
BROWSE_RATE=${BROWSE_RATE:-0}
SAMPLE=${SAMPLE:-15}          # 時系列の採取間隔[秒]。HPAの判断周期と同じ15秒が既定
PRE_VUS=${PRE_VUS:-600}
MAX_VUS=${MAX_VUS:-4000}
CYCLES=${CYCLES:-3}
RIGHTSIZE=${RIGHTSIZE:-0}     # 1 = 枠(requests)を適正化テーブルで置き換える(規則: (アイドル+1周CPU×k)/0.7)
RSTABLE=${RSTABLE:-$DIR/rightsize-requests.csv}
# CPU上限(limits)のつまみ。0=マニフェストのまま触らない / >0 = limits を requests の LIMIT_X 倍に置き換える。
# 【2026-08-20の発見】limits は「100msごとに quota だけ」というカーネルの配給制なので、バーストで来る仕事は
#   上限に叩かれて強制停止(スロットリング)される。250周/s以上の崩壊時、email が 48% 停止させられていた。
#   LIMIT_X=10 なら実質「絞りなし」= 崩壊が消えれば絞りが原因と確定できる(実験B)。
#   ※ RIGHTSIZE=1 のときだけ効く(枠の置き換えと同じ経路で当てるため)。
LIMIT_X=${LIMIT_X:-0}
LIMIT_MIN_M=${LIMIT_MIN_M:-200}
# 適正化枠を当てるサービスの限定。空なら全サービス。
# 既定 = 束ねの候補4つだけ。それ以外はマニフェストの枠に戻す(2026-09-01 ユーザ指示)。
RS_SERVICES=${RS_SERVICES:-"frontend productcatalogservice recommendationservice cartservice"}
# 枠と上限を何倍にするか。RS_SCALE=0.3333 で1/3。台数の刻みを細かくして粒度損の分解能を上げる用。
# LIMIT_SCALE は requests と同じ倍率にすること(片方だけ縮めると絞りの条件が変わる)。
RS_SCALE=${RS_SCALE:-1}
LIMIT_SCALE=${LIMIT_SCALE:-0}
# gRPC のクライアント側負荷分散 (2026-10-06 追加, grpc_lb_patch.py)。0 = 2026-10-06 までの全実験の条件 (接続1本で呼ばれる側の Pod に偏る)。
# 1 = 呼び出し側を負荷分散対応イメージに替え、宛先を headless Service にして、呼び出しごとに全 Pod へ振り分ける。
# 2 = 対照。イメージだけ負荷分散対応版に替え、振り分けは従来どおり (イメージ差と振り分けの効果を分けるため)。
GRPC_LB=${GRPC_LB:-1}   # 2026-10-07 から既定 1 (ユーザ決定)。それ以前の実験の再現は GRPC_LB=0
GRPC_RESOLVE_EVERY=${GRPC_RESOLVE_EVERY:-30}   # DNS を引き直す間隔[秒] (HPA が足した Pod を見つけるまでの最大遅れ)
LB_IMG_FRONTEND=${LB_IMG_FRONTEND:-mizuki0118/mygo:frontend-lb}
LB_IMG_CHECKOUT=${LB_IMG_CHECKOUT:-mizuki0118/mygo:checkout-lb}
LB_IMG_RECO=${LB_IMG_RECO:-mizuki0118/mygo:reco-lb}
# --- 2026-09-09 追加: 台数固定モード(HPA無し) ---
#   FIXED_REPLICAS > 0 で HPA を作らず、全 Deployment をこの台数に固定する(redis-cart は常に1)。
#   狙い: 「HPAが何台選んだか」という交絡を外し、同じ台数・同じ枠で通信の得だけを見る。
#   UNIFORM_REQ_M > 0 で全コンテナの requests をこの値に揃える(limits は触らない)。
#   HPA を使わないので requests は「スケール判断の分母」ではなく単なる予約になり、
#   一律にすると3アームの予約が完全に一致する(4台×10コンテナ×150m = 6.0コア)。
#   2026-07-14 の固定台数実験(latency-breakdown/fixed-replicas.sh)と同じ規則。
# アーム間・サイクル間に挟む休憩[秒]。長時間連続で回すとマシンが熱を持ち、
# 熱による周波数低下が測定に混ざる(同じ条件でも後半のサイクルだけCPU時間が増える)。
# 休憩中は負荷が無いので、その間にノードが冷える。
REST_ARM=${REST_ARM:-0}
REST_CYCLE=${REST_CYCLE:-0}
# 【2026-10-13 追加】点ごとの冷却待ち (RESET_EACH_POINT=1 のときだけ効く)。各点のリセットの前に、
#   CPU (coretemp) の最高温度が COOL_TEMP [℃] 以下になるまで待つ (最長 COOL_MAX_WAIT 秒)。
#   rightsizing/measure-mix-cpu.sh と同じ規則。既定は空 = 待たない (従来どおり)。
COOL_TEMP=${COOL_TEMP:-""}
COOL_MAX_WAIT=${COOL_MAX_WAIT:-600}
cpu_temp(){ local m=0 f v; for f in /sys/class/hwmon/hwmon*/; do [ "$(cat ${f}name 2>/dev/null)" = coretemp ] || continue
  for v in $(cat ${f}temp*_input 2>/dev/null); do [ $(( v / 1000 )) -gt $m ] && m=$(( v / 1000 )); done; done
  [ $m -gt 0 ] && echo $m; }
cool_down(){ [ -z "$COOL_TEMP" ] && return; local t0=$(date +%s) t
  while :; do t=$(cpu_temp); [ -z "$t" ] && { echo "  (温度が読めないので冷却待ちなし)"; return; }
    [ "$t" -le "$COOL_TEMP" ] && break
    [ $(( $(date +%s) - t0 )) -ge "$COOL_MAX_WAIT" ] && { echo "  !! 冷却待ちが上限 ${COOL_MAX_WAIT}s に達した (${t}℃) のまま開始"; break; }
    sleep 10; done
  echo "  冷却待ち $(( $(date +%s) - t0 ))s → ${t}℃"; }
FIXED_REPLICAS=${FIXED_REPLICAS:-0}
UNIFORM_REQ_M=${UNIFORM_REQ_M:-0}
# recommendationservice の readiness/liveness プローブの timeoutSeconds を上書きする(0=マニフェストのまま)。
#   既定は1秒で、負荷が高いと Python(GIL)の reco が応答しきれず NotReady に落ち、
#   Service のエンドポイントから外れて残りの台に負荷が集中する連鎖が起きる(2026-09-08 発見)。
#   これを緩めて分離の容量が回復するかを見るのが目的(= 容量向上の主因の切り分け)。
#   マニフェストは編集せず、デプロイ後に patch で当てる。3アームすべてに同じ値を当てて条件を揃える。
PROBE_TIMEOUT=${PROBE_TIMEOUT:-0}
# mega を複数台にすると Pod内 redis も台数分でき、カートが割れて1周の仕事量が他アームと変わる。
#   shared = redis だけ Pod の外に出して全 megapod で共有(normal/front3 と同条件)
MEGA_REDIS=${MEGA_REDIS:-shared}
CYC_START=${CYC_START:-1}     # サイクル番号の開始値(条件を交互に回すとき、番号を通しにするために使う)
# --- 2026-10-08 追加: 同居ペアの前向き検証用 (すべて既定では従来どおりの挙動) ---
# 枠の置換の取り違え防止。RS_STRICT=1 なら、対象サービスが RSTABLE に無いとき警告だけで続けず、そのアームを中止する。
RS_STRICT=${RS_STRICT:-0}
# CHECK_FRAMES=1 なら、デプロイ後 (RESET_EACH_POINT では各点の前にも) 全コンテナの requests が表どおりか、
# LIMIT_OVERRIDE の limits が指定どおりか、requests <= limits かを検査し、1つでも違えば「!! 枠不一致」を出してそのアーム/点を中止する。
# RIGHTSIZE=1 が前提。RS_SERVICES を渡し忘れると既定の4サービスだけが対象になる (全10サービスを明示して渡すこと)。
CHECK_FRAMES=${CHECK_FRAMES:-0}
# サービス名=値 (空白区切り) で limits.cpu を**コンテナ単位**に上書き。requests は触らない (枠の置換のあとに当てる)。
# 例: LIMIT_OVERRIDE="frontend=3000m productcatalogservice=3000m adservice=1000m" (rightsizing/measure-mix-cpu.sh と同じ書式)。RIGHTSIZE=1 が前提。
LIMIT_OVERRIDE=${LIMIT_OVERRIDE:-}
# RESET_EACH_POINT=1: 各アームのデプロイは1サイクルに1回。そのあと POINTS × STARTS の各組について
#   HPA 全削除 → 全 Deployment を開始台数に scale (redis-cart は1) → 全 Pod Ready 待ち → k6 開始 → 直後に HPA 作成 → 従来どおり計測。
#   RATES / BROWSE_RATE は使わない (点は POINTS で指定)。FIXED_REPLICAS とは併用しない。
RESET_EACH_POINT=${RESET_EACH_POINT:-0}
POINTS=${POINTS:-}               # 点の名前 b<購入型 周/秒>v<閲覧型 周/秒> (rightsizing/measure-mix-cpu.sh と同じ形式。例 "b100v0 b100v100 b100v150")
STARTS=${STARTS:-"1 2"}          # 開始台数 (全 Deployment を最初にこの台数にする。redis-cart は常に1)
SHUFFLE_POINTS=${SHUFFLE_POINTS:-0}   # 1 = (点 × 開始台数) の順番をサイクルごとに並べ替える。乱数は SHUFFLE_SEED とサイクル番号で固定 (再現できる)
SHUFFLE_SEED=${SHUFFLE_SEED:-1}
ROTATE_ARMS=${ROTATE_ARMS:-0}    # 1 = ARMS の先頭アームをサイクルごとに1つずつ回転 (cyc1: A B C D / cyc2: B C D A ...)。CYC_START 基準
# リセット後、k6 を始める前に置く待ち時間[秒]。gRPC の負荷分散 (GRPC_LB=1) は DNS を GRPC_RESOLVE_EVERY 秒ごとにしか引き直さず、
#   scale で増減した Pod を既存の呼び出し側が見つけるまで最大その秒数かかるので、それより少し長く置く (HPA はまだ無いので無負荷の空白は HPA に影響しない)。
POINT_SETTLE=${POINT_SETTLE:-$(( GRPC_RESOLVE_EVERY + 5 ))}
POINT_READY_TIMEOUT=${POINT_READY_TIMEOUT:-300}   # リセット後に全台 Ready にならない場合、この秒数で点を中止する
FRAMES_OK=NA                     # 直近の枠検査の結果 (1=全部一致 / 0=不一致 / NA=検査していない (CHECK_FRAMES=0))。results の frames_ok 列に入る
CSV=${CSV:-$DIR/results-bundle-vs-loss2.csv}
TL=${TL:-$DIR/timeline-bundle-vs-loss2.csv}
EV=${EV:-$DIR/events-bundle-vs-loss2.csv}
LOG=${LOG:-$DIR/bundle-vs-loss2.log}
[ "$FIXED_REPLICAS" != 0 ] && PRESCALE=$FIXED_REPLICAS
PROM="http://prometheus-grafana-kube-pr-prometheus.monitoring.svc:9090"
ROLLOUT=300s

exec > >(tee -a "$LOG") 2>&1
echo "================ BUNDLE-VS-LOSS2 START $(date -Is) arms=[$ARMS] rates=[$RATES] cycles=$CYCLES HPA=${HPA_TARGET}%/${HPA_MIN}-${HPA_MAX}台 warm=${WARM}s meas=${MEAS}s browse=${BROWSE_RATE}周/s sample=${SAMPLE}s 様子見=増${SU_WIN}s/減${SD_WIN}s 開始${PRESCALE}台 rightsize=${RIGHTSIZE} limit_x=${LIMIT_X} grpc_lb=${GRPC_LB} ================"
[ "$RESET_EACH_POINT" = 1 ] && echo "  点ごとリセット: points=[$POINTS] starts=[$STARTS] shuffle=$SHUFFLE_POINTS(seed $SHUFFLE_SEED) rotate_arms=$ROTATE_ARMS settle=${POINT_SETTLE}s ready_timeout=${POINT_READY_TIMEOUT}s rs_strict=$RS_STRICT check_frames=$CHECK_FRAMES limit_override=[${LIMIT_OVERRIDE}] rs_services=[${RS_SERVICES}] cool=${COOL_TEMP:-なし}℃"

# 点の名前 → "購入型 閲覧型" (rightsizing/measure-mix-cpu.sh の parse_point と同じ規則)。b100 / v200 / b100v150。
parse_point(){ local p=$1 b=0 v=0
  [[ $p =~ ^b([0-9]+) ]] && b=${BASH_REMATCH[1]}
  [[ $p =~ v([0-9]+)$ ]] && v=${BASH_REMATCH[1]}
  [[ $p =~ ^(b[0-9]+)?(v[0-9]+)?$ ]] && [ -n "$p" ] || { echo "!! 点の名前が不正: $p" >&2; return 1; }
  echo "$b $v"; }

# --- 設定の取り違えは測定を始める前に止める ---
if [ "$RESET_EACH_POINT" = 1 ]; then
  [ -n "$POINTS" ] || { echo "!! RESET_EACH_POINT=1 には POINTS が要る"; exit 1; }
  [ "$FIXED_REPLICAS" = 0 ] || { echo "!! RESET_EACH_POINT=1 は FIXED_REPLICAS と併用しない"; exit 1; }
  for p in $POINTS; do parse_point "$p" >/dev/null || exit 1; done
  for n in $STARTS; do [[ $n =~ ^[1-9][0-9]*$ ]] || { echo "!! STARTS が不正: $n"; exit 1; }; done
fi
if [ "$CHECK_FRAMES" = 1 ] || [ -n "$LIMIT_OVERRIDE" ]; then
  [ "$RIGHTSIZE" = 1 ] || { echo "!! CHECK_FRAMES / LIMIT_OVERRIDE は RIGHTSIZE=1 が前提"; exit 1; }
fi
if [ "$CHECK_FRAMES" = 1 ]; then
  # RS_SERVICES の既定は4サービスだけ。渡し忘れると残り6サービスの枠がマニフェストのままになるので、全10サービスが入っているかを先に確かめる
  for sv in frontend checkoutservice cartservice productcatalogservice currencyservice paymentservice shippingservice emailservice recommendationservice adservice; do
    case " $RS_SERVICES " in *" $sv "*) ;; *) echo "!! CHECK_FRAMES=1 なのに RS_SERVICES に $sv が無い (全10サービスを明示して渡すこと): [$RS_SERVICES]"; exit 1;; esac
  done
fi

# 出力ファイルのヘッダ。RESET_EACH_POINT=1 のときだけ列が増えるので、形式の違うファイルへの追記は止める。
H_CSV="cycle,arm,target_rate,iter_rate,dropped,failed_rate,p50,p99,running_cores,pending_cores,eff_iter_per_running_core,pods,pending,node_cpu_sec,softirq_cpu_sec,k6_cpu_sec,prod_p50,cart_p50,chk_p50,prod_p99,cart_p99,chk_p99,replicas,limit_x,dropped_win,started,replicas_at_window_start,replicas_changed_in_window,browse_rate_target,browse_rate,browse_dropped_win,browse_p50,browse_p99,rs_scale,limit_scale,reserved_core_sec,pending_core_sec,reserved_avg_cores,n_samples"
H_TL="cycle,arm,target_rate,limit_x,browse_rate,t_rel,deploy,container,hpa_util_pct,current_replicas,desired_replicas,ready_replicas,pending_pods,ns_running_cores,ns_pending_cores"
H_EV="cycle,arm,target_rate,limit_x,browse_rate,time,object,message"
if [ "$RESET_EACH_POINT" = 1 ]; then
  H_CSV="$H_CSV,point,start_replicas,start_ok,frames_ok"; H_TL="$H_TL,point,start_replicas"; H_EV="$H_EV,point,start_replicas"
fi
for pair in "$CSV:$H_CSV" "$TL:$H_TL" "$EV:$H_EV"; do
  f=${pair%%:*}; h=${pair#*:}
  if [ -s "$f" ]; then
    if [ "$RESET_EACH_POINT" = 1 ] && [ "$(head -1 "$f")" != "$h" ]; then
      echo "!! 既存ファイルの列が RESET_EACH_POINT=1 の形式と違う (別名の出力先を使うこと): $f"; exit 1; fi
    if [ "$RESET_EACH_POINT" != 1 ] && head -1 "$f" | grep -q 'start_replicas'; then
      echo "!! 既存ファイルは RESET_EACH_POINT=1 の形式 (列が増える)。RESET_EACH_POINT=1 で追記するか別名にすること: $f"; exit 1; fi
  fi
done
[ -s "$CSV" ] || echo "$H_CSV" > "$CSV"
[ -s "$TL" ] || echo "$H_TL" > "$TL"
[ -s "$EV" ] || echo "$H_EV" > "$EV"

ensure_promq(){ [ "$(kubectl get pod promq -n $NS -o jsonpath='{.status.phase}' 2>/dev/null)" = Running ] && return
  kubectl delete pod promq -n $NS --ignore-not-found >/dev/null 2>&1
  kubectl run promq -n $NS --image=curlimages/curl:latest --restart=Never --command -- sleep 86400 >/dev/null 2>&1
  for i in $(seq 1 30);do [ "$(kubectl get pod promq -n $NS -o jsonpath='{.status.phase}' 2>/dev/null)" = Running ]&&break;sleep 2;done; }
promq(){ local q="$1" i out; for i in 1 2 3 4 5;do ensure_promq
  out=$(kubectl exec promq -n $NS -- curl -s --max-time 25 "$PROM/api/v1/query" --data-urlencode "query=$q" 2>/dev/null)
  [ -n "$out" ]&&{ echo "$out"; return; }; sleep 4; done; echo ""; }
scalar(){ python3 -c "import sys,json;r=json.load(sys.stdin).get('data',{}).get('result',[]);print(round(float(r[0]['value'][1]),4) if r else 'NA')" 2>/dev/null; }

# 分離(km2/normal/)の全サービスから、引数で挙げたものだけ除いて apply する。
# 束ねアームでは束ねた2サービスの単独 Deployment が要らないので、それを除くのに使う。
apply_normal_except(){
  local skip=" $* " f
  for f in frontend checkoutservice cartservice productcatalogservice currencyservice \
           paymentservice shippingservice emailservice recommendationservice adservice; do
    case "$skip" in *" $f "*) continue;; esac
    kubectl apply -f $REPO/km2/normal/$f.yaml -n $NS >/dev/null
  done
}

apply_arm(){ local arm=$1
  case "$arm" in
    # normal2 = normal と同じ構成 (2026-10-15: 分離だけ 1 サイクルに 2 回測るため。アーム名を分けて回の取り違えを防ぐ)
    normal|normal2) for f in frontend checkoutservice cartservice productcatalogservice currencyservice \
                            paymentservice shippingservice emailservice recommendationservice adservice; do
                    kubectl apply -f $REPO/km2/normal/$f.yaml -n $NS >/dev/null; done ;;
    frontcatalog) for y in $REPO/km2/variants/frontcatalog/*.yaml;do case "$y" in *kustomization*|*loadgenerator*)continue;;esac
                    kubectl apply -f "$y" -n $NS >/dev/null; done ;;
    frontreco)    for y in $REPO/km2/variants/frontreco/*.yaml;do case "$y" in *kustomization*|*loadgenerator*)continue;;esac
                    kubectl apply -f "$y" -n $NS >/dev/null; done ;;
    frontrecocartcatalog)
                  # 4つ束ね: frontend + recommendation + productcatalog + cartservice を1Podに同居。
                  # redis-cart だけ束ねの外(状態を持つため)。cart→redis は ClusterIP。
                  # 3つ束ね(km2/variants/frontrecocatalogcart/)に cartservice を足したもの。2026-09-03 作成。
                  kubectl apply -f $DIR/manifests/frontrecocartcatalog.yaml -n $NS >/dev/null
                  # cartservice の Deployment は不要(同居)。redis と他サービスは3つ束ねの定義を流用
                  for y in $REPO/km2/variants/frontrecocatalogcart/*.yaml;do
                    case "$y" in *kustomization*|*loadgenerator*|*hpa-percontainer*|*frontrecocatalogcart.yaml)continue;;esac
                    case "$y" in *cartservice.yaml)
                      # cartservice.yaml には redis-cart も入っているので redis だけ取り出す
                      # 「redis-cart を含む」で絞ると cartservice の Deployment も一致してしまう
                      # (REDIS_ADDR: "redis-cart:6379" という文字列を持つため)。
                      # metadata.name が redis-cart のものだけを残す。
                      python3 "$DIR/extract_redis.py" "$y" | kubectl apply -f - -n $NS >/dev/null
                      continue;;
                    esac
                    kubectl apply -f "$y" -n $NS >/dev/null; done ;;
    frontrecocatalog)
                  # 3つ束ね: frontend + recommendation + productcatalog を1Podに同居。
                  # cart は redis の分裂を避けるため束ねの外(別Pod, ClusterIP)。
                  # ディレクトリ名は frontrecocatalogcart だが中身は3コンテナ(名前は旧計画の名残)。
                  # hpa-percontainer.yaml は同梱HPAなので除外(make_hpa で作り直すため)
                  for y in $REPO/km2/variants/frontrecocatalogcart/*.yaml;do
                    case "$y" in *kustomization*|*loadgenerator*|*hpa-percontainer*)continue;;esac
                    kubectl apply -f "$y" -n $NS >/dev/null; done ;;
    # --- 2026-09-07 追加: 需要のズレを最大化する束ね(閲覧型は checkout/email に届かない) ---
    #   normal の各サービスから「束ねた2つ」を除いて apply し、束ねマニフェストを上書きする。
    frontemail)      apply_normal_except frontend emailservice
                     kubectl apply -f $DIR/manifests/frontemail.yaml -n $NS >/dev/null ;;
    frontcheckout)   apply_normal_except frontend checkoutservice
                     kubectl apply -f $DIR/manifests/frontcheckout.yaml -n $NS >/dev/null ;;
    checkoutemail)   apply_normal_except checkoutservice emailservice
                     kubectl apply -f $DIR/manifests/checkoutemail.yaml -n $NS >/dev/null ;;
    catalogcheckout) apply_normal_except productcatalogservice checkoutservice
                     kubectl apply -f $DIR/manifests/catalogcheckout.yaml -n $NS >/dev/null ;;
    # --- 2026-10-08 追加: 同居ペアの前向き検証 (3 Pod を同時に同居。束ねていない4サービスは normal のまま、redis-cart は別 Pod) ---
    #   各ペアの中身は manifests/pairs*.yaml の冒頭コメントを参照。
    pairsX)  apply_normal_except productcatalogservice recommendationservice checkoutservice paymentservice shippingservice emailservice
             kubectl apply -f $DIR/manifests/pairsX.yaml -n $NS >/dev/null ;;
    pairsY)  apply_normal_except productcatalogservice paymentservice shippingservice recommendationservice frontend checkoutservice
             kubectl apply -f $DIR/manifests/pairsY.yaml -n $NS >/dev/null ;;
    pairsY2) apply_normal_except productcatalogservice emailservice paymentservice recommendationservice frontend shippingservice
             kubectl apply -f $DIR/manifests/pairsY2.yaml -n $NS >/dev/null ;;
    # --- 2026-10-13 追加: ペア距離実験 (P の近さ)。中身は manifests/pairsP*.yaml の冒頭コメント ---
    pairsP1) apply_normal_except frontend adservice checkoutservice shippingservice productcatalogservice recommendationservice
             kubectl apply -f $DIR/manifests/pairsP1.yaml -n $NS >/dev/null ;;
    #   pairsP2: normal/cartservice.yaml は redis-cart も含むので、cartservice を外すと redis-cart も消える → redis-cart.yaml を別途 apply (frontcart と同じ)
    pairsP2) apply_normal_except frontend cartservice productcatalogservice checkoutservice
             kubectl apply -f $DIR/manifests/redis-cart.yaml -n $NS >/dev/null
             kubectl apply -f $DIR/manifests/pairsP2.yaml -n $NS >/dev/null ;;
    pairsP3) apply_normal_except frontend productcatalogservice checkoutservice currencyservice
             kubectl apply -f $DIR/manifests/pairsP3.yaml -n $NS >/dev/null ;;
    # --- 2026-10-15 追加: pairsP1 から front+ad を外したもの (枠 k=3 の再測定。ad はペアに入れない) ---
    pairsP1b) apply_normal_except checkoutservice shippingservice productcatalogservice recommendationservice
             kubectl apply -f $DIR/manifests/pairsP1b.yaml -n $NS >/dev/null ;;
    # --- 2026-10-15 追加: 通信量の太い線から選んだ 4 組 (ρ の差 0.01〜0.37)。中身は manifests/pairsQ*.yaml の冒頭コメント ---
    #   pairsQ1: cartservice を外すと redis-cart も消える → redis-cart.yaml を別途 apply (pairsP2 と同じ)
    pairsQ1) apply_normal_except frontend currencyservice checkoutservice cartservice
             kubectl apply -f $DIR/manifests/redis-cart.yaml -n $NS >/dev/null
             kubectl apply -f $DIR/manifests/pairsQ1.yaml -n $NS >/dev/null ;;
    pairsQ2) apply_normal_except frontend recommendationservice
             kubectl apply -f $DIR/manifests/pairsQ2.yaml -n $NS >/dev/null ;;
    pairsQ3) apply_normal_except frontend checkoutservice
             kubectl apply -f $DIR/manifests/pairsQ3.yaml -n $NS >/dev/null ;;
    mega)         # 全部入り: 11サービスを1Podに同居(km2/variants/all/all.yaml)。
                  kubectl apply -f $REPO/km2/variants/all/all.yaml -n $NS >/dev/null
                  if [ "$MEGA_REDIS" = shared ]; then
                    # redis だけ Pod の外へ(複数台にすると Pod内 redis が分裂しカートが割れるため)
                    python3 "$DIR/extract_redis.py" $REPO/km2/normal/cartservice.yaml | kubectl apply -f - -n $NS >/dev/null
                    idx=$(kubectl get deploy megapod -n $NS -o jsonpath='{range .spec.template.spec.containers[*]}{.name}{"\n"}{end}' | grep -n '^redis$' | cut -d: -f1)
                    [ -n "$idx" ] && kubectl patch deploy megapod -n $NS --type=json \
                      -p "[{\"op\":\"remove\",\"path\":\"/spec/template/spec/containers/$((idx-1))\"}]" >/dev/null
                    kubectl set env deploy/megapod -n $NS --containers=cartservice REDIS_ADDR=redis-cart:6379 >/dev/null
                  fi ;;
    frontcart)    kubectl apply -f $DIR/manifests/frontcart.yaml -n $NS >/dev/null
                  kubectl apply -f $DIR/manifests/redis-cart.yaml -n $NS >/dev/null
                  for y in $REPO/km2/variants/frontcart/*.yaml;do case "$y" in *kustomization*|*loadgenerator*|*frontcart.yaml)continue;;esac
                    kubectl apply -f "$y" -n $NS >/dev/null; done ;;
  esac
}

# 枠の検査 (CHECK_FRAMES=1)。いまの Deployment の requests / limits が表どおりかを apply_rightsize.py の CHECK=1 で調べる。
# 戻り値 0 = 全部一致 / 1 = 不一致あり (不一致の一覧を「!! 枠不一致」付きで出す)。
check_frames(){ local out rc
  out=$(kubectl get deploy -n $NS -o json | CHECK=1 TABLE="$RSTABLE" NS="$NS" RS_SERVICES="$RS_SERVICES" RS_SCALE="$RS_SCALE" \
          LIMIT_OVERRIDE="$LIMIT_OVERRIDE" python3 "$DIR/apply_rightsize.py" 2>&1); rc=$?
  if [ $rc -ne 0 ]; then
    FRAMES_OK=0
    echo "  !! 枠不一致 (rc=$rc): 表=$RSTABLE"; printf '%s\n' "$out" | sed 's/^/     /'
    return 1
  fi
  FRAMES_OK=1; echo "  枠検査 OK: 全コンテナの requests が表どおり (limits 上書き=[${LIMIT_OVERRIDE:-なし}], requests<=limits)"; return 0; }

# 点の開始状態を作る (RESET_EACH_POINT=1)。HPA 全削除 → 全 Deployment を n0 台に (redis-cart は1) → 全台 Ready と旧 Pod の消滅を待つ → 待ち時間。
# 戻り値 0 = 準備完了 / 1 = 中止 (枠不一致 or Ready にならない)。
reset_point(){ local arm=$1 n0=$2 pt=$3 d waited=0 notready term=0
  echo "---- 点のリセット [$arm][$pt] 開始${n0}台 $(date -Is) ----"
  kubectl delete hpa --all -n $NS >/dev/null 2>&1
  if [ "$CHECK_FRAMES" = 1 ]; then check_frames || { echo "!! 点中止 [$arm][$pt] 開始${n0}台: 枠不一致"; return 1; }; fi
  for d in $(kubectl get deploy -n $NS -o jsonpath='{range .items[*]}{.metadata.name}{" "}{end}'); do
    if [ "$d" = redis-cart ]; then kubectl scale deploy/$d -n $NS --replicas=1 >/dev/null 2>&1||true
    else kubectl scale deploy/$d -n $NS --replicas=$n0 >/dev/null 2>&1||true; fi
  done
  while [ $waited -lt $POINT_READY_TIMEOUT ]; do
    # READY 列は ready/desired。desired が狙いの台数 (redis-cart は1) と違うものも未完了とみなす。
    notready=$(kubectl get deploy -n $NS --no-headers 2>/dev/null | awk -v n0=$n0 '{split($2,r,"/"); w=($1=="redis-cart")?1:n0; if(r[1]!=r[2]||r[2]!=w) printf "%s(%s) ",$1,$2}')
    # 台数を減らしたあとの終了処理中 (Terminating) の Pod も、全部消えるまで待つ (k6load/promq は除く)
    term=$(kubectl get pods -n $NS --no-headers 2>/dev/null | awk '$1!~/^(k6load|promq)/ && $3=="Terminating"{n++} END{print n+0}')
    [ -z "$notready" ] && [ "$term" = 0 ] && break
    sleep 5; waited=$((waited+5))
  done
  if [ $waited -ge $POINT_READY_TIMEOUT ]; then
    echo "!! 点中止 [$arm][$pt] 開始${n0}台: 全台Readyにならない(待機${waited}s): $(kubectl get deploy -n $NS --no-headers | awk '{printf "%s=%s ",$1,$2}') Terminating=${term}"
    return 1
  fi
  echo "  リセット完了 (全台Ready待ち ${waited}s)。gRPC 引き直し待ち ${POINT_SETTLE}s: $(kubectl get deploy -n $NS --no-headers 2>/dev/null | awk '{printf "%s=%s ",$1,$2}')"
  sleep $POINT_SETTLE
  return 0; }

# 1サイクルぶんの (点 × 開始台数) を "点:開始台数" の並びで出す。SHUFFLE_POINTS=1 ならサイクル番号と SHUFFLE_SEED で固定した乱数で並べ替える。
order_points(){ python3 - "$1" "$SHUFFLE_POINTS" "$SHUFFLE_SEED" "$POINTS" "$STARTS" <<'PY'
import sys, random
cyc, shuf, seed, points, starts = sys.argv[1:6]
combos = ["%s:%s" % (p, n) for p in points.split() for n in starts.split()]
if shuf == '1':
    random.Random("%s-%s" % (seed, cyc)).shuffle(combos)   # 文字列シードは実行ごとに変わらない (PYTHONHASHSEED の影響なし)
print(" ".join(combos))
PY
}

# ARMS を k 個ぶん左へ回転して出す (ROTATE_ARMS=1 用)
rotate_arms(){ local k=$1 a n i out=""; read -r -a a <<< "$ARMS"; n=${#a[@]}
  for ((i=0;i<n;i++)); do out="$out ${a[$(( (i+k) % n ))]}"; done; echo $out; }

make_hpa(){ local d cs c yaml
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
  behavior:
    scaleUp:   {stabilizationWindowSeconds: $SU_WIN}
    scaleDown: {stabilizationWindowSeconds: $SD_WIN}
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
  if [ "$FIXED_REPLICAS" != 0 ]; then
    echo "---- deploy $arm (HPA無し・${FIXED_REPLICAS}台固定, 枠 req=${UNIFORM_REQ_M}m一律/limits据置) ----"
  else
    echo "---- deploy $arm (HPA ${HPA_TARGET}% コンテナ別, ${HPA_MIN}-${HPA_MAX}台, 枠は変更しない) ----"
  fi
  kubectl delete hpa --all -n $NS >/dev/null 2>&1
  kubectl delete deploy --all -n $NS >/dev/null 2>&1
  for i in $(seq 1 40);do [ -z "$(kubectl get deploy -n $NS -o name 2>/dev/null)" ]&&break;sleep 3;done
  apply_arm "$arm"
  kubectl delete hpa --all -n $NS >/dev/null 2>&1
  for d in $(kubectl get deploy -n $NS -o jsonpath='{range .items[*]}{.metadata.name}{" "}{end}'); do
    kubectl patch deploy/$d -n $NS --type=merge -p '{"spec":{"template":{"metadata":{"annotations":{"sidecar.istio.io/inject":"false"}}}}}' >/dev/null 2>&1||true
    kubectl scale deploy/$d -n $NS --replicas=$PRESCALE >/dev/null 2>&1||true
  done
  kubectl scale deploy/redis-cart -n $NS --replicas=1 >/dev/null 2>&1||true
  if [ "$UNIFORM_REQ_M" != 0 ]; then
    echo "  枠(requests)を一律 ${UNIFORM_REQ_M}m に(limits は据え置き。redis-cart は除く)"
    for d in $(kubectl get deploy -n $NS -o jsonpath='{range .items[*]}{.metadata.name}{" "}{end}'); do
      [ "$d" = redis-cart ] && continue
      kubectl set resources deploy/$d -n $NS --requests=cpu=${UNIFORM_REQ_M}m >/dev/null 2>&1||true
    done
  fi
  if [ "$RIGHTSIZE" = 1 ]; then
    echo "  枠を適正化テーブルで置換: $RSTABLE (対象: ${RS_SERVICES:-全サービス}, 倍率 req×${RS_SCALE} lim×${LIMIT_SCALE})"
    [ "$LIMIT_X" != 0 ] && echo "  CPU上限(limits)も置換: requests × $LIMIT_X (下限 ${LIMIT_MIN_M}m)"
    [ -n "$LIMIT_OVERRIDE" ] && echo "  limits をコンテナ単位で上書き: $LIMIT_OVERRIDE (requests はそのまま)"
    kubectl get deploy -n $NS -o json | TABLE="$RSTABLE" NS="$NS" LIMIT_X="$LIMIT_X" LIMIT_MIN_M="$LIMIT_MIN_M" RS_SERVICES="$RS_SERVICES" \
      RS_SCALE="$RS_SCALE" LIMIT_SCALE="$LIMIT_SCALE" RS_STRICT="$RS_STRICT" LIMIT_OVERRIDE="$LIMIT_OVERRIDE" \
      python3 "$DIR/apply_rightsize.py" > /tmp/rs-$$.sh
    if [ $? -ne 0 ] && [ "$RS_STRICT" = 1 ]; then
      echo "!! アーム中止 [$arm]: 枠の置換に失敗 (RS_STRICT=1。表に無いコンテナ等。stderr の「!!」行を見ること)"; rm -f /tmp/rs-$$.sh; return 1; fi
    bash /tmp/rs-$$.sh; rm -f /tmp/rs-$$.sh
  fi
  if [ "$GRPC_LB" = 1 ] || [ "$GRPC_LB" = 2 ]; then
    if [ "$GRPC_LB" = 1 ]; then echo "  gRPC 負荷分散: round_robin + headless Service (引き直し ${GRPC_RESOLVE_EVERY}s)"
    else echo "  gRPC 負荷分散の対照: イメージだけ差し替え、振り分けは従来どおり (pick_first)"; fi
    { printf '{"deploy":'; kubectl get deploy -n $NS -o json; printf ',"svc":'; kubectl get svc -n $NS -o json; printf '}'; } \
      | NS="$NS" GRPC_RESOLVE_EVERY="$GRPC_RESOLVE_EVERY" LB_IMG_FRONTEND="$LB_IMG_FRONTEND" \
        LB_IMG_CHECKOUT="$LB_IMG_CHECKOUT" LB_IMG_RECO="$LB_IMG_RECO" LB_IMAGES_ONLY=$([ "$GRPC_LB" = 2 ] && echo 1 || echo 0) python3 "$DIR/grpc_lb_patch.py" > /tmp/lb-$$.sh
    bash /tmp/lb-$$.sh; rm -f /tmp/lb-$$.sh
  fi
  if [ "$PROBE_TIMEOUT" != 0 ]; then
    # コンテナは name で突き合わされる(strategic merge patch)ので reco のコンテナだけに当たる。
    # アームごとに reco が居る Deployment とコンテナ名が違う。
    for spec in "recommendationservice:server" "frontend:recommendation" "megapod:recommendationservice"; do
      d=${spec%%:*}; pc=${spec##*:}   # 変数名は c を避ける(外側のサイクル番号と衝突する)
      kubectl get deploy/$d -n $NS >/dev/null 2>&1 || continue
      kubectl patch deploy/$d -n $NS -p "{\"spec\":{\"template\":{\"spec\":{\"containers\":[{\"name\":\"$pc\",\"readinessProbe\":{\"timeoutSeconds\":$PROBE_TIMEOUT},\"livenessProbe\":{\"timeoutSeconds\":$PROBE_TIMEOUT}}]}}}}" >/dev/null 2>&1 \
        && echo "  プローブ緩和: $d/$pc timeoutSeconds=$PROBE_TIMEOUT"
    done
  fi
  for d in $(kubectl get deploy -n $NS -o jsonpath='{range .items[*]}{.metadata.name}{" "}{end}'); do
    kubectl rollout status deploy/$d -n $NS --timeout=$ROLLOUT >/dev/null 2>&1||true; done
  echo "  枠(req/上限lim): $(kubectl get deploy -n $NS -o jsonpath='{range .items[*]}{.metadata.name}={range .spec.template.spec.containers[*]}{.name}:{.resources.requests.cpu}/{.resources.limits.cpu}{","}{end}{" "}{end}')"
  if [ "$CHECK_FRAMES" = 1 ]; then check_frames || { echo "!! アーム中止 [$arm]: 枠不一致"; return 1; }; fi
  if [ "$RESET_EACH_POINT" = 1 ]; then echo "  HPAは作らない (RESET_EACH_POINT=1: 各点で k6 開始の直後に作る)"
  elif [ "$FIXED_REPLICAS" = 0 ]; then make_hpa; else echo "  HPAは作らない(${FIXED_REPLICAS}台固定)"; fi
  # 全 Deployment が所定台数 Ready になるまで待つ。
  # 2026-09-11: rollout status が先に返ってしまい、Ready 3/4 の状態で負荷を開始して1サイクル無効になった。
  local waited=0
  while [ $waited -lt 420 ]; do
    local notready
    # READY 列は "ready/desired" なので "/" で割って比べる(2026-09-13 修正: 以前は $4=AVAILABLE と比べていて常に不一致→毎回420s待ち切っていた)
    notready=$(kubectl get deploy -n $NS --no-headers 2>/dev/null | awk '{split($2,r,"/"); if(r[1]!=r[2]) printf "%s(%s) ",$1,$2}')
    [ -z "$notready" ] && break
    sleep 10; waited=$((waited+10))
  done
  [ $waited -ge 420 ] && echo "  !! 全台Readyにならないまま続行(待機${waited}s): $(kubectl get deploy -n $NS --no-headers | awk '{split($2,r,"/"); if(r[1]!=r[2]) printf "%s=%s ",$1,$2}')"
  [ $waited -gt 0 ] && echo "  全台Ready待ち: ${waited}s"
  echo "  deploy: $(kubectl get deploy -n $NS --no-headers 2>/dev/null | awk '{printf "%s=%s ",$1,$2}')"
}

# --- 15秒ごとの時系列採取: HPAが見ている利用率(コンテナ別)・台数・Pending ---
#     注意: 集計用pythonは別ファイル(sample_hpa.py)。`python3 - <<'PY'` にすると heredoc が
#     標準入力を占有し、パイプで渡した JSON が python に届かない(第2版スモークで実際に0行になった)。
sample_once(){ local cyc=$1 arm=$2 rate=$3 t0=$4 brw=${5:-0}
  kubectl get hpa,deploy,pods -n $NS -o json 2>/dev/null | \
    CYC="$cyc" ARM="$arm" RATE="$rate" LX="$LIMIT_X" BRW="$brw" T0="$t0" python3 "$DIR/sample_hpa.py" >> "$TL" 2>/dev/null
}

# 第5・6引数 pt, n0 は RESET_EACH_POINT=1 のときだけ渡す (点の名前と開始台数。results/timeline/events の追加列になる)
run_rate(){ local arm=$1 rate=$2 cyc=${3:-1} brw=${4:-0} pt=${5:-} n0=${6:-}
  echo "==== [cyc$cyc][$arm] 購入=${rate}周/秒 閲覧=${brw}周/秒${pt:+ 点=$pt 開始${n0}台} $(date -Is) ===="
  # sample_hpa.py / collect_events.py は TL_POINT があれば末尾に point,start_replicas を足す
  if [ -n "$pt" ]; then export TL_POINT="$pt" TL_N0="$n0"; else unset TL_POINT TL_N0; fi
  kubectl create configmap k6-script -n $NS --from-file=checkout.js=$K6DIR/checkout.js --dry-run=client -o yaml | kubectl apply -f - >/dev/null 2>&1
  kubectl delete job k6load -n $NS --ignore-not-found --wait=true >/dev/null 2>&1
  local ev_since=$(date -u +%Y-%m-%dT%H:%M:%SZ)   # k8sのイベント時刻(UTC)と直接比較できる形
  sed -e "s/__RATE__/$rate/" -e "s/__BROWSE__/$brw/" -e "s/__WARM__/$WARM/" -e "s/__MEAS__/$MEAS/" -e "s/__PRE__/$PRE_VUS/" -e "s/__MAX__/$MAX_VUS/" "$K6DIR/k6-job.yaml" | kubectl apply -f - -n $NS >/dev/null
  if [ "$RESET_EACH_POINT" = 1 ]; then
    # k6 を始めた直後に HPA を作る (無負荷の時間を挟まない)。k6 の Pod 起動を待つ前に作り、作成にかかった秒数をログに残す。
    local _h0; _h0=$(date +%s); make_hpa
    echo "  HPA作成: k6 Job の apply 直後から $(( $(date +%s) - _h0 )) 秒で完了"
  fi
  local pod=""
  for i in $(seq 1 40);do pod=$(kubectl get pods -n $NS -l app=k6load --sort-by=.metadata.creationTimestamp -o jsonpath='{.items[-1].metadata.name}' 2>/dev/null)
    [ -n "$pod" ]&&[ "$(kubectl get pod $pod -n $NS -o jsonpath='{.status.phase}' 2>/dev/null)" = Running ]&&break; sleep 3;done
  local t_run=$(date +%s)
  # --- 時系列採取をバックグラウンドで開始(k6起動直後から。スケールはウォームアップ中に起きるため) ---
  local FLAG=/tmp/tl-$$-$cyc-$arm-$rate-$brw.flag; touch "$FLAG"
  ( while [ -f "$FLAG" ]; do sample_once "$cyc" "$arm" "$rate" "$t_run" "$brw"; sleep $SAMPLE; done ) &
  local SPID=$!
  local win=$(( MEAS*5/6 )); [ $win -lt 60 ] && win=60
  # --- 計測窓に入る瞬間の台数を記録。窓の終わりの台数と比べれば「窓の中で増減したか」が分かる ---
  #     (Podが減るのを見たい場合、ウォームアップで行き過ぎた分が戻り切っているかの確認になる)
  sleep $WARM
  local REPL_START; REPL_START=$(kubectl get deploy -n $NS --no-headers 2>/dev/null | awk '{printf "%s:%s ",$1,$4}')
  sleep $MEAS
  # --- 資源側の採取(動いているPodと、Pending込みを分けて出す) ---
  local RUNC PENDC PODS PEND NODE SOFT REPL RES4
  # 枠は Pod の実体から直接数える(Prometheusのjoinで2度事故ったため。reserved.py 参照)
  # 時系列の採取はここで止める。以降(k6の終了待ち25秒)は負荷が止まった後の状態なので、
  # 採り続けると計測窓外のサンプルが時系列CSVに混ざり、集計時に絞り忘れる事故のもとになる。
  rm -f "$FLAG"; wait $SPID 2>/dev/null
  RES4=$(kubectl get pods -n $NS -o json 2>/dev/null | python3 "$DIR/reserved.py" 2>/dev/null)
  RUNC=$(echo "$RES4" | awk '{print $1}'); PENDC=$(echo "$RES4" | awk '{print $2}')
  PODS=$(echo "$RES4" | awk '{print $3}');  PEND=$(echo "$RES4" | awk '{print $4}')
  [ -z "$RUNC" ] && { RUNC=0; PENDC=0; PODS=0; PEND=0; }
  # 計測窓ぴったりのCPU秒。rate×窓長 だと平均区間(win)と窓長(MEAS)がずれ、最初の40秒を外挿することになる。
  # increase なら「この240秒で消費したCPU秒」そのものが出る(実機で rate[240s]*240 と完全一致を確認)。
  NODE=$(promq "sum(increase(node_cpu_seconds_total{mode!=\"idle\"}[${MEAS}s]))" | scalar)
  SOFT=$(promq "sum(increase(node_cpu_seconds_total{mode=\"softirq\"}[${MEAS}s]))" | scalar)
  # THROT(スロットリング率)と RETR(TCP再送)は削除。
  #   スロットリング原因説は実験B(2026-08-29, n=3)で否定され、TCP再送は全測定で0だった。
  #   どちらも kubectl exec + curl の往復が要るので、生きた仮説がない以上は取らない。
  K6CPU=$(promq "sum(increase(container_cpu_usage_seconds_total{namespace=\"$NS\",pod=~\"k6load.*\",container!=\"\"}[${MEAS}s]))" | scalar)
  REPL=$(kubectl get deploy -n $NS --no-headers 2>/dev/null | awk '{printf "%s:%s ",$1,$4}')
  local done_at=$(( t_run + WARM + MEAS + 25 ))
  while [ "$(date +%s)" -lt "$done_at" ]; do sleep 5; done
  rm -f "$FLAG"; wait $SPID 2>/dev/null
  # --- 計測窓のあいだに確保していたCPU量(時間積分)。瞬間値だと窓内の増減が落ちる ---
  local WRES RESSEC PENDSEC RESAVG NSAMP
  WRES=$(python3 "$DIR/window_reserved.py" "$TL" "$WARM" "$MEAS" "$cyc" "$arm" "$rate" "$LIMIT_X" "$brw" $pt $n0 2>/dev/null)
  RESSEC=$(echo "$WRES" | awk '{print $1}'); PENDSEC=$(echo "$WRES" | awk '{print $2}')
  RESAVG=$(echo "$WRES" | awk '{print $3}'); NSAMP=$(echo "$WRES" | awk '{print $4}')
  [ -z "$RESSEC" ] && { RESSEC=0; PENDSEC=0; RESAVG=0; NSAMP=0; }
  # RESET_EACH_POINT=1: 点と開始台数でも絞り直す。start_ok = 開始15秒以内の全 Deployment の台数が n0 と一致したか
  local SOK="" XCOLS=""
  if [ -n "$pt" ]; then
    SOK=$(python3 "$DIR/start_ok.py" "$TL" "$cyc" "$arm" "$rate" "$LIMIT_X" "$brw" "$pt" "$n0" 2>/dev/null); SOK=${SOK:-0}
    [ "$SOK" = 1 ] || echo "  !! start_ok=$SOK: 開始15秒以内に全 Deployment が ${n0}台ではなかった (または時系列が足りない)"
    XCOLS="$pt,$n0,$SOK,$FRAMES_OK"
  fi

  # --- 台数変更イベントの回収 ---
  kubectl get events -n $NS --field-selector reason=SuccessfulRescale -o json 2>/dev/null | \
    CYC="$cyc" ARM="$arm" RATE="$rate" LX="$LIMIT_X" BRW="$brw" SINCE="$ev_since" python3 "$DIR/collect_events.py" >> "$EV" 2>/dev/null
  # Pod名は「いま」取り直す。backoffLimit>0 だと最初のPodがマウント失敗で作り直されることがあり、
  # 起動待ちの時点で掴んだ名前が古くなる(2026-09-01 に欠測2件を出した)。
  local pod_now
  pod_now=$(kubectl get pods -n $NS -l app=k6load --sort-by=.metadata.creationTimestamp -o jsonpath='{.items[-1].metadata.name}' 2>/dev/null)
  [ -n "$pod_now" ] && pod="$pod_now"
  local logs summary; logs=$(kubectl logs "$pod" -n $NS 2>/dev/null)
  summary=$(printf '%s\n' "$logs" | sed -n '/@@@K6_BEGIN@@@/,/@@@K6_END@@@/p' | grep '{')
  echo "$summary" | grep -q '{' || { echo "  !! summary回収失敗(pod=$pod)"
       kubectl get events -n $NS --field-selector involvedObject.name=k6load -o jsonpath='{range .items[*]}     理由: {.reason} {.message}{"\n"}{end}' 2>/dev/null | tail -3
       kubectl delete job k6load -n $NS --ignore-not-found >/dev/null 2>&1; return; }
   EXTRA_COLS="$XCOLS" SUMMARY="$summary" LIMIT_X="$LIMIT_X" REPL0="$REPL_START" RSSCALE="$RS_SCALE" LIMSCALE="$LIMIT_SCALE" RESSEC="$RESSEC" PENDSEC="$PENDSEC" RESAVG="$RESAVG" NSAMP="$NSAMP" python3 - "$arm" "$CSV" "$cyc" "$RUNC" "$PENDC" "$PODS" "$PEND" "$NODE" "$SOFT" "$K6CPU" "$REPL" <<'PY'
import sys,json,csv,os
arm,out,cyc,runc,pendc,pods,pend,node,soft,k6cpu,repl=sys.argv[1:12]
repl0=os.environ.get('REPL0','').strip()
changed = 'yes' if repl0 and repl0 != repl.strip() else ('no' if repl0 else '')
d=json.loads(os.environ['SUMMARY'])
f=lambda x:(float(x) if x not in ('NA','') else 0.0)
it=d.get('iter_rate') or 0
eff=(it/f(runc)) if f(runc)>0 else 0
g=lambda k:round(d.get(k) or 0,1)
row=[cyc,arm,d.get('target_rate'),round(it,1),d.get('dropped'),round(d.get('failed_rate') or 0,4),
     round(d.get('p50') or 0,1),round(d.get('p99') or 0,1),round(f(runc),2),round(f(pendc),2),round(eff,1),
     int(f(pods)),int(f(pend)),round(f(node),1),round(f(soft),2),round(f(k6cpu),2),
     g('prod_p50'),g('cart_p50'),g('chk_p50'),g('prod_p99'),g('cart_p99'),g('chk_p99'),
     repl.strip(),os.environ.get('LIMIT_X','0'),
     d.get('dropped_win'),d.get('started'),repl0,changed,
     d.get('browse_rate_target'),round(d.get('browse_rate') or 0,1),
     d.get('browse_dropped_win'),
     round(d.get('browse_p50') or 0,1),round(d.get('browse_p99') or 0,1),
     os.environ.get('RSSCALE','1'),os.environ.get('LIMSCALE','0'),
     os.environ.get('RESSEC','0'),os.environ.get('PENDSEC','0'),
     os.environ.get('RESAVG','0'),os.environ.get('NSAMP','0')]
# RESET_EACH_POINT=1 のときだけ末尾に point,start_replicas,start_ok,frames_ok を足す (既定では列は従来どおり)
if os.environ.get('EXTRA_COLS'): row += os.environ['EXTRA_COLS'].split(',')
with open(out,'a',newline='') as fh: csv.writer(fh).writerow(row)
print("  -> 捌けた=%.1f/%s 取りこぼし(窓)=%s (全体%s) p50=%.0f p99=%.0f | 動作中の枠=%.2fコア(Pending分 %.2f) Pod=%d(Pending %d) | CPU時間=%.0f秒(うちsoftirq %.0f秒 / k6 %.0f秒)"
      %(it,d.get('target_rate'),d.get('dropped_win'),d.get('dropped'),d.get('p50') or 0,d.get('p99') or 0,f(runc),f(pendc),f(pods),f(pend),f(node),f(soft),f(k6cpu)))
print("     種類別p50: 商品%.0f / カート%.0f / 購入%.0f ms"
      %(d.get('prod_p50') or 0,d.get('cart_p50') or 0,d.get('chk_p50') or 0))
print("     確保したCPU: %s コア秒(窓平均 %s コア, %s サンプル) / 使ったCPU: %.0f コア秒"
      %(os.environ.get('RESSEC','0'),os.environ.get('RESAVG','0'),os.environ.get('NSAMP','0'),f(node)))
print("     台数: %s"%repl.strip())
if changed=='yes':
    print("     !! 計測窓の中で台数が変わった(窓の始め: %s)"%repl0)
if (d.get('browse_rate_target') or 0)>0:
    print("     閲覧型: 捌けた=%.1f/%s 取りこぼし(窓)=%s p50=%.0f p99=%.0f ms"
          %(d.get('browse_rate') or 0,d.get('browse_rate_target'),d.get('browse_dropped_win'),
            d.get('browse_p50') or 0,d.get('browse_p99') or 0))
PY
  kubectl delete job k6load -n $NS --ignore-not-found >/dev/null 2>&1
}

ensure_promq
for c in $(seq $CYC_START $(( CYC_START + CYCLES - 1 ))); do
  echo "################ CYCLE $c / $CYCLES $(date -Is) ################"
  ARMS_C=$ARMS
  [ "$ROTATE_ARMS" = 1 ] && { ARMS_C=$(rotate_arms $(( c - CYC_START ))); echo "  このサイクルのアーム順 (回転): $ARMS_C"; }
  for arm in $ARMS_C; do
    deploy "$arm" || { echo "!! アーム中止 [cyc$c][$arm]: デプロイ失敗 (上の「!!」行を見ること)。次のアームへ"; continue; }
    sleep 10
    if [ "$RESET_EACH_POINT" = 1 ]; then
      combos=$(order_points "$c"); echo "  [cyc$c][$arm] 点×開始台数の順番: $combos"
      for combo in $combos; do
        pt=${combo%%:*}; n0=${combo##*:}; bv=$(parse_point "$pt")
        cool_down
        reset_point "$arm" "$n0" "$pt" || { echo "  (この点は記録なし: cyc=$c arm=$arm point=$pt start=$n0)"; continue; }
        run_rate "$arm" "${bv% *}" "$c" "${bv#* }" "$pt" "$n0"
      done
    else
      for r in $RATES; do for b in $BROWSE_RATE; do run_rate "$arm" "$r" "$c" "$b"; done; done
    fi
    if [ "$REST_ARM" != 0 ]; then echo "---- 休憩 ${REST_ARM}s (アーム間) $(date -Is) ----"; sleep $REST_ARM; fi
  done
  if [ "$REST_CYCLE" != 0 ]; then echo "######## 休憩 ${REST_CYCLE}s (サイクル間) $(date -Is) ########"; sleep $REST_CYCLE; fi
done
kubectl delete job k6load -n $NS --ignore-not-found >/dev/null 2>&1
echo "================ BUNDLE-VS-LOSS2 DONE $(date -Is) ================"
