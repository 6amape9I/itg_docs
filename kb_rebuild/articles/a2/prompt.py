from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from kb_rebuild.articles.a2.batch_builder import batch_prompt_payload


PROMPT_TEMPLATE_PATH = Path(__file__).with_name("prompts") / "evidence_extract_v1.md"


def build_batch_prompt(batch: dict[str, Any], *, repair_errors: list[str] | None = None) -> str:
    template = PROMPT_TEMPLATE_PATH.read_text(encoding="utf-8")
    payload = batch_prompt_payload(batch)
    parts = [
        template.strip(),
        "",
        "Входной batch:",
        "```json",
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
        "```",
    ]
    if repair_errors:
        parts.extend(
            [
                "",
                "Предыдущий ответ был отклонен локальной валидацией.",
                "Исправь только ошибки ниже и верни полный JSON для всех task_id:",
                "```json",
                json.dumps(repair_errors, ensure_ascii=False, indent=2),
                "```",
            ]
        )
    return "\n".join(parts) + "\n"

