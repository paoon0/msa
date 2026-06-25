# Windows セットアップ指示(Claude 向け)

このファイルは **Windows マシンで初めてこのリポジトリを使うときに、Claude の記憶を Linux マシンと共有するためのセットアップ手順** です。
ユーザーから「記憶共有のセットアップをして」「このファイルの通りにして」と言われたら、Claude は以下を **そのまま実行** してください。

## 背景(なぜ必要か)

Claude Code のプロジェクト記憶は、プロジェクト絶対パスから生成したフォルダ名の下
`%USERPROFILE%\.claude\projects\<エンコード名>\memory\` に保存される。
このリポジトリでは記憶の実体を **リポジトリ内 `.claude\memory\`** に置き、git で 2 台のマシン間を同期している。
よって Windows 側でも、グローバルの `memory` フォルダを **リポジトリ内 `.claude\memory` へジャンクションで向ける** 必要がある。
(Linux 側は同名フォルダをシンボリックリンクで向け済み。)

## セットアップ手順(Claude が実行する)

### 1. リポジトリを最新化
```bat
git pull
```
これでリポジトリ内に `.claude\memory\`(MEMORY.md と各記憶ファイル)が存在することを確認する。

### 2. このリポジトリの絶対パスとエンコード名を求める
- リポジトリ絶対パス = 現在の作業ディレクトリ(例 `C:\Users\mizuki\msa`)。
- エンコード名 = その絶対パスの **英数字 [A-Za-z0-9] 以外の文字をすべて `-` に置換** したもの。
  - 例: `C:\Users\mizuki\msa` → `C--Users-mizuki-msa`
    (`:` → `-`、各 `\` → `-`)
- グローバル記憶フォルダ = `%USERPROFILE%\.claude\projects\<エンコード名>\memory`

エンコード名が不明な場合は、一度 `claude` をこのリポジトリで起動すると
`%USERPROFILE%\.claude\projects\` に該当フォルダが自動生成されるので、その名前を使う。

### 3. 既存の memory フォルダを退避し、ジャンクションを張る
`<ENC>` をエンコード名、`<REPO>` をリポジトリ絶対パスに置き換えて実行する。

```bat
:: プロジェクトフォルダを用意(無ければ作る)
mkdir "%USERPROFILE%\.claude\projects\<ENC>" 2>nul

:: 既存の実フォルダがあれば退避(中身を失わないため)
if exist "%USERPROFILE%\.claude\projects\<ENC>\memory" (
    move "%USERPROFILE%\.claude\projects\<ENC>\memory" "%USERPROFILE%\.claude\projects\<ENC>\memory.bak"
)

:: リポジトリ内実体へジャンクションを張る(管理者権限不要)
mklink /J "%USERPROFILE%\.claude\projects\<ENC>\memory" "<REPO>\.claude\memory"
```

> 注意: `mklink /J`(ジャンクション)は管理者権限不要。`/D`(シンボリックリンク)は
> 管理者権限か開発者モードが必要なので、原則 `/J` を使う。

### 4. 動作確認
```bat
dir "%USERPROFILE%\.claude\projects\<ENC>"
type "%USERPROFILE%\.claude\projects\<ENC>\memory\MEMORY.md"
```
`memory` が `<JUNCTION>` 表示になり、`MEMORY.md` の中身が読めれば成功。

## 日常運用(セットアップ後)

- 記憶は両マシンとも **git で同期**: 作業前に `git pull`、記憶が更新されたら `git push`。
- `.claude\settings.local.json` はマシン固有なので共有しない(`.gitignore` 済み)。
- 両マシンで同時に記憶を編集すると `MEMORY.md` 等が通常の git コンフリクトになる。
  その場合は普通にマージ解決すればよい。

## トラブルシュート

- **ジャンクションを張り直したい**: `rmdir "%USERPROFILE%\.claude\projects\<ENC>\memory"`
  (ジャンクションの削除は `rmdir`。リンク先の実体は消えない)で外してから 手順3 を再実行。
- **記憶が空に見える**: `git pull` 済みか、ジャンクション先が `<REPO>\.claude\memory` を
  正しく指しているか(`dir` の `<JUNCTION>` 行のパス)を確認する。
