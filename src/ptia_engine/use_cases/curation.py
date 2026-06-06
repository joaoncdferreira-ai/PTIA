from __future__ import annotations

import re

from pathlib import Path

from ptia_engine.editorial_board import (
    add_final_post,
    add_editorial_topic,
    add_radar_signal,
    update_final_post_copy,
    update_final_post_status,
    update_signal_status,
    update_topic_status,
)
from ptia_engine.models import EditorialTopic, FinalPost, RadarSignal
from ptia_engine.repositories import EditorialTopicRepository, FinalPostRepository, RadarSignalRepository
from ptia_engine.search_providers import GeminiGroundedSearchProvider
from ptia_engine.services.channels import channel_enabled, load_channel_config
from ptia_engine.services.editorial_hygiene import (
    apply_ptia_editorial_rules,
    normalise_hashtags,
    validate_final_package_copy,
    validate_final_post_copy,
)
from ptia_engine.services.social_text import x_post_body
from ptia_engine.source_verifier import resolve_submitted_link

# Private helpers copied/adapted from dashboard.py to prevent circular imports

def _first_sentence(text: str, fallback: str = "") -> str:
    clean = re.sub(r"\s+", " ", text or "").strip()
    if not clean:
        return fallback
    match = re.search(r"(.{24,220}?[.!?])(?:\s|$)", clean)
    return (match.group(1) if match else clean[:220]).strip()

def _specific_editorial_seed(title: str, summary: str, why_it_matters: str) -> tuple[str, str]:
    text = f"{title} {summary} {why_it_matters}".casefold()
    if any(token in text for token in ("google", "gemini", "i/o", "alphabet")):
        return (
            "A leitura PTIA está na distribuição: a Google não precisa apenas de ter bons modelos, precisa de os tornar a camada natural dos produtos que milhões de equipas já usam.",
            "Quando a IA aparece dentro da pesquisa, do vídeo ou das ferramentas de trabalho, a concorrência deixa de ser só técnica e passa a ser uma disputa pelo hábito.",
        )
    if any(token in text for token in ("meta", "layoff", "demiss", "desped")):
        return (
            "A tensão está no sinal laboral: a mesma empresa que vende produtividade algorítmica está a redesenhar internamente o tamanho e o papel das equipas.",
            "Isto torna a IA menos uma narrativa de eficiência abstracta e mais uma escolha de gestão com consequências visíveis nas estruturas que a adoptam.",
        )
    if any(token in text for token in ("trump", "casa branca", "ordem executiva", "white house")):
        return (
            "A notícia mostra a IA a sair do laboratório e a entrar na política industrial: o poder já não está só em lançar modelos, está em definir quem pode treiná-los, comprá-los e exportá-los.",
            "Para empresas europeias, este tipo de decisão transforma tecnologia em geopolítica operacional: acesso, fornecedores e compliance passam a fazer parte da mesma conversa.",
        )
    if any(token in text for token in ("openai", "anthropic", "claude", "gpt", "modelo")):
        return (
            "A corrida dos modelos está a ficar menos limpa do que os benchmarks sugerem: cada melhoria técnica é também uma tentativa de prender o utilizador a uma forma específica de trabalhar.",
            "O vencedor pode não ser o modelo mais brilhante em abstracto, mas o que conseguir transformar capacidade em rotina antes de o mercado comparar alternativas.",
        )
    if any(token in text for token in ("regula", "bruxelas", "união europeia", "ai act", "comissão europeia")):
        return (
            "A regulação deixou de ser cenário de fundo. Está a tornar-se parte do próprio produto, porque determina que provas, limites e responsabilidades acompanham cada sistema.",
            "A vantagem passa a depender menos da promessa comercial e mais da capacidade de provar funcionamento, risco e governação sem travar a adopção.",
        )
    if any(token in text for token in ("nvidia", "chip", "semicondutor", "data center", "energia", "compute")):
        return (
            "A IA continua a ser vendida como software, mas a notícia lembra a parte física da disputa: chips, energia, centros de dados e capacidade de entrega.",
            "Quem controla essa infra-estrutura condiciona o ritmo de inovação dos outros, mesmo quando não aparece na interface que o utilizador vê.",
        )

    factual = _first_sentence(summary, title.rstrip("."))
    relevance = _first_sentence(why_it_matters, "")
    thesis = f"O dado que interessa é este: {factual}"
    consequence = relevance or f"Este movimento revela uma escolha concreta de mercado, produto ou poder em {title.rstrip('.')}"
    return thesis, consequence.rstrip(".") + "."

