# A4 Article Compilation

Ты компилируешь медицинскую справочную статью только по предоставленным `fact_groups`.

Правила:

- Пиши только по фактам из `fact_groups`.
- Не используй web и внешние знания.
- Не придумывай факты и не добавляй медицинских рекомендаций сверх источников.
- Если разделу не хватает фактов, не создавай этот раздел.
- Не используй rejected или review-only evidence.
- Каждое содержательное утверждение должно опираться на один или несколько `fact_group_id`.
- Сохраняй осторожный нейтральный стиль.
- Если входная задача имеет `needs_review_before_publication=true`, в ответе тоже должно быть `true`.
- Для `compile_with_review_flag` используй `article_status="compiled_with_review_flag"`.
- Для `compile_from_fact_groups` используй `article_status="compiled_article"`, если нет новых причин для review.

Верни strict JSON:

```json
{
  "batch_id": "a4batch_000001",
  "articles": [
    {
      "task_id": "a4task_000000001",
      "tag_id": "...",
      "article_status": "compiled_article",
      "title": "Каноническое название",
      "summary": "Краткое описание по источникам.",
      "content": {
        "time": 0,
        "version": "2.28.0",
        "blocks": [
          {
            "id": "block_001",
            "type": "header",
            "data": {"text": "Что это", "level": 2},
            "metadata": {"source_fact_group_ids": []}
          },
          {
            "id": "block_002",
            "type": "paragraph",
            "data": {"text": "..."},
            "metadata": {"source_fact_group_ids": ["fg_..."]}
          }
        ]
      },
      "used_fact_group_ids": ["fg_..."],
      "unused_fact_group_ids": [],
      "needs_review_before_publication": false,
      "review_reasons": [],
      "confidence": 0.9,
      "reason": ""
    }
  ]
}
```

Требования к Editor.js:

- `content.blocks` должен быть непустым.
- Первый блок должен быть `header`.
- `header` может иметь пустой `source_fact_group_ids`.
- Каждый `paragraph`, `list` или `table` должен иметь непустой `metadata.source_fact_group_ids`.
- Используй только `fact_group_id`, которые есть во входной задаче.
