# -*- coding: utf-8 -*-
"""告警服务：阈值判断、告警生成与去重（同一塘口同一指标 10 分钟内不重复告警）。"""
import threading
import time
from datetime import datetime

import server.db as db

_lock = threading.Lock()
_last_alert_time = {}  # (pond_id, metric) -> timestamp
DEDUP_WINDOW = 600  # 秒


def check_metrics(pond_id: str, metrics: dict, thresholds: dict, collect_time: str = None):
    """对一组水质指标做阈值检查，命中则生成告警记录。返回告警列表。"""
    alerts = []
    now = time.time()
    ts = collect_time or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    for metric, rule in thresholds.items():
        value = metrics.get(metric)
        if value is None:
            continue
        hit, threshold = _hit_threshold(value, rule)
        if not hit:
            continue
        key = (pond_id, metric)
        with _lock:
            if now - _last_alert_time.get(key, 0) < DEDUP_WINDOW:
                continue
            _last_alert_time[key] = now
        message = "%s(%s)当前 %s %s，阈值 %s。%s" % (
            rule.get("name", metric), pond_id, value, rule.get("unit", ""),
            threshold, rule.get("advice", ""))
        alert_id = db.execute(
            "INSERT INTO t_alert(pond_id, metric, value, threshold, level, status, message, alert_time) "
            "VALUES (?,?,?,?,?,0,?,?)",
            (pond_id, metric, value, threshold, rule.get("level", 1), message, ts))
        alerts.append({"id": alert_id, "pond_id": pond_id, "metric": metric,
                       "value": value, "threshold": threshold,
                       "level": rule.get("level", 1), "message": message,
                       "alert_time": ts})
    return alerts


def _hit_threshold(value, rule):
    vmin = rule.get("min")
    vmax = rule.get("max")
    if vmin is not None and value < vmin:
        return True, vmin
    if vmax is not None and value > vmax:
        return True, vmax
    return False, None
