#!/usr/bin/env python3
"""AI エージェント実行用の分離 WSL2 ディストロを作成・更新するスクリプト。

ホスト保護の設計(詳細: .sandbox-kit/README.md):
- 専用ディストロを import で新規作成(既存の開発用 WSL とは別)
- /etc/wsl.conf で interop(Windows exe 起動)を無効化。automount は
  \\wsl.localhost 共有(ホスト → ディストロのアクセス)のため有効にし、
  ホストドライブは provision.sh が入れる systemd ユニットが毎 boot unmount する
- provision.sh で Node.js とエージェント CLI(claude / codex)を導入
- ネットワークは制限しない(ファイルシステム分離のみが目的)

冪等: ディストロが既にあれば作成をスキップし、wsl.conf の再配置と
provision の再実行のみ行う。

使い方:
    python setup_sandbox.py [--distro agent-sandbox] [--install-dir <path>]
                            [--tarball <rootfs.tar.gz>] [--dry-run]
"""

import argparse
import os
import re
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

SANDBOX_ROOT = Path(__file__).resolve().parent
DEFAULT_DISTRO = "agent-sandbox"
SSH_PORT = 2222  # provision.sh の sshd_config drop-in と揃えること
ROOTFS_URL = ("https://cloud-images.ubuntu.com/wsl/releases/noble/current/"
              "ubuntu-noble-wsl-amd64-24.04lts.rootfs.tar.gz")


class SetupError(Exception):
    pass


def read_text(path: Path) -> str:
    """UTF-8(BOM 許容)で読み、改行を LF に正規化して返す。"""
    return path.read_text(encoding="utf-8-sig").replace("\r\n", "\n")


def run_wsl(args, input_text=None, capture=False, check=True):
    """wsl.exe を呼ぶ。WSL_UTF8=1 を付けないと出力が UTF-16LE になる罠に注意。

    stdin はバイトで渡す: text=True だと Windows では \n → \r\n に自動変換され、
    bash や /etc/wsl.conf に \r が混入して壊れるため。
    """
    env = os.environ.copy()
    env["WSL_UTF8"] = "1"
    result = subprocess.run(
        ["wsl.exe", *args], env=env,
        input=input_text.encode("utf-8") if input_text is not None else None,
        capture_output=capture)
    if capture:
        result.stdout = result.stdout.decode("utf-8", errors="replace")
        result.stderr = result.stderr.decode("utf-8", errors="replace")
    if check and result.returncode != 0:
        detail = (result.stderr or "").strip() if capture else ""
        raise SetupError(f"wsl {' '.join(args)} が失敗しました(exit {result.returncode}) {detail}")
    return result


def wsl_available() -> bool:
    try:
        return run_wsl(["--status"], capture=True, check=False).returncode == 0
    except FileNotFoundError:
        return False


def distro_exists(name: str) -> bool:
    result = run_wsl(["--list", "--quiet"], capture=True, check=False)
    names = [line.strip() for line in result.stdout.splitlines()]
    return name in names


def download_rootfs(dest: Path):
    print(f"rootfs をダウンロード中(数百 MB あります): {ROOTFS_URL}")
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(".part")

    def hook(blocks, block_size, total):
        done = blocks * block_size
        if total > 0:
            print(f"\r  {done / 1048576:.0f} / {total / 1048576:.0f} MB", end="", flush=True)

    urllib.request.urlretrieve(ROOTFS_URL, tmp, reporthook=hook)
    print()
    tmp.replace(dest)


def import_distro(distro: str, install_dir: Path, tarball: Path):
    install_dir.mkdir(parents=True, exist_ok=True)
    print(f"ディストロ {distro} を import 中...")
    run_wsl(["--import", distro, str(install_dir), str(tarball), "--version", "2"])


def apply_wsl_conf(distro: str):
    conf = read_text(SANDBOX_ROOT / "wsl.conf")
    run_wsl(["-d", distro, "-u", "root", "--", "bash", "-c",
             "cat > /etc/wsl.conf"], input_text=conf)
    # automount/interop/default user の反映には再起動が必要
    run_wsl(["--terminate", distro], check=False)
    print("wsl.conf を配置し、ディストロを再起動しました(interop 無効 / automount 有効・ドライブは boot 時 unmount)")


def provision(distro: str):
    print("provision を実行中(初回は数分かかります)...")
    script = read_text(SANDBOX_ROOT / "provision.sh")
    # bash -s に stdin で流し込む: automount 無効でもホスト側ファイルの
    # マウントに頼らずスクリプトを渡せる
    run_wsl(["-d", distro, "-u", "root", "--", "bash", "-s"], input_text=script)
    run_wsl(["--terminate", distro], check=False)


