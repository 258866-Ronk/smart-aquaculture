# -*- coding: utf-8 -*-
"""模拟一台真实传感器设备，通过 HTTP 向平台上报一条水质数据。

用法（在项目根目录执行）：
    python scripts/push_demo.py TANK-D
    python scripts/push_demo.py TANK-D --temp 26.5 --ph 7.6 --do 5.8 --nh3 0.35
    python scripts/push_demo.py TANK-D --host 192.168.1.20 --port 5000

这就是《传感器接入指南》"方式三：HTTP 上报" 的可运行示例，
ESP32 / 树莓派 / 4G DTU 上只需把这段 HTTP 请求换成对应语言的实现即可。
"""
import argparse
import json
import random
import sys
import urllib.request
from datetime import datetime


def simulate_metrics():
    hour = datetime.now().hour
    import math
    do_base = 4.2 + 2.2 * (0.5 + 0.5 * math.sin((hour - 6) / 24.0 * 2 * math.pi))
    return {
        "temperature": round(random.gauss(27.5, 1.2), 1),
        "ph": round(random.gauss(7.8, 0.15), 1),
        "dissolved_oxygen": round(max(1.5, random.gauss(do_base, 0.4)), 2),
        "ammonia": round(abs(random.gauss(0.3, 0.12)), 3),
    }


def main():
    ap = argparse.ArgumentParser(description="模拟传感器上报一条水质数据")
    ap.add_argument("pond_id", help="塘口编号，如 TANK-A")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", default=5000, type=int)
    ap.add_argument("--device", default="DEV-DEMO-01")
    ap.add_argument("--temp", type=float)
    ap.add_argument("--ph", type=float)
    ap.add_argument("--do", dest="do_", type=float)
    ap.add_argument("--nh3", type=float)
    args = ap.parse_args()

    m = simulate_metrics()
    if args.temp is not None:
        m["temperature"] = args.temp
    if args.ph is not None:
        m["ph"] = args.ph
    if args.do_ is not None:
        m["dissolved_oxygen"] = args.do_
    if args.nh3 is not None:
        m["ammonia"] = args.nh3

    payload = {
        "device_id": args.device,
        "pond_id": args.pond_id,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "metrics": m,
    }
    url = "http://%s:%d/api/v1/water-quality" % (args.host, args.port)
    req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"),
                                 headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            body = json.loads(r.read().decode("utf-8"))
    except Exception as e:
        print("上报失败：%s" % e)
        print("请确认服务端已启动（启动服务.bat），且 host/port 正确。")
        return 1

    print("上报地址: %s" % url)
    print("上报内容: %s" % json.dumps(payload, ensure_ascii=False))
    print("服务端响应: %s" % json.dumps(body, ensure_ascii=False))
    if body.get("code") == 0:
        print("成功：塘口 %s 已接入数据，刷新「实时看板」即可看到。" % args.pond_id)
        return 0
    print("失败：%s" % body.get("message"))
    return 1


if __name__ == "__main__":
    sys.exit(main())
