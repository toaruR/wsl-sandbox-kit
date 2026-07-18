---
description: 搬入済みプロジェクトへ VS Code を繋ぎ直す(reopen_in_sandbox.py のラッパー)
argument-hint: [--name NAME] [--distro DISTRO]
---

リポジトリルートで `python sandbox/reopen_in_sandbox.py $ARGUMENTS` を実行してください。

## 注意

- `--name` を省略するとカレントディレクトリ名がプロジェクト名として使われる。
- 再搬入は行わない(既存コピーの中身には一切触れない)。まだ搬入していない場合は `/sandbox-open` を使う。
- 実行結果(標準出力・エラー)をそのままユーザーに報告する。
