from __future__ import annotations

import ast
import html
import re
import unicodedata

from ptia_engine.models import FinalPost


GENERIC_EDITORIAL_CTA_PATTERNS = [
    r"\bIsto entraria na (?:tua|sua) lista de prioridades para os pr[oó]ximos meses\?\s*",
    r"\bIsto entra na (?:tua|sua) lista de prioridades para os pr[oó]ximos meses\?\s*",
    r"\bIsto entra na (?:tua|sua) lista de preocupa[cç][oõ]es para os pr[oó]ximos meses\?\s*",
    r"\bEsta tem[aá]tica faz parte das vossas prioridades para os pr[oó]ximos meses\?\s*",
    r"\bQuem em Portugal deve prestar aten[cç][aã]o\?\s*",
    r"\bO que significa para Portugal\?\s*",
]


BANNED_EDITORIAL_BODY_PATTERNS = [
    r"\bO entusiasmo [eé] compreens[ií]vel[.,;:]?\s*",
    r"(?im)^\s*Ser[aá] que [^?\n]{1,180}\?\s*",
    r"(?im)^\s*Em suma[,:]?\s*",
    r"(?im)^\s*Em resumo[,:]?\s*",
    r"(?im)^\s*No panorama atual[,:]?\s*",
    r"(?im)^\s*Al[eé]m disso[,:]?\s*",
    r"(?im)^\s*Por outro lado[,:]?\s*",
    r"(?im)^\s*Adicionalmente[,:]?\s*",
    r"(?im)^\s*Consequentemente[,:]?\s*",
    r"\bO impacto d[eo] [^.\n]{1,90} n[aã]o pode ser subestimado[.,;:]?\s*",
    r"\b[EÉ] fundamental recordar(?: que)?[.,;:]?\s*",
    r"\bDesbloquear o potencial d[aeo] [^.\n]{1,90}[.,;:]?\s*",
    r"\bMergulhar profundamente n[ao] [^.\n]{1,90}[.,;:]?\s*",
    r"\bA verdade [eé] que[.,;:]?\s*",
    r"\b[Rr]evolucion(?:ar|a|am|ou|ando|[aá]rio|[aá]ria)[a-záãçéêíóõú]*\b",
    r"\b[Aa] pergunta [uú]til [^.\n?]{0,160}[.?]\s*",
    r"\b[Qq]uem consegue (?:executar|usar|levar|p[ôo]r)[^.\n?]{0,120}[.?]?\s*",
    r"\b[Qq]uem ganha acesso primeiro[.,;:]?\s*",
    r"\b[Qq]ue custo aparece [^.\n?]{0,120}[.?]?\s*",
    r"\bcusto,\s*risco e depend[eê]ncia\b[.,;:]?\s*",
    r"\b[Qq]ue prova fica guardada quando o sistema falha[.,;:]?\s*",
    r"\b[Qq]uem assume a decis[aã]o[.,;:]?\s*",
    r"\b[Aa] pergunta [eé][^.\n?]{0,160}[.?]?\s*",
    r"\b[Aa] not[ií]cia n[aã]o [eé][^.\n]{0,180}[.]\s*",
    r"\b[Aa] quest[aã]o,?\s*agora,?\s*n[aã]o [eé][^.\n?]{0,180}[.?]\s*",
    r"\b[Oo] detalhe a observar n[aã]o est[aá] no an[uú]ncio[.,;:]?\s*",
    r"\b[Ee]st[aá] na mudan[cç]a de incentivos[.:]?\s*",
]


EDITORIAL_WORD_REPLACEMENTS = [
    (r"\b[Cc]rucial\b", "importante"),
    (r"\b[Vv]ital\b", "importante"),
    (r"\b[Ee]ssencial\b", "importante"),
]


def clean_editorial_title(value: str) -> str:
    """Keep titles as plain text across UI, social copy and metadata."""
    clean = html.unescape(str(value or ""))
    clean = re.sub(r"<[^>]+>", "", clean)
    clean = re.sub(r"\*\*(.*?)\*\*", r"\1", clean)
    clean = re.sub(r"\*(.*?)\*", r"\1", clean)
    return re.sub(r"\s+", " ", clean).strip()


def normalise_hashtags(raw, channel: str = "") -> str:
    """Return clean social hashtags as '#TagA #TagB', never Python/JSON list syntax."""
    if not raw:
        return ""
    values = []
    if isinstance(raw, (list, tuple, set)):
        values = [str(item) for item in raw]
    else:
        text = str(raw).strip()
        try:
            parsed = ast.literal_eval(text)
        except (ValueError, SyntaxError):
            parsed = None
        if isinstance(parsed, (list, tuple, set)):
            values = [str(item) for item in parsed]
        else:
            values = re.findall(r"#?[\wÀ-ÿ]+", text.replace(",", " "))
            if "#" not in text:
                values = []

    tags = []
    seen = set()
    for value in values:
        tag = value.strip().strip("[](){}'\".,;:")
        if not tag:
            continue
        tag = tag[1:] if tag.startswith("#") else tag
        tag = unicodedata.normalize("NFKD", tag).encode("ascii", "ignore").decode("ascii")
        tag = re.sub(r"[^A-Za-z0-9_]", "", tag)
        if not tag:
            continue
        tag = f"#{tag}"
        key = tag.casefold()
        if key in seen:
            continue
        seen.add(key)
        tags.append(tag)

    max_count = {"linkedin": 4, "instagram": 5, "x": 2}.get(channel, 5)
    return " ".join(tags[:max_count])


