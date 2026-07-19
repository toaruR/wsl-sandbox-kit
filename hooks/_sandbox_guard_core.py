"""agent-sandbox 誤オープン検知の共有ロジック。

Claude Code / Codex CLI 両アダプタ(sandbox_guard.py)から import される
ツール非依存のコア。検知ロジックと警告文言のみを持ち、各ツール固有の
stdin/stdout 契約はアダプタ側に置く。

知見記録キットの一部として .claude/hooks/ と .codex/hooks/ の両方に
同一内容がコピー配置される(install_kit.py が管理)。
"""

import ctypes
import os
import re

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


def build_warning_message(cwd: str) -> str:
    return (f"警告: agent-sandbox 内のフォルダ ({cwd}) をホスト側で開いた状態で"
            "エージェントを起動しています。この状態ではエージェントがホスト Windows の"
            "権限で動き、サンドボックスの隔離が効きません。VS Code の Remote-SSH "
            "(agent-sandbox) で開き直してください (.sandbox-kit/README.md 参照)。")
