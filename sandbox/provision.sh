#!/bin/bash
# agent-sandbox ディストロ内のプロビジョニング(root で実行・冪等)。
# setup_sandbox.py から `wsl -d <distro> -u root bash -s` 形式で流し込まれる。
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive
# wsl.exe 起動時の cwd はホスト側 (/mnt/d/...) を引き継ぐことがある。後述の
# ホストドライブ unmount で自分の cwd が消えると npm 等が uv_cwd ENOENT で
# 死ぬため、最初に安全な場所へ移動しておく
cd /

echo "== ユーザー作成 =="
if ! id -u agent >/dev/null 2>&1; then
    useradd -m -s /bin/bash agent
    echo "ユーザー agent を作成しました"
else
    echo "ユーザー agent は作成済み"
fi
# エージェントには sudo を与えない: sudo があると `mount -t drvfs C: ...` で
# ホストドライブをマウントでき、分離が自力で破れる。パッケージ追加等の管理
# 操作はホスト側から `wsl -d <distro> -u root -- apt-get install -y <pkg>` で行う
gpasswd -d agent sudo 2>/dev/null || true
rm -f /etc/sudoers.d/agent
mkdir -p /home/agent/projects
chown agent:agent /home/agent/projects

# ホスト側ガード (.claude/hooks/sandbox_guard.py) がサンドボックス内パスを識別する
# ためのマーカー。SSHFS 等でマウントされた場合の検知に使う。agent が消して
# 警告を無効化できないよう root 所有 + immutable にする
for f in /home/agent/.agent-sandbox /home/agent/projects/.agent-sandbox; do
    [ -e "$f" ] || touch "$f"
    chattr +i "$f" 2>/dev/null || true
done

# automount 無効化前の起動で作られたドライブ用空ディレクトリを掃除
for d in /mnt/?; do rmdir "$d" 2>/dev/null || true; done

echo "== interop binfmt のマスク =="
# wsl.conf で interop を無効にしても、systemd が /usr/lib/binfmt.d/WSLInterop.conf
# からハンドラを再登録する(中継ソケットが無いため機能はしないが、登録を残さない)
mkdir -p /etc/binfmt.d
ln -sf /dev/null /etc/binfmt.d/WSLInterop.conf
if [ -e /proc/sys/fs/binfmt_misc/WSLInterop ]; then
    echo -1 > /proc/sys/fs/binfmt_misc/WSLInterop 2>/dev/null || true
fi

echo "== ホストドライブの unmount(毎 boot)=="
# wsl.conf の automount は有効(\\wsl.localhost 共有を担う plan9 サーバーが
# automount 設定に連動して起動するため)。代わりにホストドライブ (drvfs) を
# boot のたびに unmount して分離を保つ。agent に sudo は無いので再マウント不可。
# 共有(plan9)は unmount 後も生き続けることを確認済み
cat > /usr/local/sbin/sandbox-umount-host-drives <<'EOF'
#!/bin/sh
grep drvfs /proc/mounts | cut -d' ' -f2 | while read -r m; do
    umount "$m" 2>/dev/null || umount -l "$m"
    rmdir "$m" 2>/dev/null || true
done
exit 0
EOF
chmod 755 /usr/local/sbin/sandbox-umount-host-drives
cat > /etc/systemd/system/sandbox-umount-host-drives.service <<'EOF'
[Unit]
Description=Unmount Windows host drives (sandbox isolation)
Before=ssh.service

[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart=/usr/local/sbin/sandbox-umount-host-drives

[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
systemctl enable sandbox-umount-host-drives.service >/dev/null 2>&1 || true
/usr/local/sbin/sandbox-umount-host-drives

echo "== 基本パッケージ =="
apt-get update -y -qq
apt-get install -y -qq --no-install-recommends \
    ca-certificates curl git sudo unzip build-essential \
    python3 python3-venv python3-pip

echo "== Node.js LTS =="
if ! command -v node >/dev/null 2>&1; then
    curl -fsSL https://deb.nodesource.com/setup_22.x | bash -
    apt-get install -y -qq nodejs
fi
node -v

echo "== SSH サーバー (VS Code Remote-SSH 用) =="
# WSL リモート拡張は Windows 側パスの /mnt/c 参照(automount)前提で動くため
# 分離ディストロでは使えない。代わりに localhost:2222 の sshd 経由で接続する。
apt-get install -y -qq --no-install-recommends openssh-server
cat > /etc/ssh/sshd_config.d/90-agent-sandbox.conf <<'EOF'
Port 2222
PasswordAuthentication no
AllowUsers agent
EOF
install -d -m 700 -o agent -g agent /home/agent/.ssh
touch /home/agent/.ssh/authorized_keys
chmod 600 /home/agent/.ssh/authorized_keys
chown agent:agent /home/agent/.ssh/authorized_keys
# Ubuntu 24.04 の ssh は socket activation(ポート 22 固定)が既定のため、
# sshd_config の Port を効かせるには service 直起動に切り替える必要がある
systemctl disable --now ssh.socket >/dev/null 2>&1 || true
systemctl enable ssh.service >/dev/null 2>&1 || true
systemctl restart ssh.service >/dev/null 2>&1 || true

echo "== エージェント CLI =="
npm install -g --no-fund --no-audit \
    @anthropic-ai/claude-code \
    @openai/codex

# --- Antigravity CLI --------------------------------------------------
# スタンドアロンの CLI インストール手順が未確認のためプレースホルダー。
# 公式手順が判明したらここに追記する。
# Antigravity は VS Code 系 IDE のため、当面は IDE 側の WSL リモート接続で
# 本ディストロに繋ぐ運用を想定(.sandbox-kit/README.md 参照)。
# ----------------------------------------------------------------------

echo "== バージョン確認 =="
claude --version || echo "警告: claude が見つかりません"
codex --version || echo "警告: codex が見つかりません"

echo "== provision 完了 =="
