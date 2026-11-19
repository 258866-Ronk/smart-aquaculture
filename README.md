# 人工智能技术助力斗门鲈鱼养殖 —— 智慧渔业一体化平台（可运行版）

依据《软件需求说明书（SRS）V1.0》与系统框架图实现的 **云—边—端三层架构** 全链路可运行系统，
覆盖 SRS 中 FR-01 ~ FR-03、FR-05 ~ FR-07 的核心功能（FR-04 微信小程序部分由 Web 移动端适配页 +
标准 HTTPS 接口预留承载）。

## 一、系统架构与模块对照

| 框架层 | 本项目实现 | 对应需求 |
|---|---|---|
| 感知层 | 传感器模拟器（内置昼夜溶氧周期模型），支持外接真实 RS232 串口设备 | FR-01-05 |
| 边缘层 | `edge/gateway.py` 边缘网关：RS232 帧协议解析（0xAA55 + CRC16-Modbus）、TCP Client 长连接、断网本地缓存 + 补传、采集日志 | FR-01 |
| 网络层 | TCP 长连接（JSON\n 报文）+ HTTP | 6.1 / 6.2 |
| 平台层 | `server/` Flask 数据分发：TCP Server 多客户端并发（线程）、RESTful API、SQLite（可切 MySQL）、阈值告警引擎、AI 推理 | FR-02 / FR-06 |
| 应用层 | Web 可视化大屏（ECharts）+ PyQt5 模型调试界面 | FR-03 / FR-06-05 |
| 安全运维 | 登录鉴权接口、入参白名单校验、操作日志 t_op_log、统一 JSON 响应 | NFR-S |

## 二、快速启动（Windows）

```bat
:: 1. 安装依赖（首次）
python -m venv venv
venv\Scripts\pip install -r requirements.txt

:: 2. 初始化数据（建表 + 7天假数据 + 训练模型 + 生成CV测试图）
venv\Scripts\python scripts\init_data.py

:: 3. 启动服务端（Flask HTTP 5000 + TCP Server 9000）
venv\Scripts\python run_server.py

:: 4. 另开一个窗口，启动边缘网关/传感器模拟器（持续上报实时数据）
venv\Scripts\python run_simulator.py

:: 5.（可选）PyQt5 模型调试界面
venv\Scripts\python pyqt_app\main.py
```

浏览器打开 **http://127.0.0.1:5000/** 即可看到实时大屏（模拟器运行时数据约 5 秒刷新一次）。

也可直接双击 `start_server.bat` / `start_simulator.bat` / `start_pyqt.bat`。

### 传感器接入（卡片显示"待接入传感器"怎么办）

三种方式，任选其一，详见 **`docs/传感器接入指南.md`**：

1. **自动接入（默认）**：`run_simulator.py` 保持运行即可。边缘网关每 20 秒从服务端拉取一次塘口列表，
   新增塘口后无需任何操作，约 20 秒内自动开始上报数据，设备号形如 `EDGE-GW-01-TANK-D`。
2. **一键接入**：实时看板该塘口卡片上点「一键接入传感器」（接口 `POST /api/v1/sensor/simulate`），1 秒生效。
3. **接真实硬件**：RS232 串口（改 `config.json -> collection.serial`）或 HTTP/TCP 上报，
   示例脚本 `python scripts/push_demo.py TANK-D`。

| 现象 | 原因 | 处理 |
|---|---|---|
| 全部塘口都"待接入" | 模拟器窗口没开 | 双击 `启动模拟器.bat` |
| 只有新塘口"待接入" | 还没到刷新点 | 等 20 秒，或点「一键接入传感器」 |
| 数据停住不动 | 服务端重启过，TCP 断连 | 网关自动重连；否则重启模拟器 |

### 自测验证

```bat
venv\Scripts\python scripts\selftest.py
```

覆盖 60 项检查：页面/静态资源、HTML 与 JS 元素一致性、全部 API（含禁用渔药拦截 403、
非法入参 400、错误密码 401）、塘口新增后各处同步、传感器接入、生长分析数据合理性等。
自测脚本会清理自己产生的测试数据，可反复运行、不污染数据库。

## 二点五、业务功能清单（Web 大屏 11 个页签）

| 页签 | 功能 |
|---|---|
| 实时看板 | 全部塘口最新水质四指标卡片，10 秒自动刷新，异常变色，无数据塘口显示"待接入" |
| 历史趋势 | 任意塘口 × 4 指标 × 24h/3天/7天，数据抽稀防卡顿 |
| 告警中心 | 阈值告警列表、按塘口/状态筛选、一键处理 |
| 塘口管理 | 塘口 CRUD，新增后看板与所有下拉框即时同步 |
| AI 预测 | 随机森林生长曲线、未来 6h 溶氧预测、今日投喂建议 |
| 密度识别 | OpenCV 鱼群密度估算（上传图片或一键测试图） |
| **生长分析** | 日均水温/溶氧、日投喂量柱状图、生长曲线与上市规格线、**预估生产周期 / 预估产量 / 饲料系数 FCR** |
| **投喂管理** | 投喂记录录入与查询、今日/日均/累计统计 |
| **员工管理** | 员工增删改、在职/离职切换、负责塘口绑定 |
| **苗种管理** | 批次登记（品种/供应商/数量/规格/放苗日期） |
| **用药管理** | 用药记录、休药期管理，**内置禁用渔药清单自动拦截（孔雀石绿、氯霉素等）** |

