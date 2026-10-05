#!/usr/bin/env python3
"""agent-sandbox 誤オープン検知フック(Cursor sessionStart / beforeSubmitPrompt 用)。

Claude Code 用アダプタ(claude_sandbox_guard.py)の Cursor 版。検知ロジック本体は
同じディレクトリの _sandbox_guard_core.py にある。

Cursor のフックは stdin に {hook_event_name, workspace_roots, ...} を受け取る
(cwd は共通フィールドに無いため workspace_roots を見る。無ければ環境変数
CURSOR_PROJECT_DIR、それも無ければカレントディレクトリ)。
beforeSubmitPrompt は {"continue": false, "user_message": ...} でプロンプトを
ブロックできる。sessionStart はブロックできないため、additional_context で
エージェントへ警告を渡すだけにする(Cursor 公式ドキュメント hooks による)。

install.py により、インストール先の .cursor/hooks/ に配置され、
同じプロジェクトの .cursor/hooks.json から呼ばれる(trusted workspace のみ)。
"""

import json
import os
import sys

from _sandbox_guard_core import find_sandbox_path, build_warning_message


def main():
    if os.name != "nt":
        return  # ディストロ内(正しい使い方)ではガード不要

    try:
        payload = json.load(sys.stdin)
    except Exception:
        payload = {}
    roots = payload.get("workspace_roots") or []
    if not roots:
        roots = [os.environ.get("CURSOR_PROJECT_DIR") or os.getcwd()]
    hit = find_sandbox_path(roots)
    if hit is None:
        return

    msg = build_warning_message(hit)
    if payload.get("hook_event_name") == "beforeSubmitPrompt":
        out = {"continue": False, "user_message": msg}
    else:
        out = {"additional_context": msg, "user_message": msg}
    print(json.dumps(out))


if __name__ == "__main__":
    main()
