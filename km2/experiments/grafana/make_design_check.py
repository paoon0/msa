#!/usr/bin/env python3
"""設計の確認用 Grafana ダッシュボード (design-check.json) を作る (2026-11-02)。

目的: AI が書いた測定スクリプトとは別の経路 (Prometheus がスクリプトと無関係に記録しているもの) で、
実験が設計どおりだったかを人が後から確かめる。スクリプトの CSV と比べるための表も置く。

使い方:
  python3 make_design_check.py            # design-check.json を書き出す
  Grafana への登録は README.md の手順で (Grafana の保存先が emptyDir なので、Pod が作り直されたら登録し直す)
"""
import json, os

DS = {"type": "prometheus", "uid": "${ds}"}
NS = 'namespace="$ns"'
SEL = NS + ',container!="",container!="POD",pod!~"promq.*"'
# Pod 名 → Deployment 名 (measure-mix-cpu の _write_mixpoint.py の dep_of と同じ規則: 末尾の "-<ReplicaSet の英数字>-<5文字>" を落とす)
def dep(expr):
    return 'label_replace(%s, "deploy", "$1", "pod", "(.+)-[a-f0-9]{6,}-[a-z0-9]+")' % expr

panels = []
y = 0


def add(p, h, w=24, x=0):
    global y
    p["gridPos"] = {"h": h, "w": w, "x": x, "y": y}
    p["id"] = len(panels) + 1
    p.setdefault("datasource", DS)
    panels.append(p)


def row(title):
    global y
    add({"type": "row", "title": title, "collapsed": False, "panels": []}, 1)
    y += 1


def text(md, h):
    global y
    add({"type": "text", "title": "", "options": {"mode": "markdown", "content": md}}, h)
    y += h


def ts(title, exprs, unit="short", w=12, x=0, h=8, desc="", stack=False):
    add({"type": "timeseries", "title": title, "description": desc,
         "targets": [{"refId": chr(65 + i), "expr": e, "legendFormat": lf, "range": True}
                     for i, (e, lf) in enumerate(exprs)],
         "fieldConfig": {"defaults": {"unit": unit, "custom": {"lineInterpolation": "stepAfter", "showPoints": "never",
                                                               "stacking": {"mode": "normal" if stack else "none"}}},
                         "overrides": []},
         "options": {"legend": {"displayMode": "table", "placement": "right", "calcs": ["lastNotNull", "max"]},
                     "tooltip": {"mode": "multi", "sort": "desc"}}}, h, w, x)


def table(title, exprs, w=12, x=0, h=10, desc="", unit="short", decimals=1):
    """区間の終わりの時刻で instant query した結果を横棒グラフで出す (棒の横に値)。exprs = [(式, 名前)]
    折れ線にしないのは、折れ線の最後の点は区間の終わりと一致しないため (CSV と同じ計算にならない)"""
    def legend(e, name):
        if 'by(deploy, container)' in e:
            return '{{deploy}} / {{container}}  ' + name
        if 'by(pod)' in e:
            return '{{pod}}  ' + name
        return name
    add({"type": "bargauge", "title": title, "description": desc,
         "targets": [{"refId": chr(65 + i), "expr": e, "instant": True, "range": False, "legendFormat": legend(e, n)}
                     for i, (e, n) in enumerate(exprs)],
         "fieldConfig": {"defaults": {"unit": unit, "decimals": decimals, "min": 0,
                                      "color": {"mode": "fixed", "fixedColor": "blue"}}, "overrides": []},
         "options": {"orientation": "horizontal", "displayMode": "basic", "showUnfilled": True,
                     "valueMode": "text", "namePlacement": "left", "sizing": "auto",
                     "reduceOptions": {"calcs": ["lastNotNull"], "values": False, "fields": ""}}}, h, w, x)


