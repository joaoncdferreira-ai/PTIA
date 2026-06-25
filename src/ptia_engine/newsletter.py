from __future__ import annotations

import json
import re
import unicodedata

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from html import escape
from pathlib import Path
from textwrap import dedent

from ptia_engine.dedupe import stable_hash
from ptia_engine.models import (
    ContentPerformance,
    FinalPost,
    NewsletterIssue,
    RadarSignal,
    TrendSignal,
    utc_now_iso,
)
from ptia_engine.services.media import public_image_url
from ptia_engine.services.site import article_url_for_site_post, site_public_base_url
from ptia_engine.storage import append_jsonl, load_newsletter_issues, write_jsonl


NEWSLETTER_STATUSES = {"draft", "approved", "scheduled", "sent", "rejected", "failed"}
NEWSLETTER_GENERATOR_VERSION = "4"


@dataclass(slots=True)
class NewsletterCandidate:
    item_id: str
    title: str
    source_name: str
    url: str
    published_at: str
    summary: str
    why_it_matters: str
    why_engaged: str
    portugal_angle: str
    score: int
    kind: str
    event_key: str = ""
    image_url: str = ""


def _parse_date(value: str) -> datetime:
    raw = (value or "").strip()
    if not raw:
        return datetime.min.replace(tzinfo=timezone.utc)
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        if len(raw) == 10:
            return datetime.fromisoformat(raw).replace(tzinfo=timezone.utc)
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        return datetime.min.replace(tzinfo=timezone.utc)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _recent_enough(value: str, days: int) -> bool:
    parsed = _parse_date(value)
    if parsed == datetime.min.replace(tzinfo=timezone.utc):
        return True
    return parsed >= datetime.now(timezone.utc) - timedelta(days=days)


def _clean(value: str, fallback: str = "") -> str:
    text = " ".join((value or "").split())
    return text or fallback


def _short(value: str, limit: int = 260) -> str:
    text = _clean(value)
    if len(text) <= limit:
        return text
    return text[:limit].rsplit(" ", 1)[0].rstrip(".,;:") + "..."


_EVENT_STOPWORDS = {
    "about",
    "after",
    "and",
    "aos",
    "aqui",
    "artificial",
    "abert",
    "apresentad",
    "com",
    "como",
    "codigo",
    "codig",
    "daqui",
    "daqu",
    "das",
    "disponivel",
    "dos",
    "for",
    "from",
    "fica",
    "ferramenta",
    "ferrament",
    "inteligencia",
    "inteligenc",
    "into",
    "julho",
    "julh",
    "lancad",
    "modelo",
    "model",
    "para",
    "pela",
    "pelo",
    "por",
    "portugal",
    "portugues",
    "portugu",
    "portuguesa",
    "primeiro",
    "primeir",
    "que",
    "ser",
    "sobre",
    "the",
    "uma",
    "vai",
    "with",
}


def _normalize_event_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value or "")
    return normalized.encode("ascii", "ignore").decode("ascii").casefold()


def _canonical_event_token(token: str) -> str:
    if token.isdigit() or len(token) <= 4 or token.endswith("ia"):
        return token
    return token.rstrip("aeios")


def _event_tokens(value: str) -> set[str]:
    tokens = set()
    for token in re.findall(r"[a-z0-9]+", _normalize_event_text(value)):
        canonical = _canonical_event_token(token)
        if (len(canonical) > 2 or canonical.isdigit()) and canonical not in _EVENT_STOPWORDS:
            tokens.add(canonical)
    return tokens


def _same_news_event(left: NewsletterCandidate, right: NewsletterCandidate) -> bool:
    if left.event_key and right.event_key and left.event_key == right.event_key:
        return True
    left_title_tokens = _event_tokens(left.title)
    right_title_tokens = _event_tokens(right.title)
    left_tokens = _event_tokens(f"{left.title} {left.summary}")
    right_tokens = _event_tokens(f"{right.title} {right.summary}")
    if not left_tokens or not right_tokens:
        return False
    left_numbers = {token for token in left_tokens if token.isdigit()}
    right_numbers = {token for token in right_tokens if token.isdigit()}
    if left_numbers and right_numbers and left_numbers != right_numbers:
        return False
    shared_tokens = left_tokens & right_tokens
    overlap_ratio = len(shared_tokens) / min(len(left_tokens), len(right_tokens))
    if overlap_ratio >= 0.58:
        return True
    strong_shared_tokens = {token for token in shared_tokens if len(token) >= 5 and not token.isdigit()}
    if strong_shared_tokens and overlap_ratio >= 0.34:
        return True
    title_strong_tokens = {token for token in left_title_tokens & right_title_tokens if len(token) >= 5 and not token.isdigit()}
    return bool(title_strong_tokens) and (
        len(left_title_tokens) <= 4 or len(right_title_tokens) <= 4 or len(shared_tokens) >= 2
    )


