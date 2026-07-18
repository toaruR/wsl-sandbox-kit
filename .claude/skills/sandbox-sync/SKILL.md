---
description: サンドボックス内プロジェクトの git 履歴を refs/remotes/sandbox/* へ取り込む(sync_from_sandbox.py のラッパー)
argument-hint: [--name NAME] [--distro DISTRO]
---

リポジトリルートで `python sandbox/sync_from_sandbox.py $ARGUMENTS` を実行してください。

## 注意

- host の作業ツリー・現在のブランチには触れず、`refs/remotes/sandbox/*` を更新するだけの操作。
- 実行後、必要であれば `git log refs/remotes/sandbox/<ブランチ名>` 等で取り込み結果をユーザーに提示する。
- 実行結果(標準出力・エラー)をそのままユーザーに報告する。
