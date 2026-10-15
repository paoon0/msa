#!/usr/bin/env python3
"""適正化した枠(requests)を、いま動いている Deployment に当てるためのコマンドを出力する。

標準入力: kubectl get deploy -n <ns> -o json
標準出力: `kubectl set resources ...` のコマンド行(呼び出し側の bash が実行する)

考え方: 枠は「サービスごと」に決まる。束ねたPodでは同じPodの中に複数サービスのコンテナが入るので、
  コンテナ名からどのサービスかを引いて、それぞれに対応する値を当てる。
  (同居してもアプリのCPU消費は変わらないことは実測済みなので、分離時に測った値をそのまま使える)

環境変数:
  TABLE   = 適正化テーブルCSV
  NS      = namespace
  LIMIT_X = CPU上限(limits)を requests の何倍にするか。0 または未設定ならマニフェストのまま触らない。
            (2026-08-20 の発見: limits はカーネルの「100msごとに quota だけ」という配給制なので、
             バーストで来る仕事は上限に叩かれて強制停止される。email が48%停止させられていた。
             LIMIT_X を大きく取ると実質「絞りなし」になり、崩壊の原因が絞りかどうかを切り分けられる)
  LIMIT_MIN_M = 上限の下限値[m]。小さすぎる上限を作らないための保険(既定 200m)。
  RS_SCALE  = 枠(requests)を何倍にするか。既定1.0。
            1/3 にすると利用率が3倍になり、必要台数も約3倍になる。
            狙い: 粒度損は「余分な1台の枠」なので、台数の刻みを細かくすると損の分解能が上がる
            (これまでは台数が1〜3台しかなく、損が0か1台分かの二択で中間が測れなかった)。
  LIMIT_SCALE = 上限(limits)を何倍にするか。既定0=触らない。
            requests と同じ倍率にしないと、絞りの当たり方が変わって条件が揃わない。
  RS_SERVICES = 適正化枠を当てる deploy 名を空白区切りで列挙。未設定なら全サービスに当てる。
            ここに無いサービスはマニフェストの枠のまま(=「まとめている部分以外は通常の枠に戻す」)。
            狙い: 束ねの候補(frontend/productcatalog/recommendation/cart)だけ枠を揃え、
            それ以外は既定値に戻して、絞りすぎによる過剰スケール(ad 69m など)の人工物を持ち込まない。
            ※ 全アームで同じ集合を指定すること。アームごとに変えると粒度損の基準が変わって比較が壊れる。
  RS_STRICT = 1 なら、適正化の対象 (RS_SERVICES、空なら全サービス) のコンテナが表に無いとき、
            警告だけで続けず、何も出力せず非 0 で終了する (2026-10-08 追加。取り違え防止。既定0=従来どおり警告のみ)。
  LIMIT_OVERRIDE = "サービス名=値 ..." (例 "frontend=3000m productcatalogservice=3000m adservice=1000m")。
            そのサービスの**コンテナ単位**で limits.cpu を上書きするコマンドを、requests の置換のあとに出す
            (`kubectl set resources deploy/<d> -c <container> --limits=cpu=...`。requests は触らない)。
            同居 Pod の中のそのコンテナにも効く (CONTAINER_TO_SERVICE で サービスを引く)。RS_SERVICES の対象外でも効く。
            測定時 (rightsizing/measure-mix-cpu.sh の LIMIT_OVERRIDE) と条件を揃えるためのもの。既定は空 = 何もしない。
  CHECK = 1 なら検査モード。コマンドは出さず、標準入力の Deployment の**いまの値**が表どおりかを調べる。
            (a) 対象サービスの requests.cpu == 表の値 × RS_SCALE、(b) LIMIT_OVERRIDE のサービスの limits.cpu が指定どおり、
            (c) 全コンテナで requests ≤ limits、(d) redis-cart 以外のコンテナが RS_SERVICES の対象内であること
            (対象外 = RS_SERVICES の渡し忘れの疑いなので不一致扱い)。
            1つでも違えば不一致を標準出力に列挙し、終了コード 1 (全部一致なら 0)。
"""
import sys, json, csv, os

ns = os.environ.get('NS', 'exp')
table = os.environ.get('TABLE', 'km2/experiments/summer2026/rightsize-requests.csv')
limit_x = float(os.environ.get('LIMIT_X', '0') or 0)
limit_min = int(float(os.environ.get('LIMIT_MIN_M', '200') or 200))
rs_services = set((os.environ.get('RS_SERVICES') or '').replace(',', ' ').split())
rs_scale = float(os.environ.get('RS_SCALE', '1') or 1)
limit_scale = float(os.environ.get('LIMIT_SCALE', '0') or 0)
strict = os.environ.get('RS_STRICT', '0') == '1'
check = os.environ.get('CHECK', '0') == '1'


def _cpu_m(v):
    if not v: return 0.0
    v = str(v)
    return float(v[:-1]) if v.endswith('m') else float(v) * 1000.0

# LIMIT_OVERRIDE: "サービス名=値" の空白区切り → {サービス名: ミリコア}
limit_override = {}
for kv in (os.environ.get('LIMIT_OVERRIDE') or '').replace(',', ' ').split():
    k, _, v = kv.partition('=')
    if not k or not v or _cpu_m(v) <= 0:
        print("# apply_rightsize: LIMIT_OVERRIDE の書式が不正: %r" % kv, file=sys.stderr)
        sys.exit(2)
    limit_override[k] = _cpu_m(v)

