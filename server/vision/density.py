# -*- coding: utf-8 -*-
"""计算机视觉鱼群密度识别（OpenCV）。

思路：图像去噪 -> ROI 裁剪 -> HSV/灰度分割鱼体目标 -> 形态学清理 -> 连通域计数
输出：密度等级（低/中/高）、估计鱼数、置信度。附带合成测试图生成器，便于无真实相机调试。
"""
import cv2
import numpy as np

# 密度等级阈值：单位面积内目标数量（可按相机视野标定）
LEVEL_THRESHOLDS = {"低": 25, "中": 70}


def estimate_density(image_path: str):
    """估计一张塘口图像的鱼群密度。返回 (density_level, fish_count, confidence)。"""
    img = cv2.imread(image_path)
    if img is None:
        raise ValueError("无法读取图像: %s" % image_path)
    count, coverage = _count_fish(img)
    area_factor = (img.shape[0] * img.shape[1]) / (640.0 * 480.0)
    count_norm = int(count / max(area_factor, 0.01))
    if count_norm < LEVEL_THRESHOLDS["低"]:
        level = "低"
    elif count_norm < LEVEL_THRESHOLDS["中"]:
        level = "中"
    else:
        level = "高"
    confidence = round(min(0.95, 0.55 + coverage * 0.4), 2)
    return level, count, confidence


def _count_fish(img):
    """基于暗色目标分割的鱼体计数，返回 (目标数, 目标覆盖率)。"""
    # ROI：去边 5%（去水印/刻度）
    h, w = img.shape[:2]
    img = img[int(h * .05):int(h * .95), int(w * .05):int(w * .95)]
    blur = cv2.GaussianBlur(img, (5, 5), 0)
    gray = cv2.cvtColor(blur, cv2.COLOR_BGR2GRAY)
    # 自适应阈值分割比水体暗的目标（鱼体/阴影）
    th = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                               cv2.THRESH_BINARY_INV, 25, 8)
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    th = cv2.morphologyEx(th, cv2.MORPH_OPEN, kernel, iterations=2)
    th = cv2.morphologyEx(th, cv2.MORPH_CLOSE, kernel, iterations=2)
    contours, _ = cv2.findContours(th, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    h2, w2 = th.shape
    min_area = (h2 * w2) * 0.0004   # 过滤噪声小块
    max_area = (h2 * w2) * 0.05     # 过滤背景大块
    count = 0
    covered = 0
    for c in contours:
        a = cv2.contourArea(c)
        if min_area <= a <= max_area:
            count += 1
            covered += a
    return count, covered / float(h2 * w2)


def generate_test_image(path: str, fish_count=60, width=640, height=480, seed=None):
    """生成合成塘口测试图（蓝色水体 + 灰黑色椭圆鱼体），用于无真实相机调试。"""
    rng = np.random.default_rng(seed)
    img = np.full((height, width, 3), 0, dtype=np.uint8)
    img[:, :, 0] = 160  # 蓝
    img[:, :, 1] = 120  # 绿
    img[:, :, 2] = 70   # 红 -> 水体蓝绿色
    noise = rng.normal(0, 10, (height, width, 1)).astype(np.int16)
    img = np.clip(img.astype(np.int16) + noise, 0, 255).astype(np.uint8)
    for _ in range(fish_count):
        cx, cy = int(rng.integers(20, width - 20)), int(rng.integers(20, height - 20))
        angle = float(rng.uniform(0, 180))
        ax, ay = int(rng.integers(9, 16)), int(rng.integers(3, 6))
        cv2.ellipse(img, (cx, cy), (ax, ay), angle, 0, 360,
                    (int(rng.integers(25, 60)),) * 3, -1)
    cv2.imwrite(path, img)
    return path
