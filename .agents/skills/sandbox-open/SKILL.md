---
name: sandbox-open
description: プロジェクトをサンドボックスへ搬入して IDE(VS Code / Cursor / Antigravity)で開く(open_in_sandbox.py のラッパー)
disable-model-invocation: true
---

リポジトリルートで `python .sandbox-kit/open_in_sandbox.py` を実行してください。
ユーザーが会話中で `project` / `export_dest` や `--name NAME` / `--distro DISTRO` /
`--force` / `--no-code` / `--export` / `--ide IDE` を指定していれば、コマンドライン引数として渡す。

## 注意

- 何も指定が無い場合はカレントディレクトリが対象になる。
- `--ide` は `code`(VS Code)/ `cursor` / `antigravity`(別名 `agy`)のいずれか。省略時は環境変数 `AGENT_SANDBOX_IDE`、未設定なら `code`。
  ユーザーが IDE 名だけを言った場合(「Cursor で開いて」等)も対応する値を `--ide` に渡す。
- 搬入先ディレクトリが既に存在し `--force` が指定されていない場合、スクリプトが `y/N` の確認入力を対話的に求める。Bash 実行では標準入力に応答できないため、上書きしてよいかを事前にユーザーへ確認してから `--force` の要否を判断すること。
- 実行結果(標準出力・エラー)をそのままユーザーに報告する。
