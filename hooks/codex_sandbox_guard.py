#!/usr/bin/env python3
"""agent-sandbox 誤オープン検知フック(Codex CLI SessionStart / UserPromptSubmit 用)。

Claude Code 用アダプタ(claude_sandbox_guard.py)の Codex 版。検知ロジック本体は
同じディレクトリの _sandbox_guard_core.py にある。

Codex CLI のフックは stdin に {session_id, cwd, hook_event_name, ...} を受け取り、
UserPromptSubmit は {"decision": "block", "reason": ...} でプロンプトをブロックできる。
systemMessage は UI へ警告として表示される(Codex 公式ドキュメント hooks による)。
イベント種別は stdin payload の hook_event_name を優先し、無ければ
.codex/hooks.json のフック登録コマンドに付与する --event 引数で判定する。

install.py により、インストール先の .codex/hooks/ に配置され、
同じプロジェクトの .codex/hooks.json から呼ばれる。プロジェクトのフックは
.codex/ 層が trusted のときだけ読まれ、定義ごとに /hooks での承認が要る。
"""

import argparse
import json
import os
import sys

from _sandbox_guard_core import is_sandbox_path, build_warning_message


def main():
    if os.name != "nt":
        return  # ディストロ内(正しい使い方)ではガード不要

    parser = argparse.ArgumentParser()
    parser.add_argument("--event", choices=["SessionStart", "UserPromptSubmit"], default=None)
    args, _ = parser.parse_known_args()

    try:
        payload = json.load(sys.stdin)
    except Exception:
        payload = {}
    event = payload.get("hook_event_name") or args.event
    cwd = payload.get("cwd") or os.getcwd()
    if not is_sandbox_path(cwd):
        return

    msg = build_warning_message(cwd)
    if event == "UserPromptSubmit":
        out = {"decision": "block", "reason": msg, "systemMessage": msg}
    else:
        out = {"systemMessage": msg}
    print(json.dumps(out))


if __name__ == "__main__":
    main()
