---
name: prometheus-rate-edge-underestimate
description: Prometheus の rate()/increase() は窓の端のサンプル間隔が空くと必ず過小に出る (mix-cpu4 で 188/1612 行が −2% 超、最大 −13%)。CPU は -raw.csv の生カウンタ差分で出す
metadata:
  type: project
---

2026-11-20 アヌビスが発見、自分でも再計算して確認。`measure-mix-cpu.sh:189` の `rate(container_cpu_usage_seconds_total[160s])` は、窓の端から最初/最後のサンプルまでが平均サンプル間隔 × 1.1 を超えると補外を半間隔で打ち切る。cAdvisor のサンプル間隔は 10〜20 s で不規則なので、よく起きる。誤差は常に過小方向 (過大は 0 行)。mix-cpu4 で 1612 行中 188 行が −2% 超、最大 −13.4% (frontend 34 行)。close20-chk の「v300 −2.6%」もこれが原因 (生カウンタでは +0.5%)。`rate[30s]` の 15 秒刻みで「1 Pod が瞬間的に 1/4 に落ちる」ように見えたのもこの見かけ。

**Why:** ρ のペア差は 0.005 程度の勝負なので、この誤差で順位が入れ替わる (1 台の front−reco が +0.0065 → −0.0053)。
**How to apply:** CPU 使用量は `-raw.csv` の窓内の最初と最後のサンプルの (差 ÷ 時刻差) で出す。Pod 別の時系列は生の隣接差か rate[60s] 以上で見る。bundle-vs-loss2 の k6_cpu_sec (increase) にも同じ誤差がある。過去の ρ・枠 (mix-cpu2/3/4、mc4 表) は作り直すかどうかがユーザの判断待ち。記録 = km2/approach/related_work.md §9.31。関連: [[rho-pair-selection-focus]] [[k6-frontend-pod-pinning]] [[verify-numbers-python]]
