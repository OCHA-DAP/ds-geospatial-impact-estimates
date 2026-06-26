import puppeteer from "puppeteer";

const browser = await puppeteer.launch({ headless: "new", args: ["--no-sandbox"] });
const page = await browser.newPage();

const logs = [];
const apiCalls = [];
const failed = [];
page.on("console", (m) => logs.push(`[${m.type()}] ${m.text()}`));
page.on("pageerror", (e) => logs.push(`[pageerror] ${e.message}`));
page.on("requestfailed", (r) => failed.push(`${r.url()} :: ${r.failure()?.errorText}`));
page.on("request", (r) => {
  if (r.url().includes("/api/")) apiCalls.push(r.url());
});

try {
  await page.goto("http://localhost:5173/", { waitUntil: "networkidle2", timeout: 30000 });
} catch (e) {
  console.log("GOTO ERROR:", e.message);
}
await new Promise((r) => setTimeout(r, 6000));

const status = await page.$eval("#status", (el) => el.textContent).catch(() => "(no #status)");
const canvas = await page.$$eval("canvas", (c) => c.length);

console.log("=== console / page errors ===");
console.log(logs.length ? logs.join("\n") : "(none)");
console.log("=== /api calls fired ===", apiCalls);
console.log("=== requestfailed ===", failed.length ? failed.join("\n") : "(none)");
console.log("=== #status text ===", status);
console.log("=== canvas elements (deck/maplibre) ===", canvas);

await browser.close();