def _dedupe_newsletter_candidates(candidates: list[NewsletterCandidate], *, limit: int) -> list[NewsletterCandidate]:
    selected: list[NewsletterCandidate] = []
    seen_keys: set[str] = set()
    for candidate in sorted(candidates, key=lambda item: (item.score, item.published_at), reverse=True):
        direct_key = candidate.event_key or stable_hash(f"{candidate.url}:{candidate.title}", 16)
        if direct_key in seen_keys:
            continue
        if any(_same_news_event(candidate, previous) for previous in selected):
            continue
        selected.append(candidate)
        seen_keys.add(direct_key)
        if len(selected) >= limit:
            break
    return selected


def _portugal_angle(title: str, hint: str = "") -> str:
    text = f"{title} {hint}".lower()
    if any(word in text for word in ["regulation", "regul", "ai act", "gdpr", "privacy"]):
        return "Importa para equipas portuguesas que têm de decidir compliance antes de automatizar processos."
    if any(word in text for word in ["agent", "developer", "api", "open source", "model"]):
        return "Importa para builders e equipas de produto em Portugal que querem testar sem comprar hype."
    if any(word in text for word in ["enterprise", "business", "sales", "marketing", "work"]):
        return "Importa para PME e líderes operacionais que procuram produtividade com risco controlado."
    return "Importa para Portugal porque ajuda a separar avanço real de ruído internacional."


def _action_line(candidate: NewsletterCandidate) -> str:
    if candidate.kind == "owned_post":
        return "Aprofunda este tema na próxima semana: novo ângulo, exemplo português ou versão mais prática."
    if candidate.kind == "social_trend":
        return "Usa como leitura de formato: percebe o ângulo que gerou conversa, mas valida sempre na fonte primária."
    if "regul" in candidate.portugal_angle.lower() or "compliance" in candidate.portugal_angle.lower():
        return "Revê se isto altera políticas internas, contratos, dados pessoais ou processos de decisão automatizada."
    return "Guarda a fonte, avalia impacto no teu contexto e decide se merece teste, briefing interno ou simples monitorização."


def _ptia_post_url(post: FinalPost | None) -> str:
    base_url = site_public_base_url()
    if not post:
        return base_url
    if post.published_url and "ptia.pt" in post.published_url:
        return post.published_url
    if post.channel == "site":
        return f"{base_url}/{article_url_for_site_post(post).lstrip('/')}"
    return base_url


def _radar_candidate(signal: RadarSignal) -> NewsletterCandidate:
    return NewsletterCandidate(
        item_id=signal.signal_id,
        title=_clean(signal.title, "Sinal de IA"),
        source_name=_clean(signal.source_name, signal.source_type),
        url=signal.url,
        published_at=signal.published_at or signal.fetched_at,
        summary=_short(signal.summary or signal.notes, 300),
        why_it_matters=_short(signal.why_it_matters or signal.summary, 260),
        why_engaged=_short(signal.why_engaged or "Tema com potencial de leitura para decisores e equipas.", 220),
        portugal_angle=_short(_portugal_angle(signal.title, signal.topic_hint), 220),
        score=int(signal.engagement_score or 0),
        kind="news",
        event_key=stable_hash(f"news:{signal.url or signal.title}", 16),
    )


def _trend_candidate(signal: TrendSignal) -> NewsletterCandidate:
    score = int(signal.engagement_score or signal.score + signal.comments * 2)
    return NewsletterCandidate(
        item_id=signal.signal_id,
        title=_clean(signal.title, "Trend de IA"),
        source_name=_clean(signal.platform, "social"),
        url=signal.url or signal.discussion_url,
        published_at=signal.published_at or signal.fetched_at,
        summary=_short(signal.ptia_angle or signal.topic, 300),
        why_it_matters=_short(signal.ptia_angle or signal.why_it_worked, 260),
        why_engaged=_short(signal.why_it_worked or "Gerou conversa porque tocou numa dor, curiosidade ou promessa prática.", 220),
        portugal_angle=_short(_portugal_angle(signal.title, signal.topic), 220),
        score=score,
        kind="social_trend",
        event_key=stable_hash(f"trend:{signal.url or signal.discussion_url or signal.title}", 16),
    )


def _post_candidate(post: FinalPost) -> NewsletterCandidate:
    return NewsletterCandidate(
        item_id=post.post_id,
        title=_clean(post.title, "Curadoria PTIA"),
        source_name="PTIA",
        url=_ptia_post_url(post),
        published_at=post.scheduled_time or post.created_at,
        summary=_short(post.body, 300),
        why_it_matters=_short(post.body, 260),
        why_engaged="Já passou pelo funil editorial PTIA.",
        portugal_angle=_short(_portugal_angle(post.title, post.body), 220),
        score=70 if post.status == "published" else 55,
        kind="ptia_post",
        event_key=post.topic_id or stable_hash(f"post:{post.source_urls[0] if post.source_urls else post.title}", 16),
        image_url=public_image_url(post),
    )


