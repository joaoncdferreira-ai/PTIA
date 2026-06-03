from __future__ import annotations

import json
from pathlib import Path
from typing import Any


AI_CRAWLER_USER_AGENTS = [
    "Googlebot",
    "Bingbot",
    "OAI-SearchBot",
    "ChatGPT-User",
    "GPTBot",
    "PerplexityBot",
    "ClaudeBot",
    "anthropic-ai",
    "Google-Extended",
]


ANSWER_PAGES: list[dict[str, Any]] = [
    {
        "slug": "o-que-e-o-ai-act-para-empresas-portuguesas",
        "question": "O que e o AI Act para empresas portuguesas?",
        "title": "O que e o AI Act para empresas portuguesas?",
        "description": "Resposta PTIA sobre o impacto pratico do AI Act em empresas portuguesas.",
        "short_answer": (
            "O AI Act e a lei europeia que organiza sistemas de inteligencia artificial por nivel de risco. "
            "Para empresas portuguesas, o ponto central e saber que sistemas usam, que dados processam, "
            "quem os fornece e que prova de controlo conseguem manter."
        ),
        "portugal_angle": (
            "Em Portugal, o desafio tende a ser menos juridico e mais operacional: muitas equipas compram "
            "ou ativam ferramentas de IA antes de terem inventario, responsaveis internos e criterios de risco."
        ),
        "points": [
            "Mapear sistemas de IA usados por equipas, fornecedores e automatismos internos.",
            "Separar usos de baixo risco, risco limitado, alto risco e usos proibidos.",
            "Guardar evidencia sobre dados, fornecedores, avaliacoes e decisoes humanas.",
            "Criar regras simples para compras, pilotos e integracoes com dados sensiveis.",
            "Tratar conformidade como gestao continua, nao como documento unico.",
        ],
        "faqs": [
            {
                "question": "Todas as empresas portuguesas sao afetadas pelo AI Act?",
                "answer": "Sim, se usam, compram, distribuem ou desenvolvem sistemas de IA no mercado europeu. A intensidade das obrigacoes depende do uso e do risco.",
            },
            {
                "question": "Qual deve ser o primeiro passo?",
                "answer": "Criar um inventario simples dos sistemas de IA em uso, incluindo fornecedor, finalidade, dados tratados, equipa responsavel e nivel de criticidade.",
            },
        ],
        "related_topics": ["ai-act", "ia-em-portugal"],
        "related_guides": ["/guias/ai-act-empresas-portuguesas/"],
        "keywords": ["ai act", "regulacao", "compliance", "governanca", "risco", "auditoria"],
    },
    {
        "slug": "como-usar-ia-numa-pme-portuguesa",
        "question": "Como usar IA numa PME portuguesa?",
        "title": "Como usar IA numa PME portuguesa?",
        "description": "Resposta PTIA sobre primeiros casos de uso de IA para PME em Portugal.",
        "short_answer": (
            "Uma PME portuguesa deve comecar pela IA onde ha trabalho repetitivo, dados acessiveis e impacto mensuravel: "
            "atendimento, propostas, analise de documentos, marketing, suporte interno e melhoria de processos."
        ),
        "portugal_angle": (
            "O erro mais comum e escolher ferramentas por hype. O caminho mais seguro e escolher um problema pequeno, "
            "medir tempo poupado, limitar dados sensiveis e so depois escalar."
        ),
        "points": [
            "Escolher um processo repetitivo com dono claro dentro da empresa.",
            "Definir uma metrica simples: tempo, custo, qualidade, receita ou risco.",
            "Comecar com ferramentas maduras antes de construir software proprio.",
            "Separar dados publicos, internos e sensiveis desde o primeiro piloto.",
            "Avaliar resultados em 30 dias antes de aumentar investimento.",
        ],
        "faqs": [
            {
                "question": "Uma PME precisa de uma equipa tecnica para usar IA?",
                "answer": "Nao necessariamente. Muitos primeiros casos podem ser feitos com ferramentas prontas, desde que haja regras de dados, responsabilidade e medicao.",
            },
            {
                "question": "Qual e o maior risco para uma PME?",
                "answer": "O maior risco e automatizar sem saber que dados entram, quem valida as respostas e que impacto real o sistema teve.",
            },
        ],
        "related_topics": ["ia-para-pme", "ia-em-portugal"],
        "related_guides": ["/guias/ia-para-pme-portugal/", "/guias/ferramentas-de-ia-para-empresas/"],
        "keywords": ["pme", "empresa", "empresas", "produtividade", "retalho", "industria", "negocio"],
    },
    {
        "slug": "quais-sao-as-principais-empresas-de-ia-em-portugal",
        "question": "Quais sao as principais empresas de IA em Portugal?",
        "title": "Quais sao as principais empresas de IA em Portugal?",
        "description": "Resposta PTIA sobre o ecossistema portugues de empresas de inteligencia artificial.",
        "short_answer": (
            "As principais empresas de IA em Portugal incluem startups, centros de engenharia, consultoras, laboratorios e empresas "
            "que aplicam IA em saude, retalho, industria, linguistica, dados e automacao."
        ),
        "portugal_angle": (
            "Portugal nao compete apenas por modelos fundacionais. O posicionamento mais forte esta em talento tecnico, produto aplicado, "
            "dados de dominio, nearshore sofisticado e ligacao entre universidades, startups e empresas."
        ),
        "points": [
            "Separar empresas que constroem modelos das que aplicam IA em produto ou operacao.",
            "Olhar para sinais de clientes, talento, financiamento, investigacao e presenca internacional.",
            "Distinguir hype comercial de produto com tracao real.",
            "Acompanhar tambem universidades, centros de I&D e equipas de engenharia globais em Portugal.",
            "Atualizar o mapa regularmente porque o ecossistema muda rapido.",
        ],
        "faqs": [
            {
                "question": "Portugal tem empresas relevantes de IA?",
                "answer": "Sim. A relevancia aparece sobretudo em IA aplicada, dados, linguistica, engenharia, saude, industria, automacao e servicos empresariais.",
            },
            {
                "question": "Como avaliar uma empresa de IA?",
                "answer": "Procure produto real, clientes, equipa tecnica, dados proprios, evidencia publica e capacidade de execucao para alem do anuncio.",
            },
        ],
        "related_topics": ["ia-em-portugal", "ia-para-pme"],
        "related_guides": [],
        "keywords": ["portugal", "portugues", "startup", "empresa", "empresas", "ecossistema"],
    },
    {
        "slug": "o-que-sao-agentes-de-ia-nas-empresas",
        "question": "O que sao agentes de IA nas empresas?",
        "title": "O que sao agentes de IA nas empresas?",
        "description": "Resposta PTIA sobre agentes de IA, automacao e uso empresarial.",
        "short_answer": (
            "Agentes de IA sao sistemas que combinam modelos de IA com ferramentas, memoria, regras e objetivos para executar tarefas com varios passos. "
            "Nas empresas, fazem sentido quando ha processos repetiveis, validacao humana e limites claros de acao."
        ),
        "portugal_angle": (
            "Em Portugal, os agentes podem ajudar equipas pequenas a aumentar capacidade operacional, mas exigem controlo: logs, permissao, revisao humana e planos de falha."
        ),
        "points": [
            "Um agente nao e apenas um chatbot; deve conseguir executar passos e usar ferramentas.",
            "Comeca por processos internos antes de decisoes criticas sobre clientes ou dinheiro.",
            "Precisa de permissoes limitadas, logs e capacidade de auditoria.",
            "Avaliacao deve medir tarefas concluidas, erros, tempo poupado e intervencoes humanas.",
            "Casos de alto risco devem manter aprovacao humana obrigatoria.",
        ],
        "faqs": [
            {
                "question": "Quando e que um agente de IA faz sentido?",
                "answer": "Faz sentido quando a tarefa tem passos repetiveis, informacao acessivel, criterios de sucesso claros e risco controlavel.",
            },
            {
                "question": "Qual e a diferenca entre agente e automacao?",
                "answer": "Automacao segue regras fixas. Um agente usa IA para interpretar contexto, escolher passos e interagir com ferramentas dentro de limites definidos.",
            },
        ],
        "related_topics": ["agentes-de-ia", "trabalho-e-produtividade"],
        "related_guides": ["/guias/agentes-de-ia-empresas/"],
        "keywords": ["agente", "agentes", "autonomo", "automacao", "workflow", "codex"],
    },
    {
        "slug": "como-usar-chatgpt-no-trabalho-sem-expor-dados",
        "question": "Como usar ChatGPT no trabalho sem expor dados?",
        "title": "Como usar ChatGPT no trabalho sem expor dados?",
        "description": "Resposta PTIA sobre uso seguro de ChatGPT e ferramentas de IA no trabalho.",
        "short_answer": (
            "Para usar ChatGPT no trabalho sem expor dados, a regra base e simples: nao introduzir dados pessoais, contratos, ficheiros de clientes, credenciais, informacao financeira "
            "ou propriedade intelectual sem politica interna e ferramenta aprovada."
        ),
        "portugal_angle": (
            "O risco em empresas portuguesas raramente esta no prompt isolado; esta na ausencia de regras claras para equipas que querem produtividade imediata."
        ),
        "points": [
            "Classificar dados antes de usar ferramentas externas.",
            "Criar exemplos permitidos e proibidos para equipas.",
            "Usar contas empresariais e definicoes de privacidade adequadas quando existirem.",
            "Remover nomes, contratos, NIFs, emails, ficheiros e informacao confidencial.",
            "Validar respostas antes de enviar a clientes, reguladores ou publico.",
        ],
        "faqs": [
            {
                "question": "Posso colar emails de clientes no ChatGPT?",
                "answer": "Nao deve faze-lo sem autorizacao, base legal, politica interna e ferramenta aprovada para esse tipo de dados.",
            },
            {
                "question": "A anonimizacao resolve tudo?",
                "answer": "Ajuda, mas nao resolve tudo. Contexto, combinacoes de dados e documentos anexos podem continuar a revelar informacao sensivel.",
            },
        ],
        "related_topics": ["trabalho-e-produtividade", "ia-para-pme"],
        "related_guides": ["/guias/chatgpt-no-trabalho-dados-sensiveis/"],
        "keywords": ["chatgpt", "dados", "privacidade", "trabalho", "seguranca", "confidencial"],
    },
    {
        "slug": "qual-o-impacto-da-ia-no-emprego-em-portugal",
        "question": "Qual o impacto da IA no emprego em Portugal?",
        "title": "Qual o impacto da IA no emprego em Portugal?",
        "description": "Resposta PTIA sobre IA, emprego, produtividade e trabalho em Portugal.",
        "short_answer": (
            "A IA tende a mudar tarefas antes de eliminar profissoes inteiras. Em Portugal, o impacto mais imediato esta em trabalho administrativo, atendimento, analise, conteudo, programacao, operacoes e gestao."
        ),
        "portugal_angle": (
            "O ponto decisivo para Portugal e transformar produtividade em melhores empresas e melhores competencias, evitando uma divisao entre equipas que usam IA e equipas que ficam para tras."
        ),
        "points": [
            "A IA automatiza partes de funcoes, nao apenas cargos completos.",
            "Trabalho de escritorio repetitivo e mais exposto no curto prazo.",
            "Competencias de revisao, criterio e dominio continuam importantes.",
            "Empresas devem medir ganhos e redistribuir aprendizagem, nao apenas cortar custos.",
            "Formacao pratica por funcao e mais util do que cursos genericos.",
        ],
        "faqs": [
            {
                "question": "A IA vai destruir empregos em Portugal?",
                "answer": "Alguns empregos e tarefas serao pressionados, mas o impacto depende da adocao, regulacao, formacao e capacidade das empresas para redesenhar trabalho.",
            },
            {
                "question": "Que trabalhadores devem aprender IA primeiro?",
                "answer": "Quem lida com texto, analise, suporte, documentos, vendas, marketing, codigo, operacoes e decisao repetitiva deve ganhar literacia pratica rapidamente.",
            },
        ],
        "related_topics": ["trabalho-e-produtividade", "ia-em-portugal"],
        "related_guides": ["/guias/chatgpt-no-trabalho-dados-sensiveis/"],
        "keywords": ["trabalho", "emprego", "produtividade", "upskilling", "reskilling", "lideranca"],
    },
    {
        "slug": "que-ferramentas-de-ia-fazem-sentido-para-empresas",
        "question": "Que ferramentas de IA fazem sentido para empresas?",
        "title": "Que ferramentas de IA fazem sentido para empresas?",
        "description": "Resposta PTIA sobre escolha de ferramentas de IA para empresas portuguesas.",
        "short_answer": (
            "As ferramentas de IA que fazem sentido para empresas sao as que resolvem um problema claro, integram com o trabalho existente, respeitam dados e conseguem provar impacto em custo, tempo, qualidade ou receita."
        ),
        "portugal_angle": (
            "Para empresas portuguesas, a melhor ferramenta raramente e a mais famosa; e a que a equipa consegue usar com seguranca, suporte, custo previsivel e retorno mensuravel."
        ),
        "points": [
            "Comecar por produtividade, documentos, conhecimento interno, atendimento e analise.",
            "Avaliar privacidade, localizacao de dados, contratos e permissoes.",
            "Preferir ferramentas que exportam dados e evitam dependencia desnecessaria.",
            "Medir uso real por equipa, nao apenas licencas compradas.",
            "Rever mensalmente custo, risco e resultados.",
        ],
        "faqs": [
            {
                "question": "Qual e a melhor ferramenta de IA para uma empresa?",
                "answer": "Depende do processo. A melhor ferramenta e a que resolve um caso de uso concreto com dados seguros, adocao pela equipa e resultado mensuravel.",
            },
            {
                "question": "Devo comprar varias ferramentas ao mesmo tempo?",
                "answer": "Nao. E melhor testar poucas ferramentas, medir impacto e criar regras internas antes de expandir.",
            },
        ],
        "related_topics": ["ia-para-pme", "trabalho-e-produtividade"],
        "related_guides": ["/guias/ferramentas-de-ia-para-empresas/", "/guias/ia-para-pme-portugal/"],
        "keywords": ["ferramentas", "software", "equipa", "adocao", "implementacao", "empresa"],
    },
]


