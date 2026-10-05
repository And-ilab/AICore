#!/bin/bash
set -euo pipefail
# Bring bank VPN back and restart sufler listen (Idchain=live, line 1001).
systemctl start strongswan-starter 2>/dev/null || true
ipsec up activecloud || true
systemctl restart xl2tpd
sleep 1
echo c activecloud > /var/run/xl2tpd/l2tp-control
sleep 6
PPP=$(ip -br addr | awk '/^ppp[0-9]+/ {print $1; exit}')
if [ -z "${PPP:-}" ]; then
  echo "VPN_IFACE_MISSING"
  exit 1
fi
ip link set "$PPP" up || true
ip route replace 10.1.1.0/24 dev "$PPP"
sysctl -w "net.ipv4.conf.${PPP}.rp_filter=0" >/dev/null
sysctl -w net.ipv4.conf.all.rp_filter=0 >/dev/null
BACKEND_IP=$(docker inspect sufler-backend-1 --format '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{println}}{{end}}' | grep -E '^[0-9]+(\.[0-9]+){3}$' | head -n1 || true)
echo "BACKEND_IP=${BACKEND_IP:-none}"
iptables -t nat -C POSTROUTING -d 10.1.1.0/24 -o "$PPP" -j MASQUERADE 2>/dev/null \
  || iptables -t nat -A POSTROUTING -d 10.1.1.0/24 -o "$PPP" -j MASQUERADE
iptables -C FORWARD -o "$PPP" -d 10.1.1.0/24 -j ACCEPT 2>/dev/null \
  || iptables -A FORWARD -o "$PPP" -d 10.1.1.0/24 -j ACCEPT
iptables -C FORWARD -i "$PPP" -m state --state RELATED,ESTABLISHED -j ACCEPT 2>/dev/null \
  || iptables -A FORWARD -i "$PPP" -m state --state RELATED,ESTABLISHED -j ACCEPT
if echo "${BACKEND_IP:-}" | grep -Eq '^[0-9]+(\.[0-9]+){3}$'; then
  iptables -t nat -C PREROUTING -i "$PPP" -p udp --dport 32768:65535 -j DNAT --to-destination "$BACKEND_IP" 2>/dev/null \
    || iptables -t nat -I PREROUTING -i "$PPP" -p udp --dport 32768:65535 -j DNAT --to-destination "$BACKEND_IP"
else
  echo SKIP_DNAT
fi
iptables -C DOCKER-USER -i "$PPP" -j ACCEPT 2>/dev/null || iptables -I DOCKER-USER -i "$PPP" -j ACCEPT || true
iptables -C DOCKER-USER -o "$PPP" -j ACCEPT 2>/dev/null || iptables -I DOCKER-USER -o "$PPP" -j ACCEPT || true
ping -c 2 -W 3 10.1.1.181 || echo PBX_PING_FAIL
cd /opt/sufler/infra
docker compose restart backend
docker compose -f docker-compose.yml -f docker-compose.frontend-prod.yml build frontend
docker compose -f docker-compose.yml -f docker-compose.frontend-prod.yml up -d --no-deps frontend
echo LIVE_LISTEN_READY iface="$PPP"
