from __future__ import annotations

import html
import re
import textwrap
from pathlib import Path

from ptia_engine.dedupe import stable_hash
from ptia_engine.editorial import draft_text
from ptia_engine.models import ContentAsset, ContentDraft, FinalPost
from ptia_engine.storage import append_jsonl, load_content_assets

SECTION_COLORS = {
    "builders": ("#0f766e", "#d9f7f3"),
    "business": ("#5b4b00", "#fff3bf"),
    "regulation": ("#7f1d1d", "#fee2e2"),
    "research": ("#4338ca", "#e0e7ff"),
    "tools": ("#075985", "#e0f2fe"),
    "portugal_ai": ("#166534", "#dcfce7"),
    "world_ai": ("#1f2937", "#eef2f7"),
}


def _wrap(text: str, width: int, max_lines: int) -> list[str]:
    clean = re.sub(r"\s+", " ", text).strip()
    lines = textwrap.wrap(clean, width=width, break_long_words=False, replace_whitespace=True)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        lines[-1] = lines[-1].rstrip(".") + "..."
    return lines


def _svg_text(lines: list[str], x: int, y: int, size: int, weight: int = 600, fill: str = "#111827") -> str:
    output = []
    for index, line in enumerate(lines):
        output.append(
            f'<text x="{x}" y="{y + index * int(size * 1.25)}" font-size="{size}" '
            f'font-weight="{weight}" fill="{fill}">{html.escape(line)}</text>'
        )
    return "\n".join(output)


def _extract_carousel_slides(outline: str) -> list[dict[str, str]]:
    slides: list[dict[str, str]] = []
    parts = re.split(r"\n\s*\n", outline.strip())
    for part in parts:
        if not part.strip().lower().startswith("slide"):
            continue
        headline_match = re.search(r"Slide\s+\d+:\s*(.+)", part, re.IGNORECASE)
        text_match = re.search(r"Texto:\s*(.+)", part, re.IGNORECASE)
        visual_match = re.search(r"Visual:\s*(.+)", part, re.IGNORECASE)
        slides.append(
            {
                "headline": headline_match.group(1).strip() if headline_match else "PTIA",
                "text": text_match.group(1).strip() if text_match else "",
                "visual": visual_match.group(1).strip() if visual_match else "",
            }
        )
    return slides


def render_square_card(
    title: str,
    section: str,
    source: str,
    takeaway: str,
    label: str = "PTIA",
) -> str:
    accent, tint = SECTION_COLORS.get(section, SECTION_COLORS["world_ai"])
    title_lines = _wrap(title, 24, 5)
    takeaway_lines = _wrap(takeaway, 36, 5)
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="1080" height="1080" viewBox="0 0 1080 1080">
  <rect width="1080" height="1080" fill="#f7f8fb"/>
  <rect x="64" y="64" width="952" height="952" rx="36" fill="#ffffff" stroke="#d9dee8" stroke-width="2"/>
  <rect x="64" y="64" width="952" height="18" fill="{accent}"/>
  <text x="96" y="140" font-size="34" font-weight="800" fill="{accent}">{html.escape(label)}</text>
  <rect x="96" y="174" width="260" height="44" rx="22" fill="{tint}"/>
  <text x="118" y="204" font-size="22" font-weight="700" fill="{accent}">{html.escape(section.replace('_', ' ').upper())}</text>
  {_svg_text(title_lines, 96, 330, 60, 800)}
  <line x1="96" x2="984" y1="710" y2="710" stroke="#e4e7ee" stroke-width="2"/>
  {_svg_text(takeaway_lines, 96, 780, 34, 500, "#344054")}
  <text x="96" y="956" font-size="24" font-weight="600" fill="#667085">Fonte: {html.escape(source[:70])}</text>
  <text x="850" y="956" font-size="24" font-weight="800" fill="{accent}">ptia</text>
