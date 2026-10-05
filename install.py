#!/usr/bin/env python3
"""agent-sandbox-kit をプロジェクトへインストール・更新する。

配置するもの(すべてキット所有。差分があれば常にキット版へ揃える):

- .sandbox-kit/            ← sandbox/ 一式(ホスト側で実行するサンドボックス操作スクリプト)
- Skill                    ← クライアントごとの実ディレクトリを個別ソースとして配置
    claude                     .claude/skills/sandbox-*/  ← .claude/skills/
    codex/antigravity/cursor   .agents/skills/sandbox-*/  ← .agents/skills/
- 誤オープン検知フック       ← hooks/_sandbox_guard_core.py + hooks/<client>_sandbox_guard.py
    claude       .claude/hooks/   登録先 .claude/settings.json
    codex        .codex/hooks/    登録先 .codex/hooks.json
    cursor       .cursor/hooks/   登録先 .cursor/hooks.json
    antigravity  .agents/hooks/   登録先 .agents/hooks.json

フック登録は既存の設定ファイルへ冪等にマージする(sandbox_guard.py を起動する
エントリだけを追加・更新し、他のフックには触れない)。tools/destroy_sandbox.py は
ディストロ全体を破棄する運用専用ツールのため配布しない。

使い方:
    python install.py <target> [--clients claude,codex,antigravity,cursor] [--dry-run]
"""

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

KIT_ROOT = Path(__file__).resolve().parent

CLIENTS = ("claude", "codex", "antigravity", "cursor")

# クライアント → Skill のソース(キット内)と配置先(target 内)。
# codex / antigravity / cursor はいずれも .agents/skills/ を読むため同じ配置先を共有する。
SKILL_DIRS = {
    "claude": (".claude/skills", ".claude/skills"),
    "codex": (".agents/skills", ".agents/skills"),
    "antigravity": (".agents/skills", ".agents/skills"),
    "cursor": (".agents/skills", ".agents/skills"),
}

# クライアント → フックスクリプトの配置先ディレクトリ
HOOK_DIRS = {
    "claude": ".claude/hooks",
    "codex": ".codex/hooks",
    "cursor": ".cursor/hooks",
    "antigravity": ".agents/hooks",
}

GUARD_CORE_NAME = "_sandbox_guard_core.py"
GUARD_NAME = "sandbox_guard.py"
HOOK_TIMEOUT = 10

# Antigravity の hooks.json はトップレベルがフック名 → イベント設定の対応になっている
ANTIGRAVITY_HOOK_NAME = "agent-sandbox-guard"


class InstallError(Exception):
    pass


@dataclass
class Report:
    placed: list = field(default_factory=list)
    updated: list = field(default_factory=list)
    skipped: list = field(default_factory=list)
    warnings: list = field(default_factory=list)


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def write_text(path: Path, text: str, dry_run: bool):
    if dry_run:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)


def normalize(text: str) -> str:
    return text.replace("\r\n", "\n")


def sync_kit_owned_file(src: Path, dest: Path, label: str, dry_run: bool, report: Report):
    """キット所有ファイルを配置する。既存と差分があれば常にキット版で上書きする。"""
    text = normalize(read_text(src))
    if not dest.exists():
        write_text(dest, text, dry_run)
        report.placed.append(label)
    elif normalize(read_text(dest)) != text:
        write_text(dest, text, dry_run)
        report.updated.append(label)


# ------------------------------------------------------------------ files

def install_sandbox_files(target: Path, dry_run: bool, report: Report):
    src_dir = KIT_ROOT / "sandbox"
    files = sorted(p for p in src_dir.iterdir() if p.is_file())
    if not files:
        raise InstallError(f"{src_dir} が空です。")
    for src in files:
        sync_kit_owned_file(src, target / ".sandbox-kit" / src.name,
                            f".sandbox-kit/{src.name}", dry_run, report)


def install_skills(target: Path, clients, dry_run: bool, report: Report):
    pairs = sorted({SKILL_DIRS[c] for c in clients})
    for src_rel, dest_rel in pairs:
        src_root = KIT_ROOT / src_rel
        for src in sorted(src_root.rglob("*")):
            if not src.is_file():
                continue
            rel = src.relative_to(src_root).as_posix()
            sync_kit_owned_file(src, target / dest_rel / rel, f"{dest_rel}/{rel}", dry_run, report)


def install_hook_files(target: Path, client: str, dry_run: bool, report: Report):
    hook_dir = HOOK_DIRS[client]
    sources = {
        GUARD_CORE_NAME: KIT_ROOT / "hooks" / GUARD_CORE_NAME,
        GUARD_NAME: KIT_ROOT / "hooks" / f"{client}_{GUARD_NAME}",
    }
    for fname, src in sources.items():
        sync_kit_owned_file(src, target / hook_dir / fname, f"{hook_dir}/{fname}", dry_run, report)