def _performance_score(perf: ContentPerformance) -> int:
    return (
        int(perf.likes or 0)
        + int(perf.clicks or 0) * 2
        + int(perf.comments or 0) * 2
        + int(perf.shares or 0) * 3
        + int(perf.saves or 0) * 3
        + int(perf.followers_gained or 0) * 4
        + int(perf.site_views or 0)
        + int(perf.unique_visitors or 0) * 2
        + int(perf.newsletter_signups or 0) * 8
    )


def _performance_candidate(perf: ContentPerformance, final_posts: dict[str, FinalPost]) -> NewsletterCandidate:
    post = final_posts.get(perf.draft_id) or final_posts.get(perf.post_id)
    title = post.title if post else perf.topic
    body = post.body if post else perf.notes
    url = ""
    if post:
        url = _ptia_post_url(post)
    else:
        url = site_public_base_url()
    metrics = (
        f"Likes {perf.likes}, comentários {perf.comments}, shares {perf.shares}, "
        f"saves {perf.saves}, clicks {perf.clicks}."
    )
    return NewsletterCandidate(
        item_id=perf.performance_id,
        title=_clean(title, "Post PTIA com melhor performance"),
        source_name=_clean(perf.channel, "PTIA"),
        url=url,
        published_at=perf.published_at or perf.created_at,
        summary=_short(body or perf.notes or metrics, 300),
        why_it_matters=_short(
            f"Este tema entrou no Top 5 semanal da PTIA por performance real: {metrics}",
            260,
        ),
        why_engaged=_short(perf.notes or "Funcionou melhor do que a média da semana.", 220),
        portugal_angle=_short(_portugal_angle(title, body), 220),
        score=_performance_score(perf),
        kind="owned_post",
        event_key=(post.topic_id if post else stable_hash(f"performance:{url or title}", 16)),
        image_url=public_image_url(post) if post else "",
    )


def weekly_owned_post_candidates(
    performance: list[ContentPerformance],
    final_posts: list[FinalPost],
    *,
    limit: int = 5,
    days: int = 7,
) -> list[NewsletterCandidate]:
    posts_by_id = {post.post_id: post for post in final_posts}
    candidates = [
        _performance_candidate(perf, posts_by_id)
        for perf in performance
        if _recent_enough(perf.published_at or perf.created_at, days)
    ]
    candidates = [candidate for candidate in candidates if candidate.score > 0]
    return _dedupe_newsletter_candidates(candidates, limit=limit)


def sample_weekly_items() -> list[NewsletterCandidate]:
    samples = [
        (
            "Como uma PME portuguesa deve começar com IA sem comprar hype",
            "linkedin",
            184,
            "O post que melhor funcionou esta semana foi o mais prático: começar por workflows pequenos, medir tempo poupado e só depois escalar.",
            "Funcionou porque responde a uma dor concreta: muita gente quer usar IA, mas não sabe por onde começar sem cair em ferramentas soltas.",
            "Para PME portuguesas, a oportunidade está menos em trocar equipas por IA e mais em reduzir trabalho repetitivo em vendas, apoio ao cliente, operações e reporting.",
        ),
        (
            "AI agents: o que muda quando o software começa a executar tarefas",
            "instagram",
            151,
            "A audiência guardou e partilhou mais quando explicámos agents como uma mudança operacional, não como buzzword técnica.",
            "Agents tornam a IA mais útil porque ligam decisão, ferramentas e execução. Mas também aumentam risco, permissões e necessidade de validação.",
            "Empresas portuguesas devem começar por agents internos, com limites claros, logs e aprovação humana antes de tocar em clientes ou dados sensíveis.",
        ),
        (
            "AI Act: a pergunta que as empresas ainda não estão a fazer",
            "linkedin",
            127,
            "O tema regulatório teve bom engagement quando foi traduzido para decisões práticas: que sistemas usamos, com que dados e quem aprova.",
            "O AI Act não é só jurídico. Obriga equipas a mapear uso de IA, fornecedores, riscos e responsabilidades.",
            "PME e scaleups em Portugal devem criar um inventário simples de ferramentas de IA antes de pensarem em políticas longas.",
        ),
        (
            "A diferença entre automatizar trabalho e automatizar julgamento",
            "site",
            104,
            "Este foi o tema mais lido no site porque separa produtividade útil de decisões que exigem responsabilidade humana.",
            "Automatizar tarefas repetitivas é diferente de automatizar decisões sobre pessoas, crédito, saúde, emprego ou compliance.",
            "Em Portugal, este enquadramento ajuda equipas de gestão a decidir onde a IA pode entrar já e onde precisa de controlo adicional.",
        ),
        (
            "O stack mínimo de IA para uma equipa pequena",
            "instagram",
            96,
            "O formato checklist funcionou: poucos conceitos, ferramentas por função e uma recomendação de começar pequeno.",
            "Equipas pequenas não precisam de dez subscrições. Precisam de um modelo, um gestor de conhecimento, automações simples e regras de uso.",
            "Para empresas portuguesas com orçamento apertado, o ganho está em reduzir fragmentação antes de adicionar mais ferramentas.",
        ),
    ]
    return [
        NewsletterCandidate(
            item_id=f"sample_{index}",
            title=title,
            source_name=channel,
            url="https://ptia.pt",
            published_at=utc_now_iso(),
            summary=summary,
            why_it_matters=why,
            why_engaged=why,
            portugal_angle=portugal,
            score=score,
            kind="owned_post",
            event_key=f"sample_{index}",
        )
        for index, (title, channel, score, summary, why, portugal) in enumerate(samples, start=1)
    ]


