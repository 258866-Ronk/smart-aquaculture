# -*- coding: utf-8 -*-
"""数据库层：默认 SQLite（零依赖、免安装），配置可切换 MySQL。"""
import os
import sqlite3
import threading
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_lock = threading.Lock()
_conn = None
_db_type = "sqlite"


def _now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def init_db(config: dict):
    """初始化数据库连接与表结构。"""
    global _conn, _db_type
    db_conf = config.get("database", {})
    _db_type = db_conf.get("type", "sqlite")
    if _db_type == "mysql":
        import pymysql  # 可选依赖
        m = db_conf["mysql"]
        _conn = pymysql.connect(host=m["host"], port=m["port"], user=m["user"],
                                password=m["password"], database=m["database"],
                                charset="utf8mb4", autocommit=True)
        placeholder = "%s"
    else:
        path = os.path.join(BASE_DIR, db_conf.get("sqlite_path", "data/aqua.db"))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        _conn = sqlite3.connect(path, check_same_thread=False)
        _conn.row_factory = sqlite3.Row
        _conn.execute("PRAGMA journal_mode=WAL")
        _conn.execute("PRAGMA busy_timeout=5000")
        _conn.commit()
        placeholder = "?"
    _create_tables(placeholder)
    return _conn


def _create_tables(ph):
    ddl = [
        """CREATE TABLE IF NOT EXISTS t_pond (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pond_id VARCHAR(32) UNIQUE NOT NULL,
            name VARCHAR(64),
            area_mu DECIMAL(8,2),
            stock_count INTEGER,
            stock_date DATE,
            manager VARCHAR(32),
            create_time DATETIME)""",
        """CREATE TABLE IF NOT EXISTS t_water_quality (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pond_id VARCHAR(32) NOT NULL,
            device_id VARCHAR(64),
            temperature DECIMAL(5,1),
            ph DECIMAL(4,1),
            dissolved_oxygen DECIMAL(5,2),
            ammonia DECIMAL(6,3),
            collect_time DATETIME NOT NULL,
            create_time DATETIME)""",
        "CREATE INDEX IF NOT EXISTS idx_wq_pond_time ON t_water_quality(pond_id, collect_time)",
        """CREATE TABLE IF NOT EXISTS t_alert (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pond_id VARCHAR(32) NOT NULL,
            metric VARCHAR(32),
            value DECIMAL(8,2),
            threshold DECIMAL(8,2),
            level TINYINT,
            status TINYINT DEFAULT 0,
            message VARCHAR(255),
            alert_time DATETIME)""",
        "CREATE INDEX IF NOT EXISTS idx_alert_pond_time ON t_alert(pond_id, alert_time)",
        """CREATE TABLE IF NOT EXISTS t_feeding (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pond_id VARCHAR(32) NOT NULL,
            feed_kg DECIMAL(8,2),
            feed_time DATETIME,
            note VARCHAR(255))""",
        """CREATE TABLE IF NOT EXISTS t_vision_density (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pond_id VARCHAR(32),
            density_level VARCHAR(16),
            fish_count INTEGER,
            confidence DECIMAL(5,2),
            image_path VARCHAR(255),
            create_time DATETIME)""",
        """CREATE TABLE IF NOT EXISTS t_employee (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name VARCHAR(32) NOT NULL,
            role VARCHAR(32),
            phone VARCHAR(20),
            pond_id VARCHAR(32),
            hire_date DATE,
            status TINYINT DEFAULT 1,
            create_time DATETIME)""",
        """CREATE TABLE IF NOT EXISTS t_seedling (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pond_id VARCHAR(32),
            batch_no VARCHAR(32),
            species VARCHAR(32),
            supplier VARCHAR(64),
            count INTEGER,
            spec_cm DECIMAL(5,1),
            stock_date DATE,
            note VARCHAR(255),
            create_time DATETIME)""",
        """CREATE TABLE IF NOT EXISTS t_medication (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pond_id VARCHAR(32),
            med_name VARCHAR(64),
            dosage VARCHAR(64),
            method VARCHAR(32),
            reason VARCHAR(255),
            start_date DATE,
            end_date DATE,
            operator VARCHAR(32),
            withdrawal_days INTEGER,
            create_time DATETIME)""",
        """CREATE TABLE IF NOT EXISTS t_op_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user VARCHAR(32),
            action VARCHAR(64),
            detail VARCHAR(500),
            create_time DATETIME)""",
    ]
    with _lock:
        for sql in ddl:
            _conn.execute(sql.replace("INTEGER PRIMARY KEY AUTOINCREMENT",
                                      "INT PRIMARY KEY AUTO_INCREMENT") if _db_type == "mysql" and "AUTOINCREMENT" in sql else sql)
        _conn.commit()


def execute(sql: str, params=()):
    with _lock:
        cur = _conn.execute(sql, params)
        _conn.commit()
        return cur.lastrowid


def query(sql: str, params=()):
    with _lock:
        cur = _conn.execute(sql, params)
        rows = cur.fetchall()
        return [dict(r) for r in rows]


def query_one(sql: str, params=()):
    rows = query(sql, params)
    return rows[0] if rows else None


def log_op(user: str, action: str, detail: str = ""):
    execute("INSERT INTO t_op_log(user, action, detail, create_time) VALUES (?,?,?,?)",
            (user, action, detail, _now()))
