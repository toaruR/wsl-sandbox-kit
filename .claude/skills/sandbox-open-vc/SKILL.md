---
name: sandbox-open-vc
description: 搬入済みプロジェクトへ IDE(VS Code / Cursor / Antigravity)を繋ぎ直す(reopen_in_sandbox.py のラッパー)
disable-model-invocation: true
---

リポジトリルートで `python .sandbox-kit/reopen_in_sandbox.py` を実行してください。
ユーザーが会話中で `--name NAME` / `--distro DISTRO` / `--ide IDE` を指定していれば、コマンドライン引数として渡す。

## 注意

- `--name` を省略するとカレントディレクトリ名がプロジェクト名として使われる。
- `--ide` は `code`(VS Code)/ `cursor` / `antigravity`(別名 `agy`)のいずれか。省略時は環境変数 `AGENT_SANDBOX_IDE`、未設定なら `code`。
- 再搬入は行わない(既存コピーの中身には一切触れない)。まだ搬入していない場合は sandbox-open スキルを使う。
- 実行結果(標準出力・エラー)をそのままユーザーに報告する。
