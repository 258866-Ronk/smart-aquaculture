/* 智慧渔业数据平台 前端逻辑 */
const API = "/api/v1";
const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => document.querySelectorAll(sel);

const METRIC_META = {
  temperature: { name: "水温", unit: "℃", good: [18, 32], warn: [15, 34] },
  ph: { name: "pH", unit: "", good: [6.8, 8.5], warn: [6.5, 9.0] },
  dissolved_oxygen: { name: "溶解氧", unit: "mg/L", good: [4.5, 99], warn: [3.5, 99] },
  ammonia: { name: "氨氮", unit: "mg/L", good: [0, 0.4], warn: [0, 0.5], lowerBetter: true },
};
const CHART_COLORS = ["#2f6fed", "#14b8a6", "#f59e0b", "#e5484d", "#8b5cf6"];

async function api(path, options = {}) {
  const resp = await fetch(API + path, options);
  const body = await resp.json();
  if (body.code !== 0) throw new Error(body.message);
  return body.data;
}
/* 操作反馈：成功/失败都有提示，避免"点了没反应" */
function toast(msg, ok = true) {
  let el = $("#toast");
  if (!el) {
    el = document.createElement("div");
    el.id = "toast";
    document.body.appendChild(el);
  }
  el.textContent = msg;
  el.className = "toast " + (ok ? "ok" : "err");
  el.style.display = "block";
  clearTimeout(el._t);
  el._t = setTimeout(() => { el.style.display = "none"; }, 3000);
}
function handleError(e) { toast("操作失败: " + e.message, false); }

function fmtVal(v, digits = 2) {
  return v === null || v === undefined ? "--" : Number(v).toFixed(digits);
}
/* 数据抽稀：点数太多时均匀采样，保证图表流畅 */
function sampleArr(arr, max = 500) {
  if (arr.length <= max) return arr;
  const out = [];
  const step = arr.length / max;
  for (let i = 0; i < max; i++) out.push(arr[Math.floor(i * step)]);
  return out;
}

function metricClass(key, v) {
  const m = METRIC_META[key];
  if (v === null || v === undefined) return "";
  if (m.lowerBetter) {
    if (v > m.warn[1]) return "crit";
    if (v > m.good[1]) return "warn";
    return "good";
  }
  if (v < m.warn[0]) return "crit";
  if (v < m.good[0] || v > m.good[1]) return "warn";
  return "good";
}

function switchTab(tab) {
  const btn = Array.from($$(".tab")).find(b => b.dataset.tab === tab);
  if (!btn) return;
  $$(".tab").forEach(b => b.classList.remove("active"));
  $$(".panel").forEach(p => p.classList.remove("active"));
  btn.classList.add("active");
  $("#tab-" + tab).classList.add("active");
  refreshTab(tab);
}

