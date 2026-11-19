# -*- coding: utf-8 -*-
"""自动化自测：覆盖全部 API + 前端资源一致性检查。用法：python scripts/selftest.py"""
import io
import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
WEB = os.path.join(str(BASE), "web")
ROOT = "http://127.0.0.1:5000"
PASSED, FAILED = [], []


def call(method, path, body=None, expect_code=0, raw=False):
    req = urllib.request.Request(ROOT + path, method=method,
                                 data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            text = r.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        text = e.read().decode("utf-8")
    try:
        data = json.loads(text)
    except ValueError:
        check(False, "%s %s -> 非JSON响应: %s" % (method, path, text[:80]))
        return None
    if raw:
        return data
    ok = data.get("code") == expect_code
    check(ok, "%s %s -> code=%s %s" % (method, path, data.get("code"),
                                       ("" if ok else "期望 %s, msg=%s" % (expect_code, data.get("message")))))
    return data


def check(ok, name):
    (PASSED if ok else FAILED).append(name)
    print(("  PASS  " if ok else "  FAIL  ") + name)


print("== 1. 页面与静态资源 ==")
for path, kw in [("/", "智慧渔业数据平台"), ("/app.js", "loadAnalysis"),
                 ("/style.css", "toast"), ("/vendor/echarts.min.js", "echarts")]:
    try:
        with urllib.request.urlopen(ROOT + path, timeout=10) as r:
            body = r.read().decode("utf-8", errors="ignore")
        check(kw in body, "GET %s 包含关键字 %r" % (path, kw))
    except Exception as e:
        check(False, "GET %s 异常 %s" % (path, e))

print("== 2. HTML/JS 一致性 ==")
html = open(BASE / "web" / "index.html", encoding="utf-8").read()
js = open(BASE / "web" / "app.js", encoding="utf-8").read()
tabs = re.findall(r'data-tab="([\w-]+)"', html)
missing_panels = [t for t in tabs if 'id="tab-%s"' % t not in html]
check(not missing_panels, "每个 tab 都有对应 panel（缺失: %s）" % missing_panels)
ids_js = set(re.findall(r'\$\("#([\w-]+)"\)', js))
ids_html = set(re.findall(r'id="([\w-]+)"', html))
# toast 是运行时创建的，排除
ids_js.discard("toast")
missing_ids = sorted(ids_js - ids_html)
check(not missing_ids, "JS 引用的元素都在 HTML 中（缺失: %s）" % missing_ids)
sections_open = len(re.findall(r"<section\b", html))
sections_close = html.count("</section>")
check(sections_open == sections_close, "section 标签配对 (%d vs %d)" % (sections_open, sections_close))
check(html.count("</main>") == 1 and html.count("<main>") == 1, "main 标签唯一且配对")
btns = ["hist-refresh", "alert-refresh", "pred-refresh", "ana-refresh", "feed-refresh", "med-refresh"]
unbound = [b for b in btns if ('$("#%s").addEventListener' % b) not in js]
check(not unbound, "查询/刷新按钮已绑定事件（未绑定: %s）" % unbound)

print("== 3. 核心 API（SRS 6.3） ==")
call("GET", "/api/v1/stats/overview")
call("GET", "/api/v1/water-quality/overview")
call("GET", "/api/v1/water-quality/latest?pond_id=TANK-A")
call("GET", "/api/v1/water-quality/history?pond_id=TANK-A")
call("POST", "/api/v1/water-quality", {"pond_id": "TANK-A", "device_id": "SELFTEST",
                                       "metrics": {"temperature": 27, "ph": 7.8, "dissolved_oxygen": 5.5, "ammonia": 0.3}})
call("GET", "/api/v1/alerts")
_feed = call("POST", "/api/v1/feeding", {"pond_id": "TANK-A", "feed_kg": 35.5, "note": "自测"}, raw=True)
call("DELETE", "/api/v1/feeding/%d" % _feed["data"]["id"])
call("DELETE", "/api/v1/feeding/999999", expect_code=404)  # 自测数据不留残留，避免污染 FCR

call("GET", "/api/v1/feeding/advice?pond_id=TANK-A")
call("GET", "/api/v1/prediction/growth?pond_id=TANK-A")
call("GET", "/api/v1/prediction/water-quality?pond_id=TANK-A")
call("POST", "/api/v1/auth/login", {"username": "admin", "password": "admin123"})
call("POST", "/api/v1/auth/login", {"username": "admin", "password": "wrong"}, expect_code=401)

print("== 4. 塘口：新增后各处同步 ==")
call("POST", "/api/v1/ponds", {"pond_id": "TANK-T", "name": "自测塘", "area_mu": 3, "stock_count": 5000, "stock_date": "2026-05-01"})
d = call("GET", "/api/v1/water-quality/overview", raw=True)
pond_ids = [r["pond_id"] for r in d["data"]]
check("TANK-T" in pond_ids, "新增塘口出现在 water-quality/overview（无数据也返回）")
check(any(r["pond_id"] == "TANK-T" and r.get("has_data") is False for r in d["data"]), "无数据塘口 has_data=False")
d = call("GET", "/api/v1/ponds", raw=True)
check("TANK-T" in [p["pond_id"] for p in d["data"]], "新增塘口出现在 /ponds")
# 清理
import urllib.request as _u
req = _u.Request(ROOT + "/api/v1/ponds/TANK-T", method="DELETE")
_u.urlopen(req, timeout=10).read()
check(True, "清理测试塘口 TANK-T")

print("== 5. 员工管理 CRUD ==")
d = call("POST", "/api/v1/employees", {"name": "自测员工", "role": "测试岗", "phone": "13000000000", "hire_date": "2026-09-13"}, raw=True)
eid = d["data"]["id"]
call("GET", "/api/v1/employees")
call("PUT", "/api/v1/employees/%d" % eid, {"status": 0})
call("DELETE", "/api/v1/employees/%d" % eid)
call("POST", "/api/v1/employees", {"name": ""}, expect_code=1)

print("== 6. 苗种管理 ==")
d = call("POST", "/api/v1/seedlings", {"pond_id": "TANK-A", "batch_no": "TEST-01", "count": 1000, "spec_cm": 4.8, "stock_date": "2026-09-13"}, raw=True)
sid = d["data"]["id"]
call("GET", "/api/v1/seedlings")
call("DELETE", "/api/v1/seedlings/%d" % sid)
call("POST", "/api/v1/seedlings", {"pond_id": "", "count": None}, expect_code=1)

print("== 7. 用药管理 + 禁药拦截 ==")
call("GET", "/api/v1/medications")
d = call("POST", "/api/v1/medications", {"pond_id": "TANK-A", "med_name": "二氧化氯", "dosage": "0.3mg/L", "method": "全池泼洒", "start_date": "2026-09-13"}, raw=True)
call("DELETE", "/api/v1/medications/%d" % d["data"]["id"])
call("POST", "/api/v1/medications", {"pond_id": "TANK-A", "med_name": "孔雀石绿"}, expect_code=403)
call("POST", "/api/v1/medications", {"pond_id": "TANK-A", "med_name": "含氯霉素成分"}, expect_code=403)

print("== 8. 投喂管理 ==")
call("GET", "/api/v1/feeding/list")
d = call("GET", "/api/v1/feeding/stats", raw=True)
check("today_kg" in d["data"] and "daily" in d["data"], "feeding/stats 返回今日与每日序列")

print("== 9. 生长分析 ==")
d = call("GET", "/api/v1/analysis/growth?pond_id=TANK-A", raw=True)
a = d["data"]
for key in ["current_weight_g", "days_to_market", "estimated_yield_kg", "fcr", "daily_temp", "daily_feed", "curve"]:
    check(key in a, "analysis/growth 包含 %s（值: %s）" % (key, str(a.get(key))[:40]))
check(len(a["daily_temp"]) > 0, "日均水温序列非空")
check(len(a["daily_feed"]) > 0, "日投喂序列非空")
call("GET", "/api/v1/analysis/growth?pond_id=NOPE", expect_code=1)

print("== 10. 传感器接入 ==")
d = call("POST", "/api/v1/sensor/simulate", {"pond_id": "TANK-A"}, raw=True)
check(set(["temperature", "ph", "dissolved_oxygen", "ammonia"]).issubset(d["data"]["metrics"].keys()),
      "一键接入返回四项指标: %s" % d["data"]["metrics"])
call("POST", "/api/v1/sensor/simulate", {"pond_id": "NOT-EXIST"}, expect_code=404)
call("POST", "/api/v1/sensor/simulate", {}, expect_code=1)
d = call("GET", "/api/v1/water-quality/overview", raw=True)
check(all(r["has_data"] for r in d["data"]), "全部塘口均已接入传感器（无「待接入」残留）")
# 前端「一键接入」入口存在性
_js = io.open(os.path.join(WEB, "app.js"), encoding="utf-8").read()
check("connectSensor" in _js and "sensor/simulate" in _js, "前端存在一键接入入口 connectSensor")
check("window.connectSensor" in _js, "connectSensor 已挂载到 window（onclick 可调用）")
check(os.path.isfile(os.path.join(BASE, "docs", "传感器接入指南.md")), "《传感器接入指南》文档存在")
check(os.path.isfile(os.path.join(BASE, "scripts", "push_demo.py")), "外接设备上报示例脚本存在")

print("== 11. 非法输入防护 ==")
call("GET", "/api/v1/water-quality/latest?pond_id=", expect_code=1)
call("POST", "/api/v1/ponds", {"pond_id": "bad id!@#"}, expect_code=1)

print()
print("=" * 50)
print("通过 %d 项，失败 %d 项" % (len(PASSED), len(FAILED)))
if FAILED:
    print("失败清单:")
    for f in FAILED:
        print(" -", f)
    sys.exit(1)
print("全部自测通过 ✔")
