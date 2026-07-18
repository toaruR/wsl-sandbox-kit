#!/usr/bin/env python3
"""プロジェクトをサンドボックス(分離 WSL2 ディストロ)へ搬入し、VS Code で開く。

- プロジェクトを tar 化し、wsl.exe の stdin 経由でディストロ内
  /home/agent/projects/<名前> に展開する
  (\\\\wsl.localhost 共有経由の UNC コピーでも届くが、除外フィルタと
  所有者・パーミッションの正しさのため tar ストリームを使い続ける)
- node_modules / .venv / __pycache__ はコピーしない(ディストロ内で入れ直す)
- コピー後、ホスト側から `code --remote ssh-remote+<distro>` で VS Code を起動する
  (WSL リモート拡張は automount 前提で分離ディストロでは動かないため Remote-SSH)

成果物の回収は git push、または --export による逆方向コピーで行う
(詳細: sandbox/README.md)。

使い方:
    python open_in_sandbox.py [プロジェクトのパス] [--name <名前>]
                              [--distro agent-sandbox] [--force] [--no-code]
                              (プロジェクトのパスを省略するとカレントディレクトリを使う)
    python open_in_sandbox.py --export <名前> <取り出し先ディレクトリ>
"""

import argparse
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

DEFAULT_DISTRO = "agent-sandbox"
COPY_EXCLUDE = {"node_modules", ".venv", "__pycache__"}
PROJECTS_DIR = "/home/agent/projects"


class OpenError(Exception):
    pass


def run_wsl(args, check=True, capture=False, stdin=None, stdout=None):
    """wsl.exe を呼ぶ。WSL_UTF8=1 を付けないと出力が UTF-16LE になる罠に注意。

    stdin/stdout はバイナリのファイルオブジェクトを渡せる(tar ストリーム用)。
    """
    env = os.environ.copy()
    env["WSL_UTF8"] = "1"
    result = subprocess.run(
        ["wsl.exe", *args], env=env, capture_output=capture,
        stdin=stdin, stdout=stdout)
    if capture:
        result.stdout = result.stdout.decode("utf-8", errors="replace")
        result.stderr = result.stderr.decode("utf-8", errors="replace")
    if check and result.returncode != 0:
        raise OpenError(f"wsl {' '.join(args)} が失敗しました(exit {result.returncode})")
    return result


def check_name(name: str):
    if not re.fullmatch(r"[A-Za-z0-9._-]+", name):
        raise OpenError(f"名前に使えない文字が含まれています: {name}(--name で指定してください)")


def make_tar(src: Path, tmp_path: str):
    """src の中身を除外パターン適用でアーカイブする(トップレベルは含めない)。"""

    def tar_filter(info: tarfile.TarInfo):
        parts = Path(info.name).parts
        if any(p in COPY_EXCLUDE for p in parts):
            return None
        return info

    with tarfile.open(tmp_path, "w") as tar:
        for entry in sorted(src.iterdir()):
            tar.add(entry, arcname=entry.name, filter=tar_filter)


def import_project(src: Path, name: str, distro: str, force: bool):
    linux_dest = f"{PROJECTS_DIR}/{name}"
    exists = run_wsl(["-d", distro, "--", "test", "-e", linux_dest],
                     check=False, capture=True)
    if exists.returncode == 0:
        if not force:
            print(f"警告: 置き換えると {linux_dest} 内の未 push 作業はすべて失われます。\n"
                  "      キット更新が目的なら update_kit_in_sandbox.py を使ってください。")
            answer = input(f"{linux_dest} は既に存在します。中身を置き換えますか? [y/N]: ")
            if answer.strip().lower() != "y":
                print("中断しました(追記コピーはしません)。")
                return None
        run_wsl(["-d", distro, "--", "rm", "-rf", linux_dest])
        print(f"既存の {linux_dest} を削除しました")

    print(f"コピー中: {src} → {distro}:{linux_dest}")
    tmp = tempfile.NamedTemporaryFile(suffix=".tar", delete=False)
    tmp.close()
    try:
        make_tar(src, tmp.name)
        with open(tmp.name, "rb") as fh:
            run_wsl(["-d", distro, "--", "bash", "-c",
                     f"mkdir -p {linux_dest} && tar -xf - -C {linux_dest}"],
                    stdin=fh)
    finally:
        os.unlink(tmp.name)
    print("コピー完了(node_modules / .venv / __pycache__ は除外。ディストロ内で入れ直してください)")
    return linux_dest


