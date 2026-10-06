---
name: memory-synced-via-git
description: メモリの実体はリポジトリ内 .claude/memory/ へのシンボリックリンク=メモはgit管理され2台のマシン間で同期される。
metadata:
  node_type: memory
  type: project
---

2026-10-06 に確認。ハーネスのメモリ置き場 `/home/mizuki/.claude/projects/-home-mizuki--------msa/memory` は、**リポジトリ内の `/home/mizuki/ダウンロード/msa/.claude/memory` へのシンボリックリンク**（2026-06-25 に設定）。

- メモリを書く＝リポジトリに書くことなので、**コミットしないと消える / もう1台のマシンに届かない**。
- 逆に、もう1台で書いたメモは `git pull` でこちらに入る（実例: 2026-10-06 の `3eeb674` でカメラレディ作業の記録が `fose2026-live-paper.md` に入ってきた）。
- 本研究は計算資源の多いマシンと少ないマシンの2台を使うので、この同期が前提になっている。

関連: [[subagent-setup]]
