# -*- coding: utf-8 -*-
"""生成鱼群密度识别「原图 vs 识别标注图」对比图（用于答辩 PPT 展示）。

复用 server/vision/density.py 的真实分割链路：
去噪 -> ROI -> 自适应阈值 -> 形态学 -> 连通域，再把命中目标框出来标注。
"""
import os
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from server.vision.density import _count_fish, LEVEL_THRESHOLDS

SRC = os.path.join(BASE, "data", "images", "sample_pond.jpg")
OUT = r"C:\Users\MEC\WorkBuddy\2026-09-12-19-32-40\_ppt\shots\vision_annotated.png"
FONT = r"C:\Windows\Fonts\msyh.ttc"


def annotate(img):
    """按 _count_fish 同样的链路取轮廓并画框。"""
    h, w = img.shape[:2]
    roi = img[int(h * .05):int(h * .95), int(w * .05):int(w * .95)]
    blur = cv2.GaussianBlur(roi, (5, 5), 0)
    gray = cv2.cvtColor(blur, cv2.COLOR_BGR2GRAY)
    th = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                               cv2.THRESH_BINARY_INV, 25, 8)
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    th = cv2.morphologyEx(th, cv2.MORPH_OPEN, kernel, iterations=2)
    th = cv2.morphologyEx(th, cv2.MORPH_CLOSE, kernel, iterations=2)
    contours, _ = cv2.findContours(th, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    h2, w2 = th.shape
    min_area = (h2 * w2) * 0.0004
    max_area = (h2 * w2) * 0.05
    vis = roi.copy()
    count, covered = 0, 0
    for c in contours:
        a = cv2.contourArea(c)
        if min_area <= a <= max_area:
            count += 1
            covered += a
            x, y, cw, ch = cv2.boundingRect(c)
            cv2.rectangle(vis, (x, y), (x + cw, y + ch), (60, 179, 113), 1)
            cv2.drawContours(vis, [c], -1, (60, 179, 113), 1)
    return vis, count, covered / float(h2 * w2)


def main():
    img = cv2.imread(SRC)
    vis, count, coverage = annotate(img)
    # 规范化计数（与 estimate_density 相同口径）
    area_factor = (img.shape[0] * img.shape[1]) / (640.0 * 480.0)
    count_norm = int(count / max(area_factor, 0.01))
    level = "低" if count_norm < LEVEL_THRESHOLDS["低"] else ("中" if count_norm < LEVEL_THRESHOLDS["中"] else "高")
    confidence = round(min(0.95, 0.55 + coverage * 0.4), 2)

    vis_full = img.copy()
    h, w = img.shape[:2]
    vis_full[int(h * .05):int(h * .95), int(w * .05):int(w * .95)] = vis

    scale = 1.6
    a = cv2.resize(img, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
    b = cv2.resize(vis_full, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
    gap = 46
    canvas = np.full((a.shape[0] * 2 + gap, a.shape[1], 3), 255, dtype=np.uint8)
    canvas[:a.shape[0]] = a
    canvas[a.shape[0] + gap:] = b

    im = Image.fromarray(cv2.cvtColor(canvas, cv2.COLOR_BGR2RGB))
    d = ImageDraw.Draw(im)
    f1 = ImageFont.truetype(FONT, 34)
    f2 = ImageFont.truetype(FONT, 30)
    d.rectangle([0, a.shape[0], im.width, a.shape[0] + gap], fill=(68, 114, 196))
    d.text((18, 12), "原始图像（模拟水下相机）", font=f1, fill=(40, 40, 40))
    d.text((18, a.shape[0] + 8),
           "识别结果：%s 密度 · 估计鱼数 %d 尾 · 覆盖率 %.0f%% · 置信度 %.2f" % (level, count_norm, coverage * 100, confidence),
           font=f2, fill=(255, 255, 255))
    im.save(OUT)
    print("saved", OUT, im.size, "count=", count_norm, "level=", level, "conf=", confidence)


if __name__ == "__main__":
    main()
