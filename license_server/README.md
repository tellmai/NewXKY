# 授权服务端部署

NewXKY 的验证码必须由服务端判定“首次激活、绑定哪台电脑、40 分钟何时到期”。服务端数据库只保存 SHA-256 哈希，V3.0.1 起由 Ed25519 私钥签发租约，客户端用内置公钥验证签名。

## V3.0.1 签名授权升级

1. 构建机执行 `runtime\python.exe scripts\configure_license_signing.py`，生成或复用 `license_server/data/lease-signing-key.pem`，并把公钥写入客户端配置。正式密钥必须备份和复用，不要每次发版重新生成。
2. 先部署配套服务端，再分发客户端。旧客户端仍能调用同一激活接口；新客户端拒绝无签名响应。旧缓存只有联网重新确认后才能继续使用，原到期时间不延长。
3. 只更新现有服务器时，运行 `runtime\python.exe scripts\package_server.py --upgrade-only --output dist\NewXKY-LicenseServer-V3.0.1-Update.zip`。它不包含验证码数据库；`deploy.sh` 保留线上 `licenses.db`，已有私钥与更新包不一致时会停止。
4. 服务端更新包包含签名私钥，只用于服务器部署，不能公开分发。客户端包只含公钥。密钥和数据库都要备份。
5. 手动安装服务端时需安装 `python3-cryptography`；`deploy.sh` 会自动安装。自定义私钥路径可通过 `NEWXKY_SIGNING_KEY` 设置，默认使用数据库同目录的 `lease-signing-key.pem`。

## 大陆服务器（北京/上海/广州）先确认 ICP 备案

大陆节点通常要求域名完成 ICP 备案并接入当前云厂商，否则 80/443 可能被封锁，Caddy 无法申请证书。已有备案域名且接入商一致可直接部署；没有备案请先在腾讯云/阿里云提交新增或接入备案，或改用香港/新加坡服务器。具体入口和材料见项目根目录的 `部署操作清单.md`。

## 还没有服务器和域名怎么办

需要一个可公网访问的 HTTPS 地址，推荐最小组合：

1. **云服务器**：腾讯云/阿里云轻量应用服务器，2 核 2G、Ubuntu 22.04。香港/新加坡节点通常不需要 ICP 备案；大陆节点需要备案。费用大约每月几十元。
2. **域名**：在腾讯云、阿里云、Cloudflare 等注册一个域名，约每年几十元；也可以使用已有域名。
3. **DNS**：添加一条 A 记录，例如 `license.你的域名.com` 指向服务器公网 IP。
4. **HTTPS**：不需要单独购买证书。按下面的 Caddy 配置，Caddy 会自动申请和续期 Let's Encrypt 证书。
5. 把域名（只需要域名，不需要服务器密码）填入 `newxky/license_config.py` 后重新打包客户端。

> 没有公网服务器时，无法实现“验证码只能用一次、换电脑失效”。本地记录可以被复制，不能作为正式发行方案。

## 组成

```text
license_server/
  server.py          HTTP API（标准库 HTTP + cryptography 签名）
  signing.py         Ed25519 租约签发（仅服务端持有私钥）
  db.py              SQLite schema、单次激活事务
  codes.py           验证码格式、哈希
  generate_codes.py  生成 20 个 Excel 并播种数据库（需要 openpyxl）
  import_codes.py    从已有 Excel 导入
  data/licenses.db   验证码哈希和激活记录
  data/lease-signing-key.pem  签名私钥（不可放进客户端）
```

## 1. 生成验证码

在项目根目录执行：

```powershell
.\.venv\Scripts\python.exe license_server\generate_codes.py --count 10000 --files 20 --per-file 500
```

生成：

- `dist\授权码-40分钟\NewXKY授权码-01.xlsx` 至 `-20.xlsx`，每份 500 行。
- `license_server\data\licenses.db`：已写入 10,000 条验证码哈希。
- `dist\授权码\manifest.json`：数量、文件 SHA-256。

