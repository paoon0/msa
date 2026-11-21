---
name: cpu-frequency-not-pinned
description: CPU 周波数を 2026-11-17 16:56 に基本の周波数 (ターボ無し P 2.1 / E 1.5 GHz) で固定した (旧 2026-10-19「固定しない」を覆した)。それ以前の測定は全て非固定なので混ぜない。再起動で戻るので実験前に status を確認
metadata:
  node_type: memory
  type: project
  originSessionId: 79ed5039-ad0e-4c07-9dc8-15de8c3cc2cf
  modified: 2026-11-17T07:41:06.663Z
---

**2026-11-17 ユーザ決定: CPU 周波数を固定にする** (「周波数を固定にする話だけど、やっぱり固定にする」)。旧決定 (2026-10-19「固定しない」) を覆した。**2026-11-17 16:56:21 に固定した** (ユーザ選択 A = 基本の周波数: ターボ無し、P コア 2.1 GHz・E コア 1.5 GHz、governor/EPP = performance、下限 = 上限)。`km2/experiments/shared/cpufreq.sh pin` を sudo で実行 (ユーザの依頼でパスワードを渡されて実行)。負荷をかけたコアが 2100 / 1500 MHz に張り付くことを確認 (仕事のないコアは休止で 400 MHz と表示されるだけ)。**OS を再起動すると元に戻る** → 実験前に `bash km2/experiments/shared/cpufreq.sh status` で確かめる。解除は `sudo bash km2/experiments/shared/cpufreq.sh unpin`。

マシン (2026-11-17 確認): i7-1260P、intel_pstate active、ガバナ powersave、ターボ有効 (no_turbo=0)。P コア 4 個 × 2 スレッド (cpu0–7) は基本 2.1 GHz / 最大 4.7 GHz、E コア 8 個 (cpu8–15) は基本 1.5 GHz / 最大 3.4 GHz。pdistk3sep2 の -times.csv では平均周波数 約 3.2 GHz (2.9–3.4)、最高温度 77–100 °C (固定前の値)。

**旧決定 (2026-10-19) の理由 (比較の扱いに要るので残す):** 研究目的は性能でなく相性の良い組み合わせの傾向。HPA は実運用でも周波数の変わる CPU 時間で判断する。周波数が上がると無関係なサービスの CPU 時間が減って見える (Sock Shop 購入側 −12〜−34%、OB は購入 25 で −26〜−32%、高負荷で頭打ち後は +2〜+12%)。根拠 Linux cgroup-v2 doc "does not account for the frequency"、文献 km2/approach/related_work.md §8。Sock Shop の購入側どうしの細かい ρ 比較はしない (「≈0 の塊」)。

**How to apply:**
- 2026-11-17 より前の測定 (FOSE、mix-cpu3 の ρ、枠の表 rightsize-pdist-k3-mc3.csv、pdistk3sep2/pair2、smoke-k3win / smoke-k3su30) は**すべて周波数非固定**。固定後の測定と混ぜない。
- 枠 (requests) と ρ は非固定で測った CPU から出しているので、固定 (特にターボ無し) にすると 1 周あたり CPU が変わり、測り直しが要る。
- 周波数・温度は引き続き毎点記録する (-times.csv の freq_ghz / temp_max_c)。
- 旧 fix.sh は残っていない (2026-11-17 に探して無し)。
- 関連: [[rho-pair-selection-focus]]
- 時刻の表の `freq_ghz` は 16 スレッドの単純平均で、休んでいるコアの低い値 (約 400 MHz) が混ざる → 固定の証拠にならない (固定中の最大 1.80 GHz)。証拠は熱低下カウンタの増分と P/E 別の窓内最大 (2026-11-17 アヌビス、related_work.md §9.30)。
- 2026-11-19 固定の効果を確認: 需要モデルの「形のずれ」(配合ごと 6 サイクル平均の残差、b50v150 の D 比) が mix-cpu3→mix-cpu4 で 1 台 6.1→2.9%・2 台 6.6→1.7%、サイクルの揺れは約 2% で不変 (km2/experiments/rightsizing/analysis-fit-shape.txt、related_work.md §9.31)。
