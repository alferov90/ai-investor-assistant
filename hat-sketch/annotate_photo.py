#!/usr/bin/env python3
"""Накладывает русские пометки на референсное фото шляпы."""

from __future__ import annotations

import math
import os
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent
SRC = ROOT.parent / ".cursor" / "projects" / "Users-sergejalferov-Projects-ai-investor-assistant" / "assets" / "IMG_0FA960739987-1-400d2d7a-cc36-474c-b897-01b9e3ed9d00.png"
OUT = ROOT / "annotated-reference.png"

FONT_CANDIDATES = [
    "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
    "/System/Library/Fonts/Supplemental/Arial.ttf",
    "/Library/Fonts/Arial.ttf",
]


def load_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for path in FONT_CANDIDATES:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except OSError:
                continue
    return ImageFont.load_default()


def annotate() -> Path:
    img = Image.open(SRC).convert("RGBA")
    width, height = img.size
    scale = width / 1000

    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    font_title = load_font(int(26 * scale))
    font_label = load_font(int(16 * scale))

    def label_box(x: int, y: int, text: str, anchor: str = "left") -> tuple[int, int]:
        lines = text.split("\n")
        sizes = [draw.textbbox((0, 0), line, font=font_label) for line in lines]
        line_heights = [b[3] - b[1] for b in sizes]
        max_w = max(b[2] - b[0] for b in sizes)
        pad_x, pad_y = int(8 * scale), int(6 * scale)
        gap = int(4 * scale)
        box_h = sum(line_heights) + pad_y * 2 + gap * (len(lines) - 1)
        box_w = max_w + pad_x * 2

        if anchor == "right":
            left = x - box_w
        elif anchor == "center":
            left = x - box_w // 2
        else:
            left = x
        top = y - box_h // 2

        draw.rounded_rectangle(
            (left, top, left + box_w, top + box_h),
            radius=int(6 * scale),
            fill=(255, 255, 255, 220),
            outline=(0, 102, 170, 255),
            width=max(1, int(2 * scale)),
        )

        cursor_y = top + pad_y
        for line, line_h in zip(lines, line_heights):
            draw.text((left + pad_x, cursor_y), line, font=font_label, fill=(20, 20, 20, 255))
            cursor_y += line_h + gap

        if anchor == "right":
            anchor_x = left
        elif anchor == "center":
            anchor_x = left + box_w // 2
        else:
            anchor_x = left + box_w
        return anchor_x, top + box_h // 2

    def arrow(start: tuple[int, int], end: tuple[int, int], color=(0, 102, 170, 255)) -> None:
        draw.line([start, end], fill=color, width=max(1, int(2.5 * scale)))
        angle = math.atan2(end[1] - start[1], end[0] - start[0])
        head = int(12 * scale)
        p1 = (
            end[0] + head * math.cos(angle + math.pi * 0.85),
            end[1] + head * math.sin(angle + math.pi * 0.85),
        )
        p2 = (
            end[0] + head * math.cos(angle - math.pi * 0.85),
            end[1] + head * math.sin(angle - math.pi * 0.85),
        )
        draw.polygon([end, p1, p2], fill=color)

    def callout(
        label_pos: tuple[int, int],
        target_pos: tuple[int, int],
        text: str,
        anchor: str = "left",
    ) -> None:
        anchor_pos = label_box(*label_pos, text, anchor=anchor)
        arrow(anchor_pos, target_pos)

    title = "ЭСКИЗ ШЛЯПЫ — РАЗМЕТКА ДЕТАЛЕЙ"
    bbox = draw.textbbox((0, 0), title, font=font_title)
    title_w, title_h = bbox[2] - bbox[0], bbox[3] - bbox[1]
    title_x = (width - title_w) // 2
    title_y = int(15 * scale)
    draw.rounded_rectangle(
        (title_x - 12, title_y - 8, title_x + title_w + 12, title_y + title_h + 8),
        radius=8,
        fill=(0, 0, 0, 180),
    )
    draw.text((title_x, title_y), title, font=font_title, fill=(255, 255, 255, 255))

    callout(
        (int(width * 0.62), int(height * 0.12)),
        (int(width * 0.50), int(height * 0.22)),
        "КОРОНА (тулья)\nВысота ≈ 17–18 см\nЦилиндр с куполом",
    )
    callout(
        (int(width * 0.08), int(height * 0.30)),
        (int(width * 0.42), int(height * 0.30)),
        "ЛЕНТА\nШирина ≈ 4 см\nТкань в тон",
    )
    callout(
        (int(width * 0.05), int(height * 0.48)),
        (int(width * 0.18), int(height * 0.42)),
        "ПОЛЕ (борт)\nГлубина ≈ 23 см\nУгол наклона ≈ 38°",
    )
    callout(
        (int(width * 0.88), int(height * 0.38)),
        (int(width * 0.78), int(height * 0.36)),
        "КРАЙ ПОЛЯ\nПроволока Ø 2 мм\nПодгиб + стежок",
        anchor="right",
    )
    callout(
        (int(width * 0.55), int(height * 0.55)),
        (int(width * 0.55), int(height * 0.45)),
        "МАТЕРИАЛ\nЛён / канвас\noff-white, 280–320 г/м²",
    )
    callout(
        (int(width * 0.50), int(height * 0.72)),
        (int(width * 0.72), int(height * 0.52)),
        "ОБЩАЯ ШИРИНА ≈ 46 см",
        anchor="center",
    )
    callout(
        (int(width * 0.72), int(height * 0.18)),
        (int(width * 0.58), int(height * 0.25)),
        "ЖЁСТКОСТЬ\nДублерин в короне\nи поле",
    )

    bracket_x = int(width * 0.32)
    y_top, y_bottom = int(height * 0.22), int(height * 0.30)
    draw.line([(bracket_x, y_top), (bracket_x, y_bottom)], fill=(204, 102, 0, 255), width=max(1, int(2 * scale)))
    for y in (y_top, y_bottom):
        draw.line(
            [(bracket_x - int(8 * scale), y), (bracket_x + int(8 * scale), y)],
            fill=(204, 102, 0, 255),
            width=max(1, int(2 * scale)),
        )
    label_box(bracket_x - int(90 * scale), (y_top + y_bottom) // 2, "H = 17 см", anchor="right")

    result = Image.alpha_composite(img, overlay).convert("RGB")
    result.save(OUT, quality=95)
    return OUT


if __name__ == "__main__":
    output = annotate()
    print(output)