不要把 `licenses.db` 和 Excel 放在同一个可公开下载的目录。Excel 是发给用户的明文验证码；数据库只应放在服务器。

如果已有 Excel：

```powershell
.\.venv\Scripts\python.exe license_server\import_codes.py dist\授权码-40分钟\*.xlsx --db license_server\data\licenses.db
```

> `--reset-db` 会删除已有激活记录，只能在首次部署或确认作废旧数据时使用。

## 2. 部署服务端

要求：Python 3.11+，一台有公网 HTTPS 域名的服务器（Windows/Linux 均可）。服务端本身只监听本机 HTTP，由 Caddy/Nginx 终止 TLS。

把整个 `license_server` 目录和已播种的 `data/licenses.db` 上传到服务器，例如 `/opt/newxky/license_server`。

### 最省事流程：上传后一条命令（Ubuntu 22.04/24.04）

前提：域名 A 记录已指向服务器公网 IP，云厂商防火墙已放行 TCP 80/443。

在 Windows 本机项目目录上传部署包：

```powershell
scp .\dist\NewXKY-LicenseServer-V3.0.1.zip root@服务器公网IP:/tmp/
ssh root@服务器公网IP
```

在服务器上执行：

```bash
apt update && apt install -y unzip openssl
cd /opt
unzip /tmp/NewXKY-LicenseServer-V3.0.1.zip
cd NewXKY-LicenseServer
TOKEN=$(openssl rand -hex 24)
bash license_server/deploy.sh license.你的域名.com "$TOKEN"
```

脚本会完成：安装 Python/Caddy、创建 `newxky` 服务用户、复制服务端代码和数据库、保留已有激活记录、写入 systemd、配置 HTTPS 反向代理、启动并检查本机健康。

成功后验证：

```bash
curl https://license.你的域名.com/healthz
curl -H "X-Admin-Token: 你的TOKEN" https://license.你的域名.com/api/v1/admin/stats
```

管理员令牌只用于查看统计，不要写进客户端或公开。部署完成后回到本文档“3. 配置客户端地址”。

> 如果服务器是全新且只用于 NewXKY，脚本可直接使用；如果服务器已有其他 Caddy 站点，脚本会备份原 Caddyfile 后覆盖，请先合并配置。

### 手动部署（备用）

```bash
# 1. 基础环境
sudo apt update
sudo apt install -y python3 python3-cryptography unzip caddy

# 2. 解压部署包（上传 NewXKY-LicenseServer-V3.0.1.zip 到 /tmp）
sudo mkdir -p /opt/newxky
sudo unzip /tmp/NewXKY-LicenseServer-V3.0.1.zip -d /opt/
sudo mv /opt/NewXKY-LicenseServer/license_server /opt/newxky/
sudo useradd -r -s /usr/sbin/nologin newxky || true
sudo chown -R newxky:newxky /opt/newxky

# 3. 安装 systemd 服务并填入一个长随机令牌
sudo cp /opt/newxky/license_server/newxky-license.service.example /etc/systemd/system/newxky-license.service
sudo nano /etc/systemd/system/newxky-license.service
sudo systemctl daemon-reload
sudo systemctl enable --now newxky-license
curl http://127.0.0.1:8787/healthz

# 4. 配置 Caddy：把 license.example.com 改成你的域名
sudo cp /opt/newxky/license_server/Caddyfile.example /etc/caddy/Caddyfile
sudo nano /etc/caddy/Caddyfile
sudo systemctl reload caddy
curl https://license.你的域名.com/healthz
```

> 如果 `apt install caddy` 找不到包，按 Caddy 官方文档添加软件源，或直接使用上面的 `deploy.sh`。

DNS 的 A 记录必须先指向服务器，且防火墙开放 80/443；Caddy 才能自动申请证书。

直接运行（不使用 systemd 时）：

```bash
cd /opt/newxky
NEWXKY_LICENSE_DB=/opt/newxky/license_server/data/licenses.db \
NEWXKY_LICENSE_HOST=127.0.0.1 \
NEWXKY_LICENSE_PORT=8787 \
NEWXKY_ADMIN_TOKEN='换成长随机字符串' \
python3 -m license_server.server
```