def _ensure_source_line(body: str, source_line: str, source_url: str) -> str:
    if not source_url or source_url in body:
        return body.strip()
    if re.search(r"(?im)^\s*Fonte(?: original)?\s*:", body):
        return body.strip()
    return f"{body.strip()}\n\n{source_line}".strip()

def _high_quality_image_prompt(
    title: str,
    body: str,
    feedback: str = "",
    *,
    group: str = "linkedin_site",
    visual_title: str = "",
    include_x: bool = True,
) -> str:
    feedback_line = f"\nPedido adicional do editor: {feedback.strip()}" if feedback.strip() else ""
    context_line = f'\nContexto editorial PTIA: "{body.strip()[:680]}"' if body.strip() else ""
    if group == "instagram_x":
        target_channels = "Instagram e X" if include_x else "Instagram"
        x_adaptable = " e adaptável para X" if include_x else ""
        selected_title = (
            f'"{visual_title.strip()}"'
            if visual_title.strip()
            else "[escolher no dashboard antes de gerar]"
        )
        return (
            f'Cria uma imagem editorial premium para {target_channels} sobre este tema: "'
            f"{title}"
            '"\n\n'
            f"Título visual escolhido no dashboard para o overlay PTIA: {selected_title}\n"
            "Não desenhes esse título, o logo, palavras, letras, hashtags, legendas ou pseudo-tipografia "
            "na imagem gerada. O dashboard aplica por cima uma camada PTIA fixa com fonte, wordmark, "
            "linha editorial e título para manter a marca consistente.\n\n"
            f"Resultado esperado: master visual feed-first em 1:1, forte em Instagram{x_adaptable}. "
            "Reserva o terço inferior com textura visual simples e contraste controlado para receber "
            "o overlay PTIA; mantém o assunto principal legível acima dessa zona. "
            "Estilo: PTIA editorial, inteligente, crítico quando fizer sentido, fotorealista/cinemático, "
            "luz natural sofisticada, profundidade, textura real e composição memorável. "
            "Comunica a tese através de uma metáfora visual concreta, humana e relevante. "
            "Evita robôs azuis, circuitos neon, dashboards genéricos, ícones flutuantes baratos, "
            "pessoas a apontar para hologramas e aspecto stock. "
            "Entrega apenas a imagem-base sem texto."
            f"{context_line}"
            f"{feedback_line}"
        )
    return (
        'Cria uma imagem sem texto editorial premium para LinkedIn e site sobre este tema: "'
        f"{title}"
        '"\n\n'
        "Resultado esperado: imagem editorial landscape para LinkedIn e site, visual forte, original e memorável, "
        "com qualidade de campanha editorial. "
        "Estilo: fotorealista/cinemático, luz natural sofisticada, composição limpa, profundidade, textura real, "
        "sem texto escrito na imagem, sem mockups de dashboards genéricos, sem ícones flutuantes baratos, sem aspecto stock. "
        "Deve comunicar a ideia central da notícia através de uma metáfora visual concreta, humana e relevante. "
        "Se o tema envolver Portugal, pode usar sinais visuais subtis portugueses ou europeus, mas sem mapas literais forçados. "
        "Evita clichés de robôs azuis, circuitos neon e pessoas a apontar para hologramas, salvo se forem essenciais ao conceito. "
        "A imagem deve funcionar como capa premium de uma publicação de tecnologia e sociedade."
        f"{context_line}"
        f"{feedback_line}"
    )

