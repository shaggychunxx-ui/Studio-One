"""
UCNET event type IDs from Android libucnet.so RTTI (LiNNNN template params).

Wire format for the two-byte tag is **big-endian** ASCII mnemonic:
  DiscoveryAlive 0x4441 → bytes 44 41 = b'DA'
  DiscoveryQuery 0x4451 → bytes 44 51 = b'DQ'
  ParamValue     0x5056 → bytes 50 56 = b'PV'
  KeepAlive      0x4B41 → bytes 4B 41 = b'KA'
"""

from __future__ import annotations

import struct
from enum import IntEnum


class EventType(IntEnum):
    BINARY = 0x424F  # BO  BinaryEvent
    MESSAGE_CHUNK = 0x434B  # CK  MessageChunkEvent
    DISCOVERY_ALIVE = 0x4441  # DA  DiscoveryAliveEvent
    DEBUG = 0x4442  # DB  DebugEvent
    DISCOVERY_LEAVE = 0x444C  # DL  DiscoveryLeaveEvent
    DISCOVERY_QUERY = 0x4451  # DQ  DiscoveryQueryEvent
    EXTENSION_QUERY = 0x4551  # EQ  ExtensionQueryEvent
    FILE_ABORT = 0x4641  # FA  FileAbortEvent
    FILE_DATA = 0x4644  # FD  FileDataEvent
    FILE_REQUEST = 0x4652  # FR  FileRequestEvent
    FILE_DATA_RATE = 0x4653  # FS  FileDataRateEvent
    # EncodedMessageEvent — large UCXML/component payloads (RTTI Li19021)
    ENCODED_MESSAGE = 0x4A4D  # JM  EncodedMessageEvent (0x4A4D=19021)
    KEEP_ALIVE = 0x4B41  # KA  KeepAliveEvent
    LOOPBACK_QUERY = 0x4C51  # LQ  LoopbackQueryEvent
    LOOPBACK_REPLY = 0x4C52  # LR  LoopbackReplyEvent
    MULTI_MIDI = 0x4D41  # MA  MultiMidiMessageEvent
    METER8 = 0x4D42  # MB  MeterEvent8
    MUSIC_INPUT = 0x4D49  # MI  MusicInputEvent
    MIDI_MESSAGE = 0x4D4D  # MM  MidiMessageEvent
    SURROUND_METER = 0x4D52  # MR  SurroundMeterEvent
    METER16 = 0x4D53  # MS  MeterEvent16
    NO_OP = 0x4E4F  # NO  NoOpEvent
    PARAM_COLOR = 0x5043  # PC  ParamColorEvent
    PARAM_EDIT = 0x5045  # PE  ParamEditEvent
    PARAM_INCREMENT = 0x5049  # PI  ParamIncrementEvent
    PARAM_STRING_LIST = 0x504C  # PL  ParamStringListEvent
    PARAM_MODE = 0x504D  # PM  ParamModeEvent
    PARAM_RANGE = 0x5052  # PR  ParamRangeEvent
    PARAM_STRING = 0x5053  # PS  ParamStringEvent
    PARAM_VALUE = 0x5056  # PV  ParamValueEvent
    MIDI_LONG_SYSEX = 0x534C  # SL  MidiLongSysexEvent
    MIDI_SHORT_SYSEX = 0x5353  # SS  MidiShortSysexEvent
    TIME_CODE = 0x5443  # TC  TimeCodeEvent
    UDP_MAPPING = 0x554D  # UM  UDPMappingEvent


def event_tag_be(event: int | EventType) -> bytes:
    return struct.pack(">H", int(event))


def event_name(event: int) -> str:
    try:
        return EventType(event).name
    except ValueError:
        return f"UNK_0x{event:04X}"


def pack_uc_header(version: int = 1) -> bytes:
    return b"UC" + struct.pack(">H", version)


def parse_event_tag(data: bytes, offset: int = 0) -> int | None:
    if len(data) < offset + 2:
        return None
    return struct.unpack_from(">H", data, offset)[0]