/* 支持 URL 直接打开指定页签：?tab=dashboard 或 #history */
function initTabFromUrl() {
  const q = new URLSearchParams(location.search).get("tab");
  const h = (location.hash || "").replace(/^#/, "");
  const tab = q || h;
  if (tab && $("#tab-" + tab)) switchTab(tab);
}

/* ---------- Tab 切换 ---------- */
$$(".tab").forEach(btn => btn.addEventListener("click", () => switchTab(btn.dataset.tab)));

function refreshTab(tab) {
  const fn = {
    dashboard: loadDashboard, history: loadHistory, alerts: loadAlerts,
    ponds: loadPonds, prediction: loadPrediction, vision: loadVisionRecords,
    analysis: loadAnalysis, feeding: loadFeeding, employees: loadEmployees,
    seedlings: loadSeedlings, medications: loadMedications,
  }[tab];
  if (fn) fn().catch(handleError);
}

/* ---------- 实时看板（显示全部塘口，无数据显示"待接入"） ---------- */
async function loadDashboard() {
  const [stats, rows] = await Promise.all([api("/stats/overview"), api("/water-quality/overview")]);
  $("#stat-row").innerHTML = [
    stat(stats.ponds, "接入塘口"),
    stat(stats.water_records, "水质数据总量"),
    stat(stats.alerts_active, "未处理告警", stats.alerts_active > 0 ? "crit" : ""),
    stat(fmtVal(stats.feed_total_kg, 1) + " kg", "累计投喂量"),
  ].join("");
  $("#pond-cards").innerHTML = rows.map(r => pondCard(r)).join("") || "<p class='hint'>暂无塘口，请到「塘口管理」新增。</p>";
}
function stat(num, label, cls = "") {
  return `<div class="stat"><div class="num ${cls}">${num}</div><div class="label">${label}</div></div>`;
}
function pondCard(r) {
  const m = (key, digits) => {
    const v = r[key];
    return `<div class="metric"><div class="v ${metricClass(key, v)}">${fmtVal(v, digits)}</div>
      <div class="k">${METRIC_META[key].name}${METRIC_META[key].unit ? "(" + METRIC_META[key].unit + ")" : ""}</div></div>`;
  };
  const badge = r.has_data ? "<span class='badge'>实时</span>" : "<span class='badge gray'>待接入传感器</span>";
  const foot = r.has_data
    ? "采集时间: " + r.collect_time + " · 设备: " + (r.device_id || "--")
    : "该塘口暂无水质数据 · <a href='javascript:void(0)' onclick='connectSensor(\"" + r.pond_id + "\")'>一键接入传感器</a>"
      + "<span class='hint-inline'>（边缘网关也会在约 20 秒内自动接入）</span>";
  return `<div class="card">
    <h3>${r.pond_name || r.pond_id} <small>(${r.pond_id})</small> ${badge}</h3>
    <div class="metrics">${m("temperature", 1)}${m("ph", 1)}${m("dissolved_oxygen", 2)}${m("ammonia", 3)}</div>
    <div class="time">${foot}</div>
  </div>`;
}

/* 一键接入传感器：立即为该塘口生成一条模拟读数 */
async function connectSensor(pondId) {
  try {
    await api("/sensor/simulate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ pond_id: pondId }),
    });
    toast("已为 " + pondId + " 接入传感器并生成读数", true);
    await loadDashboard();
  } catch (e) {
    handleError(e);
  }
}
window.connectSensor = connectSensor;

/* ---------- 历史趋势 ---------- */
async function loadHistory() {
  const pond = $("#hist-pond").value || ($("#hist-pond").options[0] && $("#hist-pond").options[0].value);
  if (!pond) { toast("暂无塘口，请先到塘口管理新增", false); return; }
  const metric = $("#hist-metric").value;
  const hours = parseInt($("#hist-range").value, 10);
  const start = new Date(Date.now() - hours * 3600 * 1000).toISOString().slice(0, 19).replace("T", " ");
  const data = await api(`/water-quality/history?pond_id=${pond}&start=${encodeURIComponent(start)}`);
  const recs = sampleArr(data.records || [], 400);   // 抽稀，避免几万点卡顿
  if (!recs.length) { toast("该时间范围内没有数据", false); }
  const times = recs.map(r => (r.collect_time || "").slice(5, 16));
  const rangeLabel = hours >= 24 ? (hours / 24) + "天" : hours + "小时";
  drawLine("chart-history", `${METRIC_META[metric].name}变化趋势（${pond}，近${rangeLabel}，共${(data.records || []).length}条）`, times,
    [{ name: METRIC_META[metric].name + (METRIC_META[metric].unit ? `(${METRIC_META[metric].unit})` : ""),
       data: recs.map(r => r[metric]) }]);
  drawLine("chart-history2", "四指标对比（归一化展示）", times,
    Object.keys(METRIC_META).map((k, i) => ({
      name: METRIC_META[k].name,
      data: normalize(recs.map(r => r[k])),
      color: CHART_COLORS[i],
    })));
  toast(`查询完成：${pond} 近${rangeLabel}共 ${(data.records || []).length} 条`);
}
function normalize(arr) {
  const vals = arr.filter(v => v !== null && v !== undefined).map(Number);
  if (!vals.length) return arr.map(() => null);
  const min = Math.min(...vals), max = Math.max(...vals), span = max - min || 1;
  return arr.map(v => v === null || v === undefined ? null : Number(((v - min) / span).toFixed(3)));
}
/* 复用图表实例：同一容器重复 init 会出现空白/画布堆叠，这里统一先取旧实例并 resize 校正 */
function chartFor(el) {
  if (!el) return null;
  let chart = echarts.getInstanceByDom(el);
  if (!chart) chart = echarts.init(el);
  chart.resize();   // 容器从隐藏变可见、或窗口变化后，强制按当前尺寸重排，杜绝 0 尺寸空白卡片
  return chart;
}