def _polish_final_post_copy_helper(
    *,
    channel: str,
    title: str,
    body: str,
    hashtags: str,
    source_urls: list[str],
) -> dict:
    from ptia_engine.services.gemini import polish_final_post_copy as _service_polish_final_post_copy
    return _service_polish_final_post_copy(
        channel=channel,
        title=title,
        body=body,
        hashtags=hashtags,
        source_urls=source_urls,
        provider=GeminiGroundedSearchProvider(),
        apply_editorial_rules=apply_ptia_editorial_rules,
    )

def _ensure_x_post_for_topic_helper(
    post_repo: FinalPostRepository,
    buffer_channels_path: Path,
    topic_id: str,
    target_status: str = "needs_final_review",
) -> FinalPost | None:
    config = load_channel_config(buffer_channels_path)
    if not channel_enabled(config, "x"):
        return None
    posts = post_repo.load_all()
    existing = next((post for post in posts if post.topic_id == topic_id and post.channel == "x"), None)
    if existing:
        return existing
    source = next(
        (
            post
            for channel in ("instagram", "linkedin", "site")
            for post in posts
            if post.topic_id == topic_id
            and post.channel == channel
            and post.status in {"needs_final_review", "approved_for_schedule"}
        ),
        None,
    )
    if not source:
        return None
    source_url = source.source_urls[0] if source.source_urls else ""
    source_line = f"Fonte: {source_url or 'fonte original'}"
    body_without_source = re.sub(
        r"(?im)^\s*(?:\*\*)?Fonte(?:s| original)?(?:\*\*)?\s*:.*$",
        "",
        source.body or "",
    ).strip()
    body_without_source = re.sub(r"https?://\S+", "", body_without_source).strip()
    summary = _first_sentence(body_without_source, source.title)
    x_hashtags = normalise_hashtags(source.hashtags or "#IA #PTIA", "x")
    created = add_final_post(
        post_repo.file_path,
        topic_id=topic_id,
        channel="x",
        title=source.title,
        body=x_post_body(summary, "", source_line, x_hashtags),
        hashtags=x_hashtags,
        image_prompt=_high_quality_image_prompt(
            source.title,
            body_without_source or source.body,
            group="instagram_x",
            include_x=True,
        ),
        source_urls=source.source_urls,
        image_path=source.image_path,
        image_variants=source.image_variants,
        editor_notes="X criado automaticamente porque o canal voltou a estar ativo.",
    )
    if target_status == "approved_for_schedule":
        validate_final_post_copy(created)
        return update_final_post_status(
            post_repo.file_path,
            created.post_id,
            status="approved_for_schedule",
        )
    return created

# Curation Use Case classes

class CreateTopicFromSignalUseCase:
    def __init__(self, topic_repo: EditorialTopicRepository):
        self.topic_repo = topic_repo

    def execute(self, title: str, thesis: str, portugal_angle: str, audience: str, signal_ids: list[str], urgency_score: int = 0) -> EditorialTopic:
        return add_editorial_topic(
            self.topic_repo.file_path,
            title=title,
            thesis=thesis,
            portugal_angle=portugal_angle,
            audience=audience,
            source_signal_ids=signal_ids,
            urgency_score=urgency_score,
        )

