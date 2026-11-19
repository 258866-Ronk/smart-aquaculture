# -*- coding: utf-8 -*-
"""Flask 应用工厂：静态大屏 + RESTful API。"""
import os

from flask import Flask, jsonify, send_from_directory

import server.db as db
from server.api import api_bp
from server.tcp_server import TCPServer

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def create_app(config: dict) -> Flask:
    app = Flask(__name__, static_folder=None)
    app.config["THRESHOLDS"] = config.get("thresholds", {})
    app.config["CONFIG"] = config
    app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 0   # 前端迭代频繁，禁止浏览器缓存静态文件
    db.init_db(config)
    app.register_blueprint(api_bp)

    web_dir = os.path.join(BASE_DIR, "web")

    @app.get("/")
    def index():
        return send_from_directory(web_dir, "index.html")

    @app.get("/<path:path>")
    def static_files(path):
        return send_from_directory(web_dir, path)

    @app.get("/data/images/<path:name>")
    def image_files(name):
        img_dir = os.path.join(BASE_DIR, "data", "images")
        return send_from_directory(img_dir, name)

    @app.errorhandler(404)
    def not_found(_):
        return jsonify({"code": 404, "message": "not found", "data": None}), 404

    @app.errorhandler(500)
    def server_error(e):  # 统一异常响应
        return jsonify({"code": 500, "message": str(e), "data": None}), 500

    return app


def create_tcp_server(config: dict) -> TCPServer:
    db.init_db(config)
    s = config.get("server", {})
    return TCPServer(s.get("host", "0.0.0.0"), int(s.get("tcp_port", 9000)), config)