function drawLine(domId, title, x, series) {
  const el = document.getElementById(domId);
  if (!el) return;
  el.classList.add("charted");
  const chart = chartFor(el);
  chart.setOption({
    title: { text: title, left: "center", textStyle: { fontSize: 14, color: "#1f2d3d" } },
    tooltip: { trigger: "axis" },
    legend: { top: 28 },
    grid: { top: 70, left: 50, right: 30, bottom: 40 },
    xAxis: { type: "category", data: x, axisLabel: { color: "#7a8ba3" } },
    yAxis: { type: "value", axisLabel: { color: "#7a8ba3" }, splitLine: { lineStyle: { color: "#eef2f7" } } },
    series: series.map(s => ({ type: "line", smooth: true, showSymbol: false,
      name: s.name, data: s.data, lineStyle: { width: 2, color: s.color },
      itemStyle: s.color ? { color: s.color } : undefined })),
  });
  return chart;
}

/* ---------- 告警中心 ---------- */
async function loadAlerts() {
  const pond = $("#alert-pond").value;
  const status = $("#alert-status").value;
  const qs = [];
  if (pond) qs.push("pond_id=" + pond);
  if (status !== "") qs.push("status=" + status);
  const rows = await api("/alerts" + (qs.length ? "?" + qs.join("&") : ""));
  $("#alert-table tbody").innerHTML = rows.map(a => `<tr>
    <td>${a.id}</td><td>${a.pond_id}</td><td>${metricName(a.metric)}</td>
    <td>${fmtVal(a.value)}</td><td>${fmtVal(a.threshold)}</td>
    <td class="lvl-${a.level}">${a.level === 2 ? "严重" : "一般"}</td>
    <td>${a.alert_time}</td>
    <td class="st-${a.status}">${a.status === 1 ? "已处理" : "未处理"}</td>
    <td>${a.status === 0 ? `<button class="btn small" onclick="handleAlert(${a.id})">处理</button>` : ""}</td>
  </tr>`).join("") || "<tr><td colspan='9' class='hint'>暂无告警</td></tr>";
}
function metricName(key) { return (METRIC_META[key] || {}).name || key; }
async function handleAlert(id) {
  await api(`/alerts/${id}/handle`, { method: "POST" });
  toast("告警已处理");
  loadAlerts().catch(handleError);
}

/* ---------- 塘口管理 ---------- */
async function loadPonds() {
  const rows = await api("/ponds");
  $("#pond-table tbody").innerHTML = rows.map(p => `<tr>
    <td>${p.pond_id}</td><td>${p.name || ""}</td><td>${p.area_mu ?? ""}</td>
    <td>${p.stock_count ?? ""}</td><td>${(p.stock_date || "").slice(0, 10)}</td><td>${p.manager || ""}</td>
    <td><button class="btn small danger" onclick="delPond('${p.pond_id}')">删除</button></td>
  </tr>`).join("");
  // 同步所有塘口下拉框
  const options = rows.map(p => `<option value="${p.pond_id}">${p.name || p.pond_id}(${p.pond_id})</option>`).join("");
  const withAll = ["alert-pond", "feed-pond", "med-pond"];     // 带"全部"选项
  const noAll = ["hist-pond", "pred-pond", "vision-pond", "ana-pond", "emp-pond", "seed-pond", "feed-form-pond", "med-form-pond"];
  withAll.concat(noAll).forEach(id => {
    const el = $("#" + id);
    if (!el) return;
    const cur = el.value;
    const first = withAll.includes(id) ? "<option value=''>全部</option>"
      : (id === "emp-pond" ? "<option value=''>不限塘口</option>" : "");
    el.innerHTML = first + options;
    if ([...el.options].some(o => o.value === cur)) el.value = cur;
  });
}
$("#pond-add-toggle").addEventListener("click", () => $("#pond-form").classList.toggle("hidden"));
$("#pond-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  try {
    const body = Object.fromEntries(new FormData(e.target).entries());
    await api("/ponds", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    e.target.reset();
    e.target.classList.add("hidden");
    await loadPonds();
    await loadDashboard();
    toast(`塘口 ${body.pond_id} 已添加，看板与所有下拉框已同步`);
  } catch (err) { handleError(err); }
});
async function delPond(id) {
  if (!confirm("确认删除塘口 " + id + " ？")) return;
  try {
    await api("/ponds/" + id, { method: "DELETE" });
    toast("已删除 " + id);
    await loadPonds();
    loadDashboard().catch(() => {});
  } catch (err) { handleError(err); }
}

