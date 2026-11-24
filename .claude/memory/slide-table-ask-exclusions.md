---
name: slide-table-ask-exclusions
description: pdist-k3 のスライド用の表 (ρ の差・affinity・引きずり回数) を呼び出すときは、外すペアを先にユーザへ尋ねる (2026-11-24 ユーザ指示)
metadata:
  type: feedback
---

pdist-k3 3 回目のスライド用の表 `km2/experiments/rightsizing/slide-table-pdistk3-3.md` (Excel/PowerPoint 用は同じ名前の `.csv`、BOM 付き・「2/15」を列に分けた版) を出すときは、**まず「外すペアはありますか」と尋ねる**。尋ね方は AskUserQuestion ではなく本文で、11 組 (3 つ同居を含む) の名前を並べて選んでもらう。外したら、その行を除いた表を出し、何を外したかを表の下に書く。

**Why:** 2026-11-24 ユーザ「私がこの資料を呼び出す際に、外すペアも尋ねてほしい」。発表ごとに見せる組を変えたいため。

**How to apply:** 「あの表」「スライドの表」「引きずりの表」などで呼ばれたらこのファイルを読み、外すペアを聞いてから出す。表の数値は出所 (同ファイルの「出所」節) から変えない。affinity は 9/08 値が既定、ρ と同じ条件の b50v50 値もある。関連: [[loss-counting-time-average]]、[[rho-pair-selection-focus]]
