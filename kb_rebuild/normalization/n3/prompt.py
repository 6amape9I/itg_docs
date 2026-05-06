from __future__ import annotations

import json
from pathlib import Path

from kb_rebuild.normalization.n3.models import N3InputGroup


PROMPT_PATH = Path(__file__).with_name("prompts") / "validate_group_v1.md"


def load_prompt_template(path: Path = PROMPT_PATH) -> str:
    return path.read_text(encoding="utf-8")


def build_group_prompt(group: N3InputGroup, *, repair_errors: list[str] | None = None) -> str:
    prompt = load_prompt_template()
    payload = json.dumps(group.to_prompt_payload(), ensure_ascii=False, indent=2, sort_keys=True)
    message = f"{prompt}\n\n## Candidate group input\n\n```json\n{payload}\n```"
    if repair_errors:
        errors = "\n".join(f"- {error}" for error in repair_errors[-20:])
        message += (
            "\n\n## Repair instruction\n\n"
            "Предыдущий ответ был невалиден. Исправь только JSON-ответ для той же группы. "
            "Не добавляй markdown, комментарии или рассуждения.\n\n"
            f"Ошибки валидации:\n{errors}"
        )
    return message

