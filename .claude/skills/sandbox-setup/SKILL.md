---
description: エージェント用の分離 WSL2 ディストロを作成・更新する(setup_sandbox.py のラッパー)
argument-hint: [--distro DISTRO] [--install-dir PATH] [--tarball ROOTFS.TAR.GZ] [--dry-run]
---

リポジトリルートで `python sandbox/setup_sandbox.py $ARGUMENTS` を実行してください。

## 注意

- 初回はディストロの新規作成(rootfs ダウンロード含む)に数分かかる。既にある場合は
  wsl.conf の再配置と provision の再実行のみ行う冪等な処理。
- 実行後、認証(`wsl -d agent-sandbox` → `claude` / `codex login`)はこのコマンドの範囲外。
  ユーザーに案内する。
- 実行結果(標準出力・エラー)をそのままユーザーに報告する。
