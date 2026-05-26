from __future__ import annotations

import os
import shutil
import sys
from dataclasses import asdict
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

os.environ["PTIA_PUBLIC_ASSET_BASE_URL"] = "https://raw.githubusercontent.com/joaoncdferreira-ai/PTIA/main/site"

from ptia_engine.buffer_api import BufferClient  # noqa: E402
from ptia_engine.dashboard import (  # noqa: E402
    DashboardState,
    _buffer_channel_id_for,
    _copy_image_to_public_site_assets,
    _ensure_public_images_for_buffer,
    _final_post_text,
    _format_image_variants,
    _load_buffer_channels,
    _normalise_hashtags,
    _public_image_url_for_buffer,
    _sync_static_site_feed,
    _validate_final_post_copy,
    load_final_posts,
    update_final_post_copy,
    update_final_post_status,
)
from ptia_engine.editorial_board import add_final_post  # noqa: E402
from ptia_engine.models import FinalPost, utc_now_iso  # noqa: E402
from ptia_engine.storage import write_jsonl  # noqa: E402


PLAN = [
    ("topic_16b630487bd7bb9793", "2026-05-27T09:00:00+01:00", "Vaticano"),
    ("topic_27e89209eed0ce2c2a", "2026-05-27T13:00:00+01:00", "Google Zero"),
    ("topic_bf09483ad316d81fe2", "2026-05-27T16:00:00+01:00", "Bezos"),
    ("topic_36934e59c528511b96", "2026-05-27T21:00:00+01:00", "Nvidia"),
]
SOCIAL_CHANNELS = {"linkedin", "x"}
LOCAL_ONLY_CHANNELS = {"site"}
INSTAGRAM_CAROUSEL_TIME = "2026-05-27T21:00:00+01:00"


def load_dotenv() -> None:
    env_path = ROOT / ".env.local"
    if not env_path.exists():
        return
    for raw in env_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def first_sentence(text: str, fallback: str) -> str:
    clean = " ".join((text or "").replace("\n", " ").split())
    for marker in (". ", "? ", "! "):
        if marker in clean:
            return clean.split(marker, 1)[0].strip() + marker.strip()
    return clean[:240].rsplit(" ", 1)[0].strip(" .,:;") + "." if len(clean) > 240 else (clean or fallback)


def ensure_vatican_channels(state: DashboardState) -> None:
    posts = load_final_posts(state.final_posts_path)
    vatican = [post for post in posts if post.topic_id == "topic_16b630487bd7bb9793"]
    instagram = next(post for post in vatican if post.channel == "instagram")
    site = next(post for post in vatican if post.channel == "site")

    linkedin_body = (
        "O Papa Leão XIV divulgou a sua primeira encíclica, “Magnifica Humanitas”, "
        "com uma linha vermelha explícita para a inteligência artificial em contexto militar: "
        "decisões letais ou irreversíveis não devem ser entregues a sistemas artificiais.\n\n"
        "A força da notícia está menos na novidade tecnológica e mais na fronteira que coloca. "
        "Num momento em que a autonomia letal se aproxima da linguagem de produto, o Vaticano "
        "reintroduz uma pergunta que nenhuma arquitetura técnica resolve sozinha: quem responde "
        "quando a decisão deixa de ser reversível?\n\n"
        "Para empresas, decisores e equipas técnicas, a implicação é direta. A governação da IA "
        "não pode aparecer no fim, como camada reputacional. Tem de estar no desenho do sistema, "
        "nas permissões, nos limites e na cadeia de responsabilidade.\n\n"
        "Fonte: G1"
    )
    x_body = (
        "O Vaticano traçou uma linha vermelha para a IA na guerra: decisões letais ou irreversíveis "
        "não devem ser entregues a sistemas artificiais. A questão já não é só precisão técnica. "
        "É responsabilidade humana quando a decisão não tem retorno.\n\n"
        f"Fonte: {site.source_urls[0]}"
    )

    shared = {
        "topic_id": site.topic_id,
        "image_prompt": instagram.image_prompt or site.image_prompt,
        "source_urls": site.source_urls,
        "image_path": site.image_path or instagram.image_path,
        "image_variants": site.image_variants or instagram.image_variants,
        "editor_notes": "Canal recuperado para o pacote de 2026-05-27; texto refeito em voz PTIA.",
    }
    specs = {
        "linkedin": {
            "title": "Vaticano traça linha vermelha: IA não decide sobre a vida na guerra",
            "body": linkedin_body,
            "hashtags": "#InteligenciaArtificial #EticaIA #RegulacaoIA #Defesa",
        },
        "x": {
            "title": "Vaticano traça linha vermelha: IA não decide sobre a vida na guerra",
            "body": x_body,
            "hashtags": "#IA #EticaIA",
        },
    }
    existing_by_channel = {post.channel: post for post in vatican}
    for channel, spec in specs.items():
        existing = existing_by_channel.get(channel)
        if existing:
            update_final_post_copy(
                state.final_posts_path,
                existing.post_id,
                title=spec["title"],
                body=spec["body"],
                hashtags=spec["hashtags"],
                image_prompt=shared["image_prompt"],
                notes=shared["editor_notes"],
            )
            update_final_post_status(
                state.final_posts_path,
                existing.post_id,
                "approved_for_schedule",
                buffer_post_id="",
                image_path=shared["image_path"],
                image_variants=shared["image_variants"],
                image_status=instagram.image_status or site.image_status,
            )
        else:
            created = add_final_post(
                state.final_posts_path,
                channel=channel,
                title=spec["title"],
                body=spec["body"],
                hashtags=spec["hashtags"],
                **shared,
            )
            update_final_post_status(state.final_posts_path, created.post_id, "approved_for_schedule")