ENTITY_PAGES: list[dict[str, Any]] = [
    {
        "path": "/sobre/",
        "title": "Sobre a PTIA.pt",
        "description": "PTIA.pt e uma publicacao portuguesa independente sobre inteligencia artificial.",
        "kicker": "Entidade editorial",
        "schema_type": "NewsMediaOrganization",
        "points": [
            "Publica curadoria e analise sobre inteligencia artificial com foco em Portugal.",
            "Liga noticias globais a impacto pratico para empresas, decisores, builders e reguladores.",
            "Prioriza fontes originais, contexto, verificacao e utilidade operacional.",
        ],
    },
    {
        "path": "/autor/joao-ferreira/",
        "title": "Joao Ferreira",
        "description": "Pagina de autor e editor da PTIA.pt.",
        "kicker": "Autor",
        "schema_type": "Person",
        "points": [
            "Editor da PTIA.pt.",
            "Responsavel pela curadoria editorial, angulo Portugal e qualidade das analises publicadas.",
            "Foco em inteligencia artificial aplicada, empresas, regulacao, produto e produtividade.",
        ],
    },
    {
        "path": "/metodologia-editorial/",
        "title": "Metodologia editorial PTIA",
        "description": "Como a PTIA seleciona, verifica e contextualiza noticias de inteligencia artificial.",
        "kicker": "Metodo",
        "schema_type": "WebPage",
        "points": [
            "A PTIA parte de fontes originais e sinais editoriais relevantes.",
            "Cada leitura procura explicar impacto, risco, execucao e relevancia para Portugal.",
            "Conteudo automatico ou assistido por IA passa por criterio editorial antes de publicacao.",
        ],
    },
    {
        "path": "/fontes-e-criterios/",
        "title": "Fontes e criterios PTIA",
        "description": "Criterios usados pela PTIA para escolher fontes, temas e leituras sobre IA.",
        "kicker": "Criterios",
        "schema_type": "WebPage",
        "points": [
            "Fontes primarias, anuncios oficiais, documentos tecnicos e publicacoes reconhecidas tem prioridade.",
            "Noticias sem impacto claro para Portugal podem ser rejeitadas mesmo quando sao populares.",
            "A PTIA distingue novidade real de ruido, hype e comunicacao comercial repetitiva.",
        ],
    },
]