class BuildFinalPackUseCase:
    def __init__(
        self,
        signal_repo: RadarSignalRepository,
        topic_repo: EditorialTopicRepository,
        post_repo: FinalPostRepository,
        buffer_channels_path: Path,
    ):
        self.signal_repo = signal_repo
        self.topic_repo = topic_repo
        self.post_repo = post_repo
        self.buffer_channels_path = buffer_channels_path

    def execute(self, signal_id: str) -> dict:
        signal = self.signal_repo.get_by_id(signal_id)
        if not signal:
            raise ValueError(f"Signal not found: {signal_id}")
        if signal.status not in {"verified", "verified_secondary", "selected"}:
            raise ValueError("Só sinais verificados podem gerar pacote final.")

        source_url = signal.url
        topic = add_editorial_topic(
            self.topic_repo.file_path,
            title=signal.title[:120],
            thesis=signal.summary or signal.why_it_matters or signal.title,
            portugal_angle=(
                "Validar o impacto para empresas, profissionais e builders em Portugal "
                "antes de publicar."
            ),
            audience="PTIA",
            source_signal_ids=[signal.signal_id],
            urgency_score=max(6, min(10, signal.engagement_score // 10 or 6)),
        )
        topic = update_topic_status(
            self.topic_repo.file_path,
            topic.topic_id,
            "approved_for_final",
            "Criado a partir de Verified Selection.",
        )

        base_summary = signal.summary or "A fonte publicou uma nova informação sobre inteligência artificial."
        why_it_matters = signal.why_it_matters or (_first_sentence(base_summary, signal.title))
        ptia_lens, next_action = _specific_editorial_seed(signal.title, base_summary, why_it_matters)
        hashtags = "#InteligenciaArtificial #IA #Portugal #PTIA"
        body_context = f"{base_summary}\n\n{why_it_matters}\n\n{ptia_lens}"
        
        linkedin_site_image_prompt = _high_quality_image_prompt(signal.title, body_context)
        channel_config = load_channel_config(self.buffer_channels_path)
        include_x = channel_enabled(channel_config, "x")
        
        instagram_x_image_prompt = _high_quality_image_prompt(
            signal.title,
            body_context,
            group="instagram_x",
            include_x=include_x,
        )
        source_line = f"Fonte: {source_url}"
        x_hashtags = "#IA #PTIA"
        
        posts = [
            add_final_post(
                self.post_repo.file_path,
                topic_id=topic.topic_id,
                channel="linkedin",
                title=signal.title,
                body=f"{base_summary}\n\n{ptia_lens}\n\n{why_it_matters} {next_action}\n\n{source_line}",
                hashtags=hashtags,
                image_prompt=linkedin_site_image_prompt,
                source_urls=[source_url],
            ),
            add_final_post(
                self.post_repo.file_path,
                topic_id=topic.topic_id,
                channel="instagram",
                title=signal.title,
                body=f"{base_summary}\n\n{ptia_lens}\n\n{why_it_matters}\n\n{next_action}\n\n{source_line}",
                hashtags=hashtags,
                image_prompt=instagram_x_image_prompt,
                source_urls=[source_url],
            ),
            add_final_post(
                self.post_repo.file_path,
                topic_id=topic.topic_id,
                channel="site",
                title=signal.title,
                body=f"{base_summary}\n\n{ptia_lens}\n\n{why_it_matters}\n\n{next_action}\n\n{source_line}",
                hashtags="",
                image_prompt=linkedin_site_image_prompt,
                source_urls=[source_url],
            ),
        ]
        
        if include_x:
            posts.insert(
                2,
                add_final_post(
                    self.post_repo.file_path,
                    topic_id=topic.topic_id,
                    channel="x",
                    title=signal.title,
                    body=x_post_body(base_summary, why_it_matters, source_line, x_hashtags),
                    hashtags=x_hashtags,
                    image_prompt=instagram_x_image_prompt,
                    source_urls=[source_url],
                ),
            )
            
        polished_posts = []
        for post in posts:
            polished = _polish_final_post_copy_helper(
                channel=post.channel,
                title=post.title,
                body=post.body,
                hashtags=post.hashtags,
                source_urls=post.source_urls,
            )
            polished_hashtags = normalise_hashtags(polished["hashtags"], post.channel)
            polished_body = polished["body"]
            if post.channel == "x":
                x_seed = re.sub(r"(?im)^\s*(?:\*\*)?Fonte(?:s| original)?(?:\*\*)?\s*:.*$", "", polished_body)
                x_seed = re.sub(r"https?://\S+", "", x_seed).strip()
                source_label = signal.source_name or "fonte original"
                polished_body = x_post_body(x_seed, "", f"Fonte: {source_label}", polished_hashtags)
            else:
                polished_body = _ensure_source_line(polished_body, source_line, source_url)
            
            polished_posts.append(
                update_final_post_copy(
                    self.post_repo.file_path,
                    post.post_id,
                    title=polished["title"],
                    body=polished_body,
                    hashtags=polished_hashtags,
                    notes=polished["editor_notes"],
                )
            )
            
        update_signal_status(
            self.signal_repo.file_path,
            signal.signal_id,
            "used",
            "Pacote final criado para revisão.",
        )
        return {"topic": topic, "posts": polished_posts}

class ApprovePackageUseCase:
    def __init__(self, post_repo: FinalPostRepository, buffer_channels_path: Path):
        self.post_repo = post_repo
        self.buffer_channels_path = buffer_channels_path

    def execute(self, reference_post_id: str) -> list[FinalPost]:
        posts = self.post_repo.load_all()
        reference = next((post for post in posts if post.post_id == reference_post_id), None)
        if not reference:
            raise ValueError(f"Final post not found: {reference_post_id}")
            
        _ensure_x_post_for_topic_helper(self.post_repo, self.buffer_channels_path, reference.topic_id)
        
        posts = self.post_repo.load_all()
        package_posts = [
            post
            for post in posts
            if post.topic_id == reference.topic_id and post.status == "needs_final_review"
        ]
        if not package_posts:
            raise ValueError("Este pacote já nao esta em A Rever.")
            
        validate_final_package_copy(package_posts)
        updated = []
        for post in package_posts:
            updated.append(
                update_final_post_status(
                    self.post_repo.file_path,
                    post.post_id,
                    "approved_for_schedule",
                )
            )
        return updated

class EditPolishPostUseCase:
    def __init__(self, post_repo: FinalPostRepository):
        self.post_repo = post_repo

    def execute(self, post_id: str, title: str | None = None, body: str | None = None, hashtags: str | None = None, image_prompt: str | None = None, notes: str = "") -> FinalPost:
        post = self.post_repo.get_by_id(post_id)
        if not post:
            raise ValueError(f"Post not found: {post_id}")
            
        clean_title, clean_body = apply_ptia_editorial_rules(
            title if title is not None else post.title,
            body if body is not None else post.body,
            post.channel,
        )
        
        candidate = FinalPost(
            post_id=post.post_id,
            topic_id=post.topic_id,
            channel=post.channel,
            title=clean_title,
            body=clean_body,
            hashtags=normalise_hashtags(hashtags if hashtags is not None else post.hashtags, post.channel),
            image_prompt=image_prompt if image_prompt is not None else post.image_prompt,
            source_urls=post.source_urls,
            image_path=post.image_path,
            image_variants=post.image_variants,
            image_status=post.image_status,
            editor_notes=post.editor_notes,
            status=post.status,
            scheduled_time=post.scheduled_time,
            buffer_post_id=post.buffer_post_id,
            published_url=post.published_url,
            created_at=post.created_at,
        )
        validate_final_post_copy(candidate)
        
        return update_final_post_copy(
            self.post_repo.file_path,
            post_id,
            title=clean_title,
            body=clean_body,
            hashtags=candidate.hashtags,
            image_prompt=candidate.image_prompt,
            notes=notes,
        )

class ReverifySignalUseCase:
    def __init__(self, signal_repo: RadarSignalRepository):
        self.signal_repo = signal_repo

    def _update_signal_verification_fields(
        self,
        signal_id: str,
        *,
        source_name: str,
        title: str,
        url: str,
        published_at: str,
        summary: str,
        notes: str,
    ) -> RadarSignal:
        signals = self.signal_repo.load_all()
        for signal in signals:
            if signal.signal_id != signal_id:
                continue
            signal.status = "verified"
            signal.source_name = source_name or signal.source_name
            signal.title = title or signal.title
            signal.url = url or signal.url
            signal.published_at = published_at or signal.published_at
            signal.summary = summary or signal.summary
            if notes:
                from ptia_engine.models import utc_now_iso
                signal.notes = f"{signal.notes}\n[{utc_now_iso()}] {notes}".strip()
            self.signal_repo.save_all(signals)
            return signal
        raise ValueError(f"Signal not found: {signal_id}")

    def execute_single(self, signal_id: str) -> dict:
        signal = self.signal_repo.get_by_id(signal_id)
        if not signal:
            raise ValueError(f"Signal not found: {signal_id}")
            
        verification = resolve_submitted_link(signal.url, thought=signal.topic_hint or signal.notes)
        if verification.status == "verified":
            new_signal = add_radar_signal(
                self.signal_repo.file_path,
                source_type="news",
                source_name=verification.source_name,
                title=verification.title,
                url=verification.verified_url or signal.url,
                published_at=verification.published_at,
                engagement_score=max(signal.engagement_score, 60),
                summary=verification.summary or signal.summary,
                topic_hint=signal.topic_hint,
                why_it_matters=signal.why_it_matters,
                why_engaged=signal.why_engaged,
                notes=verification.notes,
                status="verified",
                require_recent=True,
            )
            
            if new_signal.signal_id == signal.signal_id:
                verified_signal = self._update_signal_verification_fields(
                    signal.signal_id,
                    source_name=verification.source_name,
                    title=verification.title,
                    url=verification.verified_url or signal.url,
                    published_at=verification.published_at,
                    summary=verification.summary or signal.summary,
                    notes="Fonte credivel e data encontradas; sinal reposto em Verified Selection.",
                )
                return {"verified": True, "signal": verified_signal}
                
            update_signal_status(
                self.signal_repo.file_path,
                signal.signal_id,
                "used",
                "Fonte credivel encontrada; novo sinal verificado criado.",
            )
            return {"verified": True, "signal": new_signal}

        pending_signal = update_signal_status(
            self.signal_repo.file_path,
            signal.signal_id,
            "verifying",
            verification.notes,
        )
        return {
            "verified": False,
            "signal": pending_signal,
            "status": verification.status,
            "notes": verification.notes,
        }

    def execute_queue(self) -> dict:
        signals = self.signal_repo.load_all()
        signal_ids = [signal.signal_id for signal in signals if signal.status == "verifying"]
        results = []
        verified = 0
        failed = 0
        for signal_id in signal_ids:
            try:
                result = self.execute_single(signal_id)
            except Exception as exc:
                failed += 1
                results.append({"signal_id": signal_id, "status": "error", "error": str(exc)})
                continue
            signal = result["signal"]
            verified += int(bool(result["verified"]))
            results.append(
                {
                    "signal_id": signal.signal_id,
                    "status": signal.status,
                    "source_name": signal.source_name,
                }
            )
        return {
            "checked": len(signal_ids),
            "verified": verified,
            "verifying": len(signal_ids) - verified - failed,
            "failed": failed,
            "results": results,
        }

class GenerateNoopScheduleUseCase:
    def __init__(self, repo_root: Path, final_posts_path: Path | None = None, buffer_channels_path: Path | None = None):
        self.repo_root = repo_root
        self.final_posts_path = final_posts_path
        self.buffer_channels_path = buffer_channels_path

    def execute(self, date_str: str, plan_json_path: Path | None = None) -> dict:
        from ptia_engine.scheduler import build_schedule_day_plan, load_schedule_slots
        slots = load_schedule_slots(plan_json_path) if plan_json_path else None
        plan = build_schedule_day_plan(
            repo_root=self.repo_root,
            date=date_str,
            final_posts_path=self.final_posts_path,
            buffer_channels_path=self.buffer_channels_path,
            slots=slots,
            dry_run=True,
        )
        return plan.to_record()