/* ---------- AI 预测 ---------- */
async function loadPrediction() {
  const pond = $("#pred-pond").value || ($("#pred-pond").options[0] && $("#pred-pond").options[0].value);
  if (!pond) return;
  const data = await api(`/prediction/growth?pond_id=${pond}`);
  $("#pred-meta").textContent = `模型: ${data.model.algorithm} · R²=${data.model.r2 ?? "-"} · MAE=${data.model.mae_g ?? "-"}g · 当前养殖 ${data.current_age_days} 天`;
  const growthEl = document.getElementById("chart-growth");
  growthEl.classList.add("charted");
  const chart = chartFor(growthEl);
  chart.setOption({
    title: { text: `生长预测曲线（${pond}，水温 ${data.water_temp}℃）`, left: "center", textStyle: { fontSize: 14 } },
    tooltip: { trigger: "axis", valueFormatter: v => v + " g" },
    grid: { top: 60, left: 60, right: 30, bottom: 40 },
    xAxis: { type: "category", data: data.curve.map(c => c.date), axisLabel: { color: "#7a8ba3" } },
    yAxis: { type: "value", name: "平均体重(g)", axisLabel: { color: "#7a8ba3" }, splitLine: { lineStyle: { color: "#eef2f7" } } },
    series: [{ type: "line", smooth: true, data: data.curve.map(c => c.weight_g),
      lineStyle: { width: 3, color: "#2f6fed" }, areaStyle: { color: "rgba(47,111,237,0.12)" } }],
  });
  try {
    const doData = await api(`/prediction/water-quality?pond_id=${pond}`);
    drawLine("chart-do-forecast", `未来 6 小时溶氧预测（${pond}）`,
      doData.forecast.map(f => f.time.slice(5, 16)),
      [{ name: "预测溶氧(mg/L)", data: doData.forecast.map(f => f.dissolved_oxygen), color: "#14b8a6" }]);
  } catch (e) { /* 历史不足时忽略 */ }
  try {
    const adv = await api(`/feeding/advice?pond_id=${pond}`);
    $("#feeding-advice").innerHTML = `<h4>今日投喂建议</h4>
      <p>预估平均规格: <span class="big">${adv.avg_weight_g} g</span></p>
      <p>存塘生物量: 约 ${adv.biomass_kg} kg（${adv.stock_count} 尾）</p>
      <p>当前水温: ${adv.water_temp} ℃ · 投喂率: ${adv.feed_rate_percent}%</p>
      <p style="margin-top:8px"><b>建议投喂量: ${adv.advice_feed_kg} kg/日</b>，分 2~3 次投喂。</p>
      <p class="hint">${adv.advice}</p>`;
  } catch (e) { $("#feeding-advice").textContent = "投喂建议获取失败: " + e.message; }
  toast("预测已刷新: " + pond);
}

