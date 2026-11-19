# -*- coding: utf-8 -*-
"""RESTful API（SRS 6.3 约定，统一响应格式 {"code":0,"message":"success","data":{}}）。"""
import math
import os
import random
import re
from datetime import datetime, timedelta

from flask import Blueprint, jsonify, request

import server.db as db
from server.alerts import check_metrics

api_bp = Blueprint("api", __name__, url_prefix="/api/v1")

# 简易会话 Token 存储（演示级鉴权，生产环境应换 JWT）
_tokens = {}
_USERS = {"admin": {"password": "admin123", "role": "admin"},
          "farmer": {"password": "farmer123", "role": "farmer"}}


def ok(data=None, message="success"):
    return jsonify({"code": 0, "message": message, "data": data})


def fail(message, code=1, http=400):
    resp = jsonify({"code": code, "message": message, "data": None})
    resp.status_code = http
    return resp


def _safe(s, maxlen=64):
    """入参白名单校验，防注入（SRS NFR-S-03）。"""
    if s is None:
        return None
    s = str(s)
    if not re.match(r"^[\w\-\.: ]{0,%d}$" % maxlen, s):
        return None
    return s


def _require_token():
    token = request.headers.get("X-Token", "")
    return token in _tokens


# ---------------- 认证 ----------------
@api_bp.post("/auth/login")
def login():
    body = request.get_json(silent=True) or {}
    username = _safe(body.get("username"), 32)
    password = body.get("password", "")
    user = _USERS.get(username or "")
    if not user or user["password"] != password:
        return fail("用户名或密码错误", code=401, http=401)
    token = "%s-%d" % (username, random.randint(10**8, 10**9 - 1))
    _tokens[token] = username
    db.log_op(username, "login", "用户登录")
    return ok({"token": token, "role": user["role"], "username": username})


# ---------------- 水质数据 ----------------
@api_bp.post("/water-quality")
def post_water_quality():
    body = request.get_json(silent=True) or {}
    records = body.get("records") if body.get("type") == "batch" else [body]
    count = 0
    for r in records:
        pond_id = _safe(r.get("pond_id"), 32)
        if not pond_id:
            return fail("pond_id 非法")
        m = r.get("metrics") or {}
        ts = str(r.get("timestamp") or datetime.now().isoformat(timespec="seconds")).replace("T", " ")[:19]
        db.execute(
            "INSERT INTO t_water_quality(pond_id, device_id, temperature, ph, dissolved_oxygen, ammonia, collect_time, create_time) "
            "VALUES (?,?,?,?,?,?,?,datetime('now','localtime'))",
            (pond_id, _safe(r.get("device_id"), 64), _num(m.get("temperature")), _num(m.get("ph")),
             _num(m.get("dissolved_oxygen")), _num(m.get("ammonia")), ts))
        count += 1
        from flask import current_app
        check_metrics(pond_id, m, current_app.config["THRESHOLDS"], ts)
    return ok({"count": count}, "已入库 %d 条" % count)


def _num(v):
    try:
        v = float(v)
        if math.isnan(v) or math.isinf(v):
            return None
        return v
    except (TypeError, ValueError):
        return None


@api_bp.get("/water-quality/latest")
def latest_water_quality():
    pond_id = _safe(request.args.get("pond_id"), 32)
    if not pond_id:
        return fail("缺少 pond_id 参数")
    row = db.query_one(
        "SELECT * FROM t_water_quality WHERE pond_id=? ORDER BY collect_time DESC, id DESC LIMIT 1", (pond_id,))
    return ok(row)


@api_bp.get("/water-quality/history")
def history_water_quality():
    pond_id = _safe(request.args.get("pond_id"), 32)
    if not pond_id:
        return fail("缺少 pond_id 参数")
    start = _safe(request.args.get("start"), 32) or (datetime.now() - timedelta(hours=24)).strftime("%Y-%m-%d %H:%M:%S")
    end = _safe(request.args.get("end"), 32) or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    rows = db.query(
        "SELECT pond_id, device_id, temperature, ph, dissolved_oxygen, ammonia, collect_time "
        "FROM t_water_quality WHERE pond_id=? AND collect_time BETWEEN ? AND ? ORDER BY collect_time",
        (pond_id, start, end))
    return ok({"pond_id": pond_id, "start": start, "end": end, "count": len(rows), "records": rows})