def apply_ptia_editorial_rules(title: str, body: str, channel: str = "") -> tuple[str, str]:
    """Apply non-negotiable PTIA editorial hygiene before review/publish."""
    clean_title = clean_editorial_title(re.sub(
        r"\s*[—–\-:]\s*O que significa para Portugal\??\s*$",
        "",
        title,
        flags=re.IGNORECASE,
    ))
    clean_body = body
    for pattern in GENERIC_EDITORIAL_CTA_PATTERNS:
        clean_body = re.sub(pattern, "", clean_body, flags=re.IGNORECASE)
    for pattern in BANNED_EDITORIAL_BODY_PATTERNS:
        clean_body = re.sub(pattern, "", clean_body, flags=re.IGNORECASE)
    for pattern, replacement in EDITORIAL_WORD_REPLACEMENTS:
        clean_body = re.sub(pattern, replacement, clean_body)
    clean_body = re.sub(
        r"^\s*(?:A leitura PTIA|O que observar(?: agora)?|Porque importa|A not[ií]cia)\s*:\s*",
        "",
        clean_body,
        flags=re.IGNORECASE | re.MULTILINE,
    )
    clean_body = re.sub(
        r"\bA not[ií]cia (d[aeo]s?|do|da|de)\b",
        r"O relato \1",
        clean_body,
        flags=re.IGNORECASE,
    )
    clean_body = re.sub(
        r"\bA not[ií]cia\b",
        "O relato",
        clean_body,
        flags=re.IGNORECASE,
    )
    if channel in {"instagram", "linkedin", "x"}:
        clean_body = re.sub(r"\*\*(.*?)\*\*", r"\1", clean_body)
        clean_body = re.sub(r"\*(.*?)\*", r"\1", clean_body)
        clean_body = re.sub(r"<i>(.*?)</i>", r"\1", clean_body)
        clean_body = re.sub(r"</?i>", "", clean_body)
    if channel == "site":
        clean_body = re.sub(r"\*\*Fonte:\*\*", "Fonte:", clean_body)
        clean_body = re.sub(r"\*(.*?)\*", r"<i>\1</i>", clean_body)
    clean_body = re.sub(r"(?im)^\s*-\s*-\s*(Fonte(?: original)?\s*:)", r"\1", clean_body)
    clean_body = re.sub(r"(?im)^\s*-\s*(?=Fonte(?: original)?\s*:)", "", clean_body)
    clean_body = re.sub(r"(?m)^\s*-\s*$\n?", "", clean_body)
    clean_body = re.sub(r"\n{3,}", "\n\n", clean_body).strip()
    return clean_title or title, clean_body


def copy_quality_issues(post: FinalPost) -> list[str]:
    """Return blocking copy problems that must not reach approval or Buffer."""
    body = (post.body or "").strip()
    title = (post.title or "").strip()
    issues: list[str] = []
    if not title:
        issues.append("titulo vazio")
    if not body:
        issues.append("texto vazio")
        return issues

    broken_patterns = [
        (r"(?im)^\s*-\s*(?:-\s*)?Fonte(?: original)?\s*:", "bullet de fonte quebrada"),
        (r"(?im)^\s*-\s*$", "bullet vazio"),
        (r"(?m)[^\n][ \t]+Fonte(?:s| original)?\s*:", "fonte colada no meio da frase"),
        (r"\b(?:importa perceber|contudo, importa perceber|é perceber)\s*(?:\.|$)", "frase truncada"),
        (r"\b(?:Tr[eê]s (?:coisas|pontos|leituras)[^:\n]*:)\s*$", "lista de pontos sem conteudo"),
    ]
    for pattern, label in broken_patterns:
        if re.search(pattern, body):
            issues.append(label)

    if re.search(r"(?im)^\s*Tr[eê]s (?:coisas|pontos|leituras)[^:\n]*:", body):
        valid_bullets = [
            line
            for line in body.splitlines()
            if re.match(r"^\s*-\s+\S", line) and not re.match(r"^\s*-\s*(?:-\s*)?Fonte", line, re.IGNORECASE)
        ]
        if post.channel == "instagram" and len(valid_bullets) < 2:
            issues.append("lista Instagram incompleta")

    body_no_urls = re.sub(r"https?://\S+", "", body)
    if re.search(r"\b\w+\?\w+", body_no_urls):
        issues.append("possivel erro de encoding no texto")

    return list(dict.fromkeys(issues))


def validate_final_post_copy(post: FinalPost) -> None:
    issues = copy_quality_issues(post)
    if issues:
        raise ValueError(f"Copy bloqueada em {post.channel}: {post.title} ({'; '.join(issues)})")


def validate_final_package_copy(posts: list[FinalPost]) -> None:
    failures: list[str] = []
    for post in posts:
        issues = copy_quality_issues(post)
        if issues:
            failures.append(f"{post.channel}: {post.title} ({'; '.join(issues)})")
    if failures:
        raise ValueError("Pacote bloqueado por copy desalinhada/incompleta: " + " | ".join(failures))
