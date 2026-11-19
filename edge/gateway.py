# -*- coding: utf-8 -*-
"""边缘网关 / 采集终端（Python 采集程序）。

职责（SRS 边缘层）：
- 按 RS232 帧协议（0xAA55 + CRC16）读取串口数据（pyserial 可选，未接硬件时走内置传感器模拟）
- 以 TCP Client 长连接向 Flask 服务端（TCP Server）推送 JSON 报文
- 断网时本地缓存（JSONL 文件），恢复后批量补传
- 采集日志记录
"""
import json
import os
import random
import signal
import socket
import sys
import time
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

from server.protocol import build_frame, build_water_payload, encode_tcp_message  # noqa: E402

CONFIG_PATH = os.path.join(BASE_DIR, "config.json")


def load_config():
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def log(msg):
    print("[%s] %s" % (datetime.now().strftime("%H:%M:%S"), msg), flush=True)


class EdgeGateway:
    def __init__(self, config):
        self.cfg = config["collection"]
        self.pond = config["ponds"][0]["pond_id"]
        self.device_id = "EDGE-GW-01"
        self.interval = self.cfg.get("interval_seconds", 5)
        self.host = self.cfg.get("tcp_host", "127.0.0.1")
        self.port = int(self.cfg.get("tcp_port", 9000))
        self.cache_dir = os.path.join(BASE_DIR, self.cfg.get("cache_dir", "data/edge_cache"))
        os.makedirs(self.cache_dir, exist_ok=True)
        self.cache_file = os.path.join(self.cache_dir, "offline_cache.jsonl")
        self.sock = None
        self.buffer = b""
        self._stop = False
        self.serial_cfg = self.cfg.get("serial", {})
        self.serial = None
        self.pond_list = [self.pond]
        if self.serial_cfg.get("enabled"):
            self._open_serial()

    def _open_serial(self):
        try:
            import serial  # pyserial
            s = self.serial_cfg
            self.serial = serial.Serial(s["port"], s.get("baudrate", 9600),
                                        bytesize=s.get("bytesize", 8),
                                        parity=s.get("parity", "N"),
                                        stopbits=s.get("stopbits", 1), timeout=2)
            log("串口已打开: %s @%d" % (s["port"], s.get("baudrate", 9600)))
        except Exception as e:
            log("串口打开失败(%s)，回退到内置传感器模拟" % e)
            self.serial = None

    # ---------- 传感数据来源 ----------
    def read_serial_frame(self):
        """从串口按帧读取并解析（帧头 0xAA55 起始）。"""
        raw = b""
        while not raw.endswith(b"\r"):
            b1 = self.serial.read(1)
            if not b1:
                return None
            raw += b1
            if len(raw) > 64:
                return None
            if len(raw) < 2 and raw not in (b"\xAA", b"\xAA\x55", b""):
                raw = b""
            elif len(raw) >= 2 and not raw.startswith(b"\xAA\x55"):
                raw = raw[1:]
        from server.protocol import parse_frame
        return parse_frame(raw)

    def simulate_reading(self):
        """内置传感器模拟：昼夜溶氧周期 + 随机扰动（FR-01-05 硬件信号模拟）。"""
        hour = datetime.now().hour
        do_base = 4.2 + 2.2 * (0.5 + 0.5 * __import__("math").sin((hour - 6) / 24.0 * 2 * 3.14159))
        return {
            "temperature": round(random.gauss(27.5, 1.2), 1),
            "ph": round(random.gauss(7.8, 0.15), 1),
            "dissolved_oxygen": round(max(1.5, random.gauss(do_base, 0.4)), 2),
            "ammonia": round(abs(random.gauss(0.3, 0.12)), 3),
        }

    # ---------- 网络与缓存 ----------
    def connect(self):
        try:
            self.sock = socket.create_connection((self.host, self.port), timeout=5)
            self.sock.settimeout(5)
            log("已连接服务端 %s:%d" % (self.host, self.port))
            return True
        except OSError:
            self.sock = None
            return False

    def send(self, payload: bytes):
        self.sock.sendall(payload)
        try:
            ack = self.sock.recv(256)
            return ack
        except socket.timeout:
            return b""

    def cache_offline(self, msg: dict):
        with open(self.cache_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(msg, ensure_ascii=False) + "\n")

    def flush_cache(self):
        """断网续传：恢复连接后补传缓存数据。"""
        if not os.path.exists(self.cache_file):
            return 0
        records = []
        with open(self.cache_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        records.append(json.loads(line))
                    except ValueError:
                        continue
        if not records:
            os.remove(self.cache_file)
            return 0
        batch = {"type": "batch", "records": records}
        self.send((json.dumps(batch, ensure_ascii=False) + "\n").encode("utf-8"))
        os.remove(self.cache_file)
        return len(records)

    # ---------- 塘口自动发现 ----------
    def fetch_ponds(self):
        """从服务端拉取全部塘口（含用户新建的），失败时回退到 config.json。

        这样在 Web 页面「塘口管理」新增塘口后，模拟传感器会在 ~1 分钟内自动接入。
        """
        try:
            import urllib.request
            with urllib.request.urlopen("http://127.0.0.1:5000/api/v1/ponds", timeout=3) as r:
                data = json.loads(r.read().decode("utf-8"))
            if data.get("code") == 0 and data.get("data"):
                ids = [p["pond_id"] for p in data["data"]]
                if ids != self.pond_list:
                    log("塘口列表更新: %s" % ", ".join(ids))
                return ids
        except Exception:
            pass
        return self.pond_list or [p["pond_id"] for p in load_config()["ponds"]]

    # ---------- 主循环 ----------
    def run(self):
        self.pond_list = [self.pond]
        log("边缘网关启动：采集间隔 %ds，缓存目录 %s，塘口自动发现已开启" % (self.interval, self.cache_dir))
        seq = 0
        cycle = 0
        while not self._stop:
            try:
                if self.sock is None and not self.connect():
                    time.sleep(min(self.interval, 5))
                    continue
                cycle += 1
                if cycle % 4 == 1:  # 约 20 秒刷新一次塘口列表
                    self.pond_list = self.fetch_ponds()
                # 数据来源：串口帧 or 模拟
                if self.serial:
                    parsed = self.read_serial_frame()
                    if parsed and "metrics" in parsed:
                        batch = [(self.pond, parsed["metrics"])]
                    else:
                        time.sleep(self.interval)
                        continue
                else:
                    batch = [(pond, self.simulate_reading()) for pond in self.pond_list]
                ts = datetime.now().isoformat(timespec="seconds")
                msgs, payloads = [], []
                for pond, metrics in batch:
                    dev = "%s-%s" % (self.device_id, pond) if len(self.pond_list) > 1 else self.device_id
                    msgs.append({"device_id": dev, "pond_id": pond, "timestamp": ts, "metrics": metrics})
                    payloads.append(encode_tcp_message(dev, pond, metrics, ts))
                try:
                    for msg, payload in zip(msgs, payloads):
                        self.send(payload)
                        seq += 1
                    log("上报 #%d 共 %d 个塘口" % (seq, len(payloads)))
                    n = self.flush_cache()
                    if n:
                        log("断网缓存已补传 %d 条" % n)
                except OSError:
                    for msg in msgs:
                        self.cache_offline(msg)
                    self.sock = None
                    log("连接断开，数据已本地缓存（共待补传）")
                time.sleep(self.interval)
            except KeyboardInterrupt:
                break
            except Exception as e:
                log("采集异常: %s（3 秒后重试）" % e)
                self.sock = None
                time.sleep(3)
        log("边缘网关停止")

    def stop(self, *_):
        self._stop = True


def main():
    config = load_config()
    gw = EdgeGateway(config)
    signal.signal(signal.SIGINT, gw.stop)
    signal.signal(signal.SIGTERM, gw.stop)
    gw.run()


if __name__ == "__main__":
    main()
