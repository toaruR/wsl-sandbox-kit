#!/usr/bin/env python3
"""agent-sandbox 誤オープン検知フック(Claude Code SessionStart / UserPromptSubmit 用)。

サンドボックス(agent-sandbox WSL ディストロ)内のフォルダを、ホスト Windows 側の
IDE / Claude Code で直接開いてエージェントを使うと、エージェントがホスト権限で
動いてしまい隔離が無意味になる。このフックはその状態を検知して警告し、
UserPromptSubmit ではプロンプト送信をブロックする。

検知ロジック本体は同じディレクトリの _sandbox_guard_core.py にある
(Codex CLI / Cursor / Antigravity 用アダプタと共有)。
このファイルは Claude Code の stdin/stdout 契約に変換するだけの薄いアダプタ。

install.py により、インストール先の .claude/hooks/ に配置され、
同じプロジェクトの .claude/settings.json から呼ばれる。
"""

import json
import os
import sys

from _sandbox_guard_core import is_sandbox_path, build_warning_message


def main():
    if os.name != "nt":
        return  # ディストロ内(正しい使い方)ではガード不要

    try:
        payload = json.load(sys.stdin)
    except Exception:
        payload = {}
    cwd = payload.get("cwd") or os.getcwd()
    if not is_sandbox_path(cwd):
        return

    msg = build_warning_message(cwd)
    if payload.get("hook_event_name") == "UserPromptSubmit":
        out = {"decision": "block", "reason": msg, "systemMessage": msg}
    else:
        out = {"systemMessage": msg}
    # ensure_ascii 既定(True)のまま出力する: Windows コンソールの cp932 でも壊れない
    print(json.dumps(out))


if __name__ == "__main__":
    main()