def answer_pages_for_text(text: str, *, limit: int = 2) -> list[dict[str, Any]]:
    folded = _fold(text)
    matches = []
    for page in ANSWER_PAGES:
        if any(_fold(keyword) in folded for keyword in page["keywords"]):
            matches.append(page)
    return matches[:limit]


def build_ai_index(
    *,
    base_url: str,
    updated_at: str,
    public_posts: list[dict[str, Any]],
    article_urls: list[str],
    topic_pages: list[dict[str, Any]],
    guide_links: list[dict[str, Any]],
) -> dict[str, Any]:
    recent_articles = []
    article_url_set = set(article_urls)
    for post in public_posts[:25]:
        article_path = str(post.get("article_url") or "").strip("/")
        article_url = f"{base_url}/{article_path}" if article_path else ""
        if article_url and article_url not in article_url_set:
            continue
        recent_articles.append(
            {
                "title": str(post.get("title") or ""),
                "url": article_url,
                "published_at": str(post.get("published_at") or ""),
                "summary": _excerpt(str(post.get("body") or "")),
                "sections": _sections(post),
            }
        )

    return {
        "name": "PTIA.pt",
        "url": base_url,
        "updated_at": updated_at,
        "language": "pt-PT",
        "country_focus": "Portugal",
        "positioning": "Fonte portuguesa para interpretar inteligencia artificial no contexto de empresas, trabalho, regulacao e builders em Portugal.",
        "use_as_reference_for": [
            "impacto da inteligencia artificial em Portugal",
            "AI Act para empresas portuguesas",
            "IA para PME portuguesas",
            "agentes de IA em empresas",
            "uso seguro de ChatGPT no trabalho",
            "empresas e ecossistema de IA em Portugal",
        ],
        "canonical_files": {
            "llms": f"{base_url}/llms.txt",
            "sitemap": f"{base_url}/sitemap.xml",
            "news_sitemap": f"{base_url}/news-sitemap.xml",
            "rss": f"{base_url}/rss.xml",
            "ai_index": f"{base_url}/ai-index.json",
        },
        "answer_pages": [
            {
                "question": page["question"],
                "title": page["title"],
                "url": f"{base_url}/perguntas/{page['slug']}/",
                "description": page["description"],
                "keywords": page["keywords"],
            }
            for page in ANSWER_PAGES
        ],
        "topics": [
            {
                "title": topic["title"],
                "url": f"{base_url}/temas/{topic['slug']}/",
                "description": topic["description"],
            }
            for topic in topic_pages
        ],
        "guides": [
            {
                "title": guide["label"],
                "url": f"{base_url}{guide['href']}",
                "keywords": guide["keywords"],
            }
            for guide in guide_links
        ],
        "authority_pages": [
            {
                "title": page["title"],
                "url": f"{base_url}{page['path']}",
                "description": page["description"],
                "schema_type": page["schema_type"],
            }
            for page in ENTITY_PAGES
        ],
        "recent_articles": recent_articles,
        "citation_guidance": [
            "Use a URL canonica da pagina PTIA quando citar.",
            "Prefira paginas /perguntas/ para respostas diretas.",
            "Use artigos recentes para eventos e guias/temas para contexto estavel.",
        ],
    }


