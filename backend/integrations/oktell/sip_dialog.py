"""Minimal SIP REGISTER + INVITE + RTP recv for Oktell 02*/03* barge."""

from __future__ import annotations

import hashlib
import logging
import os
import random
import re
import socket
import threading
import time
from dataclasses import dataclass
from typing import Callable
from urllib.parse import unquote

logger = logging.getLogger(__name__)

_SIP_PORT = 5060
_HDR = re.compile(r"(?P<k>[A-Za-z0-9-]+)\s*:\s*(?P<v>.*)")


@dataclass
class SipAuth:
    realm: str
    nonce: str
    algorithm: str = "MD5"
    qop: str = ""
    opaque: str = ""


@dataclass
class SipMedia:
    host: str
    port: int
    payload_type: int
    local_port: int
    rtp_sock: socket.socket


class SipDialogError(RuntimeError):
    """REGISTER/INVITE failed."""


def parse_authenticate(header: str) -> SipAuth:
    realm = _quoted(header, "realm") or ""
    nonce = _quoted(header, "nonce") or ""
    if not realm or not nonce:
        raise SipDialogError("WWW-Authenticate missing realm/nonce")
    qop = _quoted(header, "qop") or _token(header, "qop")
    return SipAuth(
        realm=realm,
        nonce=nonce,
        algorithm=(_quoted(header, "algorithm") or _token(header, "algorithm") or "MD5"),
        qop="auth" if qop and "auth" in qop else "",
        opaque=_quoted(header, "opaque") or "",
    )


def digest_response(
    *,
    username: str,
    password: str,
    method: str,
    uri: str,
    auth: SipAuth,
    nc: str = "00000001",
    cnonce: str = "suflercnonce",
) -> str:
    ha1 = hashlib.md5(f"{username}:{auth.realm}:{password}".encode()).hexdigest()
    ha2 = hashlib.md5(f"{method}:{uri}".encode()).hexdigest()
    if auth.qop:
        raw = f"{ha1}:{auth.nonce}:{nc}:{cnonce}:{auth.qop}:{ha2}"
    else:
        raw = f"{ha1}:{auth.nonce}:{ha2}"
    return hashlib.md5(raw.encode()).hexdigest()


def authorization_header(
    *,
    username: str,
    password: str,
    method: str,
    uri: str,
    auth: SipAuth,
) -> str:
    response = digest_response(
        username=username,
        password=password,
        method=method,
        uri=uri,
        auth=auth,
    )
    parts = [
        f'Digest username="{username}"',
        f'realm="{auth.realm}"',
        f'nonce="{auth.nonce}"',
        f'uri="{uri}"',
        f'response="{response}"',
        f"algorithm={auth.algorithm or 'MD5'}",
    ]
    if auth.qop:
        parts.extend(["qop=auth", "nc=00000001", 'cnonce="suflercnonce"'])
    if auth.opaque:
        parts.append(f'opaque="{auth.opaque}"')
    return ", ".join(parts)


def parse_sdp_audio(body: str) -> tuple[str, int, int]:
    host = ""
    port = 0
    payload = 8
    for line in body.splitlines():
        stripped = line.strip()
        if stripped.startswith("c=") and "IP4" in stripped:
            host = stripped.split()[-1]
        elif stripped.startswith("m=audio"):
            bits = stripped.split()
            if len(bits) >= 4:
                port = int(bits[1])
                nums = [int(item) for item in bits[3:] if item.isdigit()]
                if 8 in nums:
                    payload = 8
                elif 0 in nums:
                    payload = 0
                elif nums:
                    payload = nums[0]
    if not host or not port:
        raise SipDialogError("SDP has no audio address")
    return host, port, payload


def _quoted(header: str, name: str) -> str:
    match = re.search(rf'{name}\s*=\s*"([^"]*)"', header, flags=re.I)
    return unquote(match.group(1)) if match else ""


def _token(header: str, name: str) -> str:
    match = re.search(rf"{name}\s*=\s*([^,\s]+)", header, flags=re.I)
    return match.group(1).strip().strip('"') if match else ""


def _local_ip(peer_host: str, peer_port: int = _SIP_PORT) -> str:
    override = (os.getenv("OKTELL_SIP_LOCAL_IP") or "").strip()
    if override:
        return override
    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        probe.connect((peer_host, peer_port))
        return probe.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        probe.close()


def _parse_message(raw: bytes) -> tuple[str, dict[str, str], str]:
    text = raw.decode("utf-8", errors="replace")
    head, _, body = text.partition("\r\n\r\n")
    lines = head.split("\r\n")
    status = lines[0] if lines else ""
    headers: dict[str, str] = {}
    for line in lines[1:]:
        match = _HDR.match(line)
        if match:
            headers[match.group("k").lower()] = match.group("v").strip()
    return status, headers, body


