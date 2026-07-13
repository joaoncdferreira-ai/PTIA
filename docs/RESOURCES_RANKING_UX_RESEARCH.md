# Recursos PTIA — pesquisa de UX, rankings e engagement

Data: 13 de julho de 2026

## Decisão

A página Recursos passa a funcionar como uma publicação de rankings, não como um diretório de cartões. Há três tipos de conteúdo com regras diferentes:

1. **Top comparável** — posições numeradas apenas quando todos os itens foram avaliados pelos mesmos critérios e a categoria tem pelo menos duas fontes externas independentes. Abaixo desse gate, as ferramentas aparecem como shortlist sem posições.
2. **Watchlist verificável** — pessoas e empresas sem posição até cumprirem o gate de estado ativo, duas fontes independentes e verificação recente.
3. **Seleção editorial** — prompts explicitamente escolhidos por clareza, reutilização e utilidade; não apresentados como popularidade.

Esta separação remove as etiquetas ambíguas “a acompanhar”, “provisório” e “médio” da experiência principal. Em seu lugar aparecem medidas que o leitor consegue interpretar: posição, índice relativo, quatro critérios e progresso do gate de fontes.

## O que a literatura suporta

### 1. A aparência influencia a confiança, mas não substitui a utilidade

Tractinsky, Katz e Ikar encontraram um efeito forte da estética na perceção posterior de usabilidade. O estudo sobre prototipicidade de Miniukovich e Figl, com mais de 1.500 participantes e mais de 3.000 páginas, mostra também uma relação forte com confiança. A consequência não é tornar a interface decorativa: é usar uma estrutura familiar de ranking, com acabamento visual distintivo.

