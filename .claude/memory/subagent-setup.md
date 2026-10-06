---
name: subagent-setup
description: サブエージェント3体(calc-coder/anubis(旧paper-referee)/related-work)を .claude/agents/ に新規作成。一覧はセッション開始時に固定されるので作成後は再起動が必要。
metadata:
  node_type: memory
  type: project
---

2026-10-06。ユーザの「サブエージェントを使ってみたい」から始めて、このリポジトリ専用のサブエージェントを3体定義した。定義は `.claude/agents/*.md`、委譲ルールは `CLAUDE.md` の「サブエージェントの使い分け」節（CLAUDE.md に書いたので自発的な委譲が許可された状態）。**役割と委譲条件はその2箇所に書いてあるので、ここには設計判断と落とし穴だけ残す。**

## 落とし穴（実測で確認）
- **エージェント一覧はセッション開始時に読み込まれ、走っているセッションには反映されない。** 作成直後に `calc-coder` を呼んだら `Agent type 'calc-coder' not found. Available agents: claude, claude-code-guide, Explore, general-purpose, Plan, statusline-setup` で失敗した。`/clear` では不十分な見込みで、`claude` の再起動が必要。
- サブエージェントは**メインの会話の文脈をゼロ継承**する。起動時の指示文に、研究の前提（同居の主張・主指標が softirq/周・対象が Online Boutique）、対象ファイルのパス、期待する出力形式を毎回書かないと的外れな作業をする。
- サブエージェントのツール出力はメインの文脈に入らない（＝CSV を大量に読ませても文脈が汚れない）。これが使う最大の利点なので、軽い作業に使うと逆に損。

## 設計判断（なぜそうしたか）
- **anubis(旧paper-referee) には Write/Edit を持たせていない。** 査読役が原稿を書き換えると「誰の判断で通ったか」が曖昧になるため、判定と指摘だけを返させる。モデルも唯一 Opus（判定の甘さが成果物の価値を壊すため）。
- **anubis(旧paper-referee) の最優先軸は「数値の取得方法の妥当性」**（ユーザ指示 2026-10-06: 「数値の取得方法が妥当であるかが一番大事」）。統計処理より前に、指標の定義・計測窓・カウンタの差分化・サンプリング間隔・帰属・分母・観測の摂動・道具が測っている量・失敗の扱い・再現性の10項目を見る。他の軸（主張と証拠の対応、ベースラインの公平性 等）はその後。
- **related-work は知識の蓄積が義務。** `km2/approach/related_work.md` を所有し、調査したら必ず追記させる（過去にこのファイルが git 未追跡のまま失われた事故があるため）。ハルシネーション禁止を最大の禁止事項にし、DOI/URL に到達できなければ「書誌情報未確認」と書かせる。
- **実験の進行（負荷の投入・停止、マニフェストの apply/delete、台数やしきい値の変更）は誰にもやらせない。** 引き金は常にユーザーが引く。calc-coder は読み取りの kubectl と `exec` までは自由（マニフェストやメトリクス列名を推測で書かせないため）。
- manifest-auditor（束ね構成と分離構成のマニフェストを機械的に diff する役）は**作らないと判断した** — anubis(旧paper-referee) の軸13（ベースラインの公平性）とほぼ重複するため。必要なら anubis(旧paper-referee) に「先にマニフェストを diff してから判定せよ」と頼む。

関連: [[verify-numbers-python]] [[memory-synced-via-git]]