class SipUserAgent:
    def __init__(
        self,
        *,
        user: str,
        password: str,
        domain: str,
        peer_host: str,
        peer_port: int = _SIP_PORT,
        timeout: float = 8.0,
    ) -> None:
        self.user = user
        self.password = password
        self.domain = domain
        self.peer_host = peer_host
        self.peer_port = peer_port
        self.timeout = timeout
        self.call_id = f"{int(time.time())}-{random.randint(1000, 9999)}@{domain}"
        self.tag = f"sf{random.randint(10000, 99999)}"
        self.branch_seq = random.randint(1000, 9999)
        self.cseq = 0
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.settimeout(timeout)
        self.sock.bind(("0.0.0.0", 0))
        self.local_ip = _local_ip(peer_host, peer_port)
        self.local_port = self.sock.getsockname()[1]
        self.auth: SipAuth | None = None
        self.dialog_uri = ""
        self.dialog_to = ""

    def close(self) -> None:
        try:
            self.sock.close()
        except OSError:
            pass

    def _branch(self) -> str:
        self.branch_seq += 1
        return f"z9hG4bKsufler{self.branch_seq}"

    def _send(self, method: str, uri: str, to_header: str, extra: list[str], body: str = "") -> None:
        self.cseq += 1
        from_uri = f'"sufler" <sip:{self.user}@{self.domain}>'
        lines = [
            f"{method} {uri} SIP/2.0",
            f"Via: SIP/2.0/UDP {self.local_ip}:{self.local_port};rport;branch={self._branch()}",
            "Max-Forwards: 70",
            f"From: {from_uri};tag={self.tag}",
            to_header,
            f"Call-ID: {self.call_id}",
            f"CSeq: {self.cseq} {method}",
            f"Contact: <sip:{self.user}@{self.local_ip}:{self.local_port}>",
            "User-Agent: SuflerTelephony/0.1",
            *extra,
        ]
        if body:
            lines.append("Content-Type: application/sdp")
            lines.append(f"Content-Length: {len(body.encode())}")
            payload = "\r\n".join(lines) + "\r\n\r\n" + body
        else:
            lines.append("Content-Length: 0")
            payload = "\r\n".join(lines) + "\r\n\r\n"
        self.sock.sendto(payload.encode(), (self.peer_host, self.peer_port))

    def _recv(self) -> tuple[int, dict[str, str], str]:
        raw, _addr = self.sock.recvfrom(8192)
        status, headers, body = _parse_message(raw)
        match = re.search(r"SIP/2.0\s+(\d+)", status)
        code = int(match.group(1)) if match else 0
        logger.info("SIP %s <- %s", self.user, status.strip())
        return code, headers, body

    def _exchange(
        self, method: str, uri: str, to_header: str, extra: list[str], body: str = ""
    ) -> tuple[int, dict[str, str], str]:
        self._send(method, uri, to_header, extra, body)
        return self._recv_final()

    def _recv_final(self) -> tuple[int, dict[str, str], str]:
        code, headers, body = self._recv()
        tries = 0
        while code in {100, 180, 181, 182, 183} and tries < 8:
            code, headers, body = self._recv()
            tries += 1
        return code, headers, body

    def _ack(self, uri: str, to_hdr: str) -> None:
        payload = (
            f"ACK {uri} SIP/2.0\r\n"
            f"Via: SIP/2.0/UDP {self.local_ip}:{self.local_port};rport;branch={self._branch()}\r\n"
            f"Max-Forwards: 70\r\n"
            f"From: \"sufler\" <sip:{self.user}@{self.domain}>;tag={self.tag}\r\n"
            f"To: {to_hdr}\r\n"
            f"Call-ID: {self.call_id}\r\n"
            f"CSeq: {self.cseq} ACK\r\n"
            f"Content-Length: 0\r\n\r\n"
        )
        self.sock.sendto(payload.encode(), (self.peer_host, self.peer_port))

    def _with_auth(
        self,
        method: str,
        uri: str,
        to_header: str,
        extra: list[str],
        body: str = "",
    ) -> tuple[int, dict[str, str], str]:
        code, headers, resp_body = self._exchange(method, uri, to_header, list(extra), body)
        if code not in {401, 407}:
            return code, headers, resp_body
        auth_header = headers.get("www-authenticate") or headers.get("proxy-authenticate")
        if not auth_header:
            raise SipDialogError(f"{method} {code} without authenticate")
        if method == "INVITE":
            self._ack(uri, headers.get("to") or to_header.split(":", 1)[-1].strip())
        self.auth = parse_authenticate(auth_header)
        prefix = "Proxy-Authorization: " if code == 407 else "Authorization: "
        retry = [
            *extra,
            prefix
            + authorization_header(
                username=self.user,
                password=self.password,
                method=method,
                uri=uri,
                auth=self.auth,
            ),
        ]
        return self._exchange(method, uri, to_header, retry, body)

    def register(self) -> None:
        uri = f"sip:{self.domain}"
        to_header = f"To: <sip:{self.user}@{self.domain}>"
        code, _headers, _body = self._with_auth("REGISTER", uri, to_header, ["Expires: 300"])
        if code not in {200, 202}:
            raise SipDialogError(f"REGISTER failed {code} for {self.user}")

    def invite_recvonly(self, target: str) -> SipMedia:
        rtp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        rtp_sock.bind(("0.0.0.0", 0))
        rtp_port = rtp_sock.getsockname()[1]
        sdp = (
            f"v=0\r\n"
            f"o=- {int(time.time())} 1 IN IP4 {self.local_ip}\r\n"
            f"s=sufler-barge\r\n"
            f"c=IN IP4 {self.local_ip}\r\n"
            f"t=0 0\r\n"
            f"m=audio {rtp_port} RTP/AVP 8 0\r\n"
            f"a=rtpmap:8 PCMA/8000\r\n"
            f"a=rtpmap:0 PCMU/8000\r\n"
            f"a=recvonly\r\n"
        )
        to_header = f"To: <{target}>"
        code, headers, body = self._with_auth(
            "INVITE",
            target,
            to_header,
            ["Allow: INVITE, ACK, CANCEL, BYE", "Supported: replaces"],
            sdp,
        )
        tries = 0
        while code in {100, 180, 183} and tries < 5:
            code, headers, body = self._recv()
            tries += 1
        if code != 200:
            rtp_sock.close()
            raise SipDialogError(f"INVITE {target} failed {code}")
        host, port, payload = parse_sdp_audio(body)
        to_hdr = headers.get("to") or f"<{target}>"
        self.dialog_uri = target
        self.dialog_to = to_hdr
        self._ack(target, to_hdr)
        rtp_sock.settimeout(1.0)
        return SipMedia(
            host=host,
            port=port,
            payload_type=payload,
            local_port=rtp_port,
            rtp_sock=rtp_sock,
        )

    def hangup(self) -> None:
        """End the barge so the PBX will accept the next INVITE."""
        if not self.dialog_uri:
            return
        try:
            self._send("BYE", self.dialog_uri, f"To: {self.dialog_to}", [])
        except OSError:
            pass
        self.dialog_uri = ""


