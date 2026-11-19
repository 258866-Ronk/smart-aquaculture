# -*- coding: utf-8 -*-
"""通信协议模块：RS232 帧协议 + CRC16-Modbus + TCP JSON 报文。

帧格式（水质传感器）：
  帧头(2B: 0xAA 0x55) 设备地址(1B) 功能码(1B: 0x01水质/0x02气象)
  数据长度(1B) 数据域(NB) CRC16(2B, Modbus) 帧尾(1B: 0x0D)
数据域：温度(2B) pH(2B) 溶解氧(2B) 氨氮(2B)，均为实际值 x10 的整型（大端）。
CRC 范围：设备地址 ~ 数据域最后一字节。
"""
import json
import struct
from datetime import datetime

FRAME_HEAD = b"\xAA\x55"
FRAME_TAIL = 0x0D
FUNC_WATER = 0x01
FUNC_WEATHER = 0x02


def crc16_modbus(data: bytes) -> int:
    """CRC16-Modbus 校验。"""
    crc = 0xFFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            if crc & 0x0001:
                crc = (crc >> 1) ^ 0xA001
            else:
                crc >>= 1
    return crc & 0xFFFF


def build_frame(device_addr: int, func: int, payload: bytes) -> bytes:
    """组装一帧完整报文。"""
    body = bytes([device_addr & 0xFF, func & 0xFF, len(payload)]) + payload
    crc = crc16_modbus(body)
    return FRAME_HEAD + body + struct.pack("<H", crc) + bytes([FRAME_TAIL])


def build_water_payload(temperature: float, ph: float, dissolved_oxygen: float, ammonia: float) -> bytes:
    """水质数据域：4 个 x10 放大整型，每个 2 字节大端。"""
    values = [
        int(round(temperature * 10)),
        int(round(ph * 10)),
        int(round(dissolved_oxygen * 10)),
        int(round(ammonia * 10)),
    ]
    return b"".join(struct.pack(">H", v & 0xFFFF) for v in values)


def parse_frame(frame: bytes):
    """解析并校验一帧报文。返回 dict 或抛出 ValueError。"""
    if len(frame) < 9:
        raise ValueError("帧长度不足")
    if frame[:2] != FRAME_HEAD:
        raise ValueError("帧头错误")
    if frame[-1] != FRAME_TAIL:
        raise ValueError("帧尾错误")
    body = frame[2:-3]
    crc_recv = struct.unpack("<H", frame[-3:-1])[0]
    if crc16_modbus(body) != crc_recv:
        raise ValueError("CRC 校验失败")
    addr = body[0]
    func = body[1]
    length = body[2]
    payload = body[3:]
    if len(payload) != length:
        raise ValueError("数据长度不匹配")
    result = {"device_addr": addr, "func": func, "raw": frame.hex().upper()}
    if func == FUNC_WATER and length >= 8:
        vals = struct.unpack(">HHHH", payload[:8])
        result["metrics"] = {
            "temperature": vals[0] / 10.0,
            "ph": vals[1] / 10.0,
            "dissolved_oxygen": vals[2] / 10.0,
            "ammonia": vals[3] / 10.0,
        }
    else:
        result["payload"] = payload.hex().upper()
    return result


def encode_tcp_message(device_id: str, pond_id: str, metrics: dict, timestamp: str = None) -> bytes:
    """TCP 上报报文：JSON(UTF-8) + 换行符。"""
    msg = {
        "device_id": device_id,
        "pond_id": pond_id,
        "timestamp": timestamp or datetime.now().isoformat(timespec="seconds"),
        "metrics": metrics,
    }
    return (json.dumps(msg, ensure_ascii=False) + "\n").encode("utf-8")


def decode_tcp_stream(buffer: bytes):
    """从字节流中按换行符切分 JSON 报文。

    返回 (messages: list[dict], remainder: bytes)。
    非法 JSON 行会被丢弃。
    """
    messages = []
    while b"\n" in buffer:
        line, buffer = buffer.split(b"\n", 1)
        line = line.strip()
        if not line:
            continue
        try:
            messages.append(json.loads(line.decode("utf-8")))
        except (ValueError, UnicodeDecodeError):
            continue  # 丢弃非法帧，保证脏数据不入库
    return messages, buffer
