const { chromium } = require("playwright");

(async () => {
  const userDataDir = "C:/Users/joaon/ptia-content-engine/.tmp/playwright-linkedin";
  console.log("-> A iniciar o browser persistente do LinkedIn em: " + userDataDir);
  
  const context = await chromium.launchPersistentContext(userDataDir, {
    headless: false,
    viewport: { width: 1400, height: 950 },
  });
  
  const page = context.pages()[0] || await context.newPage();
  
  // Aceder à página inicial do LinkedIn
  await page.goto("https://www.linkedin.com/feed/", {
    waitUntil: "domcontentloaded",
    timeout: 60000,
  });
  
  console.log("\n==================================================================");
  console.log("INSTRUÇÕES DE LOGIN:");
  console.log("1. Se não estiveres logado, faz login na conta PTIA na janela aberta.");
  console.log("2. Confirma que a página inicial carrega com a conta da PTIA.");
  console.log("3. Fechar esta janela do browser guarda a sessão automaticamente.");
  console.log("==================================================================\n");
  
  // Deixar aberto para o utilizador interagir livremente
  // O browser irá manter-se ativo até ser fechado manualmente pelo utilizador
})();
