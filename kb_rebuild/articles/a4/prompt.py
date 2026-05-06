from __future__ import annotations

import json
from pathlib import Path
from typing import Any


PROMPT_TEMPLATE_PATH = Path(__file__).with_name("prompts") / "article_compile_v1.md"


def build_batch_prompt(batch: dict[str, Any], *, repair_errors: list[str] | None = None) -> str:
    template = PROMPT_TEMPLATE_PATH.read_text(encoding="utf-8")
    payload = {
        "batch_id": batch.get("batch_id"),
        "tasks": batch.get("tasks", []),
    }
    sections = []
    if repair_errors:
        sections.append("Ошибки предыдущей попытки, которые нужно исправить:\n" + "\n".join(f"- {error}" for error in repair_errors[:30]))
    sections.append("Входные задачи A4:\n```json\n" + json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n```")
    return template.rstrip() + "\n\n" + "\n\n".join(sections)

