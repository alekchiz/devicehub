#!/bin/sh
# Xray-клиент: поднимает локальный SOCKS5+HTTP прокси, весь трафик уходит
# через VLESS (WS+TLS). Конфиг генерируется из env, чтобы ключи VLESS
# не лежали в коде/репозитории, а только в .env.

set -e
: "${VLESS_SERVER:?VLESS_SERVER is required}"
: "${VLESS_UUID:?VLESS_UUID is required}"

mkdir -p /etc/xray
cat > /etc/xray/config.json <<EOF
{
  "log": {"loglevel": "warning"},
  "inbounds": [
    {"tag": "socks-in", "listen": "0.0.0.0", "port": ${XRAY_SOCKS_PORT:-1080},
     "protocol": "socks", "settings": {"udp": true, "auth": "noauth"}},
    {"tag": "http-in", "listen": "0.0.0.0", "port": ${XRAY_HTTP_PORT:-8118},
     "protocol": "http", "settings": {}}
  ],
  "outbounds": [
    {"tag": "proxy", "protocol": "vless",
     "settings": {"vnext": [{"address": "${VLESS_SERVER}", "port": ${VLESS_PORT:-443},
       "users": [{"id": "${VLESS_UUID}", "encryption": "none"}]}]},
     "streamSettings": {"network": "ws", "security": "tls",
       "tlsSettings": {"serverName": "${VLESS_SNI:-$VLESS_SERVER}",
         "alpn": ["${VLESS_ALPN:-http/1.1}"], "fingerprint": "${VLESS_FP:-chrome}"},
       "wsSettings": {"path": "${VLESS_PATH:-/}"}}}
  ],
  "dns": {"servers": ["1.1.1.1", "8.8.8.8"]}
}
EOF

exec xray run -c /etc/xray/config.json
