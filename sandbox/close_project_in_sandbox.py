#!/usr/bin/env python3
"""サンドボックス内の単一プロジェクトを、git 履歴を回収したうえで削除する。

destroy_sandbox.py がディストロ(agent-sandbox)全体を破棄するのに対し、
こちらは /home/agent/projects/<名前> の1プロジェクトだけを対象にする。
ディストロ自体や他プロジェクトには一切触れない。

回収漏れを防ぐため、削除前に必ず sync_from_sandbox.py と同じ経路(git bundle
経由)で git 履歴を host 側 refs/remotes/sandbox/* へ取り込む。ただし
sync_from_sandbox.py 自身と同じ理由で、コミットされていない作業ツリーの
変更(git status --porcelain)は取り込めない。削除前に host 側リポジトリで
その旨を警告するので、必要なら削除を中断してディストロ内から手動で
回収すること。

使い方:
    python sandbox/close_project_in_sandbox.py [--name <名前>] [--distro agent-sandbox]
                                               [--yes] [--force]
    (--name 省略時はカレントディレクトリ名を使う。--yes は最終確認プロンプトを
     スキップする。--force は git 履歴の回収(sync)に失敗しても削除を続行する)
"""

import argparse
import sys
from pathlib import Path

from open_in_sandbox import DEFAULT_DISTRO, PROJECTS_DIR, OpenError, check_name, run_wsl
from sync_from_sandbox import run_git, sync


def warn_if_uncommitted():
    try:
        result = run_git(["status", "--porcelain"], capture=True)
    except OpenError:
        return
    if result.stdout.strip():
        print("\n警告: host 側の作業ツリーに未コミットの変更があります。")
        print("      sync はコミット済みの内容しか取り込めないため、")
        print("      この変更はディストロ内プロジェクトを削除すると失われます。")


def confirm(name: str) -> bool:
    try:
        typed = input(f"本当に削除しますか? 確認のためプロジェクト名 ({name}) を入力: ")
    except EOFError:
        return False
    return typed.strip() == name


def main():
    ap = argparse.ArgumentParser(
        description="サンドボックス内プロジェクトを git 履歴回収のうえ削除する"
                    "(ディストロ自体は破棄しない。破棄は destroy_sandbox.py)")
    ap.add_argument("--name", default=None, help="サンドボックス内でのプロジェクト名(既定: カレントディレクトリ名)")
    ap.add_argument("--distro", default=DEFAULT_DISTRO, help=f"ディストロ名(既定: {DEFAULT_DISTRO})")
    ap.add_argument("--yes", action="store_true", help="最終確認プロンプトをスキップする")
    ap.add_argument("--force", action="store_true", help="git 履歴の回収(sync)に失敗しても削除を続行する")
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

        linux_dest = f"{PROJECTS_DIR}/{name}"
        exists = run_wsl(["-d", args.distro, "--", "test", "-d", linux_dest], check=False, capture=True)
        if exists.returncode != 0:
            print(f"{args.distro}:{linux_dest} は既に存在しません(削除済み)。")
            return 0

        try:
            sync(name, args.distro)
        except OpenError as e:
            if not args.force:
                raise OpenError(
                    f"git 履歴の回収に失敗したため削除を中止しました: {e}\n"
                    "  回収不要と分かっている場合のみ --force で削除を続行してください。")
            print(f"警告: git 履歴の回収に失敗しましたが --force のため削除を続行します: {e}")

        warn_if_uncommitted()

        if not args.yes and not confirm(name):
            print("中断しました(何も変更していません)。")
            return 1

        run_wsl(["-d", args.distro, "--", "rm", "-rf", linux_dest])
        print(f"{args.distro}:{linux_dest} を削除しました。")
        print("再度使うには: python sandbox/open_in_sandbox.py <プロジェクトのパス>")
        return 0

    except OpenError as e:
        print(f"エラー: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
