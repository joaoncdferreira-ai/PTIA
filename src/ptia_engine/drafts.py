from __future__ import annotations

from ptia_engine.dedupe import stable_hash
from ptia_engine.models import ContentDraft, ProcessedItem, RawArticle


DEFAULT_HASHTAGS = {
    "builders": "#InteligenciaArtificial #AI #Programacao #Portugal",
    "business": "#InteligenciaArtificial #Empresas #Produtividade #Portugal",
    "regulation": "#InteligenciaArtificial #Regulacao #AIAct #Portugal",
    "research": "#InteligenciaArtificial #Investigacao #MachineLearning #Portugal",
    "tools": "#InteligenciaArtificial #FerramentasAI #Produtividade #Portugal",
    "portugal_ai": "#InteligenciaArtificial #Portugal #Tecnologia #Inovacao",
    "world_ai": "#InteligenciaArtificial #AI #Tecnologia #Portugal",
}


def _short_excerpt(article: RawArticle, max_chars: int = 360) -> str:
    excerpt = article.raw_excerpt.strip()
    if len(excerpt) <= max_chars:
        return excerpt
    return excerpt[:max_chars].rsplit(" ", 1)[0].strip() + "..."


def _angle_for_section(item: ProcessedItem) -> str:
    if item.section == "builders":
        return "Equipas tecnicas em Portugal devem observar o que isto muda em desenvolvimento, seguranca e automacao."
    if item.section == "business":
        return "Empresas portuguesas devem perceber se isto altera produtividade, operacoes ou relacao com clientes."
    if item.section == "regulation":
        return "Organizacoes em Portugal devem acompanhar impacto em compliance, dados e governanca."
    if item.section == "research":
        return "Builders e equipas de produto devem avaliar se a investigacao tem aplicacao pratica ou ainda e sinal fraco."
    if item.section == "tools":
        return "Vale testar apenas se resolver um workflow concreto, nao por novidade."
    return "O angulo para Portugal deve ser validado pelo editor antes de publicar."


def make_template_drafts(item: ProcessedItem, article: RawArticle) -> list[ContentDraft]:
    hashtags = DEFAULT_HASHTAGS.get(item.section, DEFAULT_HASHTAGS["world_ai"])
    excerpt = _short_excerpt(article)
    portugal_angle = _angle_for_section(item)
    base_title = item.title_original
    base_id = stable_hash(item.item_id)

    linkedin_body = f"""{base_title}

{excerpt or 'Resumo ainda precisa de validacao editorial.'}

{portugal_angle}

Este e um rascunho de curadoria. Confirmar fonte, claims e contexto antes de publicar.

Fonte original: {item.source_url}

Que impacto ves isto a ter em equipas portuguesas?

{hashtags}"""

    instagram_caption = f"""{base_title}

{portugal_angle}

- O que mudou na pratica?
- Quem em Portugal deve prestar atencao?
- Que acao concreta isto sugere?

Guarda para rever e segue o PTIA para curadoria de IA sem hype.

Fonte: {item.source_url}

{hashtags}"""

    carousel_outline = f"""Slide 1: {base_title}
Texto: O essencial, sem hype.
Visual: headline limpa + categoria {item.section}.

Slide 2: O que aconteceu
Texto: {excerpt or 'Validar resumo antes de publicar.'}
Visual: bloco de noticia/fonte.

Slide 3: Porque importa
Texto: Pode afetar decisoes, ferramentas ou processos ligados a IA.
Visual: tres bullets curtos.

Slide 4: Quem deve prestar atencao
Texto: Profissionais, empresas e builders conforme o impacto real.
Visual: icones por audiencia.

Slide 5: Angulo Portugal
Texto: {portugal_angle}
Visual: mapa/nota Portugal.

Slide 6: Takeaway
Texto: Confirmar fonte, testar utilidade e evitar hype.
Visual: frase final + PTIA."""

    site_body = f"""{base_title}

{excerpt or 'Resumo a completar apos revisao editorial.'}

{portugal_angle}

Fonte: {item.source_url}
"""

    newsletter_body = f"""**{base_title}**

{excerpt or 'Resumo a completar apos revisao editorial.'}

{portugal_angle}

Fonte: {item.source_url}
"""

    return [
        ContentDraft(
            draft_id=f"draft_{base_id}_linkedin",
            item_id=item.item_id,
            article_id=item.article_id,
            channel="linkedin",
            format="linkedin_post",
            title=base_title,
            body=linkedin_body,
            hashtags=hashtags,
            cta="Que impacto ves isto a ter em equipas portuguesas?",
        ),
        ContentDraft(
            draft_id=f"draft_{base_id}_instagram_caption",
            item_id=item.item_id,
            article_id=item.article_id,
            channel="instagram",
            format="instagram_caption",
            title=base_title,
            caption=instagram_caption,
            hashtags=hashtags,
            cta="Guarda para rever e partilha com quem acompanha IA.",
        ),
        ContentDraft(
            draft_id=f"draft_{base_id}_instagram_carousel",
            item_id=item.item_id,
            article_id=item.article_id,
            channel="instagram",
            format="instagram_carousel",
            title=base_title,
            carousel_outline=carousel_outline,
            hashtags=hashtags,
        ),
        ContentDraft(
            draft_id=f"draft_{base_id}_site",
            item_id=item.item_id,
            article_id=item.article_id,
            channel="site",
            format="site_short_article",
            title=base_title,
            body=site_body,
        ),
        ContentDraft(
            draft_id=f"draft_{base_id}_newsletter",
            item_id=item.item_id,
            article_id=item.article_id,
            channel="newsletter",
            format="newsletter_item",
            title=base_title,
            body=newsletter_body,
        ),
    ]
