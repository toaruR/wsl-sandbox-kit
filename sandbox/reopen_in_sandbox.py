#!/usr/bin/env python3
"""搬入済みプロジェクトへ IDE を繋ぎ直すだけの軽量ラッパー。

`<IDE> --remote ssh-remote+<distro> /home/agent/projects/<名前>` を実行するだけで、
open_in_sandbox.py と違って再搬入(既存コピーの置き換え)は一切行わない。
IDE を閉じてしまった後に繋ぎ直したいだけのときに使う。

使い方:
    python .sandbox-kit/reopen_in_sandbox.py [--name <名前>] [--distro agent-sandbox]
                                             [--ide code|cursor|antigravity]
    (--name 省略時はカレントディレクトリ名を使う。
     --ide 省略時は環境変数 AGENT_SANDBOX_IDE、未設定なら code)
"""

import argparse
import sys
from pathlib import Path

from open_in_sandbox import (DEFAULT_DISTRO, DEFAULT_IDE, PROJECTS_DIR, OpenError,
                             check_name, launch_ide, run_wsl)


def reopen(name: str, distro: str, ide: str):
    linux_dest = f"{PROJECTS_DIR}/{name}"
    exists = run_wsl(["-d", distro, "--", "test", "-d", linux_dest], check=False, capture=True)
    if exists.returncode != 0:
        raise OpenError(
            f"{distro}:{linux_dest} がありません。open_in_sandbox.py で先に搬入してください。")
    launch_ide(ide, distro, linux_dest)


def main():
    ap = argparse.ArgumentParser(
        description="搬入済みプロジェクトへ IDE を繋ぎ直す(再搬入はしない)")
    ap.add_argument("--name", default=None, help="サンドボックス内でのプロジェクト名(既定: カレントディレクトリ名)")
    ap.add_argument("--distro", default=DEFAULT_DISTRO, help=f"ディストロ名(既定: {DEFAULT_DISTRO})")
    ap.add_argument("--ide", default=DEFAULT_IDE,
                    help="起動する IDE: code / cursor / antigravity(既定: 環境変数 AGENT_SANDBOX_IDE、未設定なら code)")
    args = ap.parse_args()

    try:
        name = args.name or Path.cwd().name
        check_name(name)
        reopen(name, args.distro, args.ide)
        return 0
    except OpenError as e:
        print(f"エラー: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