@api_bp.post("/sensor/simulate")
def sensor_simulate():
    """一键接入传感器：为指定塘口立即生成一条模拟读数（演示 / 调试用）。

    真实硬件接入方式见 docs《传感器接入指南》：
    RS232 串口上报（config.json -> collection.serial）或 TCP 9000 推送 / HTTP 上报。
    """
    body = request.get_json(silent=True) or {}
    pond_id = _safe(body.get("pond_id"), 32)
    if not pond_id:
        return fail("缺少 pond_id")
    pond = db.query_one("SELECT pond_id, name FROM t_pond WHERE pond_id=?", (pond_id,))
    if not pond:
        return fail("塘口不存在，请先在「塘口管理」中新增", code=404, http=404)
    hour = datetime.now().hour
    do_base = 4.2 + 2.2 * (0.5 + 0.5 * math.sin((hour - 6) / 24.0 * 2 * math.pi))
    metrics = {
        "temperature": round(random.gauss(27.5, 1.2), 1),
        "ph": round(random.gauss(7.8, 0.15), 1),
        "dissolved_oxygen": round(max(1.5, random.gauss(do_base, 0.4)), 2),
        "ammonia": round(abs(random.gauss(0.3, 0.12)), 3),
    }
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    device_id = _safe(body.get("device_id"), 64) or ("SIM-" + pond_id)
    db.execute(
        "INSERT INTO t_water_quality(pond_id, device_id, temperature, ph, dissolved_oxygen, ammonia, collect_time, create_time) "
        "VALUES (?,?,?,?,?,?,?,datetime('now','localtime'))",
        (pond_id, device_id, metrics["temperature"], metrics["ph"],
         metrics["dissolved_oxygen"], metrics["ammonia"], ts))
    from flask import current_app
    check_metrics(pond_id, metrics, current_app.config["THRESHOLDS"], ts)
    db.log_op("system", "sensor_simulate", "一键接入传感器 %s" % pond_id)
    return ok({"pond_id": pond_id, "metrics": metrics, "collect_time": ts},
              "已为 %s 生成模拟读数" % (pond["name"] or pond_id))


@api_bp.get("/water-quality/overview")
def water_overview():
    """全部塘口的最新水质汇总（无数据的塘也返回，前端显示"待接入"）。"""
    ponds = db.query("SELECT pond_id, name FROM t_pond ORDER BY pond_id")
    rows = db.query(
        "SELECT w.* FROM t_water_quality w "
        "JOIN (SELECT pond_id, MAX(id) AS max_id FROM t_water_quality GROUP BY pond_id) t "
        "ON w.pond_id=t.pond_id AND w.id=t.max_id")
    latest = {r["pond_id"]: r for r in rows}
    data = []
    for p in ponds:
        rec = dict(latest.get(p["pond_id"]) or {"pond_id": p["pond_id"]})
        rec["pond_name"] = p["name"]
        rec["has_data"] = p["pond_id"] in latest
        data.append(rec)
    return ok(data)


# ---------------- 投喂 ----------------
@api_bp.post("/feeding")
def post_feeding():
    body = request.get_json(silent=True) or {}
    pond_id = _safe(body.get("pond_id"), 32)
    feed_kg = _num(body.get("feed_kg"))
    if not pond_id or feed_kg is None:
        return fail("pond_id / feed_kg 非法")
    ts = str(body.get("feed_time") or datetime.now().strftime("%Y-%m-%d %H:%M:%S")).replace("T", " ")[:19]
    fid = db.execute("INSERT INTO t_feeding(pond_id, feed_kg, feed_time, note) VALUES (?,?,?,?)",
                     (pond_id, feed_kg, ts, _safe(body.get("note"), 200) or ""))
    db.log_op(_tokens.get(request.headers.get("X-Token", ""), "api"), "feeding", "%s 投喂 %.2fkg" % (pond_id, feed_kg))
    return ok({"id": fid, "pond_id": pond_id, "feed_kg": feed_kg, "feed_time": ts})


