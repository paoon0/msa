---
name: monitoring-stack
description: How to reach Prometheus/Grafana for the msa load experiments
metadata: 
  node_type: memory
  type: reference
  originSessionId: d2cea3bd-2c2c-4109-8e64-b9f6f7d126fa
---

監視は `monitoring` namespace の kube-prometheus-stack。
- Prometheus: svc `prometheus-grafana-kube-pr-prometheus:9090`(port-forward して `/api/v1/query` を叩く)。
- node-exporter, kube-state-metrics, cAdvisor(kubelet 経由), metrics-server(`kubectl top` 稼働)すべて取得可。
- Grafana: pod `prometheus-grafana` は 1/3 READY(CrashLoopBackOff 表示)だが **port-forward すれば利用可能**とのこと。

関連: [[coloc-resource-efficiency-study]]
