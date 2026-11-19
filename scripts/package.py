# -*- coding: utf-8 -*-
"""打包 smart-aquaculture 源码为 zip（排除缓存/数据库/运行时文件）。"""
import os
import zipfile

ROOT = r"C:\Users\MEC\WorkBuddy\2026-09-12-19-32-40\smart-aquaculture"
OUT = r"C:\Users\MEC\WorkBuddy\2026-09-12-19-32-40\智慧渔业智慧养殖平台_代码.zip"

EXCLUDE_DIRS = {"__pycache__", "edge_cache", ".git", ".idea", ".vscode"}
EXCLUDE_EXT = {".pyc", ".pyo", ".db", ".db-shm", ".db-wal", ".log"}


def skipped(name):
    return os.path.splitext(name)[1].lower() in EXCLUDE_EXT


count = 0
with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = [d for d in dirnames if d not in EXCLUDE_DIRS]
        for fn in filenames:
            if skipped(fn):
                continue
            full = os.path.join(dirpath, fn)
            arc = os.path.join("smart-aquaculture", os.path.relpath(full, ROOT))
            zf.write(full, arc)
            count += 1
print("files:", count, "size: %.2f MB" % (os.path.getsize(OUT) / 1048576))
