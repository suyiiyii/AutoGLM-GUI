"""Scrcpy protocol helpers aligned with ya-webadb implementations."""

from __future__ import annotations

from dataclasses import dataclass

SCRCPY_CODEC_H264 = 0x68323634
SCRCPY_CODEC_H265 = 0x68323635
SCRCPY_CODEC_AV1 = 0x00617631

SCRCPY_CODEC_NAME_TO_ID: dict[str, int] = {
    "h264": SCRCPY_CODEC_H264,
    "h265": SCRCPY_CODEC_H265,
    "av1": SCRCPY_CODEC_AV1,
}

SCRCPY_KNOWN_CODECS = set(SCRCPY_CODEC_NAME_TO_ID.values())

PTS_CONFIG = 1 << 63
PTS_KEYFRAME = 1 << 62


@dataclass
class ScrcpyVideoStreamMetadata:
    device_name: str | None
    width: int | None
    height: int | None
    codec: int


@dataclass
class ScrcpyMediaStreamPacket:
    type: str
    data: bytes
    keyframe: bool | None = None
    pts: int | None = None


@dataclass
class ScrcpyVideoStreamOptions:
    send_device_meta: bool = True
    send_codec_meta: bool = True
    send_frame_meta: bool = True
    send_dummy_byte: bool = True
    video_codec: str = "h264"
