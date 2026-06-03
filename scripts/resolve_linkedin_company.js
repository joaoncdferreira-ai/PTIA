const { chromium } = require("playwright");
const fs = require("fs");
const path = require("path");

const userDataDir = "C:/Users/joaon/ptia-content-engine/.tmp/playwright-linkedin";
const mapPath = "C:/Users/joaon/ptia-content-engine/config/linkedin_urn_map.json";

async function resolveCompany(entityName) {
  if (!entityName || entityName.trim().length < 3) {
    console.error("ERRO: Nome da entidade inválido.");
    process.exit(1);
  }

  const queryName = entityName.trim();
  console.log(`[Auto-Resolver] Iniciada pesquisa para a entidade: "${queryName}"`);

  // 1. Carregar mapeamento existente para evitar duplicações
  let urnMap = { companies: {} };
  try {
    if (fs.existsSync(mapPath)) {
      urnMap = JSON.parse(fs.readFileSync(mapPath, "utf8"));
    }
  } catch (err) {
    console.error("[Auto-Resolver] Erro ao ler base de dados:", err.message);
  }

  const normalizedKey = queryName.toLowerCase();
  if (urnMap.companies[normalizedKey]) {
    console.log(`[Auto-Resolver] Entidade "${queryName}" já existe no mapeamento.`);
    console.log(JSON.stringify({ ok: true, source: "database", company: urnMap.companies[normalizedKey] }));
    process.exit(0);
  }

  // 2. Iniciar Playwright (com o perfil de sessão autenticado) com retaguarda para concorrência
  let context;
  const maxRetries = 10;
  for (let attempt = 1; attempt <= maxRetries; attempt++) {
    try {
      context = await chromium.launchPersistentContext(userDataDir, {
        headless: true, // headless true is perfect for silent background worker
        viewport: { width: 1280, height: 800 },
      });
      break; // Sucesso ao obter lock
    } catch (err) {
      if (attempt === maxRetries) {
        throw new Error(`Falhou após ${maxRetries} tentativas de obter o lock da sessão do LinkedIn: ${err.message}`);
      }
      console.log(`[Auto-Resolver] [Aviso] Concorrência detetada na sessão Playwright. A aguardar libertação de lock... (Tentativa ${attempt}/${maxRetries})`);
      await new Promise(resolve => setTimeout(resolve, 6000)); // Esperar 6 segundos antes de tentar novamente
    }
  }

  const page = context.pages()[0] || await context.newPage();

  try {
    // 3. Pesquisar diretamente no LinkedIn (CAPTCHA-free devido à sessão activa)
    const searchUrl = `https://www.linkedin.com/search/results/all/?keywords=${encodeURIComponent(queryName)}`;
    console.log(`[Auto-Resolver] A procurar URL oficial diretamente na pesquisa do LinkedIn...`);
    await page.goto(searchUrl, { waitUntil: "domcontentloaded", timeout: 45000 });

    // Esperar um pouco para os resultados carregarem
    await page.waitForTimeout(6000);

    // Extrair o primeiro URL que aponta para o LinkedIn Company
    const linkedinUrl = await page.evaluate(() => {
      const links = Array.from(document.querySelectorAll("a"));
      for (const link of links) {
        const href = link.href || "";
        const decodedHref = decodeURIComponent(href);
        if (decodedHref.includes("linkedin.com/company/")) {
          // Remover query parameters e barras finais
          const baseHref = decodedHref.split("?")[0].replace(/\/$/, "");
          // Validar se é uma raiz de empresa limpa (sem sub-pastas como /posts ou /jobs)
          const cleanUrl = baseHref.match(/https?:\/\/(www\.)?linkedin\.com\/company\/[a-zA-Z0-9.\-_]+$/i);
          if (cleanUrl) return cleanUrl[0];
        }
      }
      return null;
    });

    if (!linkedinUrl) {
      throw new Error(`Não foi possível encontrar um perfil de LinkedIn para "${queryName}" na pesquisa.`);
    }

    console.log(`[Auto-Resolver] Perfil encontrado: ${linkedinUrl}`);

    // 4. Aceder ao perfil da empresa no LinkedIn para extrair o ID
    console.log(`[Auto-Resolver] A aceder ao perfil no LinkedIn para extração de ID...`);
    await page.goto(linkedinUrl, { waitUntil: "domcontentloaded", timeout: 45000 });
    
    // Esperar um pouco para carregar a página
    await page.waitForTimeout(6000);

    const html = await page.content();

    // 5. Procurar o Company ID através de múltiplos padrões no HTML
    let companyId = null;

    // Padrão A: urn:li:fs_normalized_company:(\d+)
    const normalizedMatch = html.match(/urn:li:fs_normalized_company:(\d+)/i);
    if (normalizedMatch) {
      companyId = normalizedMatch[1];
      console.log(`[Auto-Resolver] Encontrado ID via 'fs_normalized_company': ${companyId}`);
    }

    // Padrão B: companyUniversalId":123456
    if (!companyId) {
      const universalIdMatch = html.match(/companyUniversalId["']?\s*:\s*["']?(\d+)/i);
      if (universalIdMatch) {
        companyId = universalIdMatch[1];
        console.log(`[Auto-Resolver] Encontrado ID via 'companyUniversalId': ${companyId}`);
      }
    }

    // Padrão C: links com f_C= ou currentCompany=
    if (!companyId) {
      const linkId = await page.evaluate(() => {
        const jobsLink = document.querySelector('a[href*="currentCompany="], a[href*="f_C="]');
        if (jobsLink) {
          const href = jobsLink.href;
          const match = href.match(/(currentCompany|f_C)=([^&]+)/);
          if (match) {
            return match[2].replace(/[^\d]/g, "");
          }
        }
        return null;
      });
      if (linkId) {
        companyId = linkId;
        console.log(`[Auto-Resolver] Encontrado ID via link de empregos: ${companyId}`);
      }
    }

    // Padrão D: URNs genéricas de organização no HTML
    if (!companyId) {
      const organizationMatch = html.match(/urn:li:organization:(\d+)/i);
      if (organizationMatch) {
        companyId = organizationMatch[1];
        console.log(`[Auto-Resolver] Encontrado ID via 'urn:li:organization': ${companyId}`);
      }
    }

    if (!companyId) {
      throw new Error(`Não foi possível extrair o ID numérico de base de dados para a página: ${linkedinUrl}`);
    }

    // 6. Atualizar a base de dados de mapeamento de forma atómica
    const resolvedCompany = {
      urn: `urn:li:organization:${companyId}`,
      display_name: queryName
    };

    urnMap.companies[normalizedKey] = resolvedCompany;
    fs.writeFileSync(mapPath, JSON.stringify(urnMap, null, 2), "utf8");

    console.log(`[Auto-Resolver] [SUCESSO] Entidade mapeada com sucesso!`);
    console.log(JSON.stringify({ ok: true, source: "playwright", company: resolvedCompany }));

  } catch (err) {
    console.error(`[Auto-Resolver] [ERRO] Falha no processo:`, err.message);
    console.log(JSON.stringify({ ok: false, error: err.message }));
    process.exit(1);
  } finally {
    await context.close();
  }
}

// Ler de variável de ambiente ou argumentos da linha de comandos
const entityName = process.env.RESOLVE_ENTITY || process.argv[2];
resolveCompany(entityName);