# ---------------------------------------------------------------- 説明
text("""### 設計の確認 (exp namespace)
**使い方**: 右上の時間範囲を、確かめたい 1 点の区間に合わせる。`-times.csv` の `prom_from` と `prom_to` (unix 秒) を
1000 倍して URL に入れると正確に合う: `.../d/design-check?from=<prom_from>000&to=<prom_to>000`

- **① の棒グラフ**は、その区間全体の平均 (区間の終わりの時刻で `rate(...[区間の長さ])`)。区間を `prom_from`〜`prom_to` にすれば、
  スクリプトが CSV に書いた値 (`usage_mc` など) と同じ計算になる。**ここの問い合わせ文はスクリプトとは別に、人が読める形で書いてある**。
- **② の台数・HPA、③〜⑤ の折れ線**は、区間の前後を広めに表示して「設計どおりの状態だったか」を目で確かめる用。
- 記録の細かさ: CPU (cAdvisor) は収集設定 10 秒・実際の間隔は約 15 秒、台数・設定値・Pod の状態 (kube-state-metrics) とノードは 30 秒ごと。
""", 6)

# ---------------------------------------------------------------- ① CSV と比べる
row("① 区間の平均 — CSV と比べる (時間範囲 = prom_from〜prom_to にする)")
table("CPU 使用量 [ミリコア] (Deployment ごとに Pod を合計) ↔ CSV の usage_mc",
      [("sum by(deploy, container)(%s) * 1000" % dep('rate(container_cpu_usage_seconds_total{%s}[$__range])' % SEL), "使用量 m"),
       ("count by(deploy, container)(%s)" % dep('rate(container_cpu_usage_seconds_total{%s}[$__range])' % SEL), "Pod 数")],
      w=12, x=0, h=11,
      desc="式: sum by(deploy, container)( rate(container_cpu_usage_seconds_total[区間の長さ]) ) × 1000。区間の終わりの時刻で評価。"
           "k6load (負荷をかける側) の行も出る。CSV の pods 列とも比べられる。")
table("絞られた割合 [%] ↔ CSV の throttle_pct (Pod のうち最大)",
      [("max by(deploy, container)(%s) * 100" % dep(
          'rate(container_cpu_cfs_throttled_periods_total{%s}[$__range]) / rate(container_cpu_cfs_periods_total{%s}[$__range])' % (SEL, SEL)),
        "絞り %")],
      w=6, x=12, h=11, desc="limits に当たって CPU を止められた周期の割合。5% を超えた行は解析で捨てる設計。")
table("ノード ↔ CSV の node_cores / freq_ghz / temp_max_c",
      [('sum(rate(node_cpu_seconds_total{mode!="idle"}[$__range]))', "ノード CPU [コア]"),
       ('avg(avg_over_time(node_cpu_scaling_frequency_hertz[$__range])) / 1e9', "周波数 [GHz]"),
       ('max(max_over_time(node_hwmon_temp_celsius[$__range]))', "最高温度 [℃]")],
      w=6, x=18, h=11, decimals=2)
y += 11

# ---------------------------------------------------------------- ② 構成
row("② 構成 — 台数・HPA・枠 (設計: 全サービス N 台固定、redis-cart 1 台、HPA 無し)")
ts("Deployment の台数 (設定値 spec)", [('kube_deployment_spec_replicas{%s}' % NS, "{{deployment}}")], w=8, x=0,
   desc="設計どおりなら区間の間ずっと全サービスが同じ台数 (redis-cart だけ 1)。")
ts("動いている Pod 数 (available)", [('kube_deployment_status_replicas_available{%s}' % NS, "{{deployment}}")], w=8, x=8,
   desc="設定の台数と一致していなければ、Pod が立ち上がっていない・落ちている。")
ts("HPA の数 (設計: 0)", [('count(kube_horizontalpodautoscaler_info{%s}) or vector(0)' % NS, "HPA の数")], w=8, x=16,
   desc="HPA があると台数が勝手に変わる。0 のままなら HPA 無し。")
y += 8
table("requests (予約枠) [ミリコア] ↔ CSV の req_mc", [
    ("sum by(deploy, container)(%s) * 1000" % dep('kube_pod_container_resource_requests{%s,resource="cpu"}' % NS), "requests 合計 m"),
    ("max by(deploy, container)(%s) * 1000" % dep('kube_pod_container_resource_requests{%s,resource="cpu"}' % NS), "1 Pod あたり m")],
    w=12, x=0, h=10, decimals=0, desc="区間の終わりの時刻での設定値。")
