from __future__ import annotations

import json

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
from ptia_engine.storage import append_jsonl, load_newsletter_issues, write_jsonl


NEWSLETTER_STATUSES = {"draft", "approved", "scheduled", "sent", "rejected", "failed"}
NEWSLETTER_GENERATOR_VERSION = "2"


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
    )


def _post_candidate(post: FinalPost) -> NewsletterCandidate:
    return NewsletterCandidate(
        item_id=post.post_id,
        title=_clean(post.title, "Curadoria PTIA"),
        source_name="PTIA",
        url=post.source_urls[0] if post.source_urls else post.published_url,
        published_at=post.scheduled_time or post.created_at,
        summary=_short(post.body, 300),
        why_it_matters=_short(post.body, 260),
        why_engaged="Já passou pelo funil editorial PTIA.",
        portugal_angle=_short(_portugal_angle(post.title, post.body), 220),
        score=70 if post.status == "published" else 55,
        kind="ptia_post",
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
        url = post.published_url or perf.post_id or (post.source_urls[0] if post.source_urls else "")
    else:
        url = perf.post_id
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
    return sorted(candidates, key=lambda item: (item.score, item.published_at), reverse=True)[:limit]


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

    deduped: dict[str, NewsletterCandidate] = {}
    for candidate in candidates:
        key = stable_hash(f"{candidate.url}:{candidate.title}", 16)
        existing = deduped.get(key)
        if not existing or candidate.score > existing.score:
            deduped[key] = candidate
    return sorted(deduped.values(), key=lambda item: (item.score, item.published_at), reverse=True)[:limit]


def _issue_html(
    issue_title: str,
    intro: str,
    items: list[NewsletterCandidate],
    debates: list[dict] | None = None,
    issue_date: date | None = None,
    selection_mode: str = "editorial",
) -> str:
    months = [
        "janeiro",
        "fevereiro",
        "marco",
        "abril",
        "maio",
        "junho",
        "julho",
        "agosto",
        "setembro",
        "outubro",
        "novembro",
        "dezembro",
    ]
    display_date = issue_date or datetime.now().date()
    issue_date_label = f"{display_date.day} {months[display_date.month - 1]} {display_date.year}"
    logo_url = "https://ptia.pt/assets/ptia-wordmark-navy-transparent.png"
    count = len(items)
    total_score = sum(item.score for item in items)
    lead = items[0]
    performance_backed = selection_mode == "performance"
    section_title = (
        "O que a audiencia PTIA mostrou que vale aprofundar."
        if performance_backed
        else "Os sinais que passaram o filtro editorial PTIA esta semana."
    )
    editor_layer = (
        "A camada PTIA pega no que gerou sinal real e traduz isso em leitura pratica para Portugal: "
        "empresas, profissionais e builders."
        if performance_backed
        else "A camada PTIA cruza relevancia, fonte e impacto pratico e traduz os sinais em leitura "
        "util para Portugal: empresas, profissionais e builders."
    )
    closing_quote = (
        "A newsletter nao e uma segunda timeline. E a camada que transforma engagement em leitura editorial."
        if performance_backed
        else "A newsletter nao e uma segunda timeline. E a camada que transforma sinais dispersos em leitura editorial."
    )
    learning_title = (
        "O que aprendemos com os posts que funcionaram."
        if performance_backed
        else "O que o radar editorial considera prioritario."
    )
    learning_body = (
        "Na semana seguinte, estes sinais voltam ao radar como vantagem editorial: temas a repetir, "
        "formatos a melhorar e perguntas mais fortes para LinkedIn, Instagram e site."
        if performance_backed
        else "Estes sinais foram escolhidos pela sua relevancia, qualidade da fonte e utilidade pratica. "
        "Quando existirem metricas suficientes, a performance real passa a complementar este filtro."
    )
    story_rows = []
    for index, item in enumerate(items[1:], start=2):
        story_rows.append(
            f"""
            <tr>
              <td style="padding:28px 40px;border-bottom:1px solid #14110C14;background:#FAF6EC;">
                <p style="margin:0 0 8px;color:#7A715E;font:500 9px 'JetBrains Mono',ui-monospace,monospace;letter-spacing:.13em;text-transform:uppercase;">
                  <span style="color:#C44419;font:400 22px Georgia,serif;font-style:italic;letter-spacing:0;">Nº{index:02d}</span>
                  &nbsp;&nbsp;{escape(item.source_name)} · score {item.score}
                </p>
                <h3 style="margin:0 0 10px;color:#14110C;font:400 23px Georgia,serif;line-height:1.18;letter-spacing:-.012em;">
                  <a href="{escape(item.url or 'https://ptia.pt')}" style="color:#14110C;text-decoration:none;">{escape(item.title)}</a>
                </h3>
                <p style="margin:0 0 12px;color:#3A332A;font:400 15px Georgia,serif;line-height:1.55;">{escape(item.summary)}</p>
                <p style="margin:0;color:#3A332A;font:400 14px Arial,sans-serif;line-height:1.5;">
                  <span style="display:inline-block;margin-right:8px;padding:3px 7px;background:#C4441933;color:#C44419;font:700 9px Arial,sans-serif;letter-spacing:.08em;">PT</span>
                  {escape(item.portugal_angle)}
                </p>
                <p style="margin:14px 0 0;"><a href="{escape(item.url or 'https://ptia.pt')}" style="color:#C44419;font:700 13px Arial,sans-serif;text-decoration:none;">Fonte original</a></p>
              </td>
            </tr>
            """
        )
    debate_rows = []
    if debates:
        debate_cards = []
        for d in debates:
            profile = escape(d.get("profile_name", "Decisor"))
            post_snippet = escape(_short(d.get("post_body", ""), 160))
            comment = escape(d.get("comment_text", ""))
            url = escape(d.get("post_url", "https://ptia.pt"))
            
            debate_cards.append(f"""
            <tr>
              <td style="padding:18px 40px;background:#FAF6EC;">
                <div style="padding:22px;background:#FAF6EC;border-left:4px solid #C44419;border-top:1px solid #14110C14;border-right:1px solid #14110C14;border-bottom:1px solid #14110C14;border-radius:0 6px 6px 0;">
                  <p style="margin:0 0 8px;color:#7A715E;font:700 10px Arial,sans-serif;letter-spacing:.08em;text-transform:uppercase;">Discussão com {profile}</p>
                  <p style="margin:0 0 14px;color:#3A332A;font:italic 14px Georgia,serif;line-height:1.48;">
                    "{post_snippet}"
                  </p>
                  <div style="background:#FAF6EC;border:1px solid #14110C14;padding:16px 20px;border-radius:8px;">
                    <p style="margin:0 0 4px;color:#C44419;font:700 9px Arial,sans-serif;letter-spacing:.08em;text-transform:uppercase;">Resposta PTIA</p>
                    <p style="margin:0;color:#14110C;font:400 14px Georgia,serif;line-height:1.5;">{comment}</p>
                  </div>
                  <p style="margin:12px 0 0;"><a href="{url}" style="color:#C44419;font:700 12px Arial,sans-serif;text-decoration:none;">Ver debate no LinkedIn &rarr;</a></p>
                </div>
              </td>
            </tr>
            """)
            
        debate_rows.append(f"""
        <tr>
          <td class="ptia-pad" style="padding:40px 40px 10px;background:#FAF6EC;border-top:1px solid #14110C26;">
            <p style="margin:0 0 8px;color:#C44419;font:700 10px Arial,sans-serif;letter-spacing:.16em;text-transform:uppercase;">Debate da Semana · PTIA no LinkedIn</p>
            <h2 style="margin:0;color:#14110C;font:400 31px Georgia,serif;line-height:1.12;letter-spacing:-.016em;">A nossa presença nas caixas de comentários estratégicas.</h2>
          </td>
        </tr>
        {"".join(debate_cards)}
        """)

    return dedent(
        f"""\
        <!doctype html>
        <html lang="pt">
        <head>
          <meta charset="utf-8">
          <meta name="viewport" content="width=device-width,initial-scale=1">
          <meta name="color-scheme" content="light only">
          <style>
            .preheader {{
              display:none !important; visibility:hidden; opacity:0; color:transparent;
              height:0; width:0; overflow:hidden; mso-hide:all;
            }}
            @media only screen and (max-width: 640px) {{
              .ptia-shell {{ width:100% !important; }}
              .ptia-pad {{ padding-left:22px !important; padding-right:22px !important; }}
              .ptia-h1 {{ font-size:34px !important; }}
              .ptia-lead-title {{ font-size:28px !important; }}
            }}
          </style>
        </head>
        <body style="margin:0;background:#F3EEE2;padding:0;">
          <div class="preheader">{escape(intro)}</div>
          <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background:#F3EEE2;">
            <tr>
              <td align="center" style="padding:32px 14px;">
                <table role="presentation" width="640" cellspacing="0" cellpadding="0" class="ptia-shell" style="max-width:640px;width:640px;background:#FAF6EC;border-collapse:collapse;border:1px solid #D9C8AA;">
                  <tr>
                    <td class="ptia-pad" style="padding:34px 40px 26px;background:#FAF6EC;border-bottom:1px solid #14110C26;">
                      <table role="presentation" width="100%" cellspacing="0" cellpadding="0">
                        <tr>
                          <td valign="middle">
                            <img src="{logo_url}" width="132" alt="PTIA" style="display:block;border:0;width:132px;height:auto;">
                          </td>
                          <td align="right" valign="middle" style="color:#7A715E;font:500 10px Arial,sans-serif;letter-spacing:.12em;text-transform:uppercase;line-height:1.6;">
                            Weekly · Sexta-feira<br>
                            <span style="color:#14110C;">{escape(issue_date_label)}</span>
                          </td>
                        </tr>
                      </table>
                    </td>
                  </tr>
                  <tr>
                    <td class="ptia-pad" style="padding:14px 40px;background:#F3EEE2;border-bottom:1px solid #14110C14;">
                      <table role="presentation" width="100%" cellspacing="0" cellpadding="0">
                        <tr>
                          <td style="color:#7A715E;font:700 10px Arial,sans-serif;letter-spacing:.11em;text-transform:uppercase;">Lisboa · edicao semanal</td>
                          <td align="right" style="color:#C44419;font:700 10px Arial,sans-serif;letter-spacing:.11em;text-transform:uppercase;">Top {count} · score {total_score} · leitura PTIA</td>
                        </tr>
                      </table>
                    </td>
                  </tr>
                  <tr>
                    <td class="ptia-pad" style="padding:44px 40px 34px;background:#FAF6EC;">
                      <p style="margin:0 0 16px;color:#C44419;font:700 10px Arial,sans-serif;letter-spacing:.16em;text-transform:uppercase;">Carta do editor</p>
                      <h1 class="ptia-h1" style="margin:0 0 18px;color:#14110C;font:400 44px Georgia,serif;line-height:1.06;letter-spacing:-.024em;">{escape(issue_title)}</h1>
                      <p style="margin:0 0 14px;color:#3A332A;font:400 17px Georgia,serif;line-height:1.58;">{escape(intro)}</p>
                      <p style="margin:0;color:#3A332A;font:400 17px Georgia,serif;line-height:1.58;">{escape(editor_layer)}</p>
                      <p style="margin:22px 0 0;color:#7A715E;font:700 10px Arial,sans-serif;letter-spacing:.13em;text-transform:uppercase;">Editor <span style="color:#14110C;font:400 17px Georgia,serif;font-style:italic;letter-spacing:0;text-transform:none;">Joao Ferreira</span></p>
                    </td>
                  </tr>
                  <tr>
                    <td style="padding:0;background:#FAF6EC;border-top:1px solid #14110C26;border-bottom:1px solid #14110C26;">
                      <table role="presentation" width="100%" cellspacing="0" cellpadding="0">
                        <tr>
                          <td width="25%" align="center" style="padding:18px 6px;border-right:1px solid #14110C14;"><div style="color:#14110C;font:400 30px Georgia,serif;">{count}</div><div style="color:#7A715E;font:700 9px Arial,sans-serif;letter-spacing:.13em;text-transform:uppercase;">posts</div></td>
                          <td width="25%" align="center" style="padding:18px 6px;border-right:1px solid #14110C14;"><div style="color:#14110C;font:400 30px Georgia,serif;">7</div><div style="color:#7A715E;font:700 9px Arial,sans-serif;letter-spacing:.13em;text-transform:uppercase;">dias</div></td>
                          <td width="25%" align="center" style="padding:18px 6px;border-right:1px solid #14110C14;"><div style="color:#14110C;font:400 30px Georgia,serif;">{total_score}</div><div style="color:#7A715E;font:700 9px Arial,sans-serif;letter-spacing:.13em;text-transform:uppercase;">score</div></td>
                          <td width="25%" align="center" style="padding:18px 6px;"><div style="color:#14110C;font:400 30px Georgia,serif;">9</div><div style="color:#7A715E;font:700 9px Arial,sans-serif;letter-spacing:.13em;text-transform:uppercase;">min</div></td>
                        </tr>
                      </table>
                    </td>
                  </tr>
                  <tr>
                    <td class="ptia-pad" style="padding:38px 40px 18px;background:#FAF6EC;">
                      <p style="margin:0 0 8px;color:#C44419;font:700 10px Arial,sans-serif;letter-spacing:.16em;text-transform:uppercase;">Top 5 sinais · a semana em IA, lida em Portugal</p>
                      <h2 style="margin:0;color:#14110C;font:400 31px Georgia,serif;line-height:1.12;letter-spacing:-.016em;">{escape(section_title)}</h2>
                    </td>
                  </tr>
                  <tr>
                    <td class="ptia-pad" style="padding:22px 40px 36px;background:#FAF6EC;border-bottom:1px solid #14110C14;">
                      <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background:#14110C;border-radius:4px;margin:0 0 22px;">
                        <tr>
                          <td height="200" style="height:200px;padding:0;background:#14110C;background-image:radial-gradient(circle at 25% 30%, #C44419 0, transparent 34%), radial-gradient(circle at 80% 65%, #1A3A6B 0, transparent 42%);border-radius:4px;">
                            <table role="presentation" width="100%" height="200" cellspacing="0" cellpadding="0">
                              <tr>
                                <td align="center" valign="middle" style="color:#FAF6EC;font:400 64px Georgia,serif;letter-spacing:-.06em;">PTIA</td>
                                <td align="right" valign="top" style="padding:22px;color:#FAF6EC;font:400 28px Georgia,serif;font-style:italic;">Nº01</td>
                              </tr>
                            </table>
                          </td>
                        </tr>
                      </table>
                      <p style="margin:0 0 9px;color:#7A715E;font:700 9px Arial,sans-serif;letter-spacing:.13em;text-transform:uppercase;"><span style="color:#C44419;">Lead</span> · {escape(lead.source_name)} · score {lead.score}</p>
                      <h3 class="ptia-lead-title" style="margin:0 0 12px;color:#14110C;font:400 32px Georgia,serif;line-height:1.16;letter-spacing:-.018em;"><a href="{escape(lead.url or 'https://ptia.pt')}" style="color:#14110C;text-decoration:none;">{escape(lead.title)}</a></h3>
                      <p style="margin:0 0 14px;color:#3A332A;font:400 16px Georgia,serif;line-height:1.56;">{escape(lead.summary)}</p>
                      <p style="margin:0 0 16px;color:#3A332A;font:400 15px Arial,sans-serif;line-height:1.5;"><span style="display:inline-block;margin-right:8px;padding:3px 7px;background:#C4441933;color:#C44419;font:700 9px Arial,sans-serif;letter-spacing:.08em;">PT</span>{escape(lead.portugal_angle)}</p>
                      <p style="margin:0;"><a href="{escape(lead.url or 'https://ptia.pt')}" style="color:#C44419;font:700 14px Arial,sans-serif;text-decoration:none;">Fonte original</a></p>
                    </td>
                  </tr>
                  {''.join(story_rows)}
                  {''.join(debate_rows)}
                  <tr>
                    <td class="ptia-pad" style="padding:44px 40px;background:#F3EEE2;border-top:1px solid #14110C26;border-bottom:1px solid #14110C26;">
                      <p style="margin:0 0 10px;color:#C44419;font:400 56px Georgia,serif;font-style:italic;line-height:.8;">"</p>
                      <p style="margin:0;color:#14110C;font:400 26px Georgia,serif;line-height:1.25;">{escape(closing_quote)}</p>
                      <p style="margin:18px 0 0;color:#7A715E;font:700 10px Arial,sans-serif;letter-spacing:.12em;text-transform:uppercase;">Sinal vs. ruido · leitura editorial da semana</p>
                    </td>
                  </tr>
                  <tr>
                    <td class="ptia-pad" style="padding:36px 40px;background:#FAF6EC;">
                      <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background:#14110C;border-radius:6px;">
                        <tr>
                          <td style="padding:26px;">
                            <p style="margin:0 0 10px;color:#F0764A;font:700 10px Arial,sans-serif;letter-spacing:.14em;text-transform:uppercase;">Camada PTIA</p>
                            <h4 style="margin:0 0 12px;color:#FAF6EC;font:400 28px Georgia,serif;line-height:1.12;">{escape(learning_title)}</h4>
                            <p style="margin:0;color:#FAF6ECCC;font:400 15px Georgia,serif;line-height:1.58;">{escape(learning_body)}</p>
                          </td>
                        </tr>
                      </table>
                    </td>
                  </tr>
                  <tr>
                    <td align="center" class="ptia-pad" style="padding:50px 40px;background:#FAF6EC;border-top:1px solid #14110C14;">
                      <p style="margin:0 0 10px;color:#7A715E;font:700 10px Arial,sans-serif;letter-spacing:.13em;text-transform:uppercase;">Continua no PTIA.pt</p>
                      <h3 style="margin:0 0 22px;color:#14110C;font:400 28px Georgia,serif;line-height:1.18;">Le a edicao completa e guarda os sinais que interessam para a tua equipa.</h3>
                      <a href="https://ptia.pt" style="display:inline-block;background:#14110C;color:#FAF6EC;text-decoration:none;border-radius:999px;padding:14px 26px;font:700 14px Arial,sans-serif;">Abrir PTIA.pt</a>
                    </td>
                  </tr>
                  <tr>
                    <td class="ptia-pad" style="padding:34px 40px;background:#ECE5D3;color:#7A715E;">
                      <table role="presentation" width="100%" cellspacing="0" cellpadding="0">
                        <tr>
                          <td valign="top">
                            <img src="{logo_url}" width="92" alt="PTIA" style="display:block;border:0;width:92px;height:auto;margin-bottom:10px;">
                            <p style="margin:0;color:#3A332A;font:400 14px Georgia,serif;font-style:italic;">Curadoria portuguesa de Inteligencia Artificial.</p>
                          </td>
                          <td align="right" valign="top" style="font:700 10px Arial,sans-serif;letter-spacing:.11em;text-transform:uppercase;line-height:1.9;">
                            <a href="https://ptia.pt" style="color:#14110C;text-decoration:none;">Site</a><br>
                            <a href="https://ptia.pt/#newsletter" style="color:#14110C;text-decoration:none;">Newsletter</a><br>
                            <a href="https://www.linkedin.com/company/116070074" style="color:#14110C;text-decoration:none;">LinkedIn</a>
                          </td>
                        </tr>
                      </table>
                      <p style="margin:24px 0 0;color:#7A715E;font:400 11px Arial,sans-serif;line-height:1.55;">Recebes este email porque subscreveste a PTIA Weekly. Podes <a href="{{$unsubscribe}}" style="color:#14110C;text-decoration:underline;">cancelar a subscrição</a> ou gerir preferências através dos links da MailerLite no rodapé.</p>
                      <p style="margin:14px 0 0;color:#7A715E;font:400 10px Arial,sans-serif;">PTIA.pt · Lisboa, Portugal · 2026</p>
                    </td>
                  </tr>
                </table>
              </td>
            </tr>
          </table>
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
                item.portugal_angle,
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
        "Para cancelar a subscrição: {$unsubscribe}",
        "Versão web: {$url}",
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
    mailerlite_campaign_id: str | None = None,
    mailerlite_status: str | None = None,
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
        if mailerlite_campaign_id is not None:
            issue.mailerlite_campaign_id = mailerlite_campaign_id
        if mailerlite_status is not None:
            issue.mailerlite_status = mailerlite_status
        if delivery_error is not None:
            issue.delivery_error = delivery_error
        write_jsonl(path, issues)
        return issue
    raise ValueError(f"Newsletter issue not found: {issue_id}")
