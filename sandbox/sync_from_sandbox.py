#!/usr/bin/env python3
"""サンドボックス内プロジェクトの git 履歴を、host 側リポジトリの
refs/remotes/sandbox/* へ取り込む。

サンドボックスから host へ直接 push させるには Windows 側に新しい待受
サービス(OpenSSH Server 等)を立てる必要があり、「host ドライブは見せない・
sudo は与えない」という分離方針に反して host への書き込み経路を新設する
ことになる。そのため host が主導して、`open_in_sandbox.py --export` と同じ
wsl.exe の stdin/stdout チャネル経由で git bundle を取得し、host 側で
`git fetch` する方式にしている。

host 側の作業ツリー・現在のブランチには一切触れない
(常に refs/remotes/sandbox/* だけを更新する)ため、何度でも安全に
再実行できる。

使い方:
    python sandbox/sync_from_sandbox.py [--name <名前>] [--distro agent-sandbox]
    (--name 省略時はカレントディレクトリ名を使う。取り込み先が
     refs/remotes/sandbox/* に限られるため、間違った名前を指定しても
     実害はない)

取り込み後:
    git log sandbox/<branch>
    git diff HEAD sandbox/<branch>
    git merge sandbox/<branch>
"""

import argparse
import subprocess
import sys
import tempfile
from pathlib import Path

from open_in_sandbox import DEFAULT_DISTRO, PROJECTS_DIR, OpenError, check_name, run_wsl


def run_git(args, cwd=None, check=True, capture=False):
    """git を呼ぶ。text=True(既定エンコーディング)だと日本語コミットメッセージ等の
    UTF-8 出力を Windows のロケール(cp932)で decode しようとして落ちるため、
    run_wsl と同じくバイトで受けてから明示的に UTF-8 decode する。
    """
    result = subprocess.run(["git", *args], cwd=cwd, capture_output=capture)
    if capture:
        result.stdout = result.stdout.decode("utf-8", errors="replace")
        result.stderr = result.stderr.decode("utf-8", errors="replace")
    if check and result.returncode != 0:
        detail = f": {result.stderr.strip()}" if capture else ""
        raise OpenError(f"git {' '.join(args)} が失敗しました(exit {result.returncode}){detail}")
    return result


def fetch_bundle(name: str, distro: str, tmp_path: str):
    linux_src = f"{PROJECTS_DIR}/{name}"
    exists = run_wsl(["-d", distro, "--", "test", "-d", linux_src], check=False, capture=True)
    if exists.returncode != 0:
        raise OpenError(f"{distro}:{linux_src} がありません。")
    is_repo = run_wsl(["-d", distro, "--", "test", "-d", f"{linux_src}/.git"], check=False, capture=True)
    if is_repo.returncode != 0:
        raise OpenError(f"{distro}:{linux_src} は git リポジトリではありません。")

    with open(tmp_path, "wb") as tmp_fh:
        result = run_wsl(
            ["-d", distro, "--", "git", "-C", linux_src, "bundle", "create", "-", "--branches"],
            check=False, stdout=tmp_fh)
    if result.returncode != 0:
        raise OpenError(
            f"{distro}:{linux_src} での git bundle 作成に失敗しました(exit {result.returncode})。"
            "コミットが1つも無い可能性があります。")


def sync(name: str, distro: str):
    run_git(["rev-parse", "--is-inside-work-tree"], capture=True)

    tmp = tempfile.NamedTemporaryFile(suffix=".bundle", delete=False)
    tmp.close()
    try:
        print(f"取得中: {distro}:{PROJECTS_DIR}/{name} → bundle")
        fetch_bundle(name, distro, tmp.name)
        print("反映中: refs/remotes/sandbox/*")
        run_git(["fetch", tmp.name, "+refs/heads/*:refs/remotes/sandbox/*", "--prune"])
    finally:
        Path(tmp.name).unlink(missing_ok=True)

    result = run_git(
        ["for-each-ref", "--format=%(refname:short) %(objectname:short) %(subject)", "refs/remotes/sandbox"],
        capture=True)
    branches = result.stdout.strip()
    if not branches:
        print("反映しましたが、refs/remotes/sandbox/* にブランチがありません。")
        return
    print("\n取り込んだブランチ:")
    print(branches)
    print("\n次の一手:")
    print("  git log sandbox/<branch>")
    print("  git diff HEAD sandbox/<branch>")
    print("  git merge sandbox/<branch>")


def main():
    ap = argparse.ArgumentParser(
        description="サンドボックス内プロジェクトの git 履歴を refs/remotes/sandbox/* へ取り込む"
                    "(host の作業ツリー・現在のブランチには触れない)")
    ap.add_argument("--name", default=None, help="サンドボックス内でのプロジェクト名(既定: カレントディレクトリ名)")
    ap.add_argument("--distro", default=DEFAULT_DISTRO, help=f"ディストロ名(既定: {DEFAULT_DISTRO})")
    args = ap.parse_args()

    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

    try:
        name = args.name or Path.cwd().name
        check_name(name)

        probe = run_wsl(["-d", args.distro, "--", "true"], check=False, capture=True)
        if probe.returncode != 0:
            raise OpenError(
                f"ディストロ {args.distro} にアクセスできません。"
                "先に `python sandbox/setup_sandbox.py` を実行してください。")

        sync(name, args.distro)
        return 0

    except OpenError as e:
        print(f"エラー: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