</svg>"""


def render_final_post_image(post: FinalPost, variant: int = 0, feedback: str = "") -> str:
    palettes = [
        ("#051A3B", "#C0A062", "#F9F7F1", "#1B6B5F"),
        ("#102A43", "#B88A44", "#F6F2E8", "#7A1E1E"),
        ("#101820", "#D6B56D", "#FAF8F1", "#385170"),
    ]
    navy, gold, cream, signal = palettes[variant % len(palettes)]
    title = f"{post.title} {post.body} {feedback}".lower()
    if any(word in title for word in ["incend", "fogo", "floresta", "terreno"]):
        motif = "fire"
    elif any(word in title for word in ["saude", "saúde", "sns", "hospital", "medic"]):
        motif = "health"
    elif any(word in title for word in ["regula", "ai act", "lei", "governo", "estado"]):
        motif = "public"
    elif any(word in title for word in ["agent", "builder", "codigo", "program"]):
        motif = "builder"
    else:
        motif = "signal"

    if motif == "fire":
        scene = f"""
  <path d="M143 718 C245 566, 305 524, 414 492 C563 449, 691 332, 938 258" fill="none" stroke="{navy}" stroke-width="22" stroke-linecap="round" opacity="0.9"/>
  <path d="M173 766 C326 664, 454 622, 626 565 C746 525, 833 465, 925 375" fill="none" stroke="{gold}" stroke-width="16" stroke-linecap="round" opacity="0.9"/>
  <circle cx="308" cy="668" r="84" fill="{signal}" opacity="0.16"/>
  <circle cx="638" cy="530" r="116" fill="{gold}" opacity="0.18"/>
  <path d="M266 770 C292 700, 274 672, 330 608 C306 704, 378 698, 340 792 Z" fill="{signal}" opacity="0.92"/>
"""
    elif motif == "health":
        scene = f"""
  <circle cx="330" cy="390" r="140" fill="{navy}" opacity="0.94"/>
  <circle cx="720" cy="660" r="170" fill="{gold}" opacity="0.82"/>
  <rect x="506" y="280" width="86" height="520" rx="43" fill="{signal}" opacity="0.78"/>
  <rect x="332" y="454" width="430" height="86" rx="43" fill="{signal}" opacity="0.78"/>
  <path d="M162 760 C330 602, 474 727, 623 568 C704 482, 824 464, 932 330" fill="none" stroke="{navy}" stroke-width="14" stroke-linecap="round" opacity="0.42"/>
"""
    elif motif == "public":
        scene = f"""
  <rect x="150" y="310" width="780" height="78" rx="4" fill="{navy}" opacity="0.95"/>
  <rect x="206" y="424" width="92" height="330" rx="2" fill="{gold}" opacity="0.84"/>
  <rect x="388" y="424" width="92" height="330" rx="2" fill="{gold}" opacity="0.84"/>
  <rect x="570" y="424" width="92" height="330" rx="2" fill="{gold}" opacity="0.84"/>
  <rect x="752" y="424" width="92" height="330" rx="2" fill="{gold}" opacity="0.84"/>
  <rect x="128" y="794" width="824" height="54" rx="6" fill="{navy}" opacity="0.95"/>
  <circle cx="540" cy="286" r="82" fill="{signal}" opacity="0.22"/>
"""
    elif motif == "builder":
        scene = f"""
  <rect x="165" y="275" width="750" height="530" rx="28" fill="{navy}" opacity="0.95"/>
  <circle cx="222" cy="335" r="13" fill="{gold}"/>
  <circle cx="268" cy="335" r="13" fill="{cream}" opacity="0.8"/>
  <circle cx="314" cy="335" r="13" fill="{signal}"/>
  <path d="M315 470 L235 540 L315 610" fill="none" stroke="{gold}" stroke-width="26" stroke-linecap="round" stroke-linejoin="round"/>
  <path d="M765 470 L845 540 L765 610" fill="none" stroke="{gold}" stroke-width="26" stroke-linecap="round" stroke-linejoin="round"/>
  <path d="M590 450 L500 638" fill="none" stroke="{cream}" stroke-width="20" stroke-linecap="round" opacity="0.9"/>
"""
    else:
        scene = f"""
  <circle cx="540" cy="540" r="260" fill="none" stroke="{navy}" stroke-width="26" opacity="0.86"/>
  <circle cx="540" cy="540" r="176" fill="none" stroke="{gold}" stroke-width="22" opacity="0.82"/>
  <circle cx="540" cy="540" r="96" fill="{signal}" opacity="0.36"/>
  <path d="M184 742 C330 518, 496 748, 660 462 C748 308, 838 284, 920 236" fill="none" stroke="{navy}" stroke-width="16" stroke-linecap="round" opacity="0.38"/>
