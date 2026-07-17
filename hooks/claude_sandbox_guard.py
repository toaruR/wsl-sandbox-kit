#!/usr/bin/env python3
"""agent-sandbox 誤オープン検知フック(Claude Code SessionStart / UserPromptSubmit 用)。

サンドボックス(agent-sandbox WSL ディストロ)内のフォルダを、ホスト Windows 側の
VS Code / Claude Code で直接開いてエージェントを使うと、エージェントがホスト権限で
動いてしまい隔離が無意味になる。このフックはその状態を検知して警告し、
UserPromptSubmit ではプロンプト送信をブロックする。

- Windows 以外(WSL ディストロ内・サンドボックス内)では常に何もしない。
  Remote-SSH で正しく開いた場合はディストロ内の Claude Code が動くため誤検知しない。
- 検知方法(いずれか):
  1. \\wsl.localhost\agent-sandbox / \\wsl$\agent-sandbox パス
  2. SSHFS-Win の UNC(\\sshfs\agent@localhost!2222 等)またはそのドライブ割り当て
  3. マーカーファイル .agent-sandbox を祖先ディレクトリにさかのぼって探索
     (sandbox/provision.sh がディストロ内に root 所有 + immutable で配置する)

知見記録キットの一部として、インストール先の .claude/hooks/ に配置され、
同じプロジェクトの .claude/settings.json から呼ばれる(install_kit.py が登録)。
"""

import ctypes
import json
import os
import re
import sys

MARKER = ".agent-sandbox"


def mapped_drive_target(drive_letter: str) -> str:
    """ネットワークドライブの割り当て先 UNC(\\\\sshfs\\... 等)を返す。未割り当てなら空文字。"""
    try:
        buf = ctypes.create_unicode_buffer(1024)
        size = ctypes.c_ulong(len(buf))
        if ctypes.windll.mpr.WNetGetConnectionW(drive_letter + ":", buf, ctypes.byref(size)) == 0:
            return buf.value
    except Exception:
        pass
    return ""


def is_sandbox_path(path: str) -> bool:
    if not path:
        return False
    if re.match(r"\\\\wsl(\.localhost|\$)\\agent-sandbox(\\|$)", path, re.IGNORECASE):
        return True
    if re.match(r"\\\\sshfs", path, re.IGNORECASE) and \
            re.search(r"agent-sandbox|agent@localhost", path, re.IGNORECASE):
        return True
    m = re.match(r"([A-Za-z]):", path)
    if m:
        target = mapped_drive_target(m.group(1))
        if re.search(r"sshfs|agent-sandbox|agent@localhost", target, re.IGNORECASE):
            return True
    d = os.path.abspath(path)
    while True:
        if os.path.exists(os.path.join(d, MARKER)):
            return True
        parent = os.path.dirname(d)
        if parent == d:
            return False
        d = parent


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

    msg = (f"警告: agent-sandbox 内のフォルダ ({cwd}) をホスト側で開いた状態で"
           "エージェントを起動しています。この状態ではエージェントがホスト Windows の"
           "権限で動き、サンドボックスの隔離が効きません。VS Code の Remote-SSH "
           "(agent-sandbox) で開き直してください (sandbox/README.md 参照)。")
    if payload.get("hook_event_name") == "UserPromptSubmit":
        out = {"decision": "block", "reason": msg, "systemMessage": msg}
    else:
        out = {"systemMessage": msg}
    # ensure_ascii 既定(True)のまま出力する: Windows コンソールの cp932 でも壊れない
    print(json.dumps(out))


if __name__ == "__main__":
    main()
