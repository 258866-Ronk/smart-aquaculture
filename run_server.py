# -*- coding: utf-8 -*-
"""服务端启动入口：同时启动 Flask HTTP 服务与 TCP 数据分发服务。

用法：python run_server.py [--port 5000] [--tcp-port 9000]
"""
import argparse
import json
import os
import sys
import threading

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)


def load_config():
    with open(os.path.join(BASE_DIR, "config.json"), "r", encoding="utf-8") as f:
        return json.load(f)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=None, help="HTTP 端口")
    parser.add_argument("--tcp-port", type=int, default=None, help="TCP 数据分发端口")
    args = parser.parse_args()

    config = load_config()
    if args.port:
        config["server"]["http_port"] = args.port
    if args.tcp_port:
        config["server"]["tcp_port"] = args.tcp_port

    from server.app_factory import create_app, create_tcp_server

    # TCP 数据分发服务（多客户端并发，后台线程）
    tcp_server = create_tcp_server(config)
    tcp_server.start()

    # Flask HTTP 服务
    app = create_app(config)
    http_port = int(config["server"].get("http_port", 5000))
    print("=" * 60)
    print("  智慧渔业数据分发平台已启动")
    print("  Web 大屏:   http://127.0.0.1:%d/" % http_port)
    print("  RESTful API: http://127.0.0.1:%d/api/v1/" % http_port)
    print("  TCP Server:  0.0.0.0:%d (JSON\\n 报文，多客户端并发)" % int(config["server"]["tcp_port"]))
    print("=" * 60)
    app.run(host=config["server"].get("host", "0.0.0.0"), port=http_port, threaded=True)


if __name__ == "__main__":
    main()