- [Tractinsky et al., What is beautiful is usable](https://doi.org/10.1016/S0953-5438(00)00031-X)
- [Miniukovich & Figl, prototypicality, aesthetics, usability and trustworthiness](https://www.sciencedirect.com/science/article/pii/S107158192300112X)

Aplicação: capa editorial forte, Top 3 reconhecível, lista vertical e detalhes progressivos. Evitámos uma galeria experimental ou um dashboard genérico.

### 2. A posição cria atenção — e por isso exige responsabilidade

Num sistema real com cerca de dez milhões de recomendações, Collins et al. observaram forte enviesamento de posição: o primeiro resultado recebeu muito mais cliques do que seria esperado sem esse efeito. Eye tracking mostra também concentração inicial nos primeiros itens e em elementos visualmente salientes.

- [Collins et al., A Study of Position Bias](https://arxiv.org/abs/1802.06565)
- [Pearson & van Schaik, browsing behaviour and visual saliency](https://doi.org/10.1145/1414471.1414495)

Aplicação: o pódio só existe para listas comparáveis. Uma pessoa ou empresa sem fontes não recebe “#1 provisório”, porque o número legitimaria uma posição que a evidência ainda não suporta.

### 3. Transparência funciona melhor em camadas

Kizilcec mostrou que uma explicação pode recuperar confiança quando o resultado viola expectativas, mas transparência excessiva pode também reduzi-la. A boa solução é progressiva: resposta rápida primeiro; detalhe e fontes disponíveis quando o leitor os pede.

- [Kizilcec, How Much Information? Effects of Transparency on Trust](https://doi.org/10.1145/2858036.2858402)

Aplicação: cada posição mostra imediatamente “melhor para” e índice; “Porque está aqui” abre pesos, alertas e fontes. A metodologia completa fica a um clique.

### 4. Não existe uma regra universal de “menos escolhas”

A meta-análise de Scheibehenne, Greifeneder e Todd encontrou um efeito médio de choice overload próximo de zero, com elevada variação entre contextos. Reduzir arbitrariamente o catálogo não é a solução; reduzir o custo de comparação é.

- [Scheibehenne et al., Can There Ever Be Too Many Options?](https://scheibehenne.com/ScheibehenneGreifenederTodd2010.pdf)

Aplicação: as nove categorias continuam disponíveis, mas o leitor escolhe primeiro a tarefa e vê apenas três itens. Na edição atual, seis categorias cumprem o gate e publicam um Top 3; três ficam como shortlist, explicitamente sem posições.

### 5. Confiança deve ser calibrada, não adjetivada

Um estudo experimental publicado na AAAI 2026 encontrou ganhos claros quando a confiança comunicada estava bem calibrada e ganhos mínimos quando estava mal calibrada. “Médio” ou “provisório” sem denominador não ajuda o leitor a calibrar nada.

- [Confidence Calibration in AI-Assisted Decision Making, AAAI 2026](https://ojs.aaai.org/index.php/AAAI/article/view/38798)

Aplicação: “0/2 fontes recentes” substitui “confiança provisória”; “1/2 fontes externas — sem posições publicadas” substitui “confiança média”.

## O que aprendemos com rankings de referência

- [Fortune 500](https://fortune.com/ranking/fortune500/2026/) usa uma métrica dominante compreensível, mudança de posição, pesquisa, filtros e comparação entre anos.
- [Interbrand Best Global Brands](https://interbrand.com/best-global-brands/) publica requisitos explícitos de elegibilidade e explica por que algumas marcas conhecidas ficam fora.
- [a16z Top 100 Gen AI Apps](https://a16z.com/100-gen-ai-apps-6/) combina uma metodologia mensurável com uma leitura editorial do que mudou.
- [Forbes AI 50 — metodologia](https://www.forbes.com/sites/elisabethbrier/2025/04/10/how-forbes-compiled-the-2025-ai-50-list/) e [TIME Best Inventions](https://time.com/7323662/best-inventions-2025-how-we-picked/) mostram que uma seleção pode ser prestigiada sem inventar uma ordem numérica quando a decisão inclui julgamento editorial.

O padrão comum é: promessa clara, regra de entrada, lista pesquisável/comparável, contexto de mudança e metodologia próxima.

## Arquitetura implementada

### Capa

- Uma promessa: “Os sinais de IA que valem o teu tempo.”
- Escolha da semana ligada a uma categoria real.
- Quatro provas rápidas: número de tops, critérios, perfis elegíveis e mudanças auditáveis.
- Ação primária “Explorar os tops” e partilha da edição.

### Ferramentas

- Navegação por tarefa, não por marca.
- Gate de publicação: duas fontes externas independentes por categoria; abaixo disso, shortlist alfabética sem números nem botão de partilha.
- Top 3 com hierarquia visual real.
- Índice relativo inteiro, sem falsa precisão decimal.
- “Porque está aqui” com melhor uso, alerta, quatro componentes e fontes.
- Link para a comparação completa.

### Portugal

- Perfis elegíveis recebem posição.
- Restantes perfis aparecem numa watchlist sem número.
- O indicador x/2 comunica o progresso do gate.
- Alterações de estado ficam em arquivo com fontes; Unbabel permanece visível como correção, não como empresa ativa.

### Prompts e open source

- Prompts são “seleção editorial”, com critérios declarados.
- Open source mantém-se num radar separado; stars e atividade não contaminam o índice PTIA.

## Formato LinkedIn

O LinkedIn recomenda documentos para insights, tendências e partilha de conhecimento. A sua documentação atual diz também que Pages que publicam semanalmente têm mais de cinco vezes mais seguidores e crescem sete vezes mais depressa do que Pages que publicam mensalmente.

- [LinkedIn Help — upload e partilha de documentos](https://www.linkedin.com/help/linkedin/answer/a518909/upload-and-share-documents-on-linkedin)
- [LinkedIn Page posts FAQ](https://www.linkedin.com/help/linkedin/answer/a565070)

O motor semanal gera um documento 4:5 de oito páginas:

1. promessa/tensão;
2. como ler os quatro critérios;
3–5. uma escolha por tarefa, com razão e índice;
6. correção de estado;
7. gate Portugal;
8. pergunta concreta e URL.

O post abre com uma opinião defensável, entrega três escolhas úteis, mostra uma correção e termina com uma pergunta editorial. Não publica pessoas/empresas sem gate como “destaques”.

## Hipótese e medição

**Hipótese:** se o hub começar por uma tarefa, mostrar um Top 3 explicável e disponibilizar a evidência em camadas, mais leitores executarão uma ação útil do que na grelha anterior de cartões equivalentes.

**Métrica primária:** aberturas de “Porque está aqui” por visualização de `/recursos/`.

**Secundárias:**

- seleção de outra categoria;
- abertura da comparação completa;
- partilha iniciada e concluída;
- abertura da metodologia, watchlist ou fonte;
- cliques para prompts.

**Guardrails:**

- nenhuma posição Portugal sem gate;
- arquivo/correções sempre acessíveis;
- funcionamento sem JavaScript para o primeiro top;
- navegação por teclado, foco visível e respeito por `prefers-reduced-motion`;
- Do Not Track respeitado e nenhum dado pessoal nos eventos.

Eventos implementados: `resource_category_selected`, `resource_evidence_opened`, `resource_share_started`, `resource_share_completed` e `resource_action_clicked`.

Não foi introduzido um split A/B aleatório sem conhecer o volume. Primeiro recolhe-se uma baseline; depois calcula-se a amostra necessária com tráfego e taxa reais. O novo desenho fica identificado pelos assets versionados para permitir essa comparação.

## Atualização semanal

O conteúdo continua a nascer do índice versionado gerado pelo motor. O workflow de conhecimento corre à segunda-feira às 09:00 em `Europe/Lisbon`; o workflow social prepara a revisão à sexta-feira. Em cada ciclo, o motor:

1. valida estados e gates de fontes antes de pontuar;
2. atualiza apenas os rankings que cumprem o gate e mantém os restantes como shortlist;
3. compara movimentos com a edição anterior;
4. arquiva a edição;
5. regenera o site;
6. prepara o rascunho LinkedIn num workflow separado;
7. deixa o post em revisão editorial antes da publicação.

A automação não transforma falta de evidência em certeza: quando o gate não é cumprido, a interface e o post dizem-no explicitamente.
