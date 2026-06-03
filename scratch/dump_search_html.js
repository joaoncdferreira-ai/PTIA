const { chromium } = require("playwright");

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
      // Find all list items or divs that are search results
      const results = [];
      const items = document.querySelectorAll("li, div, section");
      
      let count = 0;
      for (const item of items) {
        // Look for cards that contain author info or like buttons
        const hasRenata = item.innerText && item.innerText.includes("Renata Costa");
        const hasGostar = item.innerText && (item.innerText.includes("Gostar") || item.innerText.includes("Comment"));
        
        if (hasRenata && count < 20) {
          results.push({
            tagName: item.tagName,
            className: item.className,
            attributes: Array.from(item.attributes).map(a => `${a.name}=${a.value}`),
            childCount: item.children.length,
            textPreview: item.innerText.substring(0, 150).replace(/\n/g, " ")
          });
          count++;
        }
      }
      return results;
    });
    
    console.log(JSON.stringify(res, null, 2));
  } catch (err) {
    console.error(err);
  } finally {
    await context.close();
  }
}

run();