table("limits (上限) [ミリコア] ↔ CSV の lim_mc", [
    ("sum by(deploy, container)(%s) * 1000" % dep('kube_pod_container_resource_limits{%s,resource="cpu"}' % NS), "limits 合計 m"),
    ("max by(deploy, container)(%s) * 1000" % dep('kube_pod_container_resource_limits{%s,resource="cpu"}' % NS), "1 Pod あたり m")],
    w=12, x=12, h=10, decimals=0, desc="mix-cpu2 の設計: frontend と productcatalogservice は 3000m、adservice は 1000m に上書き。")
y += 10

# ---------------------------------------------------------------- ③ 負荷の時刻
row("③ 負荷をかけた時間 — k6 の Pod (スクリプトとは別の記録)")
ts("k6 の Pod が動いていたか (1 = Running)",
   [('max by(pod)(kube_pod_status_phase{%s,pod=~"k6load.*",phase="Running"})' % NS, "{{pod}}")],
   w=8, x=0, h=8,
   desc="kube-state-metrics の記録 (30 秒ごと) なので、始まりと終わりは最大 30 秒ずれて見える。"
        "正確な開始時刻は Explore で kube_pod_container_state_started{pod=~\"k6load.*\"} を見る (値が unix 秒)。")
ts("k6 の CPU [ミリコア] (負荷をかけている間だけ上がる)",
   [('sum by(pod)(rate(container_cpu_usage_seconds_total{%s,pod=~"k6load.*",container!="",container!="POD"}[1m])) * 1000' % NS, "{{pod}}")],
   w=16, x=8, h=8, desc="約 15 秒ごとの記録から 1 分の移動平均。立ち上がりと落ち込みの時刻が、負荷をかけていた時間の目安になる。")
y += 8

# ---------------------------------------------------------------- ④ CPU の時系列
row("④ CPU の時系列 — 区間の中で安定していたか")
ts("サービスごとの CPU 使用量 [ミリコア] (1 分の移動平均)",
   [("sum by(deploy)(%s) * 1000" % dep('rate(container_cpu_usage_seconds_total{%s,pod!~"k6load.*"}[1m])' % SEL), "{{deploy}}")],
   w=16, x=0, h=10, desc="負荷をかけている間は平らになるはず。区間の中で大きく揺れていたら、その点の平均は信用しにくい。")
ts("ノード", [('sum(rate(node_cpu_seconds_total{mode!="idle"}[1m]))', "CPU [コア]"),
             ('avg(node_cpu_scaling_frequency_hertz) / 1e9', "周波数 [GHz]")], w=8, x=16, h=10)
y += 10

# ---------------------------------------------------------------- ⑤ 異常
row("⑤ 異常がなかったか — 再起動・Ready 落ち・絞り")
ts("コンテナの再起動 (1 分あたりの増え方)",
   [('sum by(pod)(increase(kube_pod_container_status_restarts_total{%s}[1m])) > 0' % NS, "{{pod}}")], w=8, x=0,
   desc="何も出なければ再起動なし。")
ts("Ready でない Pod", [('sum by(pod)(kube_pod_status_ready{%s,condition!="true"}) > 0' % NS, "{{pod}}")], w=8, x=8,
   desc="何も出なければ全 Pod が Ready (リクエストを受け付けられる状態) だった。")
ts("絞られた割合 [%] (1 分)",
   [("max by(deploy)(%s) * 100" % dep('rate(container_cpu_cfs_throttled_periods_total{%s}[1m]) / rate(container_cpu_cfs_periods_total{%s}[1m])' % (SEL, SEL)),
     "{{deploy}}")], w=8, x=16)
y += 8

dash = {
    "uid": "design-check", "title": "設計の確認 (exp)", "tags": ["msa", "design-check"],
    "timezone": "browser", "schemaVersion": 39, "editable": True, "refresh": "",
    "time": {"from": "now-30m", "to": "now"},
    "templating": {"list": [
        {"type": "datasource", "name": "ds", "label": "データソース", "query": "prometheus", "current": {}},
        {"type": "custom", "name": "ns", "label": "namespace", "query": "exp", "current": {"text": "exp", "value": "exp"}},
    ]},
    "panels": panels,
}
out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "design-check.json")
with open(out, "w") as f:
    json.dump(dash, f, ensure_ascii=False, indent=1)
print(out, len(panels), "panels")