def export_project(name: str, dest_dir: Path, distro: str):
    """ディストロ内のプロジェクトを tar ストリームでホストへ取り出す。"""
    linux_src = f"{PROJECTS_DIR}/{name}"
    out_dir = dest_dir / name
    if out_dir.exists():
        raise OpenError(f"取り出し先が既に存在します: {out_dir}(先に退避・削除してください)")
    tmp = tempfile.NamedTemporaryFile(suffix=".tar", delete=False)
    try:
        run_wsl(["-d", distro, "--", "tar", "-cf", "-", "-C", linux_src, "."],
                stdout=tmp)
        tmp.close()
        out_dir.mkdir(parents=True)
        with tarfile.open(tmp.name) as tar:
            tar.extractall(out_dir, filter="data")
    finally:
        tmp.close()
        os.unlink(tmp.name)
    print(f"取り出し完了: {distro}:{linux_src} → {out_dir}")


def main():
    ap = argparse.ArgumentParser(description="プロジェクトをサンドボックスへ搬入して VS Code で開く")
    ap.add_argument("project", nargs="?", default=None,
                    help="搬入するプロジェクトのパス(--export 時はディストロ内の名前)。"
                         "省略時はカレントディレクトリ")
    ap.add_argument("export_dest", nargs="?", default=None,
                    help="--export 時の取り出し先ディレクトリ")
    ap.add_argument("--name", default=None, help="ディストロ内での名前(既定: ディレクトリ名)")
    ap.add_argument("--distro", default=DEFAULT_DISTRO, help=f"ディストロ名(既定: {DEFAULT_DISTRO})")
    ap.add_argument("--force", action="store_true", help="搬入先が既にあっても確認なしで置き換える")
    ap.add_argument("--no-code", action="store_true", help="コピーのみ行い VS Code を起動しない")
    ap.add_argument("--export", action="store_true",
                    help="逆方向: ディストロ内のプロジェクトをホストへ取り出す")
    args = ap.parse_args()

    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

    try:
        # ディストロの存在確認を兼ねて projects ディレクトリを用意(ディストロも起動する)
        probe = run_wsl(["-d", args.distro, "--", "mkdir", "-p", PROJECTS_DIR],
                        check=False, capture=True)
        if probe.returncode != 0:
            raise OpenError(
                f"ディストロ {args.distro} にアクセスできません。"
                "先に `python sandbox/setup_sandbox.py` を実行してください。")

        if args.export:
            if not args.project or not args.export_dest:
                raise OpenError("--export には名前と取り出し先ディレクトリの両方を指定してください。")
            check_name(args.project)
            export_project(args.project, Path(args.export_dest).resolve(), args.distro)
            return 0

        src = Path(args.project or ".").resolve()
        if not src.is_dir():
            raise OpenError(f"プロジェクトディレクトリがありません: {src}")
        name = args.name or src.name
        check_name(name)

        linux_dest = import_project(src, name, args.distro, args.force)
        if linux_dest is None:
            return 1

        if args.no_code:
            print(f"VS Code で開くには: code --remote ssh-remote+{args.distro} {linux_dest}")
            return 0

        # WSL リモート(wsl+)は automount 前提で分離ディストロでは動かないため、
        # setup_sandbox.py が用意した Remote-SSH(~/.ssh/config の Host エントリ)で開く
        code = shutil.which("code")
        if not code:
            raise OpenError("code コマンドが見つかりません。VS Code の PATH 設定を確認してください。")
        subprocess.run([code, "--remote", f"ssh-remote+{args.distro}", linux_dest], check=True)
        print(f"VS Code を起動しました(ssh-remote+{args.distro}:{linux_dest})")
        return 0

    except OpenError as e:
        print(f"エラー: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