@api_bp.delete("/feeding/<int:fid>")
def delete_feeding(fid):
    """删除误录的投喂记录。"""
    row = db.query_one("SELECT id FROM t_feeding WHERE id=?", (fid,))
    if not row:
        return fail("记录不存在", code=404, http=404)
    db.execute("DELETE FROM t_feeding WHERE id=?", (fid,))
    db.log_op("api", "feeding_delete", "删除投喂记录 #%d" % fid)
    return ok({"id": fid}, "已删除")


@api_bp.get("/feeding/advice")
def feeding_advice():
    """基于生长模型 + 当前水温给出建议投喂量（SRS SC-03）。"""
    pond_id = _safe(request.args.get("pond_id"), 32)
    if not pond_id:
        return fail("缺少 pond_id 参数")
    from server.ml.predictor import growth_predictor
    pond = db.query_one("SELECT * FROM t_pond WHERE pond_id=?", (pond_id,))
    if not pond:
        return fail("塘口不存在")
    latest = db.query_one(
        "SELECT temperature FROM t_water_quality WHERE pond_id=? ORDER BY collect_time DESC LIMIT 1", (pond_id,))
    temp = latest["temperature"] if latest else 26.0
    age_days = 90
    if pond.get("stock_date"):
        age_days = max(30, (datetime.now() - datetime.strptime(str(pond["stock_date"])[:10], "%Y-%m-%d")).days)
    weight_g = growth_predictor.predict_weight(age_days, temp, do=6.0, ammonia=0.2)
    biomass_kg = weight_g * pond["stock_count"] / 1000.0
    rate = _feed_rate_percent(weight_g, temp)  # 投喂率 %
    advice_kg = round(biomass_kg * rate / 100.0, 1)
    return ok({
        "pond_id": pond_id, "avg_weight_g": round(weight_g, 1), "age_days": age_days,
        "stock_count": pond["stock_count"], "biomass_kg": round(biomass_kg, 1),
        "water_temp": temp, "feed_rate_percent": rate,
        "advice_feed_kg": advice_kg,
        "advice": "建议每日分 2~3 次投喂，合计约 %.1f kg（投喂率 %.2f%%）。水温低于 18℃ 或高于 32℃ 时酌情减料。" % (advice_kg, rate),
    })


def _feed_rate_percent(weight_g, temp):
    """投喂率经验模型：鱼越小投喂率越高，水温脱离适温区下调。"""
    if weight_g < 50:
        rate = 6.0
    elif weight_g < 150:
        rate = 4.0
    elif weight_g < 300:
        rate = 2.8
    elif weight_g < 500:
        rate = 2.0
    else:
        rate = 1.5
    if temp < 18 or temp > 32:
        rate *= 0.5
    elif temp < 22:
        rate *= 0.8
    return round(rate, 2)


# ---------------- 视觉密度 ----------------
@api_bp.post("/vision/density")
def vision_density():
    f = request.files.get("image")
    pond_id = _safe(request.form.get("pond_id"), 32) or "TANK-A"
    if not f:
        return fail("缺少 image 文件")
    save_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "images")
    os.makedirs(save_dir, exist_ok=True)
    path = os.path.join(save_dir, "%s_%s.jpg" % (pond_id, datetime.now().strftime("%Y%m%d%H%M%S")))
    f.save(path)
    from server.vision.density import estimate_density
    try:
        result = estimate_density(path)
    except Exception as e:  # 图像无法解析
        return fail("图像识别失败: %s" % e)
    density_level, fish_count, confidence = result
    db.execute("INSERT INTO t_vision_density(pond_id, density_level, fish_count, confidence, image_path, create_time) "
               "VALUES (?,?,?,?,?,datetime('now','localtime'))",
               (pond_id, density_level, fish_count, confidence, path))
    advice = "密度正常" if density_level != "高" else "鱼群密度偏高，建议分塘或加大增氧"
    return ok({"pond_id": pond_id, "density_level": density_level,
               "fish_count": fish_count, "confidence": confidence, "advice": advice})


@api_bp.get("/vision/density")
def get_density():
    pond_id = _safe(request.args.get("pond_id"), 32)
    sql = "SELECT * FROM t_vision_density"
    params = ()
    if pond_id:
        sql += " WHERE pond_id=?"
        params = (pond_id,)
    sql += " ORDER BY create_time DESC LIMIT 20"
    return ok(db.query(sql, params))


