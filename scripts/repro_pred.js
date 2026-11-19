/* 深度诊断：加载首页 -> 点 AI 预测 -> 收集 console/网络/状态 */
const { chromium } = require("playwright-core");

(async () => {
  const browser = await chromium.launch({
    headless: true,
    executablePath: "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe",
  });
  const page = await browser.newPage({ viewport: { width: 1450, height: 900 } });
  page.on("console", (m) => console.log("[console]", m.type(), m.text().slice(0, 200)));
  page.on("pageerror", (e) => console.log("[pageerror]", String(e).slice(0, 400)));
  page.on("requestfailed", (r) => console.log("[reqfail]", r.url(), r.failure() && r.failure().errorText));
  page.on("response", (r) => { if (r.status() >= 400) console.log("[http" + r.status() + "]", r.url()); });

  await page.goto("http://127.0.0.1:5000/", { waitUntil: "networkidle" });
  await page.waitForTimeout(1000);

  const pre = await page.evaluate(() => ({
    echarts: typeof window.echarts,
    pondOptions: document.getElementById("pred-pond") ? document.getElementById("pred-pond").options.length : -1,
    appjs: performance.getEntriesByType("resource").filter(r => r.name.includes("app.js")).map(r => r.name),
  }));
  console.log("PRE:", JSON.stringify(pre));

  await page.click('button[data-tab="prediction"]');
  await page.waitForTimeout(6000);

  const post = await page.evaluate(() => ({
    meta: document.getElementById("pred-meta").textContent.slice(0, 60),
    toast: (document.getElementById("toast") || {}).textContent || "",
    growthCanvas: document.querySelectorAll("#chart-growth canvas").length,
    doCanvas: document.querySelectorAll("#chart-do-forecast canvas").length,
    charted: document.getElementById("chart-growth").classList.contains("charted"),
  }));
  console.log("POST:", JSON.stringify(post));
  await page.screenshot({ path: "C:\\Users\\MEC\\WorkBuddy\\2026-09-12-19-32-40\\_ppt\\verify_pred.png" });
  await browser.close();
})().catch((e) => { console.error("FATAL", e); process.exit(1); });
