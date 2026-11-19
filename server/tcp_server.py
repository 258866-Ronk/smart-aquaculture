# -*- coding: utf-8 -*-
"""TCP Server：一个 Server 对应多个 Client 并发（线程池 + 线程 per client）。

支持两种报文：
1. JSON(UTF-8) 以 \\n 分隔（SRS 6.2 约定，主要方式）
2. 二进制帧 0xAA55...（RS232 帧，可直接经 TCP 透传）
心跳：客户端发送 {"type":"heartbeat"}，服务端回复 pong。
"""
import json
import socket
import threading
from datetime import datetime

import server.db as db
from server.alerts import check_metrics
from server.protocol import FRAME_HEAD, decode_tcp_stream, parse_frame


class TCPServer:
    def __init__(self, host: str, port: int, config: dict):
        self.host = host
        self.port = port
        self.config = config
        self.thresholds = config.get("thresholds", {})
        self.clients = {}  # addr -> socket
        self.lock = threading.Lock()
        self._running = False
        self.stats = {"received": 0, "invalid": 0, "alerts": 0}

    # ---------- 生命周期 ----------
    def start(self, blocking: bool = False):
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._sock.bind((self.host, self.port))
        self._sock.listen(self.config.get("tcp", {}).get("max_clients", 64))
        self._running = True
        print("[TCP] 监听 %s:%d，等待采集客户端接入..." % (self.host, self.port))
        t = threading.Thread(target=self._accept_loop, daemon=True)
        t.start()
        if blocking:
            t.join()

    def stop(self):
        self._running = False
        try:
            self._sock.close()
        except OSError:
            pass

    # ---------- 并发接入 ----------
    def _accept_loop(self):
        while self._running:
            try:
                conn, addr = self._sock.accept()
            except OSError:
                break
            conn.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            with self.lock:
                self.clients[addr] = conn
            print("[TCP] 客户端接入: %s:%s（当前 %d 个）" % (addr[0], addr[1], len(self.clients)))
            threading.Thread(target=self._client_loop, args=(conn, addr), daemon=True).start()

    def _client_loop(self, conn: socket.socket, addr):
        buffer = b""
        try:
            while self._running:
                data = conn.recv(4096)
                if not data:
                    break
                # 二进制帧直接解析；否则走 JSON 流
                if data[:2] == FRAME_HEAD:
                    self._handle_binary_frame(conn, data)
                    continue
                messages, buffer = decode_tcp_stream(buffer + data)
                for msg in messages:
                    self._handle_message(conn, msg)
        except (ConnectionResetError, OSError):
            pass
        finally:
            with self.lock:
                self.clients.pop(addr, None)
            print("[TCP] 客户端断开: %s:%s（当前 %d 个）" % (addr[0], addr[1], len(self.clients)))
            conn.close()

    # ---------- 报文处理 ----------
    def _handle_message(self, conn: socket.socket, msg: dict):
        if msg.get("type") == "heartbeat":
            conn.sendall(b'{"type":"pong"}\n')
            return
        if msg.get("type") == "batch":  # 断网续传补传的批量数据
            for item in msg.get("records", []):
                self._save_water_record(item)
            conn.sendall(b'{"type":"batch_ack","count":%d}\n' % len(msg.get("records", [])))
            return
        if "metrics" in msg:
            self._save_water_record(msg)
            conn.sendall(b'{"type":"ack"}\n')

    def _handle_binary_frame(self, conn: socket.socket, data: bytes):
        try:
            parsed = parse_frame(data)
        except ValueError as e:
            self.stats["invalid"] += 1
            print("[TCP] 非法帧丢弃: %s" % e)
            return
        metrics = parsed.get("metrics")
        if metrics:
            self._save_water_record({
                "device_id": "ADDR-%02X" % parsed["device_addr"],
                "pond_id": "TANK-A",
                "timestamp": datetime.now().isoformat(timespec="seconds"),
                "metrics": metrics,
            })
        conn.sendall(b'{"type":"ack","crc":"ok"}\n')

    def _save_water_record(self, msg: dict):
        pond_id = str(msg.get("pond_id", "UNKNOWN"))[:32]
        device_id = str(msg.get("device_id", ""))[:64]
        ts = str(msg.get("timestamp", datetime.now().isoformat(timespec="seconds")))
        ts = ts.replace("T", " ")[:19]
        m = msg.get("metrics", {})
        db.execute(
            "INSERT INTO t_water_quality(pond_id, device_id, temperature, ph, dissolved_oxygen, ammonia, collect_time, create_time) "
            "VALUES (?,?,?,?,?,?,?,datetime('now','localtime'))",
            (pond_id, device_id, m.get("temperature"), m.get("ph"),
             m.get("dissolved_oxygen"), m.get("ammonia"), ts))
        self.stats["received"] += 1
        alerts = check_metrics(pond_id, m, self.thresholds, ts)
        if alerts:
            self.stats["alerts"] += len(alerts)
            for a in alerts:
                print("[告警] %s" % a["message"])
