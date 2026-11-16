---
name: no-search-onedrive
description: ローカルのファイル探しで C:\Users\user 全体を走査しない。OneDrive (特に「OneDrive - 和歌山大学」) を読むとクラウド上のファイルがダウンロードされる
metadata:
  node_type: memory
  type: feedback
  originSessionId: 32ae1817-99cb-4f9e-916c-7bf4147c442c
  modified: 2026-11-08T11:51:09.390Z
---

2026-11-08、論文 PDF を探すために `find /c/Users/user -maxdepth 5 -iname '*.pdf'` で全 PDF の 1 ページ目を pdftotext したところ、`C:\Users\user\OneDrive - 和歌山大学` の 17 ファイル (授業レポート・就活・ゼミ資料など研究と無関係) まで開いてしまった。ユーザに「onedrive から何か取得した？」と確認された。

**Why:** OneDrive の「オンラインのみ」のファイルは、読むだけでクラウドから自動でダウンロードされる。研究と無関係な私的ファイルを開くことにもなる。
**How to apply:** ファイル探しは場所を絞る (`C:\msa`、`~/Downloads`、`~/Desktop/読みたい論文` など)。ユーザのホーム全体や OneDrive 配下を再帰的に走査・読み込みしない。見つからなければ場所をユーザに聞く。
