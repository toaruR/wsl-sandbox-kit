#!/usr/bin/env python3
"""agent-sandbox 誤オープン検知フック(Antigravity PreInvocation / PreToolUse 用)。

Claude Code 用アダプタ(claude_sandbox_guard.py)の Antigravity 版。検知ロジック本体は
同じディレクトリの _sandbox_guard_core.py にある。

Antigravity のフックにはセッション開始・プロンプト送信のイベントが無く、
プロンプト自体はブロックできない(Antigravity 公式ドキュメント hooks による)。
代わりに次の2つで隔離の抜けを塞ぐ:

- PreInvocation(モデル呼び出し前): injectSteps の ephemeralMessage で警告を差し込む
- PreToolUse(ツール実行前): {"decision": "deny", "reason": ...} で全ツール実行を止める

stdin は camelCase の JSON で、作業ディレクトリは workspacePaths(配列)で渡される。
イベント種別は stdin に含まれないため、.agents/hooks.json のフック登録コマンドに
付与する --event 引数で判定する。

install.py により、インストール先の .agents/hooks/ に配置され、
同じプロジェクトの .agents/hooks.json から呼ばれる。
"""

import argparse
import json
import os
import sys

from _sandbox_guard_core import find_sandbox_path, build_warning_message


def main():
    if os.name != "nt":
        return  # ディストロ内(正しい使い方)ではガード不要

    parser = argparse.ArgumentParser()
    parser.add_argument("--event", choices=["PreInvocation", "PreToolUse"], default=None)
    args, _ = parser.parse_known_args()

    try:
        payload = json.load(sys.stdin)
    except Exception:
        payload = {}
    event = args.event or ("PreToolUse" if "toolCall" in payload else "PreInvocation")
    roots = payload.get("workspacePaths") or [os.getcwd()]
    hit = find_sandbox_path(roots)
    if hit is None:
        return

    msg = build_warning_message(hit)
    if event == "PreToolUse":
        out = {"decision": "deny", "reason": msg}
    else:
        out = {"injectSteps": [{"ephemeralMessage": msg}]}
    print(json.dumps(out))


if __name__ == "__main__":
    main()