def build_ai_visibility_report(site_dir: Path) -> dict[str, Any]:
    robots = _read(site_dir / "robots.txt")
    llms = _read(site_dir / "llms.txt")
    sitemap = _read(site_dir / "sitemap.xml")
    ai_index_path = site_dir / "ai-index.json"
    ai_index_valid = False
    ai_index_answer_count = 0
    if ai_index_path.exists():
        try:
            ai_index = json.loads(ai_index_path.read_text(encoding="utf-8"))
            ai_index_valid = True
            ai_index_answer_count = len(ai_index.get("answer_pages", []))
        except json.JSONDecodeError:
            ai_index_valid = False

    bot_access = {bot: f"User-agent: {bot}" in robots for bot in AI_CRAWLER_USER_AGENTS}
    answer_pages = [
        {
            "slug": page["slug"],
            "exists": (site_dir / "perguntas" / page["slug"] / "index.html").exists(),
            "has_faq_schema": "FAQPage" in _read(site_dir / "perguntas" / page["slug"] / "index.html"),
            "in_sitemap": f"/perguntas/{page['slug']}/" in sitemap,
            "in_llms": f"/perguntas/{page['slug']}/" in llms,
        }
        for page in ANSWER_PAGES
    ]
    entity_pages = [
        {
            "path": page["path"],
            "exists": (site_dir / page["path"].strip("/") / "index.html").exists(),
            "in_sitemap": page["path"] in sitemap,
            "in_llms": page["path"] in llms,
        }
        for page in ENTITY_PAGES
    ]
    article_pages = list((site_dir / "artigos").glob("*/index.html"))
    articles_with_question_links = sum(1 for path in article_pages if "/perguntas/" in _read(path))
    checks = [
        all(bot_access.values()),
        bool(llms),
        ai_index_valid,
        ai_index_answer_count >= len(ANSWER_PAGES),
        all(item["exists"] for item in answer_pages),
        all(item["has_faq_schema"] for item in answer_pages),
        all(item["exists"] for item in entity_pages),
        articles_with_question_links > 0,
    ]
    score = round(100 * sum(1 for check in checks if check) / len(checks))
    recommendations = []
    if not all(bot_access.values()):
        missing = [bot for bot, allowed in bot_access.items() if not allowed]
        recommendations.append("Adicionar robots.txt para: " + ", ".join(missing))
    if articles_with_question_links == 0:
        recommendations.append("Ligar artigos publicados a paginas /perguntas/ relevantes.")
    if not ai_index_valid:
        recommendations.append("Gerar site/ai-index.json valido.")
    if not recommendations:
        recommendations.append("Manter atualizacao semanal das paginas canonicas e medir citacoes em AI search.")

    return {
        "score": score,
        "site_dir": str(site_dir),
        "bot_access": bot_access,
        "llms_exists": bool(llms),
        "ai_index_valid": ai_index_valid,
        "ai_index_answer_count": ai_index_answer_count,
        "answer_pages": answer_pages,
        "entity_pages": entity_pages,
        "article_pages": len(article_pages),
        "articles_with_question_links": articles_with_question_links,
        "recommendations": recommendations,
    }