"""
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="1080" height="1080" viewBox="0 0 1080 1080">
  <defs>
    <linearGradient id="gold" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="#E1C57B"/>
      <stop offset="50%" stop-color="{gold}"/>
      <stop offset="100%" stop-color="#8D6B2D"/>
    </linearGradient>
    <radialGradient id="wash" cx="50%" cy="42%" r="70%">
      <stop offset="0%" stop-color="#FFFFFF" stop-opacity="0.96"/>
      <stop offset="100%" stop-color="{cream}" stop-opacity="1"/>
    </radialGradient>
    <pattern id="mesh" width="46" height="46" patternUnits="userSpaceOnUse">
      <path d="M46 0H0V46" fill="none" stroke="{navy}" stroke-width="1" opacity="0.055"/>
    </pattern>
  </defs>
  <rect width="1080" height="1080" fill="url(#wash)"/>
  <rect width="1080" height="1080" fill="url(#mesh)"/>
  <rect x="72" y="72" width="936" height="936" rx="34" fill="#FFFFFF" opacity="0.62" stroke="#E5DEC9" stroke-width="2"/>
  <rect x="112" y="112" width="856" height="856" rx="28" fill="none" stroke="url(#gold)" stroke-width="4" opacity="0.85"/>
  {scene}
  <circle cx="900" cy="168" r="38" fill="url(#gold)" opacity="0.95"/>
  <path d="M176 902 H904" stroke="{navy}" stroke-width="10" stroke-linecap="round" opacity="0.88"/>
  <text x="176" y="865" font-size="44" font-weight="800" fill="{navy}" font-family="Georgia, serif">PTIA</text>
</svg>"""


def create_final_post_image(post: FinalPost, out_dir: Path, feedback: str = "") -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    variant_seed = f"{post.post_id}:{feedback}:{post.image_prompt}:{post.image_path}"
    variant = int(stable_hash(variant_seed, 4), 16) % 3
    file_path = out_dir / f"{post.post_id}_{stable_hash(variant_seed, 8)}.svg"
    file_path.write_text(render_final_post_image(post, variant=variant, feedback=feedback), encoding="utf-8")
    return file_path


def create_assets_for_draft(
    draft: ContentDraft,
    item_section: str,
    source_name: str,
    out_dir: Path,
) -> list[ContentAsset]:
    out_dir.mkdir(parents=True, exist_ok=True)
    existing = {asset.asset_id for asset in load_content_assets(out_dir.parent / "content_assets.jsonl")}
    assets: list[ContentAsset] = []
    text = draft_text(draft)

    if draft.format == "instagram_carousel":
        slides = _extract_carousel_slides(draft.carousel_outline)
        for index, slide in enumerate(slides, start=1):
            asset_id = f"asset_{stable_hash(f'{draft.draft_id}:{index}')}"
            if asset_id in existing:
                continue
            file_path = out_dir / f"{draft.draft_id}_slide_{index:02d}.svg"
            svg = render_square_card(
                title=slide["headline"],
                section=item_section,
                source=source_name,
                takeaway=slide["text"] or slide["visual"],
                label=f"PTIA {index}/{len(slides)}",
            )
            file_path.write_text(svg, encoding="utf-8")
            assets.append(
                ContentAsset(
                    asset_id=asset_id,
                    draft_id=draft.draft_id,
                    item_id=draft.item_id,
                    channel=draft.channel,
                    asset_type="carousel_slide",
                    title=slide["headline"],
                    file_path=str(file_path),
                    notes=slide["visual"],
                )
            )
    else:
        asset_id = f"asset_{stable_hash(draft.draft_id)}"
        if asset_id not in existing:
            file_path = out_dir / f"{draft.draft_id}.svg"
            svg = render_square_card(
                title=draft.title,
                section=item_section,
                source=source_name,
                takeaway=text,
                label="PTIA",
            )
            file_path.write_text(svg, encoding="utf-8")
            assets.append(
                ContentAsset(
                    asset_id=asset_id,
                    draft_id=draft.draft_id,
                    item_id=draft.item_id,
                    channel=draft.channel,
                    asset_type="square_card",
                    title=draft.title,
                    file_path=str(file_path),
                )
            )

    append_jsonl(out_dir.parent / "content_assets.jsonl", assets)
    return assets
