#!/usr/bin/env python3
"""Sock Shop の同居マニフェストを sockshop/normal/ から生成する (2026-11-10)。

1 つの Deployment (名前 = GROUP) に、指定したサービスのコンテナを並べる。中身 (イメージ・環境変数・枠・プローブ) は normal のまま。
SS のアプリは全部ポート 80 で待ち受けるので、同じ Pod (= 同じネットワーク) に入れるとぶつかる。そこで:
  * 各コンテナの待ち受けポートを起動引数で変える (Java = java.sh -jar ./app.jar --port=N、Go = /app -port=N / /user -port=N。
    元の起動行は稼働中の Pod の /proc/1/cmdline で確認: "--port=80" / "-port=80")。プローブのポートも合わせる
  * 各 Service は名前・ポート 80 のまま、selector を GROUP の Pod に、targetPort を新しいポートに向ける
    → 呼ぶ側は今までどおり Service 名で呼ぶ (localhost にはしない = 通信の近さの得は入らない。2026-11-10 スモークの方式 B)
  * /tmp の emptyDir はコンテナごとに名前を分ける
使い方: python3 make_group.py <GROUP> <出力 yaml> <svc>=<port> ...
  例: python3 make_group.py buygroup arm1/buygroup.yaml carts=8081 orders=8082 payment=8083 shipping=8084 user=8085 queue-master=8086
"""
import sys, yaml, copy, os

group, out = sys.argv[1:3]
ports = dict(a.split('=') for a in sys.argv[3:])
NORMAL = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'normal')
CMD = {'payment': ['/app'], 'user': ['/user']}           # Go。それ以外 (Java) は java.sh
containers, volumes, services = [], [], []
tmpl = None
for svc, port in ports.items():
    port = int(port)
    docs = [d for d in yaml.safe_load_all(open(os.path.join(NORMAL, svc + '.yaml'))) if d]
    dep = next(d for d in docs if d['kind'] == 'Deployment'); sv = next(d for d in docs if d['kind'] == 'Service')
    spec = dep['spec']['template']['spec']
    tmpl = tmpl or dep
    c = copy.deepcopy(spec['containers'][0])
    c['command'] = (CMD[svc] + ['-port=%d' % port]) if svc in CMD else ['/usr/local/bin/java.sh', '-jar', './app.jar', '--port=%d' % port]
    c['ports'] = [{'containerPort': port}]
    for pr in ('readinessProbe', 'livenessProbe'):
        if pr in c and 'httpGet' in c[pr]:
            c[pr]['httpGet']['port'] = port
    for vm in c.get('volumeMounts', []):
        vm['name'] = '%s-%s' % (vm['name'], svc)
    for v in spec.get('volumes', []):
        v = copy.deepcopy(v); v['name'] = '%s-%s' % (v['name'], svc); volumes.append(v)
    containers.append(c)
    sv = copy.deepcopy(sv); sv['spec']['selector'] = {'name': group}
    for p in sv['spec']['ports']:
        p['targetPort'] = port
    services.append(sv)
dep = copy.deepcopy(tmpl)
dep['metadata'] = {'name': group, 'labels': {'name': group}}
dep['spec']['selector'] = {'matchLabels': {'name': group}}
dep['spec']['template']['metadata']['labels'] = {'name': group}
dep['spec']['template']['spec']['containers'] = containers
dep['spec']['template']['spec']['volumes'] = volumes
if not volumes:
    dep['spec']['template']['spec'].pop('volumes', None)
with open(out, 'w') as f:
    f.write('# make_group.py で生成 (%s)。手で直さない。元 = sockshop/normal/ の %s\n' % (group, ' '.join(ports)))
    f.write('# 呼び出しは Service 名のまま (localhost にしない)。各 Service の targetPort を新しいポートに向けてある\n')
    yaml.safe_dump_all([dep] + services, f, sort_keys=False, allow_unicode=True)
print('書いた: %s (%d コンテナ、Service %d)' % (out, len(containers), len(services)))