/* ---------- 生长分析 ---------- */
async function loadAnalysis() {
  const pond = $("#ana-pond").value || ($("#ana-pond").options[0] && $("#ana-pond").options[0].value);
  if (!pond) return;
  const d = await api(`/analysis/growth?pond_id=${pond}`);
  $("#ana-stats").innerHTML = [
    stat(`${d.current_weight_g} g`, `当前预估规格(养殖${d.age_days}天)`),
    stat(d.days_to_market === null ? "180天内未达标" : d.days_to_market + " 天", `距上市(≥${d.target_weight_g}g)`),
    stat((d.harvest_date || "--").slice(5), "预计达上市规格日期"),
    stat(d.estimated_yield_kg + " kg", `预估产量(成活率${Math.round(d.survival_rate * 100)}%)`),
    stat(d.fcr === null ? "--" : d.fcr, "饲料系数 FCR(90天)"),
    stat(d.total_feed_90d_kg + " kg", "近90天累计投喂"),
  ].join("");
  // 生长曲线 + 上市规格线
  const anaEl = document.getElementById("chart-ana-growth");
  anaEl.classList.add("charted");
  const chart = chartFor(anaEl);
  chart.setOption({
    title: { text: `生长曲线与上市规格线（${d.pond_name || pond}）`, left: "center", textStyle: { fontSize: 14 } },
    tooltip: { trigger: "axis", valueFormatter: v => v + " g" },
    grid: { top: 60, left: 60, right: 40, bottom: 40 },
    xAxis: { type: "category", data: d.curve.map(c => c.date), axisLabel: { color: "#7a8ba3" } },
    yAxis: { type: "value", name: "平均体重(g)", axisLabel: { color: "#7a8ba3" }, splitLine: { lineStyle: { color: "#eef2f7" } } },
    series: [{
      type: "line", smooth: true, data: d.curve.map(c => c.weight_g), name: "预估体重",
      lineStyle: { width: 3, color: "#2f6fed" }, areaStyle: { color: "rgba(47,111,237,0.10)" },
      markLine: { symbol: "none", data: [{ yAxis: d.target_weight_g, name: "上市规格",
        label: { formatter: "上市规格 " + d.target_weight_g + "g", position: "insideEndTop" },
        lineStyle: { color: "#e5484d", type: "dashed" } }] },
    }],
  });
  // 水温与溶氧
  drawLine("chart-ana-temp", "近14天日均水温/溶氧",
    d.daily_temp.map(r => (r.d || "").slice(5)),
    [{ name: "日均水温(℃)", data: d.daily_temp.map(r => r.temp), color: "#f59e0b" },
     { name: "日均溶氧(mg/L)", data: d.daily_temp.map(r => r.do), color: "#14b8a6" }]);
  // 投喂
  const feedEl = document.getElementById("chart-ana-feed");
  feedEl.classList.add("charted");
  const feedChart = chartFor(feedEl);
  feedChart.setOption({
    title: { text: "近14天日投喂量(kg)", left: "center", textStyle: { fontSize: 14 } },
    tooltip: { trigger: "axis" },
    grid: { top: 50, left: 50, right: 30, bottom: 40 },
    xAxis: { type: "category", data: d.daily_feed.map(r => (r.d || "").slice(5)), axisLabel: { color: "#7a8ba3" } },
    yAxis: { type: "value", axisLabel: { color: "#7a8ba3" }, splitLine: { lineStyle: { color: "#eef2f7" } } },
    series: [{ type: "bar", data: d.daily_feed.map(r => r.kg), name: "投喂量(kg)", itemStyle: { color: "#2f6fed", borderRadius: [4, 4, 0, 0] } }],
  });
}

/* ---------- 投喂管理 ---------- */
$("#feed-add-toggle").addEventListener("click", () => $("#feed-form").classList.toggle("hidden"));
$("#feed-refresh").addEventListener("click", () => loadFeeding().catch(handleError));
$("#feed-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  try {
    const body = Object.fromEntries(new FormData(e.target).entries());
    body.pond_id = $("#feed-form-pond").value;
    await api("/feeding", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    e.target.reset();
    e.target.classList.add("hidden");
    toast("投喂记录已保存");
    await loadFeeding();
  } catch (err) { handleError(err); }
});
async function loadFeeding() {
  const pond = $("#feed-pond").value;
  const qs = pond ? "?pond_id=" + pond : "";
  const [list, stats] = await Promise.all([api("/feeding/list" + qs), api("/feeding/stats" + qs)]);
  $("#feed-stats").innerHTML = [
    stat(stats.today_kg + " kg", "今日投喂"),
    stat(stats.daily.length ? (stats.daily.reduce((s, r) => s + r.kg, 0) / stats.daily.length).toFixed(1) + " kg" : "--", "近14天日均"),
    stat(stats.total_kg + " kg", "累计投喂"),
    stat(list.length + " 条", "记录条数(近14天)"),
  ].join("");
  $("#feed-table tbody").innerHTML = list.map(f => `<tr>
    <td>${f.feed_time}</td><td>${f.pond_id}</td><td>${f.feed_kg}</td><td>${f.note || ""}</td>
  </tr>`).join("") || "<tr><td colspan='4' class='hint'>暂无投喂记录</td></tr>";
}