# ---------------- 预测 ----------------
@api_bp.get("/prediction/growth")
def prediction_growth():
    pond_id = _safe(request.args.get("pond_id"), 32)
    if not pond_id:
        return fail("缺少 pond_id 参数")
    from server.ml.predictor import growth_predictor
    pond = db.query_one("SELECT * FROM t_pond WHERE pond_id=?", (pond_id,))
    if not pond:
        return fail("塘口不存在")
    latest = db.query_one("SELECT temperature FROM t_water_quality WHERE pond_id=? ORDER BY collect_time DESC LIMIT 1", (pond_id,))
    temp = latest["temperature"] if latest else 26.0
    stock_date = pond.get("stock_date")
    start_age = 30
    if stock_date:
        start_age = max(30, (datetime.now() - datetime.strptime(str(stock_date)[:10], "%Y-%m-%d")).days)
    curve = growth_predictor.growth_curve(start_age, days=90, temp=temp)
    model_info = growth_predictor.model_info()
    return ok({"pond_id": pond_id, "current_age_days": start_age, "water_temp": temp,
               "curve": curve, "model": model_info})


@api_bp.get("/prediction/water-quality")
def prediction_water_quality():
    """未来 6 小时溶解氧趋势预测（线性回归 + 日周期）。"""
    pond_id = _safe(request.args.get("pond_id"), 32)
    if not pond_id:
        return fail("缺少 pond_id 参数")
    from server.ml.predictor import predict_do_trend
    result = predict_do_trend(pond_id)
    if result is None:
        return fail("历史数据不足，无法预测")
    return ok(result)


# ---------------- 告警 ----------------
@api_bp.get("/alerts")
def get_alerts():
    pond_id = _safe(request.args.get("pond_id"), 32)
    status = request.args.get("status")
    sql = "SELECT * FROM t_alert WHERE 1=1"
    params = []
    if pond_id:
        sql += " AND pond_id=?"
        params.append(pond_id)
    if status is not None and str(status).isdigit():
        sql += " AND status=?"
        params.append(int(status))
    sql += " ORDER BY alert_time DESC LIMIT 100"
    return ok(db.query(sql, params))


@api_bp.post("/alerts/<int:alert_id>/handle")
def handle_alert(alert_id):
    db.execute("UPDATE t_alert SET status=1 WHERE id=?", (alert_id,))
    db.log_op(_tokens.get(request.headers.get("X-Token", ""), "api"), "alert_handle", "处理告警 #%d" % alert_id)
    return ok({"id": alert_id, "status": 1}, "告警已处理")


# ---------------- 塘口管理 ----------------
@api_bp.get("/ponds")
def list_ponds():
    return ok(db.query("SELECT * FROM t_pond ORDER BY pond_id"))


@api_bp.post("/ponds")
def create_pond():
    b = request.get_json(silent=True) or {}
    pond_id = _safe(b.get("pond_id"), 32)
    if not pond_id:
        return fail("pond_id 非法")
    if db.query_one("SELECT 1 FROM t_pond WHERE pond_id=?", (pond_id,)):
        return fail("塘口已存在")
    db.execute("INSERT INTO t_pond(pond_id, name, area_mu, stock_count, stock_date, manager, create_time) "
               "VALUES (?,?,?,?,?,?,datetime('now','localtime'))",
               (pond_id, _safe(b.get("name"), 64) or pond_id, _num(b.get("area_mu")) or 0,
                int(b.get("stock_count") or 0), _safe(b.get("stock_date"), 10), _safe(b.get("manager"), 32)))
    db.log_op(_tokens.get(request.headers.get("X-Token", ""), "api"), "pond_create", pond_id)
    return ok({"pond_id": pond_id})


@api_bp.put("/ponds/<pond_id>")
def update_pond(pond_id):
    pond_id = _safe(pond_id, 32)
    b = request.get_json(silent=True) or {}
    fields, params = [], []
    for key in ("name", "area_mu", "stock_count", "stock_date", "manager"):
        if key in b:
            fields.append("%s=?" % key)
            params.append(_num(b[key]) if key == "area_mu" else (_safe(b[key], 64) if isinstance(b[key], str) else b[key]))
    if not fields:
        return fail("无可更新字段")
    params.append(pond_id)
    db.execute("UPDATE t_pond SET %s WHERE pond_id=?" % ",".join(fields), params)
    return ok({"pond_id": pond_id})