def weekly_candidates(
    radar_signals: list[RadarSignal],
    trend_signals: list[TrendSignal],
    final_posts: list[FinalPost],
    *,
    limit: int = 5,
    days: int = 7,
) -> list[NewsletterCandidate]:
    candidates: list[NewsletterCandidate] = []
    for signal in radar_signals:
        if signal.status == "rejected" or not signal.url:
            continue
        if _recent_enough(signal.published_at or signal.fetched_at, days):
            candidates.append(_radar_candidate(signal))
    for signal in trend_signals:
        if signal.status == "rejected":
            continue
        if _recent_enough(signal.published_at or signal.fetched_at, days):
            candidates.append(_trend_candidate(signal))
    for post in final_posts:
        if post.status not in {"scheduled", "published"}:
            continue
        if _recent_enough(post.scheduled_time or post.created_at, days):
            candidates.append(_post_candidate(post))

    return _dedupe_newsletter_candidates(candidates, limit=limit)



def _ptia_article_url(item: NewsletterCandidate) -> str:
    return item.url if item.kind in {"ptia_post", "owned_post"} and item.url else "https://ptia.pt"


def _issue_html(
    issue_title: str,
    intro: str,
    items: list[NewsletterCandidate],
    debates: list[dict] | None = None,
    issue_date: date | None = None,
    selection_mode: str = "editorial",
) -> str:
    months = [
        "janeiro", "fevereiro", "marco", "abril", "maio", "junho",
        "julho", "agosto", "setembro", "outubro", "novembro", "dezembro",
    ]
    display_date = issue_date or datetime.now().date()
    short_date_label = f"{display_date.day:02d} {months[display_date.month - 1][:3]} {display_date.year}".upper()
    issue_number = f"W{display_date.isocalendar().week:02d}"
    lead = items[0]
    section_title = (
        "Os temas que a audi?ncia PTIA mostrou que vale aprofundar"
        if selection_mode == "performance"
        else "Os sinais que passaram o filtro editorial"
    )
    editor_layer = (
        "A camada editorial cruza fonte, relev?ncia e impacto para traduzir o ru?do da semana em leitura ?til para empresas, profissionais e builders."
    )
    method_body = (
        "Cada sinal ? escolhido pela relev?ncia, pela qualidade da fonte e pela utilidade pr?tica. "
        "Quando h? m?tricas suficientes, a performance real entra como filtro adicional, nunca como substituto do crit?rio editorial."
    )

    toc_rows = "".join(
        f"""
        <tr>
          <td width="34" valign="top" style="padding:9px 0;border-top:1px solid #E2DBCB;color:#BF4A2E;font-family:'IBM Plex Mono',Consolas,monospace;font-size:11px;font-weight:500;letter-spacing:.06em;">{index:02d}</td>
          <td valign="top" style="padding:9px 0;border-top:1px solid #E2DBCB;color:#1B1A17;font-family:Newsreader,Georgia,serif;font-size:16px;line-height:1.32;">{escape(item.title)}</td>
        </tr>
        """
        for index, item in enumerate(items, start=1)
    )
    hero_html = ""
    if lead.image_url:
        hero_html = f"""
        <tr><td colspan="2" style="padding:0 0 22px;">
          <img src="{escape(lead.image_url)}" width="554" alt="" style="display:block;width:100%;max-width:554px;height:auto;border:1px solid #E2DBCB;">
          <div style="margin-top:8px;color:#9E988C;font-family:'IBM Plex Mono',Consolas,monospace;font-size:9.5px;letter-spacing:.12em;text-transform:uppercase;">Imagem ? {escape(lead.source_name)}</div>
        </td></tr>
        """

    signal_rows = "".join(
        f"""
        <tr><td style="padding:32px 0;border-top:1px solid #E2DBCB;">
          <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="border-collapse:collapse;"><tr>
            <td valign="baseline" style="padding:0 0 11px;color:#6E6A62;font-family:'IBM Plex Mono',Consolas,monospace;font-size:10.5px;letter-spacing:.14em;text-transform:uppercase;">{escape(item.source_name)}</td>
            <td align="right" valign="baseline" style="padding:0 0 11px;color:#BF4A2E;font-family:Newsreader,Georgia,serif;font-size:15px;font-weight:500;letter-spacing:.04em;">N?&nbsp;{index:02d}</td>
          </tr></table>
          <h3 style="margin:0;color:#1B1A17;font-family:Newsreader,Georgia,serif;font-size:22px;font-weight:500;letter-spacing:-.008em;line-height:1.22;"><a href="{escape(_ptia_article_url(item))}" style="color:#1B1A17;text-decoration:none;">{escape(item.title)}</a></h3>
          <p style="margin:13px 0 0;color:#3A3833;font-family:Newsreader,Georgia,serif;font-size:16.5px;line-height:1.55;">{escape(item.summary)}</p>
          <p style="margin:18px 0 0;"><a href="{escape(_ptia_article_url(item))}" style="color:#1B1A17;font-family:'IBM Plex Mono',Consolas,monospace;font-size:11px;letter-spacing:.1em;text-decoration:none;text-transform:uppercase;border-bottom:1px solid #BF4A2E;padding-bottom:2px;">Ler mais <span style="color:#BF4A2E;">?</span></a></p>
        </td></tr>
        """
        for index, item in enumerate(items[1:], start=2)
    )

    return dedent(
        f"""\
        <!doctype html>
        <html lang="pt">
        <head>
          <meta charset="utf-8">
          <meta name="viewport" content="width=device-width,initial-scale=1">
          <meta name="color-scheme" content="light only">
          <link href="https://fonts.googleapis.com/css2?family=Newsreader:ital,opsz,wght@0,6..72,300..600;1,6..72,300..500&family=IBM+Plex+Mono:wght@400;500;600&display=swap" rel="stylesheet">
          <style>.preheader{{display:none!important;visibility:hidden;opacity:0;color:transparent;height:0;width:0;overflow:hidden;mso-hide:all}}@media only screen and (max-width:680px){{.ptia-shell{{width:100%!important}}.ptia-pad{{padding-left:24px!important;padding-right:24px!important}}.ptia-h1{{font-size:31px!important}}.ptia-lead-title{{font-size:28px!important}}}}</style>
        </head>
        <body style="margin:0;background:#E7E2D6;padding:0;-webkit-font-smoothing:antialiased;">
          <div class="preheader">{escape(intro)}</div>
          <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background:#E7E2D6;border-collapse:collapse;"><tr><td align="center" style="padding:56px 20px 72px;">
            <table role="presentation" width="660" cellspacing="0" cellpadding="0" class="ptia-shell" style="width:660px;max-width:660px;background:#F6F3EB;border:1px solid #E2DBCB;border-collapse:collapse;box-shadow:0 1px 50px rgba(27,26,23,.07);">
              <tr><td style="height:4px;background:#BF4A2E;font-size:0;line-height:0;">&nbsp;</td></tr>
              <tr><td class="ptia-pad" style="padding:30px 52px 22px;background:#F6F3EB;"><table role="presentation" width="100%" cellspacing="0" cellpadding="0"><tr><td valign="bottom" style="color:#1B1A17;font-family:Newsreader,Georgia,serif;font-size:34px;font-weight:500;letter-spacing:.14em;line-height:1;">PTIA</td><td align="right" valign="bottom" style="color:#6E6A62;font-family:'IBM Plex Mono',Consolas,monospace;font-size:10.5px;letter-spacing:.16em;line-height:1.7;text-transform:uppercase;"><span style="color:#BF4A2E;font-weight:500;">Weekly</span><br>Sexta-feira</td></tr></table><table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="margin-top:20px;border-top:1px solid #1B1A17;"><tr><td style="padding-top:13px;color:#6E6A62;font-family:'IBM Plex Mono',Consolas,monospace;font-size:10.5px;letter-spacing:.14em;text-transform:uppercase;">Edi??o N?&nbsp;{issue_number}</td><td align="center" style="padding-top:13px;color:#6E6A62;font-family:'IBM Plex Mono',Consolas,monospace;font-size:10.5px;letter-spacing:.14em;text-transform:uppercase;">Curadoria portuguesa de IA</td><td align="right" style="padding-top:13px;color:#6E6A62;font-family:'IBM Plex Mono',Consolas,monospace;font-size:10.5px;letter-spacing:.14em;text-transform:uppercase;">{escape(short_date_label)}</td></tr></table></td></tr>
              <tr><td class="ptia-pad" style="padding:22px 52px 38px;background:#F6F3EB;"><p style="margin:0;color:#BF4A2E;font-family:'IBM Plex Mono',Consolas,monospace;font-size:11px;font-weight:500;letter-spacing:.18em;text-transform:uppercase;">Carta do editor</p><h1 class="ptia-h1" style="margin:16px 0 0;color:#1B1A17;font-family:Newsreader,Georgia,serif;font-size:33px;font-weight:500;letter-spacing:-.012em;line-height:1.14;">{escape(issue_title)}</h1><p style="margin:20px 0 0;color:#3A3833;font-family:Newsreader,Georgia,serif;font-size:17.5px;line-height:1.62;">{escape(intro)}</p><p style="margin:14px 0 0;color:#3A3833;font-family:Newsreader,Georgia,serif;font-size:17.5px;line-height:1.62;">{escape(editor_layer)}</p><p style="margin:22px 0 0;color:#9E988C;font-family:'IBM Plex Mono',Consolas,monospace;font-size:10.5px;letter-spacing:.14em;text-transform:uppercase;">Editor ? <span style="color:#1B1A17;">Jo?o Ferreira</span></p></td></tr>
              <tr><td class="ptia-pad" style="padding:0 52px;background:#F6F3EB;"><table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background:#FBF9F3;border:1px solid #E2DBCB;"><tr><td style="padding:26px 28px;"><p style="margin:0 0 16px;color:#6E6A62;font-family:'IBM Plex Mono',Consolas,monospace;font-size:11px;font-weight:500;letter-spacing:.18em;text-transform:uppercase;">Nesta edi??o</p><table role="presentation" width="100%" cellspacing="0" cellpadding="0">{toc_rows}</table></td></tr></table></td></tr>
              <tr><td class="ptia-pad" style="padding:44px 52px 0;background:#F6F3EB;"><p style="margin:0;color:#BF4A2E;font-family:'IBM Plex Mono',Consolas,monospace;font-size:11px;font-weight:500;letter-spacing:.18em;text-transform:uppercase;">Top 5 sinais ? A semana em IA, lida de Portugal</p><h2 style="margin:12px 0 0;color:#1B1A17;font-family:Newsreader,Georgia,serif;font-size:24px;font-weight:500;letter-spacing:-.01em;line-height:1.2;">{escape(section_title)}</h2></td></tr>
              <tr><td class="ptia-pad" style="padding:30px 52px 36px;background:#F6F3EB;"><table role="presentation" width="100%" cellspacing="0" cellpadding="0"><tr><td valign="baseline" style="padding:0 0 16px;color:#6E6A62;font-family:'IBM Plex Mono',Consolas,monospace;font-size:10.5px;letter-spacing:.14em;text-transform:uppercase;">{escape(lead.source_name)}</td><td align="right" valign="baseline" style="padding:0 0 16px;color:#BF4A2E;font-family:Newsreader,Georgia,serif;font-size:15px;font-weight:500;letter-spacing:.04em;">N?&nbsp;01</td></tr>{hero_html}<tr><td colspan="2"><h3 class="ptia-lead-title" style="margin:0;color:#1B1A17;font-family:Newsreader,Georgia,serif;font-size:30px;font-weight:500;letter-spacing:-.012em;line-height:1.16;"><a href="{escape(_ptia_article_url(lead))}" style="color:#1B1A17;text-decoration:none;">{escape(lead.title)}</a></h3><p style="margin:16px 0 0;color:#3A3833;font-family:Newsreader,Georgia,serif;font-size:18px;line-height:1.58;">{escape(lead.summary)}</p><p style="margin:20px 0 0;"><a href="{escape(_ptia_article_url(lead))}" style="color:#1B1A17;font-family:'IBM Plex Mono',Consolas,monospace;font-size:11px;letter-spacing:.1em;text-decoration:none;text-transform:uppercase;border-bottom:1px solid #BF4A2E;padding-bottom:2px;">Ler mais <span style="color:#BF4A2E;">?</span></a></p></td></tr></table></td></tr>
              <tr><td class="ptia-pad" style="padding:0 52px 8px;background:#F6F3EB;"><table role="presentation" width="100%" cellspacing="0" cellpadding="0">{signal_rows}</table></td></tr>
              <tr><td class="ptia-pad" style="padding:30px 52px 44px;background:#F6F3EB;"><table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="border-top:1px solid #1B1A17;"><tr><td style="padding-top:30px;"><p style="margin:0;color:#1B1A17;font-family:Newsreader,Georgia,serif;font-size:27px;font-style:italic;font-weight:400;letter-spacing:-.01em;line-height:1.28;">?A newsletter n?o ? uma segunda timeline. ? a camada que transforma sinais dispersos em leitura editorial.?</p><p style="margin:18px 0 0;color:#9E988C;font-family:'IBM Plex Mono',Consolas,monospace;font-size:10px;letter-spacing:.16em;text-transform:uppercase;">Sinal vs. ru?do</p></td></tr></table></td></tr>
              <tr><td class="ptia-pad" style="padding:0 52px;background:#F6F3EB;"><table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background:#1B1A17;"><tr><td style="padding:36px 34px;"><p style="margin:0;color:#BF4A2E;font-family:'IBM Plex Mono',Consolas,monospace;font-size:10.5px;font-weight:500;letter-spacing:.18em;text-transform:uppercase;">M?todo ? C?mara PTIA</p><h3 style="margin:14px 0 0;color:#F6F3EB;font-family:Newsreader,Georgia,serif;font-size:23px;font-weight:500;letter-spacing:-.008em;line-height:1.25;">O que o radar editorial considera priorit?rio</h3><p style="margin:15px 0 0;color:#B7B2A7;font-family:Newsreader,Georgia,serif;font-size:16px;line-height:1.6;">{escape(method_body)}</p></td></tr></table></td></tr>
              <tr><td align="center" class="ptia-pad" style="padding:40px 52px 44px;background:#F6F3EB;"><p style="margin:0;color:#BF4A2E;font-family:'IBM Plex Mono',Consolas,monospace;font-size:10.5px;font-weight:500;letter-spacing:.18em;text-transform:uppercase;">Continua no PTIA.pt</p><p style="margin:14px auto 22px;max-width:380px;color:#1B1A17;font-family:Newsreader,Georgia,serif;font-size:19px;line-height:1.42;">L? a edi??o completa e guarda os sinais que interessam ? tua equipa.</p><a href="https://ptia.pt" style="display:inline-block;background:#1B1A17;color:#F6F3EB;font-family:'IBM Plex Mono',Consolas,monospace;font-size:12px;letter-spacing:.08em;text-decoration:none;text-transform:uppercase;padding:14px 26px;">Abrir PTIA.pt ?</a></td></tr>
              <tr><td class="ptia-pad" style="padding:30px 52px 40px;background:#F6F3EB;border-top:1px solid #1B1A17;"><table role="presentation" width="100%" cellspacing="0" cellpadding="0"><tr><td valign="top"><div style="color:#1B1A17;font-family:Newsreader,Georgia,serif;font-size:22px;font-weight:500;letter-spacing:.12em;line-height:1;">PTIA</div><div style="margin-top:5px;color:#6E6A62;font-family:Newsreader,Georgia,serif;font-size:14px;font-style:italic;line-height:1.4;">Curadoria portuguesa de Intelig?ncia Artificial.</div></td><td align="right" valign="top" style="color:#6E6A62;font-family:'IBM Plex Mono',Consolas,monospace;font-size:10px;letter-spacing:.12em;line-height:1.9;text-transform:uppercase;"><a href="https://ptia.pt" style="color:#6E6A62;text-decoration:none;">PTIA.pt</a><br><a href="https://ptia.pt/#newsletter" style="color:#6E6A62;text-decoration:none;">Weekly</a><br><a href="https://www.linkedin.com/company/116070074" style="color:#6E6A62;text-decoration:none;">LinkedIn</a></td></tr></table><p style="margin:26px 0 0;max-width:460px;color:#9E988C;font-family:Newsreader,Georgia,serif;font-size:12px;line-height:1.6;">Recebes este email porque subscreveste a PTIA Weekly. Podes <a href="{{{{ unsubscribe }}}}" style="color:#1B1A17;text-decoration:underline;">cancelar a subscri??o</a> ou gerir as tuas prefer?ncias a qualquer momento.</p><p style="margin:16px 0 0;color:#9E988C;font-family:'IBM Plex Mono',Consolas,monospace;font-size:9.5px;letter-spacing:.12em;text-transform:uppercase;">PTIA.pt ? Lisboa, Portugal ? 2026</p></td></tr>
            </table>
          </td></tr></table>
        </body>
        </html>
        """
    )


