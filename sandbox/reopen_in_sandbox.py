#!/usr/bin/env python3
"""搬入済みプロジェクトへ VS Code を繋ぎ直すだけの軽量ラッパー。

`code --remote ssh-remote+<distro> /home/agent/projects/<名前>` を実行するだけで、
open_in_sandbox.py と違って再搬入(既存コピーの置き換え)は一切行わない。
VS Code を閉じてしまった後に繋ぎ直したいだけのときに使う。

使い方:
    python .sandbox-kit/reopen_in_sandbox.py [--name <名前>] [--distro agent-sandbox]
    (--name 省略時はカレントディレクトリ名を使う)
"""

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

from open_in_sandbox import DEFAULT_DISTRO, PROJECTS_DIR, OpenError, check_name, run_wsl


def reopen(name: str, distro: str):
    linux_dest = f"{PROJECTS_DIR}/{name}"
    exists = run_wsl(["-d", distro, "--", "test", "-d", linux_dest], check=False, capture=True)
    if exists.returncode != 0:
        raise OpenError(
            f"{distro}:{linux_dest} がありません。open_in_sandbox.py で先に搬入してください。")

    code = shutil.which("code")
    if not code:
        raise OpenError("code コマンドが見つかりません。VS Code の PATH 設定を確認してください。")
    subprocess.run([code, "--remote", f"ssh-remote+{distro}", linux_dest], check=True)
    print(f"VS Code を起動しました(ssh-remote+{distro}:{linux_dest})")


def main():
    ap = argparse.ArgumentParser(
        description="搬入済みプロジェクトへ VS Code を繋ぎ直す(再搬入はしない)")
    ap.add_argument("--name", default=None, help="サンドボックス内でのプロジェクト名(既定: カレントディレクトリ名)")
    ap.add_argument("--distro", default=DEFAULT_DISTRO, help=f"ディストロ名(既定: {DEFAULT_DISTRO})")
    args = ap.parse_args()

    try:
        name = args.name or Path.cwd().name
        check_name(name)
        reopen(name, args.distro)
        return 0
    except OpenError as e:
        print(f"エラー: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
