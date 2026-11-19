# -*- coding: utf-8 -*-
"""初始化脚本：初始化数据库、写入塘口假数据、生成 7 天历史水质数据、训练模型、生成 CV 测试图。

用法：python scripts/init_data.py
"""
import os
import random
import sys
from datetime import datetime, timedelta

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

import json

from server import db as dbm
from server.alerts import check_metrics


def main():
    with open(os.path.join(BASE_DIR, "config.json"), "r", encoding="utf-8") as f:
        config = json.load(f)
    dbm.init_db(config)
    print("1) 数据库表结构初始化完成")

    # 塘口
    for p in config.get("ponds", []):
        if not dbm.query_one("SELECT 1 FROM t_pond WHERE pond_id=?", (p["pond_id"],)):
            dbm.execute(
                "INSERT INTO t_pond(pond_id, name, area_mu, stock_count, stock_date, manager, create_time) "
                "VALUES (?,?,?,?,?,?,datetime('now','localtime'))",
                (p["pond_id"], p["name"], p.get("area_mu", 0), p.get("stock_count", 0),
                 p.get("stock_date"), p.get("manager", "")))
    print("2) 塘口数据写入完成: %s" % ", ".join(p["pond_id"] for p in config.get("ponds", [])))

    # 7 天历史水质（每 2 小时一条），包含昼夜溶氧周期
    if dbm.query_one("SELECT COUNT(*) AS n FROM t_water_quality")["n"] < 100:
        now = datetime.now()
        for p in config.get("ponds", []):
            base_temp = random.uniform(26, 29)
            for h in range(24 * 7, 0, -2):
                ts = (now - timedelta(hours=h)).strftime("%Y-%m-%d %H:%M:%S")
                hour = (now - timedelta(hours=h)).hour
                do = round(4.0 + 2.4 * (0.5 + 0.5 * __import__("math").sin((hour - 6) / 24.0 * 2 * 3.14159))
                           + random.gauss(0, 0.35), 2)
                temp = round(base_temp + random.gauss(0, 1.0), 1)
                ph = round(random.gauss(7.8, 0.15), 1)
                ammonia = round(abs(random.gauss(0.3, 0.1)), 3)
                dbm.execute(
                    "INSERT INTO t_water_quality(pond_id, device_id, temperature, ph, dissolved_oxygen, ammonia, collect_time, create_time) "
                    "VALUES (?,?,?,?,?,?,?,?)",
                    (p["pond_id"], "HIST-SIM", temp, ph, do, ammonia, ts, ts))
        # 人为制造 1 条低氧数据触发告警链路演示
        last = config["ponds"][0]["pond_id"]
        ts = now.strftime("%Y-%m-%d %H:%M:%S")
        dbm.execute(
            "INSERT INTO t_water_quality(pond_id, device_id, temperature, ph, dissolved_oxygen, ammonia, collect_time, create_time) "
            "VALUES (?,?,?,?,?,?,?,?)", (last, "HIST-SIM", 28.5, 7.9, 3.1, 0.62, ts, ts))
        check_metrics(last, {"dissolved_oxygen": 3.1, "ammonia": 0.62}, config["thresholds"], ts)
        print("3) 7 天历史水质数据生成完成（含 1 条告警演示数据）")
    else:
        print("3) 历史数据已存在，跳过")

    # 投喂记录
    if dbm.query_one("SELECT COUNT(*) AS n FROM t_feeding")["n"] == 0:
        now = datetime.now()
        for p in config.get("ponds", []):
            for d in range(7):
                ts = (now - timedelta(days=d, hours=random.randint(0, 3))).strftime("%Y-%m-%d %H:%M:%S")
                dbm.execute("INSERT INTO t_feeding(pond_id, feed_kg, feed_time, note) VALUES (?,?,?,?)",
                            (p["pond_id"], round(random.uniform(28, 45), 1), ts, "常规投喂"))
        print("4) 投喂记录生成完成")
    else:
        print("4) 投喂记录已存在，跳过")

    # 训练生长预测模型
    from server.ml.predictor import train_growth_model
    model, metrics = train_growth_model()
    print("5) 生长预测模型训练完成: %s" % metrics)

    # 员工 / 苗种 / 用药演示数据
    if dbm.query_one("SELECT COUNT(*) AS n FROM t_employee")["n"] == 0:
        employees = [
            ("陈志强", "养殖工", "13800000001", "TANK-A", "2024-03-01"),
            ("陈小红", "投喂员", "13800000002", "TANK-B", "2025-01-15"),
            ("李文斌", "技术员", "13800000003", "", "2025-06-01"),
            ("王海燕", "质检员", "13800000004", "TANK-C", "2026-02-10"),
        ]
        for name, role, phone, pond, hire in employees:
            dbm.execute("INSERT INTO t_employee(name, role, phone, pond_id, hire_date, status, create_time) "
                        "VALUES (?,?,?,?,?,1,datetime('now','localtime'))", (name, role, phone, pond, hire))
        print("5a) 员工演示数据完成")
    if dbm.query_one("SELECT COUNT(*) AS n FROM t_seedling")["n"] == 0:
        seedlings = [
            ("TANK-A", "B2026-03-01", "海鲈", "白蕉育苗场A", 32000, 5.0, "2026-03-01"),
            ("TANK-B", "B2026-03-15", "海鲈", "白蕉育苗场B", 40000, 4.5, "2026-03-15"),
            ("TANK-C", "B2026-04-01", "海鲈", "斗门苗种基地", 46000, 4.0, "2026-04-01"),
        ]
        for pond, batch, sp, sup, cnt, spec, sd in seedlings:
            dbm.execute("INSERT INTO t_seedling(pond_id, batch_no, species, supplier, count, spec_cm, stock_date, note, create_time) "
                        "VALUES (?,?,?,?,?,?,?, '', datetime('now','localtime'))", (pond, batch, sp, sup, cnt, spec, sd))
        print("5b) 苗种演示数据完成")
    if dbm.query_one("SELECT COUNT(*) AS n FROM t_medication")["n"] == 0:
        meds = [
            ("TANK-A", "聚维酮碘", "0.5 mg/L", "全池泼洒", "水体消毒", "2026-08-20", "2026-08-20", "李文斌", 0),
            ("TANK-B", "恩诺沙星", "1.0 g/kg 饲料", "拌饵投喂", "细菌性肠炎预防", "2026-09-01", "2026-09-05", "王海燕", 7),
        ]
        for pond, mn, dose, method, reason, sd, ed, op, wd in meds:
            dbm.execute("INSERT INTO t_medication(pond_id, med_name, dosage, method, reason, start_date, end_date, operator, withdrawal_days, create_time) "
                        "VALUES (?,?,?,?,?,?,?,?,?,datetime('now','localtime'))", (pond, mn, dose, method, reason, sd, ed, op, wd))
        print("5c) 用药演示数据完成")

    # CV 测试图
    from server.vision.density import generate_test_image, estimate_density
    img_dir = os.path.join(BASE_DIR, "data", "images")
    os.makedirs(img_dir, exist_ok=True)
    test_img = os.path.join(img_dir, "sample_pond.jpg")
    if not os.path.exists(test_img):
        generate_test_image(test_img, fish_count=90, seed=7)
        level, count, conf = estimate_density(test_img)
        print("6) CV 测试图已生成并验证: 密度=%s, 计数=%d, 置信度=%.2f" % (level, count, conf))
    else:
        print("6) CV 测试图已存在，跳过")

    print("初始化全部完成。启动: python run_server.py")


if __name__ == "__main__":
    main()
