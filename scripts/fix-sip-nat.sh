#!/bin/bash
set -u
PPP=$(ip -br addr | awk '/^ppp[0-9]+/ {print $1; exit}')
if [ -z "${PPP:-}" ]; then
  echo VPN_MISSING
  exit 1
fi
BACKEND_IP=$(docker inspect sufler-backend-1 --format '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{println}}{{end}}' | grep -E '^[0-9]+(\.[0-9]+){3}$' | head -n1)
echo "PPP=$PPP BACKEND=$BACKEND_IP"
sysctl -w "net.ipv4.conf.${PPP}.rp_filter=0" >/dev/null
sysctl -w net.ipv4.conf.all.rp_filter=0 >/dev/null
ip route replace 10.1.1.0/24 dev "$PPP"
iptables -t nat -C POSTROUTING -d 10.1.1.0/24 -o "$PPP" -j MASQUERADE 2>/dev/null \
  || iptables -t nat -A POSTROUTING -d 10.1.1.0/24 -o "$PPP" -j MASQUERADE
iptables -C FORWARD -o "$PPP" -d 10.1.1.0/24 -j ACCEPT 2>/dev/null \
  || iptables -A FORWARD -o "$PPP" -d 10.1.1.0/24 -j ACCEPT
iptables -C FORWARD -i "$PPP" -m state --state RELATED,ESTABLISHED -j ACCEPT 2>/dev/null \
  || iptables -A FORWARD -i "$PPP" -m state --state RELATED,ESTABLISHED -j ACCEPT
if echo "${BACKEND_IP:-}" | grep -Eq '^[0-9]+(\.[0-9]+){3}$'; then
  iptables -t nat -C PREROUTING -i "$PPP" -p udp --dport 32768:65535 -j DNAT --to-destination "$BACKEND_IP" 2>/dev/null \
    || iptables -t nat -I PREROUTING -i "$PPP" -p udp --dport 32768:65535 -j DNAT --to-destination "$BACKEND_IP"
  echo DNAT_OK
else
  echo SKIP_DNAT
fi
iptables -I DOCKER-USER -i "$PPP" -j ACCEPT 2>/dev/null || true
iptables -I DOCKER-USER -o "$PPP" -j ACCEPT 2>/dev/null || true
curl -sS -m 8 -o /dev/null -w "health:%{http_code}\n" http://127.0.0.1:8001/health/ || true
echo NAT_DONE