# サービス識別: (deploy名, コンテナ名) → テーブルの行キー
# 束ねたPodでは deploy名が frontend でも、コンテナ名が相方サービスを表す。
CONTAINER_TO_SERVICE = {
    'productcatalog': ('productcatalogservice', 'server'),
    'recommendation': ('recommendationservice', 'server'),
    'cartservice':    ('cartservice', 'server'),
    'checkout':       ('checkoutservice', 'checkout'),
    'email':          ('emailservice', 'email'),
    'payment':        ('paymentservice', 'payment'),
    'redis':          ('redis-cart', 'redis'),
    'shipping':       ('shippingservice', 'server'),   # 2026-10-08: frontend+shipping 同居 (pairsY2) の相乗り側
    # 2026-10-13 (pdist, pairsP1/P3): frontend+ad / checkout+currency の相乗り側
    'ad':             ('adservice', 'server'),
    'currency':       ('currencyservice', 'server'),
}

req = {}
for r in csv.DictReader(open(table)):
    req[(r['deploy'], r['container'])] = int(float(r['request_m']))

try:
    d = json.load(sys.stdin)
except Exception as e:
    print("# apply_rightsize: JSON読み取り失敗 %s" % e, file=sys.stderr)
    sys.exit(1)

missing = []      # 表に無いコンテナ (従来どおり stderr に警告)
fatal = []        # 対象サービスなのに表に無いコンテナ (RS_STRICT / CHECK のとき致命)
mismatch = []     # CHECK モード: 期待値と実際の値が違うコンテナ
cmds = []         # set resources のコマンド行 (requests の置換)
lim_cmds = []     # LIMIT_OVERRIDE のコマンド行 (requests の置換のあとに出す)


def _fmt(m):
    return ('%dm' % round(m)) if m else '(なし)'


for it in d.get('items', []):
    dep = it['metadata']['name']
    for c in it['spec']['template']['spec']['containers']:
        cn = c['name']
        if cn == 'istio-proxy':
            continue
        key = CONTAINER_TO_SERVICE.get(cn, (dep, cn))
        in_scope = (not rs_services) or key[0] in rs_services
        res = c.get('resources') or {}
        live_req = _cpu_m((res.get('requests') or {}).get('cpu'))
        live_lim = _cpu_m((res.get('limits') or {}).get('cpu'))
        # limits の上書き (コンテナ単位。対象サービスかどうかは RS_SERVICES と無関係)
        if key[0] in limit_override:
            lim_cmds.append("kubectl set resources deploy/%s -n %s -c %s --limits=cpu=%dm >/dev/null"
                            % (dep, ns, cn, round(limit_override[key[0]])))
            if check and round(live_lim) != round(limit_override[key[0]]):
                mismatch.append("deploy=%s container=%s limits 期待 %s 実際 %s"
                                % (dep, cn, _fmt(limit_override[key[0]]), _fmt(live_lim)))
        if check and live_lim and live_req > live_lim:
            mismatch.append("deploy=%s container=%s requests %s > limits %s"
                            % (dep, cn, _fmt(live_req), _fmt(live_lim)))
        if key not in req:
            missing.append((dep, cn))
            if in_scope:
                fatal.append((dep, cn))
            continue
        if not in_scope:
            if check and key[0] != 'redis-cart':
                # 検査モードでは、対象外 = RS_SERVICES の渡し忘れの疑い。redis-cart だけは枠を触らない運用なので除く
                mismatch.append("deploy=%s container=%s は RS_SERVICES の対象外 (枠が表どおりか検査できない)" % (dep, cn))
            continue                      # 適正化の対象外 = マニフェストの枠のまま
        r_m = req[key] * rs_scale
        if check:
            if round(live_req) != round(r_m):
                mismatch.append("deploy=%s container=%s requests 期待 %s 実際 %s"
                                % (dep, cn, _fmt(r_m), _fmt(live_req)))
            continue
        flags = "--requests=cpu=%dm" % round(r_m)
        if limit_x > 0:
            l_m = max(int(round(r_m * limit_x)), limit_min)
            flags += " --limits=cpu=%dm" % l_m
        elif limit_scale > 0:
            # マニフェストの上限を同じ倍率で縮める(requests だけ縮めると絞りの条件が変わる)
            cur_lim = _cpu_m(((c.get('resources') or {}).get('limits') or {}).get('cpu'))
            if cur_lim > 0:
                flags += " --limits=cpu=%dm" % round(cur_lim * limit_scale)
        elif key[0] in limit_override:
            # 2026-10-15: requests と limits の上書きを同じコマンドで出す。別々だと、新しい requests がマニフェストの
            # limits を超えるとき (ad 600m > 500m) に requests の置換が API に拒否される。後段の lim_cmds は同じ値なので無害。
            flags += " --limits=cpu=%dm" % round(limit_override[key[0]])
        cmds.append("kubectl set resources deploy/%s -n %s --containers=%s %s >/dev/null"
                    % (dep, ns, cn, flags))
for m in missing:
    print("# !! 適正化テーブルに無い: deploy=%s container=%s (枠はマニフェストのまま)" % m, file=sys.stderr)

if check:
    # 検査モード: 表に無い対象コンテナも不一致として数える
    for m in fatal:
        mismatch.append("deploy=%s container=%s 表に行が無い" % m)
    for line in mismatch:
        print(line)
    sys.exit(1 if mismatch else 0)
if strict and fatal:
    print("# !! RS_STRICT=1: 対象サービスが表に無いので中止 (コマンドは出さない): %s"
          % ", ".join("%s/%s" % m for m in fatal), file=sys.stderr)
    sys.exit(3)
if cmds or lim_cmds:
    print("\n".join(cmds + lim_cmds))
