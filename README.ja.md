# agent-sandbox-kit

[English](README.md)

AI エージェント(Claude Code / Codex CLI / Cursor / Antigravity)を、ホスト Windows から
分離した専用の WSL2 ディストロ(`agent-sandbox`)内で動かすためのキット。

- ディストロの作成・分離設定・プロビジョニング
- プロジェクトの搬入・IDE(VS Code / Cursor / Antigravity)での Remote-SSH 接続・成果物の回収・削除
- 搬入済みプロジェクトを誤ってホスト側で開いたときの警告・ブロック(各クライアントのフック)
- 上記を各クライアントから呼ぶための Skill(`/sandbox-*`)

仕組み・使い方の詳細は [sandbox/README.ja.md](sandbox/README.ja.md) を参照
(インストール先には `.sandbox-kit/README.ja.md` として配置される)。

## 動作要件

- Windows 10/11 + WSL2
- ホスト側に Python 3.10 以降(`python` コマンド)
- 使う IDE と Remote-SSH 拡張

## インストール

```
python install.py <プロジェクトのパス>                                  # 全クライアント
python install.py <プロジェクトのパス> --clients claude,cursor          # クライアントを絞る
python install.py <プロジェクトのパス> --dry-run                        # 変更内容の確認のみ
```

再実行すると差分のあるファイルだけを更新する(冪等)。キット所有ファイルを手で編集
していても、次回の実行でキット版に戻る。

| 配置先 | 内容 | 対象クライアント |
|---|---|---|
| `.sandbox-kit/` | サンドボックス操作スクリプト一式 | 共通 |
| `.claude/skills/sandbox-*/` | Skill | claude |
| `.agents/skills/sandbox-*/` | Skill | codex / antigravity / cursor |
| `.claude/hooks/` + `.claude/settings.json` | 誤オープン検知フック | claude |
| `.codex/hooks/` + `.codex/hooks.json` | 同上 | codex |
| `.cursor/hooks/` + `.cursor/hooks.json` | 同上 | cursor |
| `.agents/hooks/` + `.agents/hooks.json` | 同上 | antigravity |

フック登録は既存の設定ファイルへマージする(このキットのエントリだけを追加・更新し、
他のフックや設定には触れない)。`.codex/hooks.json` と `.agents/hooks.json` には
このマシンの絶対パスが書き込まれるため、リポジトリで共有する場合は `.gitignore` に入れる。

インストール後の初回セットアップ:

```
python .sandbox-kit/setup_sandbox.py      # または各クライアントで /sandbox-setup
```

## リポジトリ構成

```
agent-sandbox-kit/
├── install.py                 インストーラ
├── sandbox/                   → インストール先 .sandbox-kit/
├── hooks/
│   ├── _sandbox_guard_core.py 検知ロジック(全クライアント共通)
│   └── <client>_sandbox_guard.py  クライアント別アダプタ(stdin/stdout 契約の変換)
├── .claude/skills/            Claude Code 向け Skill
├── .agents/skills/            Codex CLI / Antigravity / Cursor 向け Skill
├── tools/destroy_sandbox.py   ディストロ全体のガード付き破棄(配布しない)
└── tests/                     python -m unittest discover -s tests
```

Skill は `.claude/skills/` と `.agents/skills/` をそれぞれ独立したソースとして保守する
(現時点で内容が同じでも、片方からもう片方を生成しない)。

## ディストロの破棄

ディストロは全プロジェクト共用のため、破棄はこのリポジトリから行う:

```
python tools/destroy_sandbox.py                          # git 状態を確認してから破棄
python tools/destroy_sandbox.py --export-first <退避先>    # 全プロジェクトを退避してから破棄
```

## 実機で未確認の事項

各クライアントの公式ドキュメントに基づいて実装しているが、次の点は実機で確認していない。

- Codex CLI: `.codex/hooks.json` のフックが実際に発火し、`decision: block` でプロンプトが止まるか
- Cursor: `workspace_roots` の Windows パス表記、Claude Code フックの互換読み込みとの二重実行の有無
- Antigravity: フック実行時のシェルとカレントディレクトリ、`PreToolUse` の `deny` で全ツールが止まるか
- `cursor` / `antigravity-ide` コマンドの `--remote ssh-remote+<host>` 対応