@api_bp.delete("/ponds/<pond_id>")
def delete_pond(pond_id):
    pond_id = _safe(pond_id, 32)
    db.execute("DELETE FROM t_pond WHERE pond_id=?", (pond_id,))
    db.log_op(_tokens.get(request.headers.get("X-Token", ""), "api"), "pond_delete", pond_id)
    return ok({"pond_id": pond_id}, "已删除")


# ---------------- 系统总览 ----------------
@api_bp.get("/stats/overview")
def stats_overview():
    ponds = db.query("SELECT COUNT(*) AS n FROM t_pond")[0]["n"]
    records = db.query("SELECT COUNT(*) AS n FROM t_water_quality")[0]["n"]
    alerts_active = db.query("SELECT COUNT(*) AS n FROM t_alert WHERE status=0")[0]["n"]
    alerts_total = db.query("SELECT COUNT(*) AS n FROM t_alert")[0]["n"]
    feed_total = db.query("SELECT IFNULL(SUM(feed_kg),0) AS n FROM t_feeding")[0]["n"]
    return ok({"ponds": ponds, "water_records": records, "alerts_active": alerts_active,
               "alerts_total": alerts_total, "feed_total_kg": round(feed_total, 1)})


# ================= 扩展模块：员工 / 苗种 / 用药 / 投喂 / 生长分析 =================
def _date(s, default=None):
    s = _safe(s, 10)
    return s or default


# ---------------- 员工管理 ----------------
@api_bp.get("/employees")
def list_employees():
    return ok(db.query("SELECT * FROM t_employee ORDER BY id DESC"))


@api_bp.post("/employees")
def create_employee():
    b = request.get_json(silent=True) or {}
    name = _safe(b.get("name"), 32)
    if not name:
        return fail("姓名必填")
    eid = db.execute(
        "INSERT INTO t_employee(name, role, phone, pond_id, hire_date, status, create_time) "
        "VALUES (?,?,?,?,?,?,datetime('now','localtime'))",
        (name, _safe(b.get("role"), 32) or "", _safe(b.get("phone"), 20) or "",
         _safe(b.get("pond_id"), 32) or "", _date(b.get("hire_date")), 1 if b.get("status", 1) else 0))
    db.log_op("web", "employee_create", name)
    return ok({"id": eid, "name": name})


@api_bp.put("/employees/<int:eid>")
def update_employee(eid):
    b = request.get_json(silent=True) or {}
    fields, params = [], []
    for key in ("name", "role", "phone", "pond_id", "hire_date"):
        if key in b:
            fields.append("%s=?" % key)
            params.append(_safe(b[key], 64))
    if "status" in b:
        fields.append("status=?")
        params.append(1 if b["status"] else 0)
    if not fields:
        return fail("无可更新字段")
    params.append(eid)
    db.execute("UPDATE t_employee SET %s WHERE id=?" % ",".join(fields), params)
    return ok({"id": eid})


@api_bp.delete("/employees/<int:eid>")
def delete_employee(eid):
    db.execute("DELETE FROM t_employee WHERE id=?", (eid,))
    return ok({"id": eid}, "已删除")


# ---------------- 苗种管理 ----------------
@api_bp.get("/seedlings")
def list_seedlings():
    return ok(db.query("SELECT * FROM t_seedling ORDER BY stock_date DESC, id DESC"))


@api_bp.post("/seedlings")
def create_seedling():
    b = request.get_json(silent=True) or {}
    pond_id = _safe(b.get("pond_id"), 32)
    count = b.get("count")
    if not pond_id or not count:
        return fail("塘口与放苗数量必填")
    sid = db.execute(
        "INSERT INTO t_seedling(pond_id, batch_no, species, supplier, count, spec_cm, stock_date, note, create_time) "
        "VALUES (?,?,?,?,?,?,?,?,datetime('now','localtime'))",
        (pond_id, _safe(b.get("batch_no"), 32) or "", _safe(b.get("species"), 32) or "海鲈",
         _safe(b.get("supplier"), 64) or "", int(count),
         _num(b.get("spec_cm")), _date(b.get("stock_date")), _safe(b.get("note"), 200) or ""))
    db.log_op("web", "seedling_create", "%s %s尾" % (pond_id, count))
    return ok({"id": sid})


