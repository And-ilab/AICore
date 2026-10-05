"""G.711 A-law / µ-law → PCM16 (Oktell headset default is PCMA)."""

from __future__ import annotations


def _alaw_sample(byte: int) -> int:
    byte ^= 0x55
    sign = byte & 0x80
    exponent = (byte >> 4) & 0x07
    mantissa = byte & 0x0F
    sample = mantissa << 4
    if exponent > 0:
        sample += 0x100
    if exponent > 1:
        sample <<= exponent - 1
    sample += 8 if exponent == 0 else 0x84
    return -sample if sign else sample


def _ulaw_sample(byte: int) -> int:
    byte = ~byte & 0xFF
    sign = byte & 0x80
    exponent = (byte >> 4) & 0x07
    mantissa = byte & 0x0F
    sample = ((mantissa << 3) + 0x84) << exponent
    sample -= 0x84
    return -sample if sign else sample


def alaw_to_pcm16(payload: bytes) -> bytes:
    out = bytearray(len(payload) * 2)
    for index, byte in enumerate(payload):
        sample = max(-32768, min(32767, _alaw_sample(byte)))
        out[index * 2] = sample & 0xFF
        out[index * 2 + 1] = (sample >> 8) & 0xFF
    return bytes(out)


def ulaw_to_pcm16(payload: bytes) -> bytes:
    out = bytearray(len(payload) * 2)
    for index, byte in enumerate(payload):
        sample = max(-32768, min(32767, _ulaw_sample(byte)))
        out[index * 2] = sample & 0xFF
        out[index * 2 + 1] = (sample >> 8) & 0xFF
    return bytes(out)


def rtp_payload_to_pcm16(payload: bytes, pt: int) -> bytes:
    if pt == 0:
        return ulaw_to_pcm16(payload)
    return alaw_to_pcm16(payload)


def upsample_8k_to_16k(pcm16: bytes) -> bytes:
    if len(pcm16) < 2:
        return pcm16
    samples = [
        int.from_bytes(pcm16[index : index + 2], "little", signed=True)
        for index in range(0, len(pcm16) - 1, 2)
    ]
    stretched = bytearray()
    for index, sample in enumerate(samples):
        stretched += sample.to_bytes(2, "little", signed=True)
        nxt = samples[index + 1] if index + 1 < len(samples) else sample
        mid = (sample + nxt) // 2
        stretched += mid.to_bytes(2, "little", signed=True)
    return bytes(stretched)