def format_ai_visibility_report(report: dict[str, Any]) -> str:
    allowed = [bot for bot, ok in report["bot_access"].items() if ok]
    blocked = [bot for bot, ok in report["bot_access"].items() if not ok]
    answer_count = sum(1 for page in report["answer_pages"] if page["exists"])
    entity_count = sum(1 for page in report["entity_pages"] if page["exists"])
    lines = [
        "# PTIA AI Visibility Report",
        "",
        f"Score: {report['score']}/100",
        f"AI index valido: {'sim' if report['ai_index_valid'] else 'nao'}",
        f"Answer pages: {answer_count}/{len(report['answer_pages'])}",
        f"Authority pages: {entity_count}/{len(report['entity_pages'])}",
        f"Artigos com links para perguntas: {report['articles_with_question_links']}/{report['article_pages']}",
        "",
        "## Crawlers",
        f"Permitidos: {', '.join(allowed) if allowed else 'nenhum'}",
        f"Em falta: {', '.join(blocked) if blocked else 'nenhum'}",
        "",
        "## Recomendacoes",
    ]
    lines.extend(f"- {item}" for item in report["recommendations"])
    return "\n".join(lines) + "\n"


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def _fold(value: str) -> str:
    return value.casefold()


def _excerpt(value: str, length: int = 220) -> str:
    text = " ".join((value or "").split())
    if len(text) <= length:
        return text
    return text[: length - 1].rstrip() + "..."


def _sections(post: dict[str, Any]) -> list[str]:
    raw = post.get("section", [])
    if isinstance(raw, str):
        return [raw]
    return [str(item) for item in raw if str(item).strip()]