@api_bp.delete("/seedlings/<int:sid>")
def delete_seedling(sid):
    db.execute("DELETE FROM t_seedling WHERE id=?", (sid,))
    return ok({"id": sid}, "已删除")


# ---------------- 用药管理 ----------------
# 禁用渔药清单（依据水产养殖用药相关规定，录入时自动拦截）
BANNED_MEDS = ["孔雀石绿", "氯霉素", "硝基呋喃", "呋喃唑酮", "呋喃西林", "甘汞", "五氯酚钠",
               "滴滴涕", "六六六", "甲基睾丸酮", "己烯雌酚", "喹乙醇", "红霉素", "泰乐菌素"]


@api_bp.get("/medications")
def list_medications():
    pond_id = _safe(request.args.get("pond_id"), 32)
    sql, params = "SELECT * FROM t_medication", ()
    if pond_id:
        sql, params = "SELECT * FROM t_medication WHERE pond_id=?", (pond_id,)
    return ok(db.query(sql + " ORDER BY start_date DESC, id DESC LIMIT 200", params))


@api_bp.post("/medications")
def create_medication():
    b = request.get_json(silent=True) or {}
    pond_id = _safe(b.get("pond_id"), 32)
    med_name = _safe(b.get("med_name"), 64)
    if not pond_id or not med_name:
        return fail("塘口与药品名必填")
    for banned in BANNED_MEDS:
        if banned in med_name:
            db.log_op("web", "medication_rejected", "%s(%s)" % (med_name, pond_id))
            return fail("【拒绝录入】%s 属于禁用渔药，依据水产养殖质量安全规定不得使用！" % banned, code=403)
    mid = db.execute(
        "INSERT INTO t_medication(pond_id, med_name, dosage, method, reason, start_date, end_date, operator, withdrawal_days, create_time) "
        "VALUES (?,?,?,?,?,?,?,?,?,datetime('now','localtime'))",
        (pond_id, med_name, _safe(b.get("dosage"), 64) or "", _safe(b.get("method"), 32) or "全池泼洒",
         _safe(b.get("reason"), 200) or "", _date(b.get("start_date")), _date(b.get("end_date")),
         _safe(b.get("operator"), 32) or "", int(b.get("withdrawal_days") or 0)))
    db.log_op("web", "medication_create", "%s %s" % (pond_id, med_name))
    return ok({"id": mid})


@api_bp.delete("/medications/<int:mid>")
def delete_medication(mid):
    db.execute("DELETE FROM t_medication WHERE id=?", (mid,))
    return ok({"id": mid}, "已删除")


# ---------------- 投喂管理 ----------------
@api_bp.get("/feeding/list")
def feeding_list():
    pond_id = _safe(request.args.get("pond_id"), 32)
    days = int(request.args.get("days", 14) or 14)
    start = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d 00:00:00")
    sql = "SELECT * FROM t_feeding WHERE feed_time>=?"
    params = [start]
    if pond_id:
        sql += " AND pond_id=?"
        params.append(pond_id)
    sql += " ORDER BY feed_time DESC LIMIT 200"
    return ok(db.query(sql, params))


@api_bp.get("/feeding/stats")
def feeding_stats():
    pond_id = _safe(request.args.get("pond_id"), 32)
    cond, params = "", []
    if pond_id:
        cond, params = " AND pond_id=?", [pond_id]
    today = db.query_one("SELECT IFNULL(SUM(feed_kg),0) AS n FROM t_feeding WHERE date(feed_time)=date('now','localtime')" + cond, params)
    week = db.query(
        "SELECT date(feed_time) AS d, ROUND(SUM(feed_kg),1) AS kg FROM t_feeding "
        "WHERE feed_time>=datetime('now','localtime','-13 days')" + cond +
        " GROUP BY date(feed_time) ORDER BY d", params)
    total = db.query_one("SELECT IFNULL(SUM(feed_kg),0) AS n FROM t_feeding WHERE 1=1" + cond, params)
    return ok({"today_kg": round(today["n"], 1), "daily": week, "total_kg": round(total["n"], 1)})