def refresh_variants(state: DashboardState) -> None:
    posts = load_final_posts(state.final_posts_path)
    changed = False
    for topic_id, _, _ in PLAN:
        package = [post for post in posts if post.topic_id == topic_id]
        source = next((post for post in package if post.image_path and Path(post.image_path).exists()), None)
        instagram = next((post for post in package if post.channel == "instagram"), source)
        if not source or not instagram:
            continue
        variants = source.image_variants
        if not variants or "ptia_v7" not in str(variants.get("instagram", "")) or "ptia_v7" not in str(variants.get("x", "")):
            variants = _format_image_variants(Path(source.image_path), state.final_assets_dir, instagram)
        for post in package:
            if post.status in {"approved_for_schedule", "scheduled"}:
                post.image_path = source.image_path
                post.image_variants = variants
                changed = True
    if changed:
        write_jsonl(state.final_posts_path, posts)


def carousel_caption(instagram_posts: list[FinalPost]) -> str:
    paragraphs = {
        "topic_16b630487bd7bb9793": (
            "O Vaticano coloca uma fronteira clara no debate sobre IA militar: quando uma decisão pode tirar vidas "
            "ou tornar-se irreversível, a responsabilidade não pode ser delegada num sistema artificial."
        ),
        "topic_27e89209eed0ce2c2a": (
            "A possível chegada da ‘Google Zero’ mostra que a disputa da IA já não é apenas sobre modelos melhores. "
            "É sobre quem controla a porta de entrada para a informação e que espaço resta aos editores."
        ),
        "topic_bf09483ad316d81fe2": (
            "Jeff Bezos defende que regular demasiado cedo pode travar a IA. O ponto decisivo não é escolher entre "
            "inovação e regras, mas perceber que prova, risco e governação começam a fazer parte do próprio produto."
        ),
        "topic_36934e59c528511b96": (
            "O investimento de 90 mil milhões de dólares da Nvidia lembra que a IA também é uma corrida física: chips, "
            "energia, centros de dados e capacidade de entrega definem quem consegue construir em escala."
        ),
    }
    ordered = [paragraphs[post.topic_id] for post in instagram_posts]
    return "\n\n".join(ordered + ["Fontes: G1, Forbes, Exame e Veja.", "#InteligenciaArtificial #IA #PTIA #Tecnologia"])


def validate_x_texts(posts: list[FinalPost]) -> None:
    x_posts = [post for post in posts if post.channel == "x" and post.topic_id in {topic_id for topic_id, _, _ in PLAN}]
    if len(x_posts) != 4:
        raise SystemExit(f"X incompleto: esperava 4, encontrei {len(x_posts)}")
    for round_no in range(1, 4):
        print(f"X validation round {round_no}")
        for post in sorted(x_posts, key=lambda item: item.topic_id):
            text = _final_post_text(post)
            if len(text) > 280:
                raise SystemExit(f"X > 280 chars: {post.post_id} {len(text)}")
            if not post.source_urls or post.source_urls[0] not in text:
                raise SystemExit(f"X sem fonte no texto final: {post.post_id}")
            if text.count("#") > 3:
                raise SystemExit(f"X com hashtags em excesso: {post.post_id}")
            if "O entusiasmo é compreensível" in text:
                raise SystemExit(f"Frase banida encontrada em X: {post.post_id}")
            print(f"  OK {post.post_id} {len(text)} chars")