## 三、RESTful API（统一响应 `{"code":0,"message":"success","data":{}}`）

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | /api/v1/water-quality | 上报水质数据（支持 `{"type":"batch","records":[...]}` 批量补传） |
| GET | /api/v1/water-quality/latest?pond_id= | 最新一条水质 |
| GET | /api/v1/water-quality/history?pond_id=&start=&end= | 历史区间查询 |
| GET | /api/v1/water-quality/overview | 各塘最新数据汇总 |
| POST | /api/v1/feeding | 上报投喂记录 |
| GET | /api/v1/feeding/advice?pond_id= | 生长模型投喂建议 |
| POST/GET | /api/v1/vision/density | 上传图像识别鱼群密度 / 查询记录 |
| GET | /api/v1/prediction/growth?pond_id= | 生长趋势预测（随机森林） |
| GET | /api/v1/prediction/water-quality?pond_id= | 未来 6h 溶氧趋势预测 |
| GET | /api/v1/alerts?pond_id=&status= | 告警查询 |
| POST | /api/v1/alerts/<id>/handle | 处理告警 |
| GET/POST/PUT/DELETE | /api/v1/ponds | 塘口 CRUD |
| POST | /api/v1/auth/login | 登录（演示账号 admin/admin123, farmer/farmer123） |
| GET | /api/v1/stats/overview | 系统总览 |

接口可直接用 Postman / curl 测试（FR-02-05）。

## 四、协议说明（与 SRS 6.1/6.2 一致）

- **RS232**：9600,8,N,1；帧 `AA 55 | 地址 | 功能码 | 长度 | 数据域(温度/pH/DO/氨氮 ×10 整型) | CRC16 | 0D`，
  CRC16-Modbus 校验范围：地址 → 数据域末字节。见 `server/protocol.py`（含 build/parse）。
- **TCP**：服务端监听 9000，JSON(UTF-8) + `\n` 分隔，心跳 `{"type":"heartbeat"}`，断网续传走
  `{"type":"batch","records":[...]}`，可多客户端同时接入。

## 五、目录结构

```
smart-aquaculture/
├── config.json              # 全局配置（端口/阈值/塘口/串口参数）
├── run_server.py            # 服务端启动（HTTP + TCP）
├── run_simulator.py         # 边缘网关/传感器模拟启动
├── requirements.txt
├── server/
│   ├── protocol.py          # RS232 帧协议 + CRC16-Modbus + TCP 报文
│   ├── tcp_server.py        # TCP Server 多客户端并发
│   ├── app_factory.py       # Flask 应用工厂
│   ├── api.py               # RESTful API
│   ├── db.py                # 数据库层（SQLite 默认，可切 MySQL）
│   ├── alerts.py            # 阈值告警引擎（含 10 分钟去重）
│   ├── ml/predictor.py      # 随机森林生长预测 + 溶氧趋势预测
│   ├── ml/models/           # 训练好的模型文件
│   └── vision/density.py    # OpenCV 鱼群密度识别 + 合成测试图
├── edge/gateway.py          # 边缘网关（串口/TCP/断网续传）
├── pyqt_app/main.py         # PyQt5 模型调试界面
├── scripts/init_data.py     # 初始化：建表/假数据/训练模型/测试图
└── web/                     # Web 大屏（原生 HTML/CSS/JS + 本地 ECharts）
```

## 六、验收对照（SRS 第 9 章）

- AC-01 采集：`server/protocol.py` 自带帧构造/解析/CRC 校验；网关支持串口与 TCP 双通道 ✓
- AC-02 分发：TCP Server 线程并发 + 统一 JSON 响应，Postman 可测 ✓
- AC-03 前端：实时看板 / 历史趋势 / 告警列表 / 塘口管理 ✓
- AC-05 视觉：`POST /api/v1/vision/density` 传图即出密度等级，含合成测试图 ✓
- AC-06 预测：随机森林生长模型（训练输出 R²/MAE）+ PyQt5 可视化界面 ✓
- AC-07 联调：`scripts/init_data.py` 一键假数据打通 采集→分发→展示→预测 全链路 ✓

> 说明：MySQL 通过 `config.json -> database.type` 切换（需 `pip install PyMySQL`）；
> 生产环境 HTTPS 由反向代理（Nginx/Caddy）终结即可满足小程序域名要求。
