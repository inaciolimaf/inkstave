"""y-protocols message framing (spec 28).

Implements the standard ``y-protocols`` wire format so browser ``y-websocket``
clients (spec 31) interoperate. We reuse pycrdt's var-uint/var-bytes
encoders/decoders rather than hand-rolling varints.

Wire format (outer tag byte = var-uint message type):
- ``MESSAGE_SYNC`` (0): var-uint sync-type, then a var-bytes payload
  (``SYNC_STEP_1`` + state vector, ``SYNC_STEP_2`` + update, ``SYNC_UPDATE`` + update).
- ``MESSAGE_AWARENESS`` (1): a var-bytes awareness-update payload.
"""

from __future__ import annotations

from dataclasses import dataclass

from pycrdt import Decoder, write_message, write_var_uint

MESSAGE_SYNC = 0
MESSAGE_AWARENESS = 1

SYNC_STEP_1 = 0
SYNC_STEP_2 = 1
SYNC_UPDATE = 2


@dataclass(frozen=True, slots=True)
class SyncStep1:
    state_vector: bytes


@dataclass(frozen=True, slots=True)
class SyncStep2:
    update: bytes


@dataclass(frozen=True, slots=True)
class SyncUpdate:
    update: bytes


@dataclass(frozen=True, slots=True)
class AwarenessMessage:
    update: bytes


@dataclass(frozen=True, slots=True)
class UnknownMessage:
    data: bytes


Message = SyncStep1 | SyncStep2 | SyncUpdate | AwarenessMessage | UnknownMessage


def read_message(data: bytes) -> Message:
    """Parse a wire message into a typed union. Never raises — malformed or
    unknown input decodes to :class:`UnknownMessage`."""
    try:
        decoder = Decoder(data)
        message_type = decoder.read_var_uint()
        if message_type == MESSAGE_SYNC:
            sync_type = decoder.read_var_uint()
            payload = decoder.read_message()
            if payload is None:
                return UnknownMessage(data)
            if sync_type == SYNC_STEP_1:
                return SyncStep1(payload)
            if sync_type == SYNC_STEP_2:
                return SyncStep2(payload)
            if sync_type == SYNC_UPDATE:
                return SyncUpdate(payload)
            return UnknownMessage(data)
        if message_type == MESSAGE_AWARENESS:
            payload = decoder.read_message()
            if payload is None:
                return UnknownMessage(data)
            return AwarenessMessage(payload)
        return UnknownMessage(data)
    except Exception:
        return UnknownMessage(data)


def encode_sync_step1(state_vector: bytes) -> bytes:
    return write_var_uint(MESSAGE_SYNC) + write_var_uint(SYNC_STEP_1) + write_message(state_vector)


def encode_sync_step2(update: bytes) -> bytes:
    return write_var_uint(MESSAGE_SYNC) + write_var_uint(SYNC_STEP_2) + write_message(update)


def encode_update(update: bytes) -> bytes:
    return write_var_uint(MESSAGE_SYNC) + write_var_uint(SYNC_UPDATE) + write_message(update)


def encode_awareness(awareness_update: bytes) -> bytes:
    return write_var_uint(MESSAGE_AWARENESS) + write_message(awareness_update)