环境变量：

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `NEWXKY_LICENSE_DB` | `license_server/data/licenses.db` | SQLite 文件 |
| `NEWXKY_LICENSE_HOST` | `127.0.0.1` | 只监听本机，由反向代理对外 |
| `NEWXKY_LICENSE_PORT` | `8787` | 本机端口 |
| `NEWXKY_ADMIN_TOKEN` | 空 | 设置后才能访问统计接口 |
| `NEWXKY_TRUST_PROXY` | 空 | 部署在 Caddy/Nginx 后设为 `1`，用真实客户端 IP 做限流 |
| `NEWXKY_RATE_LIMIT` | `120` | 每个客户端 IP 每分钟最多激活请求数 |

### systemd 示例

`/etc/systemd/system/newxky-license.service`：

```ini
[Unit]
Description=NewXKY license service
After=network.target

[Service]
WorkingDirectory=/opt/newxky
Environment=NEWXKY_LICENSE_DB=/opt/newxky/license_server/data/licenses.db
Environment=NEWXKY_LICENSE_HOST=127.0.0.1
Environment=NEWXKY_LICENSE_PORT=8787
Environment=NEWXKY_ADMIN_TOKEN=请替换成长随机字符串
ExecStart=/usr/bin/python3 -m license_server.server
Restart=always
User=newxky

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now newxky-license
curl http://127.0.0.1:8787/healthz
```

### Caddy 反向代理（自动 HTTPS）

`/etc/caddy/Caddyfile`：

```caddyfile
license.example.com {
    reverse_proxy 127.0.0.1:8787
}
```

```bash
sudo systemctl reload caddy
curl https://license.example.com/healthz
```

Nginx 也可以，关键是使用有效证书并只代理到本机 8787。**不要直接暴露 HTTP 端口。**

## 3. 配置客户端地址

在项目 `newxky/license_config.py` 填入同一地址：

```python
LICENSE_SERVER_URL = "https://license.example.com"
```

然后按 README 重新构建 exe/ZIP。打包后的客户端不会读取环境变量覆盖该地址，避免用户把程序指向自己的假服务器。

源码开发时可以用 `NEWXKY_LICENSE_SERVER=http://127.0.0.1:8787` 联调。

## 4. 检查

```bash
curl https://license.example.com/healthz
curl -H "X-Admin-Token: 你的令牌" https://license.example.com/api/v1/admin/stats
```

统计返回总数、已用、当前有效、未使用数量。

## 规则与安全

- 首次激活在单个 SQLite `BEGIN IMMEDIATE` 事务里绑定 `machine_id`；并发请求最多一个成功。
- 同一 `machine_id` 重开返回剩余时间；不同机器返回 `already_used`（HTTP 409）。
- 到期后同一机器也返回 `expired`（HTTP 410），不能续用旧码。- 数据库只保存验证码 SHA-256，不保存明文；Excel 才是分发源。
- 客户端每个请求带机器指纹（Windows MachineGuid + 系统盘卷序列号的 SHA-256），本地授权记录再用 Windows DPAPI 加密。
- 服务端限流默认每 IP 每分钟 120 次激活请求；部署在反向代理后务必设置 `NEWXKY_TRUST_PROXY=1`，否则所有用户会共用反向代理的 IP 限流。
- 备份 `licenses.db`（连同 `-wal`、`-shm` 或先停服务）即可保留激活记录；丢失数据库会让已用码变成未用，务必定期备份。
- 更换服务器域名不会改变已有激活记录，但必须同步修改客户端 `LICENSE_SERVER_URL` 并重新构建。
- 如需停用某个码：

```sql
UPDATE licenses SET disabled=1 WHERE code_hash='<sha256>';
```

`code_hash` 可由 `license_server/codes.py` 的 `hash_code()` 计算。不要直接删除记录，删除会让该码重新变为可激活。