def main() -> None:
    load_dotenv()
    state = DashboardState(ROOT / "data")
    backup_path = state.final_posts_path.with_name(f"final_posts.jsonl.bak_before_schedule_20260527_{datetime.now():%Y%m%d_%H%M%S}")
    shutil.copy2(state.final_posts_path, backup_path)
    print(f"Backup: {backup_path}")

    ensure_vatican_channels(state)
    refresh_variants(state)
    posts = load_final_posts(state.final_posts_path)
    plan_ids = {topic_id for topic_id, _, _ in PLAN}
    plan_posts = [post for post in posts if post.topic_id in plan_ids and post.status == "approved_for_schedule"]

    for topic_id, scheduled_time, label in PLAN:
        package = [post for post in plan_posts if post.topic_id == topic_id]
        channels = {post.channel for post in package}
        expected = {"instagram", "linkedin", "x", "site"}
        if channels != expected:
            raise SystemExit(f"Pacote incompleto {label}: {sorted(channels)}")
        for post in package:
            _validate_final_post_copy(post)
        print(f"Package OK {label}: {sorted(channels)}")

    validate_x_texts(plan_posts)

    social_posts = [post for post in plan_posts if post.channel in {"linkedin", "x", "instagram"}]
    _ensure_public_images_for_buffer(state, social_posts)

    channel_config = _load_buffer_channels(state.buffer_channels_path)
    client = BufferClient()

    scheduled_records: list[FinalPost] = []
    for topic_id, scheduled_time, label in PLAN:
        topic_posts = [post for post in load_final_posts(state.final_posts_path) if post.topic_id == topic_id]
        for channel in ("linkedin", "x"):
            post = next(post for post in topic_posts if post.channel == channel and post.status == "approved_for_schedule")
            channel_id = _buffer_channel_id_for(channel, channel_config)
            if not channel_id:
                raise SystemExit(f"Buffer sem canal {channel}")
            result = client.create_scheduled_post(
                channel_id=channel_id,
                text=_final_post_text(post),
                due_at=scheduled_time,
                image_url=_public_image_url_for_buffer(post, state),
            )
            scheduled_records.append(
                update_final_post_status(
                    state.final_posts_path,
                    post.post_id,
                    "scheduled",
                    scheduled_time=scheduled_time,
                    buffer_post_id=result.id,
                )
            )
            print(f"Scheduled {label} {channel}: {result.id}")
        site_post = next(post for post in topic_posts if post.channel == "site" and post.status == "approved_for_schedule")
        scheduled_records.append(
            update_final_post_status(
                state.final_posts_path,
                site_post.post_id,
                "scheduled",
                scheduled_time=scheduled_time,
            )
        )
        print(f"Scheduled {label} site local")

    instagram_posts = []
    for topic_id, _, _ in PLAN:
        instagram_posts.append(
            next(
                post
                for post in load_final_posts(state.final_posts_path)
                if post.topic_id == topic_id and post.channel == "instagram" and post.status == "approved_for_schedule"
            )
        )
    image_urls = [_public_image_url_for_buffer(post, state) for post in instagram_posts]
    instagram_channel_id = _buffer_channel_id_for("instagram", channel_config)
    if not instagram_channel_id:
        raise SystemExit("Buffer sem canal instagram")
    caption = carousel_caption(instagram_posts)
    carousel = client.create_scheduled_post(
        channel_id=instagram_channel_id,
        text=caption,
        due_at=INSTAGRAM_CAROUSEL_TIME,
        image_urls=image_urls,
        post_type="post",
    )
    print(f"Scheduled Instagram carousel: {carousel.id}")

    for index, post in enumerate(instagram_posts):
        post.body = caption if index == 0 else f"Incluído no carrossel Instagram de 2026-05-27 às 21:00.\n\n{first_sentence(post.body, post.title)}"
        post.hashtags = _normalise_hashtags(post.hashtags, "instagram")
        post.status = "scheduled"
        post.scheduled_time = INSTAGRAM_CAROUSEL_TIME
        post.buffer_post_id = carousel.id if index == 0 else f"included_in_carousel:{carousel.id}"
        post.editor_notes = f"{post.editor_notes}\n[{utc_now_iso()}] Instagram incluído no carrossel único das 21:00.".strip()
    current = load_final_posts(state.final_posts_path)
    replacements = {post.post_id: post for post in instagram_posts}
    current = [replacements.get(post.post_id, post) for post in current]
    write_jsonl(state.final_posts_path, current)

    _sync_static_site_feed(state, deploy=False)

    final = load_final_posts(state.final_posts_path)
    tomorrow = [post for post in final if post.status == "scheduled" and post.scheduled_time.startswith("2026-05-27")]
    print(f"Scheduled records for 2026-05-27: {len(tomorrow)}")
    for post in sorted(tomorrow, key=lambda item: (item.scheduled_time, item.channel, item.title)):
        print(f"VERIFY {post.scheduled_time} {post.channel} {post.post_id} {post.buffer_post_id or 'site-local'} | {post.title}")


if __name__ == "__main__":
    main()
