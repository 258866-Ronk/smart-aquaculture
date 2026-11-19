# -*- coding: utf-8 -*-
"""边缘网关 / 采集终端启动入口。用法：python run_simulator.py"""
import os
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

from edge.gateway import main  # noqa: E402

if __name__ == "__main__":
    main()