def _issue_text(issue_title: str, intro: str, items: list[NewsletterCandidate], debates: list[dict] = None) -> str:
    lines = [f"PTIA Weekly - {issue_title}", "", intro, ""]
    for index, item in enumerate(items, start=1):
        lines.extend(
            [
                f"{index}. {item.title}",
                f"Fonte: {item.source_name} - {item.url}",
                item.summary,
                item.why_it_matters,
                _action_line(item),
                "",
            ]
        )
    if debates:
        lines.extend([
            "",
            "DEBATE DA SEMANA - PTIA NO LINKEDIN",
            "Comentamos e discutimos os avanços de IA com decisores nas redes:",
            ""
        ])
        for index, d in enumerate(debates, start=1):
            profile = d.get("profile_name", "Decisor")
            post_snippet = _short(d.get("post_body", ""), 140)
            comment = d.get("comment_text", "")
            url = d.get("post_url", "")
            lines.extend([
                f"[{index}] Discussão com {profile}",
                f"Post original: \"{post_snippet}\"",
                f"Resposta PTIA: \"{comment}\"",
                f"Link: {url}",
                ""
            ])

    lines.extend([
        "Sinal vs. Ruído: se não muda uma decisão, fica fora do radar PTIA.",
        "",
        "Para cancelar a subscrição: {{ unsubscribe }}",
        "Versão web: {{ mirror }}",
    ])
    return "\n".join(lines).strip()


