# エージェント用サンドボックス(WSL2 専用ディストロ)

AI エージェント(Claude Code / Codex CLI 等)を、ホスト Windows から分離した
専用の WSL2 ディストロ内で動かすための一式。自動承認モードでエージェントを
走らせても、被害がディストロ内に閉じることを目的とする。

## 方式と分離の範囲

VS Code の UI はホスト(Windows ネイティブ)のまま、**Remote-SSH 接続**
(localhost:2222 → ディストロ内 sshd)で分離ディストロ内のプロジェクトを開く。
エージェント・シェル・ツールはすべてディストロ内で動く。

⚠️ VS Code の **WSL リモート拡張(`wsl+`)は使えない**: あの拡張は Windows 側の
拡張ディレクトリやサーバー tarball を `/mnt/c`(automount)経由で読む前提で
動くため、automount を無効にした分離ディストロでは必ず失敗する
(`Failed to translate 'c:\...'` → `wslServer.sh: not found`)。
このため接続は Remote-SSH で行う。鍵と `~/.ssh/config` の `Host agent-sandbox`
エントリは setup_sandbox.py が自動で用意する。

| 項目 | 状態 |
|---|---|
| ホストのドライブ (C:/D:) | **見えない**(`automount` 無効) |
| Windows 実行ファイルの起動 | **できない**(`interop` 無効) |
| sudo / root | **エージェントには与えない**(sudo があると drvfs でホストドライブをマウントでき分離が破れる) |
| `\\wsl.localhost` 共有 | **使えない**(interop 無効の副作用で Plan9 共有も止まる)。コピーは tar ストリームで行う |
| ネットワーク | **制限なし**(API 呼び出し・npm install 等は素通し) |
| 二層目の防御 | Linux 上なので Claude Code / Codex 内蔵サンドボックスも有効化可 |

**限界**:

- ネットワークは全許可のため、認証情報をディストロ内に置く以上、その権限で
  できること(git push 等)はエージェントにもできる。渡すトークンは必要最小限
  の権限にすること。
- WSL2 の全ディストロは**1つの VM・カーネルを共有**している。カーネルレベルの
  脆弱性に対する強固な境界(Hyper-V VM 分離ほど)ではない。日常の暴走・誤操作
  対策と割り切ること。

## セットアップ(初回のみ)

```
python sandbox/setup_sandbox.py
```

Ubuntu 24.04 rootfs のダウンロード → `agent-sandbox` ディストロの import →
分離設定(wsl.conf)→ provision(agent ユーザー / Node.js / claude / codex)まで
自動で行う。再実行すると設定と provision だけ再適用される(冪等)。

続けて認証を行う:

```
wsl -d agent-sandbox
$ claude          # 表示された URL をホストのブラウザに手動で貼る
$ codex login     # 同上
```

⚠️ interop 無効のためブラウザは自動で開かない。URL の手動コピーで進めること。

## 日常の使い方

```
python sandbox/open_in_sandbox.py <プロジェクトのパス>
```

1. プロジェクトが tar ストリーム経由でディストロ内
   `/home/agent/projects/<名前>` にコピーされる
   (`node_modules`・`.venv`・`__pycache__` は除外)
2. VS Code が `ssh-remote+agent-sandbox` リモートで起動する
   (**Remote-SSH 拡張** `ms-vscode-remote.remote-ssh` が必要)
3. 初回はリモート側に **Claude Code 拡張をインストール**する
   (拡張ビューで「Install in SSH: agent-sandbox」)

成果物の回収:

- **git push(推奨)**: ディストロ内から push し、ホスト側で pull する
- **逆コピー**: `python sandbox/open_in_sandbox.py --export <名前> <取り出し先>`

パッケージの追加(エージェントに sudo は無い)はホスト側から行う:

```
wsl -d agent-sandbox -u root -- apt-get install -y <パッケージ>
```

## キット更新の反映(再搬入はしない)

⚠️ open_in_sandbox.py の再搬入は既存プロジェクトを**丸ごと置き換える**
(rm -rf + コピー)ため、知見記録キットの更新をディストロ内のコピーへ反映する
手段に使わないこと。エージェントの未 push 作業が消える。更新はプロジェクト
本体に触れない専用スクリプトで行う:

```
python sandbox/update_kit_in_sandbox.py <プロジェクト名>   # 1つだけ
python sandbox/update_kit_in_sandbox.py --all              # 全プロジェクト
```

- キット一式を tar でディストロ内 staging(`/home/agent/.knowledge-kit`)へ送り、
  **ディストロ内で** install_kit.py を実行する。バージョン比較・マーカー管理に
  より、手動編集の疑いがあるファイルは skip され、ハマりポイントと
  docs/specification.md は保護される
- 更新結果はサンドボックス側コピーの未コミット差分として現れるので、
  エージェントの通常フロー(コミット → push)で回収する
- 代替: ホスト側コピーに install_kit.py を当てて push → ディストロ内で pull
  でも同じ結果になる(install_kit.py は決定的に同じファイルを生成するため、
  両側で個別に更新しても衝突しにくい)

## 注意点・ハマりポイント

- **ディストロ内から `code .` は使えない**(interop 無効)。VS Code への接続は
  必ずホスト側から行う(`code --remote ssh-remote+agent-sandbox <パス>` または
  Remote Explorer の SSH ターゲット)。