/* ---------- 员工管理 ---------- */
$("#emp-add-toggle").addEventListener("click", () => $("#emp-form").classList.toggle("hidden"));
$("#emp-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  try {
    const body = Object.fromEntries(new FormData(e.target).entries());
    body.pond_id = $("#emp-pond").value;
    await api("/employees", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    e.target.reset();
    e.target.classList.add("hidden");
    toast("员工已添加");
    await loadEmployees();
  } catch (err) { handleError(err); }
});
async function loadEmployees() {
  const rows = await api("/employees");
  $("#emp-table tbody").innerHTML = rows.map(e => `<tr>
    <td>${e.id}</td><td>${e.name}</td><td>${e.role || ""}</td><td>${e.phone || ""}</td>
    <td>${e.pond_id || "不限"}</td><td>${(e.hire_date || "").slice(0, 10)}</td>
    <td class="st-${e.status}">${e.status === 1 ? "在职" : "离职"}</td>
    <td><button class="btn small" onclick="toggleEmp(${e.id}, ${e.status === 1 ? 0 : 1})">${e.status === 1 ? "离职" : "复职"}</button>
        <button class="btn small danger" onclick="delEmp(${e.id})">删除</button></td>
  </tr>`).join("") || "<tr><td colspan='8' class='hint'>暂无员工，点击上方按钮新增</td></tr>";
}
async function toggleEmp(id, status) {
  try {
    await api("/employees/" + id, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ status }) });
    await loadEmployees();
  } catch (err) { handleError(err); }
}
async function delEmp(id) {
  if (!confirm("确认删除该员工？")) return;
  try { await api("/employees/" + id, { method: "DELETE" }); await loadEmployees(); }
  catch (err) { handleError(err); }
}

/* ---------- 苗种管理 ---------- */
$("#seed-add-toggle").addEventListener("click", () => $("#seed-form").classList.toggle("hidden"));
$("#seed-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  try {
    const body = Object.fromEntries(new FormData(e.target).entries());
    body.pond_id = $("#seed-pond").value;
    await api("/seedlings", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    e.target.reset();
    e.target.classList.add("hidden");
    toast("苗种批次已登记");
    await loadSeedlings();
  } catch (err) { handleError(err); }
});
async function loadSeedlings() {
  const rows = await api("/seedlings");
  $("#seed-table tbody").innerHTML = rows.map(s => `<tr>
    <td>${s.id}</td><td>${s.batch_no || "--"}</td><td>${s.pond_id}</td><td>${s.species || ""}</td>
    <td>${s.supplier || ""}</td><td>${s.count}</td><td>${s.spec_cm ?? "--"}</td><td>${(s.stock_date || "").slice(0, 10)}</td>
    <td><button class="btn small danger" onclick="delSeed(${s.id})">删除</button></td>
  </tr>`).join("") || "<tr><td colspan='9' class='hint'>暂无苗种记录</td></tr>";
}
async function delSeed(id) {
  if (!confirm("确认删除该苗种批次？")) return;
  try { await api("/seedlings/" + id, { method: "DELETE" }); await loadSeedlings(); }
  catch (err) { handleError(err); }
}

