---
name: cpu-frequency-not-pinned
description: CPU 周波数は固定しない (2026-10-19 ユーザ決定)。研究目的は性能測定でなく相性の良い組み合わせの傾向。DVFS 偏りは記録して限界に書く
metadata:
  type: project
---

CPU 周波数 (ガバナ powersave / EPP balance_performance、i7-1260P の P/E 混在) は固定しない。2026-10-19 ユーザ決定。

**Why:** 研究目的は性能を知ることではなく、相性の良い組み合わせ (ρ でのペア選び) の傾向を知ること。HPA は実運用でも周波数の変わる CPU 時間で判断するので、変動は現実の一部。文献も両方の作法を許容する (遅延の精密測定系は固定、オートスケール系の多くは記述なし、作法文献は「固定できなければ設定を文書化」)。OB も固定せずに測っており、揃う。

**How to apply:**
- 周波数・温度は毎点記録し続ける (measure-mix-cpu.sh は freq_ghz/temp_max_c を記録済み、HPA ドライバにも入れる)。
- 論文には限界として書く: 負荷で周波数が上がると無関係なサービスの CPU 時間が減って見える (Sock Shop 購入側 −12〜−34%、OB は購入 25 で −26〜−32%、高負荷で頭打ち後は +2〜+12%)。根拠に Linux cgroup-v2 doc の "does not account for the frequency"。文献は km2/approach/related_work.md §8。
- このため Sock Shop の購入側どうしの細かい ρ 比較はしない (「≈0 の塊」として扱う)。
- 固定用 fix.sh は作ったが未実行 (sudo が必要、マシン設定は変えていない)。
- 関連: [[rho-pair-selection-focus]]
