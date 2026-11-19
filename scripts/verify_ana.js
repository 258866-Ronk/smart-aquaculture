const { chromium } = require("playwright-core");
(async () => {
  const browser = await chromium.launch({ headless: true, executablePath: "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe" });
  const page = await browser.newPage({ viewport: { width: 1450, height: 900 } });
  await page.goto("http://127.0.0.1:5000/", { waitUntil: "networkidle" });
  await page.waitForTimeout(800);
  await page.click('button[data-tab="analysis"]');
  await page.waitForTimeout(2500);
  const info = await page.evaluate(() => ({
    anaGrowth: document.querySelectorAll("#chart-ana-growth canvas").length,
    anaTemp: document.querySelectorAll("#chart-ana-temp canvas").length,
    anaFeed: document.querySelectorAll("#chart-ana-feed canvas").length,
  }));
  console.log(JSON.stringify(info));
  await page.screenshot({ path: "C:\\Users\\MEC\\WorkBuddy\\2026-09-12-19-32-40\\_ppt\\verify_analysis.png" });
  await browser.close();
})().catch(e => { console.error("FATAL", e); process.exit(1); });