def setup_ssh_access(distro: str):
    """ホスト側の SSH 鍵と ~/.ssh/config エントリを用意し、公開鍵をディストロへ登録する。

    VS Code の WSL リモート拡張は /mnt/c(automount)前提で分離ディストロでは
    動かないため、接続は Remote-SSH(wsl.exe 経由の ProxyCommand → localhost:2222)で行う。
    """
    ssh_dir = Path.home() / ".ssh"
    ssh_dir.mkdir(exist_ok=True)
    key = ssh_dir / f"{distro}_ed25519"
    if not key.exists():
        result = subprocess.run(
            ["ssh-keygen", "-t", "ed25519", "-N", "", "-C", f"{distro}-access",
             "-f", str(key)], capture_output=True)
        if result.returncode != 0:
            raise SetupError("ssh-keygen に失敗しました。Windows の OpenSSH クライアントを確認してください。")
        print(f"SSH 鍵を生成しました: {key}")

    pubkey = (ssh_dir / f"{distro}_ed25519.pub").read_text(encoding="utf-8").strip()
    # wsl.exe は引数を空白結合で作り直すため bash -c に複雑な引用は渡せない。
    # provision と同じく stdin からスクリプトを流し込む(鍵は ssh 公開鍵形式
    # なのでシングルクォートを含まない)
    register = (
        "cd /\n"  # cwd がホストドライブ上だと unmount 後に消えているため
        f"key='{pubkey}'\n"
        "f=/home/agent/.ssh/authorized_keys\n"
        "install -d -m 700 -o agent -g agent /home/agent/.ssh\n"
        'touch "$f"\n'
        'grep -qxF "$key" "$f" || echo "$key" >> "$f"\n'
        'chmod 600 "$f"\n'
        'chown agent:agent "$f"\n')
    run_wsl(["-d", distro, "-u", "root", "--", "bash", "-s"], input_text=register)
    ensure_ssh_config(distro)


