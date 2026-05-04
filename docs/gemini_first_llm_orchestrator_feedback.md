# Gemini First LLM Orchestrator Feedback

Gemini-first work was completed together with the later token-fallback update.

Primary feedback and benchmark details are in:

```text
docs/token_fallback_llm_orchestrator_feedback.md
```

Key result: `google/gemini-3-flash-preview` with `schema_lite`, `batch_size=5`, `max_inflight=4` processed the first 200 documents with `197/197` non-empty documents successful, `0` HTTP errors, and about `4489 docs/hour`.
