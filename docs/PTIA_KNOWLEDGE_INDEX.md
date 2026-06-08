# PTIA Knowledge Index

## Objetivo

O PTIA Knowledge Index consolida no site quatro ativos editoriais atualizados semanalmente:

- índice de pessoas e empresas com impacto público na IA em Portugal;
- ferramentas de IA por caso de uso;
- Top 10 prompts PTIA e biblioteca pesquisável;
- glossário português de Inteligência Artificial.

O Hub em `/recursos/` resume os quatro ativos, mostra oito vencedores de ferramentas com score PTIA e oito prompts para manter os painéis comparáveis.

O diretório histórico `site/quem-e-quem.html` continua disponível como base completa. O Top 10 é uma vista editorial sobre essa base, não a substitui.
O ranking usa uma baseline própria em `config/ptia_knowledge.json`; a ordem alfabética ou histórica do diretório não determina o Top 10.

## Comando

```powershell
$env:PYTHONPATH="src"
python -m ptia_engine.cli knowledge-update --json
```

O comando lê:

- `config/ptia_knowledge.json`;
- `site/assets/quem-e-quem.json`;
- `site/site-feed.json`;
- a edição anterior em `site/assets/ptia-index/latest.json`, quando existe.

Não lê nem escreve `data/final_posts.jsonl`, não chama o Buffer e não altera o motor de comentários LinkedIn.

## Saídas

- `site/recursos/index.html`
- `site/ia-em-portugal/index.html`
- `site/ferramentas/index.html`
- `site/prompts/index.html`
- `site/glossario/index.html`
- `site/metodologia-indice/index.html`
- `site/assets/ptia-index/latest.json`
- `site/assets/ptia-index/archive/YYYY-Www.json`

As páginas são pré-renderizadas e incluem dados estruturados Schema.org. Continuam funcionais sem JavaScript; o JavaScript serve apenas filtros, pesquisa e cópia de prompts.

Cada edição compara as posições com o arquivo semanal anterior. Os registos publicam um estado estruturado e uma etiqueta visível: `Entrou no Top`, `Subiu X`, `Desceu X`, `Manteve` ou `Nova edição/categoria`.

## Metodologia

### Pessoas e empresas

- 82%: posição editorial versionada no diretório;
- 18%: menções únicas nos artigos PTIA públicos dos últimos 84 dias.

### Ferramentas

Não existe uma escala científica única que compare ferramentas de coding, estudo, design e vídeo. Por isso, cada categoria tem pesos próprios e agrega quatro componentes:

- capacidade: benchmarks independentes quando existem, ou testes comparáveis documentados;
- popularidade: utilização pública, tráfego ou adoção publicados por fontes identificadas;
- adequação: cobertura do workflow específico;
- acesso: disponibilidade, integração, custo e facilidade de utilização.

Cada componente contém a sua própria ordem, fonte e peso em `tool_category_evidence`. O código calcula a pontuação final por agregação ponderada. Os nomes das ferramentas não determinam diretamente o resultado.

Quando não existe benchmark independente adequado, a fonte é identificada como avaliação editorial. O sistema não apresenta essa avaliação como medição científica.

Automações têm um ranking próprio, separado de produtividade, que compara plataformas de workflows e agentes como n8n, Make, Zapier, Power Automate e Manus.

### Prompts

- 78%: qualidade e reutilização editorial;
- 22%: frequência dos temas associados na cobertura recente.

A biblioteca inclui prompts de imagem. O formulário de caso de uso livre procura primeiro uma correspondência no catálogo. Quando não existe, cria localmente uma estrutura inicial e identifica-a explicitamente como não testada pela PTIA; não chama um modelo nem apresenta a sugestão como validada.

### Glossário

As definições são versionadas no catálogo. A automação pode alterar a ordem de destaque, mas não reescreve definições com um modelo generativo.

Os termos apresentados em português incluem também a designação inglesa, que participa na pesquisa e é publicada como `alternateName` nos dados estruturados. Nos acrónimos, a designação inglesa desenvolve todas as letras, por exemplo `RAG — Retrieval-Augmented Generation`.

## Segurança

A geração valida quantidades mínimas, IDs únicos, categorias, URLs e conteúdo antes de escrever. Se a validação falhar, a edição pública anterior permanece intacta.

As escritas são feitas por substituição atómica de cada ficheiro. Artigos futuros não contam para o ranking.

## Automação

`.github/workflows/weekly-knowledge.yml` executa às segundas-feiras às 09:00 no timezone `Europe/Lisbon`, acompanhando automaticamente a mudança entre horário de inverno e de verão:

1. instala o projeto;
2. executa os testes específicos;
3. gera a edição semanal;
4. cria um commit apenas com os artefactos do Knowledge Index;
5. faz push para o ramo atual, acionando o deploy Vercel.

O workflow não usa segredos nem depende deste computador.
Pode também ser executado manualmente através de `workflow_dispatch`.

## Limites editoriais

- “Influência” significa impacto editorial observável, não valor absoluto.
- “Trending PTIA” mede a agenda publicada pela PTIA, não toda a internet.
- Popularidade é um componente do score de ferramentas, não uma prova isolada de qualidade.
- Rankings e benchmarks têm datas, âmbitos e limitações diferentes; uma fonte isolada não determina a posição.
- Correções devem ser suportadas por uma fonte verificável e ficam registadas no histórico Git.