# ---------------- 生长数据分析 ----------------
@api_bp.get("/analysis/growth")
def analysis_growth():
    """生长数据分析：水温、投喂、预估生长周期、预估产量（SRS SC-05）。"""
    pond_id = _safe(request.args.get("pond_id"), 32)
    if not pond_id:
        return fail("缺少 pond_id 参数")
    pond = db.query_one("SELECT * FROM t_pond WHERE pond_id=?", (pond_id,))
    if not pond:
        return fail("塘口不存在")
    from server.ml.predictor import growth_predictor

    # 近 14 天日均水温
    daily_temp = db.query(
        "SELECT date(collect_time) AS d, ROUND(AVG(temperature),1) AS temp, "
        "ROUND(AVG(dissolved_oxygen),2) AS do FROM t_water_quality "
        "WHERE pond_id=? AND collect_time>=datetime('now','localtime','-13 days') "
        "GROUP BY date(collect_time) ORDER BY d", (pond_id,))
    # 近 14 天日投喂量
    daily_feed = db.query(
        "SELECT date(feed_time) AS d, ROUND(SUM(feed_kg),1) AS kg FROM t_feeding "
        "WHERE pond_id=? AND feed_time>=datetime('now','localtime','-13 days') "
        "GROUP BY date(feed_time) ORDER BY d", (pond_id,))
    total_feed_90d = db.query_one(
        "SELECT IFNULL(SUM(feed_kg),0) AS n FROM t_feeding WHERE pond_id=? "
        "AND feed_time>=datetime('now','localtime','-90 days')", (pond_id,))["n"]

    latest = db.query_one("SELECT temperature FROM t_water_quality WHERE pond_id=? ORDER BY collect_time DESC LIMIT 1", (pond_id,))
    temp = latest["temperature"] if latest else 26.0
    stock_date = pond.get("stock_date")
    age_days = 90
    if stock_date:
        try:
            age_days = max(30, (datetime.now() - datetime.strptime(str(stock_date)[:10], "%Y-%m-%d")).days)
        except ValueError:
            pass

    survival = 0.85          # 成活率假设
    stock_weight_g = 10.0    # 放苗均重假设
    target_g = 500.0         # 商品鱼规格（白蕉海鲈主流 1 斤/条）

    curve = growth_predictor.growth_curve(age_days, days=180, temp=temp)
    current_w = growth_predictor.predict_weight(age_days, temp)

    days_to_market, harvest_date = None, None
    for c in curve:
        if c["weight_g"] >= target_g:
            days_to_market = c["age_days"] - age_days
            harvest_date = c["date"]
            break
    harvest_w = current_w if days_to_market is None else target_g
    yield_kg = round(pond["stock_count"] * harvest_w / 1000.0 * survival, 1)
    # FCR：用"实际有投喂记录的时间跨度"对齐增重口径（饲料系数 = 投喂量 / 同期增重）
    fcr = None
    span = db.query_one(
        "SELECT MIN(date(feed_time)) AS a, MAX(date(feed_time)) AS b, IFNULL(SUM(feed_kg),0) AS n "
        "FROM t_feeding WHERE pond_id=? AND feed_time>=datetime('now','localtime','-90 days')", (pond_id,))
    if span and span["a"] and span["b"] and span["n"] > 0:
        span_days = max(1, (datetime.strptime(span["b"][:10], "%Y-%m-%d") - datetime.strptime(span["a"][:10], "%Y-%m-%d")).days + 1)
        # 用 60 天窗口的平均日增重折算，避免随机森林在短差分下的阶梯误差
        w_now = current_w
        w_before = growth_predictor.predict_weight(max(30, age_days - 60), temp)
        daily_gain_g = max((w_now - w_before) / 60.0, 0.1)
        gain_kg = pond["stock_count"] * daily_gain_g * span_days / 1000.0
        fcr = round(span["n"] / gain_kg, 2)

    return ok({
        "pond_id": pond_id, "pond_name": pond["name"], "age_days": age_days,
        "water_temp": temp, "daily_temp": daily_temp, "daily_feed": daily_feed,
        "total_feed_90d_kg": round(total_feed_90d, 1),
        "current_weight_g": round(current_w, 1),
        "target_weight_g": target_g,
        "days_to_market": days_to_market, "harvest_date": harvest_date,
        "estimated_yield_kg": yield_kg, "survival_rate": survival,
        "fcr": fcr, "curve": curve,
    })