def ensure_ssh_config(distro: str):
    """~/.ssh/config に Host <distro> エントリを用意する。旧版のエントリには ProxyCommand を追記する。

    install.py でキットを更新しただけでは setup が再実行されないため、
    open_in_sandbox.py も IDE 起動前にこれを呼ぶ。
    """
    ssh_dir = Path.home() / ".ssh"
    ssh_dir.mkdir(exist_ok=True)
    # WSL はクライアント(wsl.exe)が全て終了すると約 15 秒でディストロを停止し、
    # sshd も一緒に止まる。localhost:2222 へ直接繋ぐと停止中は Connection refused に
    # なるため、wsl.exe 経由の ProxyCommand で繋ぐ。接続のたびにディストロが起動し、
    # 接続中は wsl.exe が生き続けるのでディストロも停止しない
    proxy = f"  ProxyCommand wsl.exe -d {distro} -u agent --cd / -- nc localhost {SSH_PORT}\n"
    config = ssh_dir / "config"
    existing = config.read_text(encoding="utf-8") if config.exists() else ""
    lines = existing.splitlines(keepends=True)
    header = f"Host {distro}"
    if not any(line.strip() == header for line in lines):
        entry = (f"\nHost {distro}\n"
                 f"  HostName localhost\n"
                 f"  Port {SSH_PORT}\n"
                 f"  User agent\n"
                 f"  IdentityFile ~/.ssh/{distro}_ed25519\n"
                 f"  StrictHostKeyChecking accept-new\n"
                 f"{proxy}")
        with open(config, "a", encoding="utf-8", newline="\n") as fh:
            fh.write(entry)
        print(f"~/.ssh/config に Host {distro} エントリを追加しました")
        return

    # 旧版が作った ProxyCommand なしのエントリを更新する(ブロック末尾に追記)
    start = next(i for i, line in enumerate(lines) if line.strip() == header) + 1
    end = start
    while end < len(lines) and not re.match(r"\s*(Host|Match)\s", lines[end], re.IGNORECASE):
        end += 1
    if any(re.match(r"\s*ProxyCommand\s", line, re.IGNORECASE) for line in lines[start:end]):
        return
    while end > start and not lines[end - 1].strip():
        end -= 1  # 後続ブロックとの空行の前に差し込む
    if end > 0 and not lines[end - 1].endswith("\n"):
        lines[end - 1] += "\n"
    lines.insert(end, proxy)
    with open(config, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("".join(lines))
    print(f"~/.ssh/config の Host {distro} エントリに ProxyCommand を追加しました")


def verify_ssh(distro: str):
    """ホスト → localhost:2222 → ディストロの SSH 接続を確認する(sshd 起動待ちでリトライ)。"""
    run_wsl(["-d", distro, "--", "true"], check=False)  # ディストロを起動しておく
    for _ in range(5):
        result = subprocess.run(
            ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=5", distro, "true"],
            capture_output=True)
        if result.returncode == 0:
            print("検証: SSH 接続 (localhost:2222 → agent) → OK")
            return
        time.sleep(2)
    print("警告: SSH 接続に失敗しました。`ssh " + distro + "` で詳細を確認してください。")


def verify(distro: str):
    """分離設定と導入結果を確認する。失敗しても停止せず警告に留める。"""
    # /mnt のディレクトリ名ではなく実マウントを見る(過去の起動で残った
    # 空ディレクトリを誤検知しないため)。automount で付いたドライブは
    # boot 時の systemd ユニットが外すため、直後の起動では少し待って再確認する
    for attempt in range(5):
        mounts = run_wsl(["-d", distro, "--", "bash", "-c", "mount | grep -i drvfs || true"],
                         capture=True, check=False)
        if not mounts.stdout.strip():
            break
        time.sleep(2)
    if mounts.stdout.strip():
        print("警告: ホストドライブがマウントされています"
              f"(sandbox-umount-host-drives ユニットを確認してください):\n{mounts.stdout}")
    else:
        print("検証: ホストドライブのマウントなし → OK")
    interop = run_wsl(["-d", distro, "--", "bash", "-c",
                       "ls /proc/sys/fs/binfmt_misc/ 2>/dev/null | grep -c WSLInterop || true"],
                      capture=True, check=False)
    if interop.stdout.strip() == "0":
        print("検証: Windows interop 無効 → OK")
    else:
        print("警告: Windows interop が有効のままです(wsl.conf の反映を確認してください)")
    share = Path(rf"\\wsl.localhost\{distro}\home\agent")
    if share.is_dir():
        print(rf"検証: \\wsl.localhost\{distro} 共有 → OK")
    else:
        print(rf"警告: \\wsl.localhost\{distro} にアクセスできません"
              "(automount 設定の反映を確認してください)")
    who = run_wsl(["-d", distro, "--", "whoami"], capture=True, check=False)
    if who.stdout.strip() == "agent":
        print("検証: 既定ユーザー agent → OK")
    else:
        print(f"警告: 既定ユーザーが {who.stdout.strip()} です(期待: agent)")
    tools = run_wsl(["-d", distro, "--", "bash", "-lc",
                     "node -v && claude --version && codex --version"],
                    capture=True, check=False)
    if tools.returncode == 0:
        print("検証: node / claude / codex 導入済み → OK")
        for line in tools.stdout.strip().splitlines():
            print(f"  {line}")
    else:
        print("警告: エージェント CLI の確認に失敗しました。provision のログを確認してください。")


def show_next_steps(distro: str):
    print(f"""
=== セットアップ完了 ===
次のステップ:
1. 認証(interop 無効のためブラウザは自動で開かない。表示された URL を
   ホストのブラウザに手動で貼り付けること):
     wsl -d {distro}    (その後シェル内で)  claude   /   codex login
2. IDE から接続(Remote-SSH 拡張が必要。WSL リモート拡張は分離設定と
   非互換のため使わない。Cursor は cursor、Antigravity は antigravity-ide に読み替え):
     code --remote ssh-remote+{distro} /home/agent/projects
   初回接続後、必要ならリモート側にエージェントの拡張(Claude Code 等)をインストールする。
3. プロジェクトの搬入は open_in_sandbox.py を使う:
     python .sandbox-kit/open_in_sandbox.py <プロジェクトのパス>
詳細: .sandbox-kit/README.md""")


def main():
    ap = argparse.ArgumentParser(description="エージェント用分離 WSL2 ディストロの作成・更新")
    ap.add_argument("--distro", default=DEFAULT_DISTRO, help=f"ディストロ名(既定: {DEFAULT_DISTRO})")
    ap.add_argument("--install-dir", default=None,
                    help=r"ディストロの仮想ディスク配置先(既定: %LOCALAPPDATA%\wsl\<distro>)")
    ap.add_argument("--tarball", default=None,
                    help="使用する rootfs tarball(省略時は Ubuntu 24.04 をダウンロード)")
    ap.add_argument("--dry-run", action="store_true", help="実行せず予定だけ表示する")
    args = ap.parse_args()

    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

    try:
        if not wsl_available():
            raise SetupError(
                "WSL2 が見つかりません。管理者 PowerShell で `wsl --install` を実行し、"
                "再起動後にもう一度このスクリプトを実行してください。")

        install_dir = Path(args.install_dir) if args.install_dir else \
            Path(os.environ["LOCALAPPDATA"]) / "wsl" / args.distro
        exists = distro_exists(args.distro)

        if args.dry_run:
            print("[dry-run] 実行予定:")
            if exists:
                print(f"  - ディストロ {args.distro} は既存 → 作成をスキップ")
            else:
                src = args.tarball or f"{ROOTFS_URL} をダウンロード"
                print(f"  - rootfs: {src}")
                print(f"  - wsl --import {args.distro} {install_dir}")
            print("  - /etc/wsl.conf 配置(interop 無効 / automount 有効)+ 再起動")
            print("  - provision.sh 実行(agent ユーザー / ドライブ unmount ユニット / Node.js / claude / codex)")
            return 0

        if exists:
            print(f"ディストロ {args.distro} は既存です。設定と provision のみ再適用します。")
        else:
            tarball = Path(args.tarball) if args.tarball else install_dir / "rootfs.tar.gz"
            if args.tarball and not tarball.is_file():
                raise SetupError(f"指定された tarball がありません: {tarball}")
            if not tarball.is_file():
                download_rootfs(tarball)
            import_distro(args.distro, install_dir, tarball)

        apply_wsl_conf(args.distro)
        provision(args.distro)
        setup_ssh_access(args.distro)
        verify(args.distro)
        verify_ssh(args.distro)
        show_next_steps(args.distro)
        return 0

    except SetupError as e:
        print(f"エラー: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