/* ---------- 用药管理 ---------- */
$("#med-add-toggle").addEventListener("click", () => $("#med-form").classList.toggle("hidden"));
$("#med-refresh").addEventListener("click", () => loadMedications().catch(handleError));
$("#med-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  try {
    const body = Object.fromEntries(new FormData(e.target).entries());
    body.pond_id = $("#med-form-pond").value;
    await api("/medications", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    e.target.reset();
    e.target.classList.add("hidden");
    toast("用药记录已保存");
    await loadMedications();
  } catch (err) { handleError(err); }
});
async function loadMedications() {
  const pond = $("#med-pond").value;
  const rows = await api("/medications" + (pond ? "?pond_id=" + pond : ""));
  $("#med-table tbody").innerHTML = rows.map(m => `<tr>
    <td>${m.id}</td><td>${m.pond_id}</td><td>${m.med_name}</td><td>${m.dosage || ""}</td>
    <td>${m.method || ""}</td><td>${m.reason || ""}</td><td>${(m.start_date || "").slice(0, 10)}</td>
    <td>${(m.end_date || "").slice(0, 10)}</td><td>${m.operator || ""}</td><td>${m.withdrawal_days ?? 0}</td>
  </tr>`).join("") || "<tr><td colspan='10' class='hint'>暂无用药记录</td></tr>";
}

/* ---------- 密度识别 ---------- */
$("#vision-sample").addEventListener("click", async () => {
  const pond = $("#vision-pond").value || "TANK-A";
  try {
    const blob = await fetch(`/data/images/sample_pond.jpg`).then(r => r.blob());
    const file = new File([blob], "sample_pond.jpg", { type: "image/jpeg" });
    await uploadVision(file, pond);
  } catch (e) { handleError(e); }
});
$("#vision-upload").addEventListener("click", async () => {
  const file = $("#vision-file").files[0];
  if (!file) { toast("请先选择图像文件", false); return; }
  try { await uploadVision(file, $("#vision-pond").value || "TANK-A"); } catch (e) { handleError(e); }
});
async function uploadVision(file, pond) {
  const fd = new FormData();
  fd.append("image", file);
  fd.append("pond_id", pond);
  const data = await api("/vision/density", { method: "POST", body: fd });
  $("#vision-result").innerHTML = `<h4>识别结果</h4>
    <p>密度等级: <span class="big">${data.density_level}</span></p>
    <p>估计目标数: ${data.fish_count} · 置信度: ${(data.confidence * 100).toFixed(0)}%</p>
    <p>${data.advice}</p>`;
  toast("识别完成: " + data.density_level);
  loadVisionRecords().catch(() => {});
}
async function loadVisionRecords() {
  try {
    const rows = await api("/vision/density");
    $("#vision-table tbody").innerHTML = rows.map(r => `<tr>
      <td>${r.create_time}</td><td>${r.pond_id}</td><td>${r.density_level}</td>
      <td>${r.fish_count}</td><td>${(r.confidence * 100).toFixed(0)}%</td></tr>`).join("")
      || "<tr><td colspan='5' class='hint'>暂无识别记录</td></tr>";
  } catch (e) { /* ignore */ }
}

/* ---------- 查询/刷新按钮绑定 ---------- */
$("#hist-refresh").addEventListener("click", () => loadHistory().catch(handleError));
$("#alert-refresh").addEventListener("click", () => loadAlerts().catch(handleError));
$("#pred-refresh").addEventListener("click", () => loadPrediction().catch(handleError));
$("#ana-refresh").addEventListener("click", () => loadAnalysis().catch(handleError));

/* ---------- 时钟与自动刷新 ---------- */
/* 窗口尺寸变化时统一重排所有已创建的图表（全局只挂一次） */
window.addEventListener("resize", () => {
  document.querySelectorAll(".chart, .chart-lg").forEach(el => {
    const c = echarts.getInstanceByDom(el);
    if (c) c.resize();
  });
});
setInterval(() => {
  $("#clock").textContent = new Date().toLocaleString("zh-CN", { hour12: false });
}, 1000);
setInterval(() => {
  const active = document.querySelector(".tab.active");
  if (active && active.dataset.tab === "dashboard") loadDashboard().catch(() => {});
}, 10000);

/* 启动 */
(async function init() {
  try {
    await loadPonds();       // 先填充所有塘口下拉框
    await loadDashboard();
    initTabFromUrl();        // 支持 ?tab=xxx / #xxx 直达指定页签
  } catch (e) { handleError(e); }
})();