- **WSL リモート拡張(`wsl+`)は分離設定と非互換**(automount 前提)。
  誤って「WSL: agent-sandbox で開く」を選ぶと
  「VS Code Server for WSL closed unexpectedly」で失敗する。Remote-SSH を使うこと。
- **SSH 接続はディストロが起動していることが前提**。open_in_sandbox.py は起動まで
  面倒を見るが、PC 再起動後に直接 Remote-SSH で繋ぐ場合は先に
  `wsl -d agent-sandbox` で起こしておく(systemd 有効なので以後は動き続ける)。
- **wsl.exe の出力は UTF-16LE**。スクリプトから叩くときは `WSL_UTF8=1` を付ける
  (本ディレクトリのスクリプトは対応済み)。
- **改行コード**: Windows からコピーしたファイルは CRLF のまま。気になる場合は
  ディストロ内で `git config core.autocrlf input` を設定する。
- **Antigravity**: スタンドアロン CLI のインストール手順が未確認のため
  provision.sh はプレースホルダーのみ(手順判明後に追記)。VS Code 系 IDE の
  ため、IDE 側の WSL リモート接続で本ディストロに繋ぐ運用は可能。

## 二層目: Claude Code 内蔵サンドボックスの併用

ディストロは Linux なので、Claude Code の OS レベルサンドボックス
(bubblewrap ベース)が使える。ディストロ内プロジェクトの
`.claude/settings.json` に以下を足すと、Bash 実行がさらに閉じ込められる:

```json
{
  "sandbox": { "enabled": true }
}
```

## ホスト側ガード: 誤ってホスト側で開いたときの警告・ブロック

サンドボックス内のフォルダを**ホスト側の** VS Code / Claude Code で直接開くと
(SSHFS マウントや `\\wsl.localhost` 経由)、エージェントがホスト Windows の
権限で動いてしまい隔離が無意味になる。これを検知するフックは、知見記録キットが
**インストール先プロジェクトにのみ**配置する(ユーザーグローバル設定には入れない):

- 実体: インストール先の `.claude/hooks/sandbox_guard.py`(Python・
  Windows / WSL 両対応)。install_kit.py / `/install-kit` が同プロジェクトの
  `.claude/settings.json` の SessionStart / UserPromptSubmit に登録する
- プロジェクトは `.claude/` ごと tar でサンドボックスへ搬入されるため、搬入後の
  コピーを誤ってホスト側で開いた場合もフックが効く
- 検知方法: ① `\\wsl.localhost\agent-sandbox` / `\\wsl$\...` パス、
  ② SSHFS-Win の UNC(`\\sshfs\agent@localhost!2222` 等)とドライブ割り当て、
  ③ マーカーファイル `.agent-sandbox` の祖先探索(provision.sh がディストロ内に
  root 所有 + immutable で配置。マウント方法によらず効く)
- 動作: セッション開始時に警告表示、プロンプト送信時は**ブロック**する。
  警告だけにしたい場合はインストール先 settings.json の `UserPromptSubmit`
  エントリを削除する
- **Windows 以外では何もしない**: Remote-SSH で正しく開いた場合はディストロ内の
  Claude Code がフックを実行するが、Linux 上なので即終了する(誤検知しない)
- マーカー検知は provision 再実行(`python sandbox/setup_sandbox.py`)後に有効。
  UNC / SSHFS パターン検知はそれ以前でも効く

なお Codex CLI には同等のフック機構がないため、このガードは Claude Code のみ対象。

## ファイル構成

```
sandbox/
├── README.md              ← このファイル
├── setup_sandbox.py       ← 初回セットアップ(冪等・再実行可)
├── provision.sh           ← ディストロ内プロビジョニング(setup から自動実行)
├── wsl.conf               ← 分離設定テンプレート(/etc/wsl.conf に配置される)
├── open_in_sandbox.py     ← プロジェクト搬入・取り出し(--export)+ VS Code 起動
├── update_kit_in_sandbox.py ← ディストロ内コピーへのキット更新(本体に触れない)
└── destroy_sandbox.py     ← ガード付き破棄(git 状態確認・退避・最終確認)
```

(誤オープン検知フック本体はキット側 `.claude/hooks/sandbox_guard.py` にある)

## ディストロの破棄・作り直し

⚠️ ディストロは**全プロジェクト共有**。素の `wsl --unregister` は確認なしで
即座に消え、`/home/agent/projects` 配下すべての未 push 作業と認証状態が
一緒に失われる。破棄は必ずガード付きスクリプトで行うこと:

```
python sandbox/destroy_sandbox.py                        # git 状態を確認してから破棄
python sandbox/destroy_sandbox.py --export-first <退避先>  # 全プロジェクトを退避してから破棄
python sandbox/setup_sandbox.py                          # 再作成(認証は再度必要)
```

- 未コミット / 未 push / git 管理外のプロジェクトが1つでもあれば一覧を出して
  拒否する(push で回収してから再実行が推奨。承知のうえの強行は `--force`)
- 実行前にディストロ名の入力による最終確認がある(スクリプト実行時は `--yes`)
- 運用の原則: **ディストロは使い捨ての計算環境、永続化は git push のみ**。
  この原則を守っていれば破棄はいつでも安全

**特定プロジェクトだけ壊れた・作り直したい場合は破棄不要**:

```
wsl -d agent-sandbox -- rm -rf /home/agent/projects/<名前>
python sandbox/open_in_sandbox.py <プロジェクトのパス>    # 再搬入
```
