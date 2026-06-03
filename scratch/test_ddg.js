const { chromium } = require("playwright");

async function test() {
  const context = await chromium.launchPersistentContext("C:/Users/joaon/ptia-content-engine/.tmp/playwright-linkedin", {
    headless: true,
  });
  const page = context.pages()[0] || await context.newPage();
  try {
    const searchUrl = "https://html.duckduckgo.com/html/?q=site:linkedin.com/company/+Unbabel";
    await page.goto(searchUrl, { waitUntil: "networkidle" });
    const content = await page.content();
    console.log("HTML length:", content.length);
    console.log("Title:", await page.title());
    // print first 500 chars of body
    const bodyText = await page.evaluate(() => document.body.innerText);
    console.log("Body snippet:", bodyText.slice(0, 1000));
  } catch (err) {
    console.error("Error:", err);
  } finally {
    await context.close();
  }
}
test();
