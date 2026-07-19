#!/usr/bin/env python3
"""agent-sandbox ディストロをガード付きで破棄するスクリプト。

ディストロは全プロジェクト共有のため、素の `wsl --unregister` は確認なしで
/home/agent/projects 配下すべての未 push 作業と認証状態を一緒に消してしまう。
このスクリプトは破棄前に各プロジェクトの git 状態を検査し、失われる作業が
あれば一覧を出して拒否する(.sandbox-kit/README.md 参照)。

- 未コミット / 未 push / git 管理外のプロジェクトがあると拒否する
  (push で回収してから再実行が推奨。--export-first で全プロジェクトを
  ホストへ退避してから破棄、または --force で強行)
- 実行前にディストロ名の入力による最終確認を行う(--yes でスキップ)

使い方:
    python destroy_sandbox.py [--distro agent-sandbox] [--force] [--yes]
                              [--export-first <退避先ディレクトリ>]
"""

import argparse
import sys
from pathlib import Path

from open_in_sandbox import OpenError, export_project
from setup_sandbox import DEFAULT_DISTRO, SetupError, distro_exists, run_wsl, wsl_available

# ディストロ内で全プロジェクトの git 状態を1行ずつ「名前|状態」で出力する。
# 状態: clean / nogit / uncommitted / unpushed:<件数>(複合はスペース区切り)
CHECK_SCRIPT = """\
cd /home/agent/projects 2>/dev/null || exit 0
for d in */ ; do
    d=${d%/}
    [ -d "$d" ] || continue
    if [ ! -d "$d/.git" ]; then
        echo "$d|nogit"
        continue
    fi
    s=""
    [ -n "$(git -C "$d" status --porcelain 2>/dev/null)" ] && s="uncommitted"
    n=$(git -C "$d" log --branches --not --remotes --oneline 2>/dev/null | wc -l)
    [ "$n" -gt 0 ] && s="$s unpushed:$n"
    s=${s# }
    echo "$d|${s:-clean}"
done
"""

STATUS_LABELS = {
    "nogit": "git 管理外(回収手段なし)",
    "uncommitted": "未コミットの変更あり",
}


def describe(status: str) -> str:
    parts = []
    for token in status.split():
        if token.startswith("unpushed:"):
            parts.append(f"未 push のコミット {token.split(':', 1)[1]} 件")
        else:
            parts.append(STATUS_LABELS.get(token, token))
    return " / ".join(parts)


def project_states(distro: str):
    result = run_wsl(["-d", distro, "--", "bash", "-s"],
                     input_text=CHECK_SCRIPT, capture=True)
    states = []
    for line in result.stdout.splitlines():
        if "|" in line:
            name, status = line.split("|", 1)
            states.append((name.strip(), status.strip()))
    return states


def confirm(distro: str) -> bool:
    try:
        typed = input(f"本当に破棄しますか? 確認のためディストロ名 ({distro}) を入力: ")
    except EOFError:
        return False
    return typed.strip() == distro


def main():
    ap = argparse.ArgumentParser(description="agent-sandbox ディストロのガード付き破棄")
    ap.add_argument("--distro", default=DEFAULT_DISTRO, help=f"ディストロ名(既定: {DEFAULT_DISTRO})")
    ap.add_argument("--export-first", default=None, metavar="DIR",
                    help="破棄前に全プロジェクトを指定ディレクトリへ退避する")
    ap.add_argument("--force", action="store_true",
                    help="未 push 作業のあるプロジェクトがあっても破棄する")
    ap.add_argument("--yes", action="store_true", help="最終確認プロンプトをスキップする")
    args = ap.parse_args()

    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

    try:
        if not wsl_available():
            raise SetupError("WSL2 が見つかりません。")
        if not distro_exists(args.distro):
            print(f"ディストロ {args.distro} は存在しません(破棄済み)。")
            return 0

        states = project_states(args.distro)
        at_risk = [(n, s) for n, s in states if s != "clean"]
        if states:
            print(f"ディストロ内のプロジェクト({len(states)} 件):")
            for name, status in states:
                mark = "OK" if status == "clean" else "!!"
                print(f"  [{mark}] {name}: {'push 済み' if status == 'clean' else describe(status)}")
        else:
            print("ディストロ内にプロジェクトはありません。")

        if args.export_first:
            dest = Path(args.export_first).resolve()
            print(f"全プロジェクトを退避中: → {dest}")
            for name, _ in states:
                export_project(name, dest, args.distro)

        if at_risk and not args.force and not args.export_first:
            sys.stdout.flush()  # 一覧(stdout)を拒否メッセージ(stderr)より先に出す
            print("\nエラー: 回収されていない作業が残っているため破棄を中止しました。", file=sys.stderr)
            print("  - 推奨: 各プロジェクト内から git push で回収してから再実行", file=sys.stderr)
            print("  - 退避してから破棄: --export-first <退避先ディレクトリ>", file=sys.stderr)
            print("  - 承知のうえで強行: --force", file=sys.stderr)
            return 1

        if not args.yes and not confirm(args.distro):
            print("中断しました(何も変更していません)。")
            return 1

        run_wsl(["--terminate", args.distro], check=False)
        run_wsl(["--unregister", args.distro])
        print(f"ディストロ {args.distro} を破棄しました(認証情報・環境も消えています)。")
        print("再作成するには: python .sandbox-kit/setup_sandbox.py(認証は再度必要)")
        return 0

    except (SetupError, OpenError) as e:
        print(f"エラー: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
