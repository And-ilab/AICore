"""Map Oktell phoneevents onto the dual-leg ASR pipeline (VI.2).

Lifecycle:
  phoneevent_ringstarted  → create/update call session
  phoneevent_commstarted  → start ASR on operator + client legs
  phoneevent_commstopped  → stop ASR and finalize session
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping, MutableMapping, Sequence

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AudioLeg:
    """One telephony audio leg for dual-leg ASR (INT-T06)."""

    leg: str
    speaker: str
    audio_path: str
    codec: str = "PCM_S16LE"
    sample_rate_hz: int = 8000
    status: str = "placeholder"

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> AudioLeg:
        return cls(
            leg=str(payload.get("leg") or ""),
            speaker=str(payload.get("speaker") or ""),
            audio_path=str(payload.get("audio_path") or ""),
            codec=str(payload.get("codec") or "PCM_S16LE"),
            sample_rate_hz=int(payload.get("sample_rate_hz") or 8000),
            status=str(payload.get("status") or "placeholder"),
        )


@dataclass
class CallSession:
    """In-memory SuflerTelephony call session keyed by Oktell chainid."""

    chain_id: str
    userlogin: str = ""
    caller_id: str = ""
    userid: str = ""
    commutation_id: str | None = None
    state: str = "idle"
    legs: tuple[AudioLeg, ...] = ()
    record_links: Mapping[str, str] = field(default_factory=dict)
    metadata: MutableMapping[str, Any] = field(default_factory=dict)


AsrStartHandler = Callable[[CallSession, Sequence[AudioLeg]], Any]
AsrStopHandler = Callable[[CallSession], Any]
RingHandler = Callable[[CallSession], Any]


class AsrPipeline:
    """ASR start/stop hooks driven by Oktell events."""

    def __init__(
        self,
        *,
        on_ring: RingHandler | None = None,
        on_asr_start: AsrStartHandler | None = None,
        on_asr_stop: AsrStopHandler | None = None,
    ) -> None:
        self.on_ring = on_ring
        self.on_asr_start = on_asr_start
        self.on_asr_stop = on_asr_stop
        self._sessions: dict[str, CallSession] = {}
        self.started_sessions: list[CallSession] = []
        self.stopped_sessions: list[CallSession] = []

    @property
    def sessions(self) -> Mapping[str, CallSession]:
        return self._sessions

    def get_session(self, chain_id: str) -> CallSession | None:
        return self._sessions.get(chain_id)

    def handle_event(self, event_name: str, payload: Mapping[str, Any]) -> CallSession | None:
        if event_name == "phoneevent_ringstarted":
            return self._on_ring(payload)
        if event_name == "phoneevent_commstarted":
            return self._on_comm_started(payload)
        if event_name == "phoneevent_commstopped":
            return self._on_comm_stopped(payload)
        logger.debug("Ignoring Oktell event %s", event_name)
        return None

    def _session_from_payload(self, payload: Mapping[str, Any]) -> CallSession:
        chain_id = str(payload.get("chainid") or "").strip()
        if not chain_id:
            raise ValueError("phoneevent payload requires chainid")
        session = self._sessions.get(chain_id)
        if session is None:
            session = CallSession(chain_id=chain_id)
            self._sessions[chain_id] = session
        session.userlogin = str(payload.get("userlogin") or session.userlogin)
        session.caller_id = str(payload.get("callerid") or session.caller_id)
        session.userid = str(payload.get("userid") or session.userid)
        commutation_id = payload.get("commutationid")
        if commutation_id:
            session.commutation_id = str(commutation_id)
        return session

    def _on_ring(self, payload: Mapping[str, Any]) -> CallSession:
        session = self._session_from_payload(payload)
        session.state = "ringing"
        session.metadata["ring_qid"] = payload.get("qid")
        if self.on_ring is not None:
            self.on_ring(session)
        return session

    def _on_comm_started(self, payload: Mapping[str, Any]) -> CallSession:
        session = self._session_from_payload(payload)
        raw_legs = payload.get("mock_audio_legs") or payload.get("audio_legs") or []
        if not isinstance(raw_legs, Sequence) or isinstance(raw_legs, (str, bytes)):
            raise ValueError("commstarted payload requires audio legs sequence")
        legs = tuple(AudioLeg.from_mapping(item) for item in raw_legs)
        if not legs:
            # Real Oktell may omit mock legs; still open an empty dual-leg slot.
            legs = (
                AudioLeg(leg="operator_leg", speaker="operator", audio_path=""),
                AudioLeg(leg="client_leg", speaker="client", audio_path=""),
            )
        speakers = {leg.speaker for leg in legs}
        if not {"operator", "client"}.issubset(speakers):
            raise ValueError("dual-leg ASR requires operator and client speakers")

        session.state = "active"
        session.legs = legs
        session.metadata["comm_started_qid"] = payload.get("qid")
        self.started_sessions.append(session)
        if self.on_asr_start is not None:
            self.on_asr_start(session, legs)
        else:
            logger.info(
                "ASR start chain_id=%s commutation_id=%s legs=%s",
                session.chain_id,
                session.commutation_id,
                [(leg.leg, leg.speaker, leg.audio_path) for leg in legs],
            )
        return session

    def _on_comm_stopped(self, payload: Mapping[str, Any]) -> CallSession:
        chain_id = str(payload.get("chainid") or "").strip()
        session = self._sessions.get(chain_id)
        if session is None:
            session = self._session_from_payload(payload)
        session.state = "stopped"
        record_links = payload.get("mock_recordlinks") or payload.get("recordlinks") or {}
        if isinstance(record_links, Mapping):
            session.record_links = {
                str(key): str(value) for key, value in record_links.items()
            }
        session.metadata["comm_stopped_qid"] = payload.get("qid")
        self.stopped_sessions.append(session)
        if self.on_asr_stop is not None:
            self.on_asr_stop(session)
        else:
            logger.info(
                "ASR stop chain_id=%s commutation_id=%s",
                session.chain_id,
                session.commutation_id,
            )
        return session