# ------------------------------------------------------------ registration

def guard_command(script: str, event: str = None, quiet: bool = False) -> str:
    """python が無い環境(Ubuntu 等)と python3 が無い環境(Windows ホスト)の両対応。

    Windows ホストの利用者が多いため python をメインにし、python3 をフォールバックにする。
    quiet は1つ目の失敗時の stderr を捨てる(sh 系で実行されると分かっている Claude Code 用。
    他のクライアントは Windows での実行シェルが未確認のため付けない)。
    """
    suffix = f" --event {event}" if event else ""
    redirect = " 2>/dev/null" if quiet else ""
    return f'python "{script}"{suffix}{redirect} || python3 "{script}"{suffix}'


def abs_hook_path(target: Path, client: str) -> str:
    return (target / HOOK_DIRS[client] / GUARD_NAME).resolve().as_posix()


def is_guard_handler(handler) -> bool:
    return isinstance(handler, dict) and GUARD_NAME in (handler.get("command") or "")


def load_json(path: Path, report: Report):
    """設定 JSON を読む。読めなければ警告を積んで None を返す(無ければ空 dict)。"""
    if not path.exists():
        return {}
    try:
        data = json.loads(read_text(path))
    except ValueError:
        report.warnings.append(f"{path.name} が JSON として読めないためフック登録をスキップしました: {path}")
        return None
    if not isinstance(data, dict):
        report.warnings.append(f"{path.name} がオブジェクトでないためフック登録をスキップしました: {path}")
        return None
    return data


def upsert_grouped(entries: list, handler: dict, matcher=None) -> str:
    """Claude Code / Codex 形式(matcher グループ → hooks 配列)へ guard ハンドラを登録する。

    戻り値: "added" / "updated" / "unchanged"
    """
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        for h in entry.get("hooks", []):
            if is_guard_handler(h):
                if h == handler:
                    return "unchanged"
                h.clear()
                h.update(handler)
                return "updated"
    group = {"hooks": [handler]}
    if matcher is not None:
        group = {"matcher": matcher, **group}
    entries.append(group)
    return "added"


def upsert_flat(entries: list, handler: dict) -> str:
    """Cursor / Antigravity PreInvocation 形式(ハンドラを直接並べる)へ登録する。"""
    for h in entries:
        if is_guard_handler(h):
            if h == handler:
                return "unchanged"
            h.clear()
            h.update(handler)
            return "updated"
    entries.append(handler)
    return "added"


def save_registration(path: Path, label: str, data: dict, results: dict, dry_run: bool, report: Report):
    added = [e for e, r in results.items() if r == "added"]
    updated = [e for e, r in results.items() if r == "updated"]
    if not added and not updated:
        report.skipped.append(f"{label}(sandbox_guard フックは最新の内容で登録済み)")
        return
    write_text(path, json.dumps(data, ensure_ascii=False, indent=2) + "\n", dry_run)
    if added:
        report.placed.append(f"{label}: sandbox_guard フック登録 ({' / '.join(added)})")
    if updated:
        report.updated.append(f"{label}: sandbox_guard フックのコマンドを更新 ({' / '.join(updated)})")


def register_claude(target: Path, dry_run: bool, report: Report):
    path = target / ".claude" / "settings.json"
    data = load_json(path, report)
    if data is None:
        return
    hooks = data.setdefault("hooks", {})
    # $CLAUDE_PROJECT_DIR 経由なのでマシン依存の絶対パスを書かずに済む
    command = guard_command("$CLAUDE_PROJECT_DIR/.claude/hooks/sandbox_guard.py", quiet=True)
    handler = {"type": "command", "command": command, "timeout": HOOK_TIMEOUT}
    results = {e: upsert_grouped(hooks.setdefault(e, []), dict(handler))
               for e in ("SessionStart", "UserPromptSubmit")}
    save_registration(path, ".claude/settings.json", data, results, dry_run, report)


def register_codex(target: Path, dry_run: bool, report: Report):
    """Codex は実行時のカレントディレクトリ・プロジェクトディレクトリ変数が未確認のため絶対パスで登録する。"""
    path = target / ".codex" / "hooks.json"
    data = load_json(path, report)
    if data is None:
        return
    hooks = data.setdefault("hooks", {})
    script = abs_hook_path(target, "codex")
    results = {}
    for event in ("SessionStart", "UserPromptSubmit"):
        handler = {"type": "command", "command": guard_command(script, event), "timeout": HOOK_TIMEOUT}
        results[event] = upsert_grouped(hooks.setdefault(event, []), handler)
    save_registration(path, ".codex/hooks.json", data, results, dry_run, report)