def _load_recent_debates(
    comments_path: Path,
    *,
    limit: int = 3,
    days: int = 7,
    now: datetime | None = None,
) -> list[dict]:
    if not comments_path.exists() or limit <= 0:
        return []
    cutoff = (now or datetime.now(timezone.utc)) - timedelta(days=days)
    debates = []
    for line in comments_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if record.get("status") != "commented":
            continue
        if not _clean(record.get("comment_text", "")):
            continue
        if _parse_date(record.get("created_at", "")) < cutoff:
            continue
        debates.append(record)
    debates.sort(key=lambda record: _parse_date(record.get("created_at", "")), reverse=True)
    return debates[:limit]


def generate_weekly_issue(
    path: Path,
    *,
    radar_signals: list[RadarSignal],
    trend_signals: list[TrendSignal],
    final_posts: list[FinalPost],
    performance: list[ContentPerformance] | None = None,
    limit: int = 5,
    status: str = "draft",
    send_at: str = "",
    issue_date: date | None = None,
    debate_limit: int = 3,
) -> NewsletterIssue:
    if status not in NEWSLETTER_STATUSES:
        raise ValueError(f"Invalid newsletter status: {status}")
    items = weekly_owned_post_candidates(performance or [], final_posts, limit=limit)
    selection_mode = "performance" if items else "editorial"
    if not items:
        items = weekly_candidates(radar_signals, trend_signals, final_posts, limit=limit)
    if not items:
        raise ValueError("Ainda não há posts com métricas suficientes para gerar a newsletter.")
        
    comments_path = Path(path).parent / "linkedin_comments.jsonl"
    debates = _load_recent_debates(comments_path, limit=debate_limit)

    count = len(items)
    if selection_mode == "performance":
        title = f"Os {count} sinais PTIA com mais engagement esta semana"
        subject = f"PTIA Weekly: os {count} temas que mais mexeram esta semana"
        preheader = "Ranking editorial a partir dos nossos posts: saves, shares, comentários, clicks e leitura para Portugal."
        intro = (
            "Esta edição é construída a partir dos posts PTIA com melhor tracking da semana. "
            "Não é uma lista do que fez mais barulho lá fora: é o que a nossa audiência mostrou que vale a pena aprofundar."
        )
    else:
        title = f"Os {count} sinais de IA que merecem atenção esta semana"
        subject = f"PTIA Weekly: {count} sinais de IA para ler esta semana"
        preheader = "Curadoria editorial PTIA: fontes, impacto prático e leitura para Portugal."
        intro = (
            "Esta edição reúne os sinais selecionados pelo radar e pelo processo editorial PTIA. "
            "Foram escolhidos pela qualidade da fonte, relevância e utilidade prática para Portugal."
        )
    issue = NewsletterIssue(
        issue_id=f"weekly_{stable_hash(utc_now_iso() + ':' + '|'.join(item.item_id for item in items), 18)}",
        title=title,
        subject=subject,
        preheader=preheader,
        intro=intro,
        html=_issue_html(
            title,
            intro,
            items,
            debates=debates,
            issue_date=issue_date,
            selection_mode=selection_mode,
        ),
        text=_issue_text(title, intro, items, debates=debates),
        item_ids=[item.item_id for item in items],
        selection_mode=selection_mode,
        generator_version=NEWSLETTER_GENERATOR_VERSION,
        status=status,
        send_at=send_at,
    )
    append_jsonl(path, [issue])
    return issue


