#!/usr/bin/env python3
"""GRPC_LB=1 のとき bundle-vs-loss2.sh の deploy() から呼ばれ、gRPC のクライアント側負荷分散を入れる
kubectl コマンド列 (シェルスクリプト) を標準出力に書く。apply_rightsize.py と同じ流儀。

なぜ要るか (2026-10-06 実測, summer2026/smoke/lbcheck.log):
  既定の gRPC (pick_first) は宛先ごとに接続を1本だけ張る。ClusterIP の Service は「接続」単位でしか
  振り分けないので、呼ばれる側を4台にしても4台中1台がほぼ 0m、最も忙しい Pod が平均の約2倍になった。

やること (どのアームでも同じ規則で当てる):
  1. 別 Pod 宛ての *_SERVICE_ADDR (= "Service名:ポート") が指す Service ごとに、
     headless の双子 "<Service名>-hl" (clusterIP: None) を作る。DNS が Pod の IP を全部返す形。
     headless は宛先ポートの付け替えをしないので、ポートは targetPort (コンテナ側の番号) にする
     (emailservice は Service 5000 → コンテナ 8080)。元の Service は消さない (k6 → frontend もそのまま)。
  2. 呼び出し側コンテナの *_SERVICE_ADDR を "<Service名>-hl:<targetPort>" に書き換え、
     GRPC_LB_POLICY=round_robin と GRPC_RESOLVE_EVERY を足す。localhost 宛て (同居) は触らない。
  3. 呼び出し側 (frontend / checkout / recommendation) のイメージを、負荷分散対応版に差し替える
     (src/frontend/grpclb.go, src/checkoutservice/grpclb.go, src/recommendationservice/recommendation_server.py)。
     差し替え先は環境変数 LB_IMG_FRONTEND / LB_IMG_CHECKOUT / LB_IMG_RECO。

入力: 標準入力に {"deploy": kubectl get deploy -o json, "svc": kubectl get svc -o json} を1つの JSON で。
"""
import json, os, sys

NS = os.environ.get('NS', 'exp')
EVERY = os.environ.get('GRPC_RESOLVE_EVERY', '30')
POLICY = os.environ.get('GRPC_LB_POLICY', 'round_robin')
# 1 = 対照用。負荷分散対応イメージに差し替えるだけで、振り分けは有効にしない (GRPC_LB=2 のとき)
IMAGES_ONLY = os.environ.get('LB_IMAGES_ONLY', '0') == '1'
# 呼び出し側のイメージの見分け方 (イメージ名の一部) → 差し替え先
IMG_MAP = [   # 上から順に照合 (frontend-lb / reco-lb も mygo: を含むので checkout より先に見る)
    ('frontend', os.environ.get('LB_IMG_FRONTEND', '')),
    ('reco', os.environ.get('LB_IMG_RECO', '')),
    ('checkout', os.environ.get('LB_IMG_CHECKOUT', '')),
    ('mygo:', os.environ.get('LB_IMG_CHECKOUT', '')),   # checkout の独自イメージ mygo:bunpupaymail
]

data = json.load(sys.stdin)
svcs = {s['metadata']['name']: s for s in data['svc']['items']}


def target_port(svc, port):
    for p in svc['spec'].get('ports', []):
        if str(p.get('port')) == str(port):
            tp = p.get('targetPort', port)
            if isinstance(tp, int) or str(tp).isdigit():
                return int(tp)
            print('echo "  !! %s: targetPort が名前 (%s) なので headless 化できない"' % (svc['metadata']['name'], tp))
            return None
    return None


need_hl = {}   # 双子 Service 名 → (元 Service, targetPort)
out = []
for d in data['deploy']['items']:
    dname = d['metadata']['name']
    patches = []
    for c in d['spec']['template']['spec'].get('containers', []):
        env_new = []
        for e in c.get('env', []) or []:
            n, v = e.get('name', ''), e.get('value', '')
            if not n.endswith('_SERVICE_ADDR') or not v or ':' not in v:
                continue
            host, port = v.rsplit(':', 1)
            host = host.split(':///')[-1]
            if host in ('localhost', '127.0.0.1') or host.endswith('-hl'):
                continue
            base = host.split('.')[0]
            if base not in svcs:
                continue   # 使っていない宛先 (shopping assistant 等)
            tp = target_port(svcs[base], port)
            if tp is None:
                continue
            need_hl[base + '-hl'] = (base, tp)
            env_new.append({'name': n, 'value': '%s-hl:%d' % (base, tp)})
        img = c.get('image', '')
        new_img = next((m for k, m in IMG_MAP if k in img and m), None)
        if not env_new and not new_img:
            continue
        if IMAGES_ONLY:
            env_new = []   # 対照: イメージだけ差し替え、宛先と振り分けは従来どおり (GRPC_LB_POLICY 未設定)
        elif env_new:
            env_new += [{'name': 'GRPC_LB_POLICY', 'value': POLICY},
                        {'name': 'GRPC_RESOLVE_EVERY', 'value': str(EVERY)}]
        p = {'name': c['name']}
        if env_new:
            p['env'] = env_new
        # 呼び出し側のイメージは、宛先が全部 localhost (同居) のコンテナも含めて全アームで同じ版に揃える
        if new_img:
            p['image'] = new_img
            # タグを上書きで作り直すことがあるので、ノードに残った古いイメージを使わせない
            p['imagePullPolicy'] = 'Always'
        elif env_new:
            print('echo "  !! %s/%s: 負荷分散対応イメージが未指定 (%s)。宛先だけ headless にするので、'
                  'このコンテナからの呼び出しは偏ったまま"' % (dname, c['name'], img))
        patches.append(p)
    if patches:
        body = json.dumps({'spec': {'template': {'spec': {'containers': patches}}}})
        out.append("kubectl patch deploy/%s -n %s -p '%s' >/dev/null && echo '  gRPC負荷分散: %s (%s)'" % (
            dname, NS, body, dname, ', '.join('%s%s' % (p['name'], '+img' if 'image' in p else '') for p in patches)))

for hl, (base, tp) in ([] if IMAGES_ONLY else sorted(need_hl.items())):
    s = {'apiVersion': 'v1', 'kind': 'Service',
         'metadata': {'name': hl, 'labels': {'grpc-lb': 'headless'}},
         'spec': {'clusterIP': 'None', 'selector': svcs[base]['spec']['selector'],
                  'ports': [{'name': 'grpc', 'port': tp, 'targetPort': tp}]}}
    print("echo '%s' | kubectl apply -n %s -f - >/dev/null" % (json.dumps(s), NS))
print('\n'.join(out))
