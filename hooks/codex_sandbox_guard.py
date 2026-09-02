#!/usr/bin/env python3
"""agent-sandbox 誤オープン検知フック(Codex CLI SessionStart / UserPromptSubmit 用)。

.claude/hooks/sandbox_guard.py の Codex 版アダプタ。検知ロジック本体は
同じディレクトリの _sandbox_guard_core.py にある(Claude Code 用アダプタと共有)。

Codex CLI の SessionStart / UserPromptSubmit フックは
{continue, stopReason, systemMessage, suppressOutput} の出力契約を共有する
(Claude Code の {decision:"block", ...} 形式ではない)。イベント種別は
stdin payload の hook_event_name を優先し、無ければ .codex/config.toml の
フック登録コマンドに付与する --event 引数で判定する
(Codex 側の実際の stdin スキーマは未検証。実機確認は今後のフェーズで行う)。

知見記録キットの一部として、インストール先の .codex/hooks/ に配置され、
同じプロジェクトの .codex/config.toml から呼ばれる(install_kit.py が登録)。
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
        out = {"continue": False, "stopReason": msg, "systemMessage": msg}
    else:
        out = {"systemMessage": msg}
    print(json.dumps(out))


if __name__ == "__main__":
    main()
