const { chromium } = require("playwright");
const fs = require("fs");

const userDataDir = "C:/Users/joaon/ptia-content-engine/.tmp/playwright-linkedin";

async function run() {
  const context = await chromium.launchPersistentContext(userDataDir, {
    headless: false,
  });
  const page = context.pages()[0] || await context.newPage();
  
  try {
    await page.goto("https://www.linkedin.com/search/results/content/?keywords=AI%20Portugal&sortBy=%22date_posted%22");
    await page.waitForTimeout(5000);
    
    const res = await page.evaluate(() => {
      const xpath = "//*[contains(text(), 'RENATA COSTA') or contains(text(), 'Never give up')]";
      const evaluator = new XPathEvaluator();
      const expression = evaluator.createExpression(xpath);
      const result = expression.evaluate(document, XPathResult.ANY_TYPE, null);
      
      let node = result.iterateNext();
      if (!node) {
        const allElements = document.getElementsByTagName("*");
        for (const el of allElements) {
          if (el.innerText && el.innerText.includes("RENATA COSTA")) {
            node = el;
            break;
          }
        }
      }
      
      if (node) {
        let current = node;
        let p14 = null;
        let depth = 0;
        while (current && depth < 20) {
          if (depth === 14) { p14 = current; break; }
          current = current.parentElement;
          depth++;
        }
        
        if (p14) {
          return { found: true, html: p14.outerHTML };
        }
      }
      return { found: false };
    });
    
    if (res.found) {
      fs.writeFileSync("scratch/parent14.html", res.html, "utf-8");
      console.log("Wrote parent14.html");
    } else {
      console.log("Parent 14 not found");
    }
    
    console.log(JSON.stringify(res, null, 2));
  } catch (err) {
    console.error(err);
  } finally {
    await context.close();
  }
}

run();
