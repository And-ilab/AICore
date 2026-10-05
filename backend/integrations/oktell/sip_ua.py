"""Plan and place SIP barge calls 02*/03*1xxx from 2xxx accounts."""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from dataclasses import dataclass

from integrations.oktell.live_asr import LegTranscriber
from integrations.oktell.sip_dialog import (
    SipDialogError,
    SipUserAgent,
    receive_rtp,
)
from integrations.oktell.sip_pool import SipAccount, sip_domain, sip_packet_host
from integrations.oktell.webhook import listen_codes

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SipDial:
    speaker: str
    code: str
    target: str
    account: SipAccount

    def as_dict(self) -> dict[str, str]:
        return {
            "speaker": self.speaker,
            "code": self.code,
            "target": self.target,
            "sip_user": self.account.user,
            "sip_uri": self.account.uri,
        }


def plan_dual_leg(called_id: str, client_account: SipAccount, operator_account: SipAccount) -> list[SipDial]:
    codes = listen_codes(called_id)
    host = client_account.server or "oktell"
    client = SipDial(
        speaker="client",
        code="02",
        target=f"sip:{codes['client']}@{host}",
        account=client_account,
    )
    if codes["client"] == codes["operator"]:
        return [client]
    return [
        client,
        SipDial(
            speaker="operator",
            code="03",
            target=f"sip:{codes['operator']}@{host}",
            account=operator_account,
        ),
    ]


def invite_summary(dials: list[SipDial]) -> list[dict[str, str]]:
    planned = [dial.as_dict() for dial in dials]
    for row in planned:
        logger.info(
            "Oktell SIP barge planned user=%s target=%s",
            row["sip_user"],
            row["target"],
        )
    return planned


def place_barge_leg(
    dial: SipDial,
    *,
    stop_event: threading.Event,
    on_text: Callable[[str, bool], None],
    should_redial: Callable[[], bool] | None = None,
    on_up: Callable[[], None] | None = None,
) -> str:
    """REGISTER + INVITE recvonly, then RTP → Vosk until stop, BYE, or redial."""
    if not dial.account.password:
        raise SipDialogError(f"empty SIP password for {dial.account.user}")
    agent = SipUserAgent(
        user=dial.account.user,
        password=dial.account.password,
        domain=sip_domain() or dial.account.server,
        peer_host=sip_packet_host() or dial.account.proxy or dial.account.server,
    )
    remote_bye = False
    try:
        agent.register()
        if should_redial is not None and should_redial():
            return "redial"
        media = agent.invite_recvonly(dial.target)
        if on_up is not None:
            on_up()
        transcriber = LegTranscriber(on_text)
        if not transcriber.ready:
            logger.warning(
                "SIP up user=%s target=%s but Vosk model is missing",
                dial.account.user,
                dial.target,
            )
        reason = receive_rtp(
            media,
            stop_event=stop_event,
            on_pcm=transcriber.feed,
            sip_sock=agent.sock,
            should_redial=should_redial,
        )
        transcriber.close()
        remote_bye = reason == "bye"
        if reason in {"bye", "redial"}:
            return reason
        return "heard" if transcriber.ready else "listening"
    finally:
        if not remote_bye:
            agent.hangup()
        agent.close()
