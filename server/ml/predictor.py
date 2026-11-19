# -*- coding: utf-8 -*-
"""机器学习预测模块：随机森林生长预测 + 溶解氧趋势预测（scikit-learn）。"""
import os
import random
from datetime import datetime, timedelta

import server.db as db

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
MODEL_DIR = os.path.join(BASE_DIR, "server", "ml", "models")


class GrowthPredictor:
    """基于随机森林回归的海鲈生长预测模型。

    特征：养殖天数、水温、溶解氧、氨氮、日投喂率(%)、放养密度系数
    目标：平均体重 (g)
    """

    FEATURE_ORDER = ["age_days", "temp", "do", "ammonia", "feed_rate", "density_factor"]

    def __init__(self):
        self.model = None
        self.metrics = {}
        self._load()

    def _load(self):
        path = os.path.join(MODEL_DIR, "growth_rf.joblib")
        if os.path.exists(path):
            import joblib
            bundle = joblib.load(path)
            self.model = bundle["model"]
            self.metrics = bundle.get("metrics", {})

    @property
    def ready(self):
        return self.model is not None

    def predict_weight(self, age_days, temp=26.0, do=6.0, ammonia=0.2,
                       feed_rate=3.0, density_factor=1.0):
        x = [[age_days, temp, do, ammonia, feed_rate, density_factor]]
        return float(self.model.predict(x)[0])

    def growth_curve(self, start_age, days=90, temp=26.0):
        curve = []
        for offset in range(0, days + 1, 5):
            age = start_age + offset
            w = self.predict_weight(age, temp)
            curve.append({"date": (datetime.now() + timedelta(days=offset)).strftime("%Y-%m-%d"),
                          "age_days": age, "weight_g": round(w, 1)})
        return curve

    def metrics(self):
        return {"algorithm": "RandomForestRegressor", "features": self.FEATURE_ORDER,
                "trained": bool(self.ready), **self.metrics}

    def model_info(self):
        """统一对外模型信息（兼容 metrics 为属性 dict 或旧方法两种情况）。"""
        m = self.metrics if isinstance(self.metrics, dict) else {}
        return {"algorithm": "RandomForestRegressor", "features": self.FEATURE_ORDER,
                "trained": bool(self.ready), **m}


def train_growth_model(n_samples=40000, seed=42):
    """用领域经验公式 + 噪声合成训练集并训练随机森林，输出评估指标。"""
    import numpy as np
    from sklearn.ensemble import RandomForestRegressor
    from sklearn.metrics import mean_absolute_error, r2_score
    from sklearn.model_selection import train_test_split

    rng = np.random.default_rng(seed)
    age = rng.integers(30, 540, n_samples).astype(float)          # 养殖天数
    temp = rng.normal(26, 4, n_samples).clip(12, 36)              # 水温
    do = rng.normal(5.8, 1.2, n_samples).clip(2.5, 9.5)           # 溶解氧
    ammonia = rng.exponential(0.25, n_samples).clip(0.01, 1.2)    # 氨氮
    feed_rate = rng.normal(3.2, 1.0, n_samples).clip(0.8, 6.5)    # 投喂率%
    density = rng.normal(1.0, 0.25, n_samples).clip(0.4, 1.8)     # 密度系数

    # 海鲈生长经验模型：适温(22~30℃)生长快；高氨氮/低氧抑制生长
    temp_factor = np.exp(-((temp - 26.0) ** 2) / 120.0)
    stress = 1.0 - 0.35 * np.clip(ammonia / 0.8, 0, 1) - 0.3 * np.clip((6.0 - do) / 3.5, 0, 1)
    feed_factor = np.clip(feed_rate / 3.2, 0.4, 1.3)
    weight = 8 + 1.75 * age * temp_factor * stress * feed_factor / density
    weight = np.clip(weight, 8, 1200) * (1 + rng.normal(0, 0.03, n_samples))

    X = np.column_stack([age, temp, do, ammonia, feed_rate, density])
    X_tr, X_te, y_tr, y_te = train_test_split(X, weight, test_size=0.2, random_state=seed)
    model = RandomForestRegressor(n_estimators=120, max_depth=14, random_state=seed, n_jobs=-1)
    model.fit(X_tr, y_tr)
    pred = model.predict(X_te)
    metrics = {"r2": round(float(r2_score(y_te, pred)), 4),
               "mae_g": round(float(mean_absolute_error(y_te, pred)), 2),
               "train_samples": n_samples}

    os.makedirs(MODEL_DIR, exist_ok=True)
    import joblib
    joblib.dump({"model": model, "metrics": metrics}, os.path.join(MODEL_DIR, "growth_rf.joblib"))
    return model, metrics


def predict_do_trend(pond_id, horizon_hours=6):
    """基于近 24h 历史 + 线性回归 + 日周期正弦项，预测未来溶解氧趋势。"""
    rows = db.query(
        "SELECT dissolved_oxygen, collect_time FROM t_water_quality WHERE pond_id=? "
        "ORDER BY collect_time DESC LIMIT 300", (pond_id,))
    if len(rows) < 20:
        return None
    rows = list(reversed(rows))
    times, values = [], []
    for r in rows:
        try:
            t = datetime.strptime(str(r["collect_time"])[:19], "%Y-%m-%d %H:%M:%S")
            times.append(t)
            values.append(float(r["dissolved_oxygen"]))
        except (ValueError, TypeError):
            continue
    if len(values) < 20:
        return None
    t0 = times[0]
    xs = [((t - t0).total_seconds() / 3600.0) for t in times]
    xs_feat = [[x, math_sin(2 * 3.14159 * (t0 + timedelta(hours=x)).hour / 24.0)] for x in xs]
    from sklearn.linear_model import LinearRegression
    reg = LinearRegression()
    reg.fit(xs_feat, values)
    last_t, last_v = times[-1], values[-1]
    forecast = []
    for h in range(1, horizon_hours + 1):
        x = xs[-1] + h
        feat = [[x, math_sin(2 * 3.14159 * (last_t + timedelta(hours=h)).hour / 24.0)]]
        v = reg.predict(feat)[0]
        forecast.append({"time": (last_t + timedelta(hours=h)).strftime("%Y-%m-%d %H:%M"),
                         "dissolved_oxygen": round(max(0.5, v), 2)})
    risk = "正常"
    min_v = min(f["dissolved_oxygen"] for f in forecast)
    if min_v < 3.0:
        risk = "高风险：预测期内溶氧可能低于 3.0 mg/L，建议提前开增氧机"
    elif min_v < 4.0:
        risk = "预警：预测期内溶氧可能低于 4.0 mg/L，建议关注"
    return {"pond_id": pond_id, "base_time": last_t.strftime("%Y-%m-%d %H:%M"),
            "current_do": round(last_v, 2), "forecast": forecast, "risk": risk,
            "algorithm": "LinearRegression(time + daily-cycle)"}


def math_sin(x):
    import math
    return math.sin(x)


_growth_predictor = None


def get_growth_predictor():
    global _growth_predictor
    if _growth_predictor is None:
        _growth_predictor = GrowthPredictor()
    return _growth_predictor


# 模块级别导出，api.py 使用 from server.ml.predictor import growth_predictor
class _LazyProxy:
    def __getattr__(self, name):
        return getattr(get_growth_predictor(), name)


growth_predictor = _LazyProxy()
