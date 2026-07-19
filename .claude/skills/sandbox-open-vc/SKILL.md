---
name: sandbox-reopen
description: 搬入済みプロジェクトへ VS Code を繋ぎ直す(reopen_in_sandbox.py のラッパー)
disable-model-invocation: true
---

リポジトリルートで `python sandbox/reopen_in_sandbox.py` を実行してください。
ユーザーが会話中で `--name NAME` / `--distro DISTRO` を指定していれば、コマンドライン引数として渡す。

## 注意

- `--name` を省略するとカレントディレクトリ名がプロジェクト名として使われる。
- 再搬入は行わない(既存コピーの中身には一切触れない)。まだ搬入していない場合は sandbox-open スキルを使う。
- 実行結果(標準出力・エラー)をそのままユーザーに報告する。