def register_cursor(target: Path, dry_run: bool, report: Report):
    """Cursor のプロジェクトフックはプロジェクトルートから起動されるため相対パスで登録する。"""
    path = target / ".cursor" / "hooks.json"
    data = load_json(path, report)
    if data is None:
        return
    data.setdefault("version", 1)
    hooks = data.setdefault("hooks", {})
    command = guard_command(f"{HOOK_DIRS['cursor']}/{GUARD_NAME}")
    handler = {"command": command, "timeout": HOOK_TIMEOUT}
    results = {e: upsert_flat(hooks.setdefault(e, []), dict(handler))
               for e in ("sessionStart", "beforeSubmitPrompt")}
    save_registration(path, ".cursor/hooks.json", data, results, dry_run, report)


def register_antigravity(target: Path, dry_run: bool, report: Report):
    """Antigravity は実行時のカレントディレクトリが未確認のため絶対パスで登録する。"""
    path = target / ".agents" / "hooks.json"
    data = load_json(path, report)
    if data is None:
        return
    entry = data.setdefault(ANTIGRAVITY_HOOK_NAME, {})
    script = abs_hook_path(target, "antigravity")

    def handler(event):
        return {"type": "command", "command": guard_command(script, event), "timeout": HOOK_TIMEOUT}

    results = {
        "PreInvocation": upsert_flat(entry.setdefault("PreInvocation", []), handler("PreInvocation")),
        "PreToolUse": upsert_grouped(entry.setdefault("PreToolUse", []), handler("PreToolUse"), matcher="*"),
    }
    save_registration(path, ".agents/hooks.json", data, results, dry_run, report)


REGISTRARS = {
    "claude": register_claude,
    "codex": register_codex,
    "cursor": register_cursor,
    "antigravity": register_antigravity,
}


# ------------------------------------------------------------------ main

def parse_clients(raw: str):
    clients = [c.strip() for c in raw.split(",") if c.strip()]
    unknown = [c for c in clients if c not in CLIENTS]
    if unknown:
        raise InstallError(f"未対応のクライアント: {', '.join(unknown)}({' / '.join(CLIENTS)} から選んでください)")
    if not clients:
        raise InstallError("--clients が空です。")
    return clients


def install(target: Path, clients, dry_run: bool) -> Report:
    if not target.is_dir():
        raise InstallError(f"インストール先ディレクトリがありません: {target}")
    if target.resolve() == KIT_ROOT:
        raise InstallError("キットリポジトリ自身にはインストールできません。")
    report = Report()
    install_sandbox_files(target, dry_run, report)
    install_skills(target, clients, dry_run, report)
    for client in clients:
        install_hook_files(target, client, dry_run, report)
        REGISTRARS[client](target, dry_run, report)
    if {"claude", "cursor"} <= set(clients):
        report.warnings.append(
            "Cursor は互換のため .claude/skills/ と Claude Code のフックも読み込みます。"
            "Skill の重複表示やフックの二重実行が起きる場合は .sandbox-kit/README.md の"
            "「クライアントごとの注意」を参照してください。")
    if any(c in clients for c in ("codex", "antigravity")):
        report.warnings.append(
            ".codex/hooks.json・.agents/hooks.json にはこのマシンの絶対パスが書き込まれます。"
            "チームで共有する場合は .gitignore に追加するか、各自で install.py を実行してください。")
    return report


def print_report(report: Report, dry_run: bool):
    prefix = "[dry-run] " if dry_run else ""
    for title, items in (("配置", report.placed), ("更新", report.updated), ("変更なし", report.skipped)):
        for item in items:
            print(f"{prefix}{title}: {item}")
    for w in report.warnings:
        print(f"警告: {w}")
    if not (report.placed or report.updated):
        print(f"{prefix}すべて最新です。")


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass
    ap = argparse.ArgumentParser(description="agent-sandbox-kit をプロジェクトへインストール・更新する")
    ap.add_argument("target", help="インストール先プロジェクトのディレクトリ")
    ap.add_argument("--clients", default=",".join(CLIENTS),
                    help=f"対応させるクライアント(カンマ区切り。既定: {','.join(CLIENTS)})")
    ap.add_argument("--dry-run", action="store_true", help="書き込まずに変更内容だけ表示する")
    args = ap.parse_args()
    try:
        clients = parse_clients(args.clients)
        report = install(Path(args.target).resolve(), clients, args.dry_run)
    except InstallError as e:
        print(f"エラー: {e}", file=sys.stderr)
        return 1
    print_report(report, args.dry_run)
    return 0


if __name__ == "__main__":
    sys.exit(main())