def generate_sample_issue() -> NewsletterIssue:
    items = sample_weekly_items()
    title = "Os 5 sinais PTIA com mais engagement esta semana"
    subject = "PTIA Weekly: os 5 temas que mais mexeram esta semana"
    preheader = "Exemplo de ranking semanal: os posts PTIA com melhor tracking e a leitura para Portugal."
    intro = (
        "Exemplo de edição semanal. No produto real, estes cinco blocos vêm dos nossos posts "
        "com melhor tracking: saves, shares, comentários, clicks, likes e followers."
    )
    return NewsletterIssue(
        issue_id="weekly_sample",
        title=title,
        subject=subject,
        preheader=preheader,
        intro=intro,
        html=_issue_html(title, intro, items, debates=[], selection_mode="performance"),
        text=_issue_text(title, intro, items, debates=[]),
        item_ids=[item.item_id for item in items],
        selection_mode="performance",
        generator_version=NEWSLETTER_GENERATOR_VERSION,
        status="sample",
    )


def update_newsletter_status(
    path: Path,
    issue_id: str,
    status: str,
    send_at: str = "",
) -> NewsletterIssue:
    if status not in NEWSLETTER_STATUSES:
        raise ValueError(f"Invalid newsletter status: {status}")
    issues = load_newsletter_issues(path)
    for issue in issues:
        if issue.issue_id != issue_id:
            continue
        issue.status = status
        if send_at:
            issue.send_at = send_at
        write_jsonl(path, issues)
        return issue
    raise ValueError(f"Newsletter issue not found: {issue_id}")


def update_newsletter_delivery(
    path: Path,
    issue_id: str,
    *,
    status: str | None = None,
    send_at: str | None = None,
    delivery_provider: str | None = None,
    provider_campaign_id: str | None = None,
    provider_status: str | None = None,
    delivery_error: str | None = None,
) -> NewsletterIssue:
    if status is not None and status not in NEWSLETTER_STATUSES:
        raise ValueError(f"Invalid newsletter status: {status}")
    issues = load_newsletter_issues(path)
    for issue in issues:
        if issue.issue_id != issue_id:
            continue
        if status is not None:
            issue.status = status
        if send_at is not None:
            issue.send_at = send_at
        if delivery_provider is not None:
            issue.delivery_provider = delivery_provider
        if provider_campaign_id is not None:
            issue.provider_campaign_id = provider_campaign_id
        if provider_status is not None:
            issue.provider_status = provider_status
        if delivery_error is not None:
            issue.delivery_error = delivery_error
        write_jsonl(path, issues)
        return issue
    raise ValueError(f"Newsletter issue not found: {issue_id}")
