---
name: sandbox-open
description: プロジェクトをサンドボックスへ搬入して VS Code で開く(open_in_sandbox.py のラッパー)
disable-model-invocation: true
---

リポジトリルートで `python sandbox/open_in_sandbox.py` を実行してください。
ユーザーが会話中で `project` / `export_dest` や `--name NAME` / `--distro DISTRO` /
`--force` / `--no-code` / `--export` を指定していれば、コマンドライン引数として渡す。

## 注意

- 何も指定が無い場合はカレントディレクトリが対象になる。
- 搬入先ディレクトリが既に存在し `--force` が指定されていない場合、スクリプトが `y/N` の確認入力を対話的に求める。Bash 実行では標準入力に応答できないため、上書きしてよいかを事前にユーザーへ確認してから `--force` の要否を判断すること。
- 実行結果(標準出力・エラー)をそのままユーザーに報告する。