def sip_is_bye(raw: bytes) -> bool:
    line = raw.split(b"\r\n", 1)[0].lstrip()
    return line.startswith(b"BYE ") or line.startswith(b"CANCEL ")


def reply_ok(sock: socket.socket, raw: bytes, addr: tuple[str, int]) -> None:
    text = raw.decode("utf-8", errors="replace")
    headers: dict[str, str] = {}
    for line in text.split("\r\n")[1:]:
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        headers.setdefault(key.strip().lower(), value.strip())
    payload = (
        "SIP/2.0 200 OK\r\n"
        f"Via: {headers.get('via', '')}\r\n"
        f"From: {headers.get('from', '')}\r\n"
        f"To: {headers.get('to', '')}\r\n"
        f"Call-ID: {headers.get('call-id', '')}\r\n"
        f"CSeq: {headers.get('cseq', '1 BYE')}\r\n"
        "Content-Length: 0\r\n\r\n"
    )
    try:
        sock.sendto(payload.encode(), addr)
    except OSError:
        pass


def receive_rtp(
    media: SipMedia,
    *,
    stop_event: threading.Event,
    on_pcm: Callable[[bytes], None],
    sip_sock: socket.socket | None = None,
    should_redial: Callable[[], bool] | None = None,
) -> str:
    """Read RTP until stop, remote BYE, or a request to dial the line again."""
    from integrations.oktell.g711 import rtp_payload_to_pcm16

    if sip_sock is not None:
        sip_sock.setblocking(False)
    reason = "stopped"
    while not stop_event.is_set():
        if should_redial is not None and should_redial():
            reason = "redial"
            break
        if sip_sock is not None:
            try:
                packet, addr = sip_sock.recvfrom(8192)
            except (BlockingIOError, InterruptedError):
                pass
            except OSError:
                reason = "bye"
                break
            else:
                if sip_is_bye(packet):
                    reply_ok(sip_sock, packet, addr)
                    reason = "bye"
                    break
        try:
            packet, _addr = media.rtp_sock.recvfrom(2048)
        except socket.timeout:
            continue
        except OSError:
            reason = "bye"
            break
        if len(packet) < 12:
            continue
        header_len = 12 + 4 * (packet[0] & 0x0F)
        payload = packet[header_len:]
        if not payload:
            continue
        on_pcm(rtp_payload_to_pcm16(payload, media.payload_type))
    try:
        media.rtp_sock.close()
    except OSError:
        pass
    return reason
