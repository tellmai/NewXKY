#!/usr/bin/env bash
# NewXKY license server installer for Ubuntu 22.04/24.04.
# Usage (as root, from the extracted NewXKY-LicenseServer directory):
#   sudo bash license_server/deploy.sh license.example.com <admin-token>
set -euo pipefail

DOMAIN="${1:-}"
ADMIN_TOKEN="${2:-}"
if [[ $EUID -ne 0 ]]; then
  echo "请用 root 或 sudo 运行。" >&2
  exit 1
fi
if [[ ! "$DOMAIN" =~ ^[A-Za-z0-9.-]+\.[A-Za-z]{2,}$ ]]; then
  echo "域名格式无效，例如：license.example.com" >&2
  exit 1
fi
if [[ ! "$ADMIN_TOKEN" =~ ^[A-Za-z0-9_-]{24,128}$ ]]; then
  echo "管理员令牌至少 24 位，只能包含字母、数字、下划线和短横线。" >&2
  exit 1
fi

SOURCE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_ROOT="/opt/newxky"
TARGET_DIR="$APP_ROOT/license_server"
SERVICE_FILE="/etc/systemd/system/newxky-license.service"
CADDYFILE="/etc/caddy/Caddyfile"
STAMP="$(date +%Y%m%d-%H%M%S)"

if [[ ! -f "$SOURCE_DIR/data/licenses.db" && ! -f "$TARGET_DIR/data/licenses.db" ]]; then
  echo "没有初始数据库或现网数据库；更新包只能用于已有授权服务，请使用完整服务端包首次部署。" >&2
  exit 1
fi
if [[ ! -f "$SOURCE_DIR/data/lease-signing-key.pem" ]]; then
  echo "部署包缺少授权签名私钥，请重新生成配套的服务端 ZIP。" >&2
  exit 1
fi
if [[ -f "$TARGET_DIR/data/lease-signing-key.pem" ]] && \
   ! cmp -s "$SOURCE_DIR/data/lease-signing-key.pem" "$TARGET_DIR/data/lease-signing-key.pem"; then
  echo "部署包签名密钥与现网不一致，已停止。请使用现网私钥重新构建客户端与服务端包。" >&2
  exit 1
fi

echo "==> 安装系统依赖"
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y python3 python3-cryptography ca-certificates curl gnupg openssl unzip debian-keyring debian-archive-keyring apt-transport-https

if ! command -v caddy >/dev/null 2>&1; then
  echo "==> 安装 Caddy（自动 HTTPS）"
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' \
    | gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' \
    > /etc/apt/sources.list.d/caddy-stable.list
  apt-get update
  apt-get install -y caddy
fi

echo "==> 创建服务用户与目录"
id newxky >/dev/null 2>&1 || useradd -r -s /usr/sbin/nologin newxky
install -d -o newxky -g newxky "$TARGET_DIR" "$TARGET_DIR/data"

echo "==> 复制服务端代码（保留已有激活数据库）"
for file in __init__.py codes.py db.py server.py signing.py generate_codes.py import_codes.py README.md; do
  if [[ -f "$SOURCE_DIR/$file" ]]; then
    install -m 0644 -o newxky -g newxky "$SOURCE_DIR/$file" "$TARGET_DIR/$file"
  fi
done
if [[ ! -f "$TARGET_DIR/data/licenses.db" ]]; then
  install -m 0640 -o newxky -g newxky "$SOURCE_DIR/data/licenses.db" "$TARGET_DIR/data/licenses.db"
  echo "    已复制初始验证码数据库。"
else
  echo "    检测到已有数据库，保留现网激活记录。"
fi
if [[ ! -f "$TARGET_DIR/data/lease-signing-key.pem" ]]; then
  install -m 0640 -o newxky -g newxky "$SOURCE_DIR/data/lease-signing-key.pem" "$TARGET_DIR/data/lease-signing-key.pem"
fi
chown -R newxky:newxky "$APP_ROOT"

if [[ -f "$SERVICE_FILE" ]]; then
  cp -a "$SERVICE_FILE" "$SERVICE_FILE.bak-$STAMP"
fi
cat > "$SERVICE_FILE" <<EOF
[Unit]
Description=NewXKY license service
After=network.target

[Service]
WorkingDirectory=$APP_ROOT
Environment=NEWXKY_LICENSE_DB=$TARGET_DIR/data/licenses.db
Environment=NEWXKY_LICENSE_HOST=127.0.0.1
Environment=NEWXKY_LICENSE_PORT=8787
Environment=NEWXKY_TRUST_PROXY=1
Environment=NEWXKY_RATE_LIMIT=120
Environment=NEWXKY_ADMIN_TOKEN=$ADMIN_TOKEN
ExecStart=/usr/bin/python3 -m license_server.server
Restart=always
User=newxky

[Install]
WantedBy=multi-user.target
EOF

echo "==> 配置 Caddy"
if [[ -f "$CADDYFILE" ]]; then
  cp -a "$CADDYFILE" "$CADDYFILE.bak-$STAMP"
fi
mkdir -p /etc/caddy
cat > "$CADDYFILE" <<EOF
$DOMAIN {
    encode gzip
    reverse_proxy 127.0.0.1:8787
}
EOF

systemctl daemon-reload
systemctl enable --now newxky-license
systemctl enable --now caddy
systemctl restart newxky-license
systemctl reload caddy 2>/dev/null || systemctl restart caddy

echo "==> 本机健康检查"
sleep 2
curl -fsS http://127.0.0.1:8787/healthz
echo
echo "部署完成。"
echo "外部检查：https://$DOMAIN/healthz"
echo "统计接口：curl -H 'X-Admin-Token: $ADMIN_TOKEN' https://$DOMAIN/api/v1/admin/stats"
echo
echo "如果 HTTPS 暂时失败："
echo "  1. 确认域名 A 记录已指向本机公网 IP；"
echo "  2. 确认云厂商防火墙已放行 TCP 80 和 443；"
echo "  3. 查看日志：journalctl -u newxky-license -n 100 --no-pager"
echo "     journalctl -u caddy -n 100 --no-pager"
echo "  4. DNS 刚生效时等待几分钟后重试。"
