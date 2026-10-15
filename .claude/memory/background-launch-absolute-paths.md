---
name: background-launch-absolute-paths
description: 長時間実験を Bash の run_in_background で起動するときは cd に頼らずスクリプト・CSV・表を絶対パスで渡す
metadata:
  type: feedback
---
2026-10-15、`cd .../summer2026 && VAR=... bash bundle-vs-loss2.sh` を run_in_background で起動すると、何度か `bash: bundle-vs-loss2.sh: そのようなファイルやディレクトリはありません` (exit 127) で即終了した (cd が効いていない)。

**Why:** 失敗はログも出ないので、気づかずに「本走を始めた」と報告しかねない。

**How to apply:** `bash $S/bundle-vs-loss2.sh`、`CSV=$S/results-x.csv`、`RSTABLE=$R/...` のように全部絶対パスで渡す。起動後に stdout の「枠検査 OK」まで出たことを確かめてから報告する。関連: [[no-progress-monitors]]
