# -*- coding: utf-8 -*-
"""PyQt5 模型调试界面：展示生长预测曲线 + 溶氧趋势预测（FR-06-05）。"""
import os
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)


def main():
    try:
        from PyQt5.QtChart import (QChart, QChartView, QDateTimeAxis, QLineSeries,
                                   QValueAxis)
        from PyQt5.QtCore import QDateTime, Qt
        from PyQt5.QtGui import QPainter
        from PyQt5.QtWidgets import (QApplication, QComboBox, QFileDialog,
                                     QHBoxLayout, QLabel, QMainWindow, QPushButton,
                                     QTabWidget, QTextEdit, QVBoxLayout, QWidget)
    except ImportError:
        print("未安装 PyQt5，请执行: pip install PyQt5 PyQtChart")
        print("提示：Web 大屏同样提供预测结果可视化，可不使用本界面。")
        sys.exit(1)

    import json as _json
    import urllib.request

    API = "http://127.0.0.1:5000/api/v1"

    def api_get(path):
        try:
            with urllib.request.urlopen(API + path, timeout=5) as r:
                data = _json.loads(r.read().decode("utf-8"))
                return data.get("data")
        except Exception as e:
            print("接口调用失败: %s" % e)
            return None

    class MainWindow(QMainWindow):
        def __init__(self):
            super().__init__()
            self.setWindowTitle("AI 模型调试界面 — 斗门鲈鱼生长/水质预测")
            self.resize(960, 640)
            tabs = QTabWidget()
            self.setCentralWidget(tabs)

            # ---- Tab1: 生长预测曲线 ----
            tab1 = QWidget()
            v1 = QVBoxLayout(tab1)
            h1 = QHBoxLayout()
            h1.addWidget(QLabel("塘口:"))
            self.pond_combo = QComboBox()
            ponds = api_get("/ponds") or []
            for p in ponds:
                self.pond_combo.addItem("%s(%s)" % (p.get("name"), p.get("pond_id")), p.get("pond_id"))
            h1.addWidget(self.pond_combo)
            btn = QPushButton("查询预测")
            btn.clicked.connect(self.refresh_growth)
            h1.addWidget(btn)
            export_btn = QPushButton("导出 CSV")
            export_btn.clicked.connect(self.export_csv)
            h1.addWidget(export_btn)
            h1.addStretch()
            v1.addLayout(h1)
            self.growth_info = QLabel("点击“查询预测”获取生长曲线")
            v1.addWidget(self.growth_info)
            self.growth_chart = QChart()
            self.growth_chart.legend().hide()
            self.growth_view = QChartView(self.growth_chart)
            self.growth_view.setRenderHint(QPainter.Antialiasing)
            v1.addWidget(self.growth_view)
            tabs.addTab(tab1, "生长预测")

            # ---- Tab2: 溶氧趋势预测 ----
            tab2 = QWidget()
            v2 = QVBoxLayout(tab2)
            h2 = QHBoxLayout()
            self.pond_combo2 = QComboBox()
            for p in ponds:
                self.pond_combo2.addItem("%s(%s)" % (p.get("name"), p.get("pond_id")), p.get("pond_id"))
            btn2 = QPushButton("预测未来 6 小时溶氧")
            btn2.clicked.connect(self.refresh_do)
            h2.addWidget(QLabel("塘口:"))
            h2.addWidget(self.pond_combo2)
            h2.addWidget(btn2)
            h2.addStretch()
            v2.addLayout(h2)
            self.do_text = QTextEdit()
            self.do_text.setReadOnly(True)
            v2.addWidget(self.do_text)
            tabs.addTab(tab2, "水质预测")

        def refresh_growth(self):
            pond_id = self.pond_combo.currentData()
            data = api_get("/prediction/growth?pond_id=" + (pond_id or ""))
            if not data:
                self.growth_info.setText("获取失败（请确认服务端已启动）")
                return
            self.growth_info.setText(
                "当前养殖 %d 天，水温 %.1f℃，模型 R²=%s" %
                (data.get("current_age_days", 0), data.get("water_temp", 0),
                 data.get("model", {}).get("r2", "-")))
            chart = QChart()
            series = QLineSeries()
            series.setName("平均体重(g)")
            for pt in data.get("curve", []):
                ts = QDateTime.fromString(pt["date"] + " 12:00", "yyyy-MM-dd HH:mm").toMSecsSinceEpoch()
                series.append(ts, pt["weight_g"])
            axis_x = QDateTimeAxis()
            axis_x.setFormat("MM-dd")
            axis_x.setTitleText("日期")
            axis_y = QValueAxis()
            axis_y.setTitleText("平均体重 (g)")
            chart.addSeries(series)
            chart.setAxisX(axis_x, series)
            chart.setAxisY(axis_y, series)
            chart.setTitle("生长预测曲线（RandomForest）")
            self.growth_chart.deleteLater()
            self.growth_chart = chart
            self.growth_view.setChart(chart)
            self._last_curve = data.get("curve", [])

        def refresh_do(self):
            pond_id = self.pond_combo2.currentData()
            data = api_get("/prediction/water-quality?pond_id=" + (pond_id or ""))
            if not data:
                self.do_text.setPlainText("获取失败或历史数据不足")
                return
            lines = ["基准时间: %s   当前溶氧: %.2f mg/L" % (data["base_time"], data["current_do"]),
                     "风险提示: %s" % data["risk"], ""]
            for f in data["forecast"]:
                lines.append("%s  预测溶氧 %.2f mg/L" % (f["time"], f["dissolved_oxygen"]))
            self.do_text.setPlainText("\n".join(lines))

        def export_csv(self):
            path, _ = QFileDialog.getSaveFileName(self, "导出", "growth.csv", "CSV (*.csv)")
            if path and getattr(self, "_last_curve", None):
                import csv
                with open(path, "w", newline="", encoding="utf-8-sig") as f:
                    w = csv.writer(f)
                    w.writerow(["date", "age_days", "weight_g"])
                    for r in self._last_curve:
                        w.writerow([r["date"], r["age_days"], r["weight_g"]])

    app = QApplication(sys.argv)
    win = MainWindow()
    win.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
