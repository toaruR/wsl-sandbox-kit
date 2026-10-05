---
name: sandbox-setup
description: エージェント用の分離 WSL2 ディストロを作成・更新する(setup_sandbox.py のラッパー)
disable-model-invocation: true
---

リポジトリルートで `python .sandbox-kit/setup_sandbox.py` を実行してください。
ユーザーが会話中で `--distro DISTRO` / `--install-dir PATH` / `--tarball ROOTFS.TAR.GZ` /
`--dry-run` を指定していれば、コマンドライン引数として渡す。

## 注意

- 初回はディストロの新規作成(rootfs ダウンロード含む)に数分かかる。既にある場合は
  wsl.conf の再配置と provision の再実行のみ行う冪等な処理。
- 実行後、認証(`wsl -d agent-sandbox` → `claude` / `codex login`)はこのスキルの範囲外。
  ユーザーに案内する。
- 実行結果(標準出力・エラー)をそのままユーザーに報告する。
