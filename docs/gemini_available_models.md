# Gemini Available Models

Generated at: 2026-05-05T08:27:44Z

## Recommended mapping

TAGGING_PRIMARY = gemini-3-flash-preview
EVIDENCE_EXTRACTION_PRIMARY = gemini-3-flash-preview
TAG_NORMALIZATION_PRIMARY = gemini-3-pro-preview
ARTICLE_COMPILATION_PRIMARY = gemini-3-pro-preview
FOLDER_HIERARCHY_PRIMARY = gemini-3-flash-preview
QA_AUDIT_PRIMARY = gemini-3-flash-preview

Discovered with key_count=3; keys are not stored in this report.

## Raw available models

| name | baseModelId | version | displayName | input | output | methods | recommended_role |
|---|---|---|---|---:|---:|---|---|
| models/gemini-2.5-flash |  | 001 | Gemini 2.5 Flash | 1048576 | 65536 | generateContent, countTokens, createCachedContent, batchGenerateContent | available_generateContent_candidate |
| models/gemini-2.5-pro |  | 2.5 | Gemini 2.5 Pro | 1048576 | 65536 | generateContent, countTokens, createCachedContent, batchGenerateContent | stable_pro_fallback_candidate |
| models/gemini-2.0-flash |  | 2.0 | Gemini 2.0 Flash | 1048576 | 8192 | generateContent, countTokens, createCachedContent, batchGenerateContent | stable_flash_fallback_candidate |
| models/gemini-2.0-flash-001 |  | 2.0 | Gemini 2.0 Flash 001 | 1048576 | 8192 | generateContent, countTokens, createCachedContent, batchGenerateContent | available_generateContent_candidate |
| models/gemini-2.0-flash-lite-001 |  | 2.0 | Gemini 2.0 Flash-Lite 001 | 1048576 | 8192 | generateContent, countTokens, createCachedContent, batchGenerateContent | available_generateContent_candidate |
| models/gemini-2.0-flash-lite |  | 2.0 | Gemini 2.0 Flash-Lite | 1048576 | 8192 | generateContent, countTokens, createCachedContent, batchGenerateContent | available_generateContent_candidate |
| models/gemini-2.5-flash-preview-tts |  | gemini-2.5-flash-exp-tts-2025-05-19 | Gemini 2.5 Flash Preview TTS | 8192 | 16384 | countTokens, generateContent | available_generateContent_candidate |
| models/gemini-2.5-pro-preview-tts |  | gemini-2.5-pro-preview-tts-2025-05-19 | Gemini 2.5 Pro Preview TTS | 8192 | 16384 | countTokens, generateContent, batchGenerateContent | available_generateContent_candidate |
| models/gemma-3-1b-it |  | 001 | Gemma 3 1B | 32768 | 8192 | generateContent, countTokens | available_generateContent_candidate |
| models/gemma-3-4b-it |  | 001 | Gemma 3 4B | 32768 | 8192 | generateContent, countTokens | available_generateContent_candidate |
| models/gemma-3-12b-it |  | 001 | Gemma 3 12B | 32768 | 8192 | generateContent, countTokens | available_generateContent_candidate |
| models/gemma-3-27b-it |  | 001 | Gemma 3 27B | 131072 | 8192 | generateContent, countTokens | available_generateContent_candidate |
| models/gemma-3n-e4b-it |  | 001 | Gemma 3n E4B | 8192 | 2048 | generateContent, countTokens | available_generateContent_candidate |
| models/gemma-3n-e2b-it |  | 001 | Gemma 3n E2B | 8192 | 2048 | generateContent, countTokens | available_generateContent_candidate |
| models/gemma-4-26b-a4b-it |  | 001 | Gemma 4 26B A4B IT | 262144 | 32768 | generateContent, countTokens | available_generateContent_candidate |
| models/gemma-4-31b-it |  | 001 | Gemma 4 31B IT | 262144 | 32768 | generateContent, countTokens | available_generateContent_candidate |
| models/gemini-flash-latest |  | Gemini Flash Latest | Gemini Flash Latest | 1048576 | 65536 | generateContent, countTokens, createCachedContent, batchGenerateContent | available_generateContent_candidate |
| models/gemini-flash-lite-latest |  | Gemini Flash-Lite Latest | Gemini Flash-Lite Latest | 1048576 | 65536 | generateContent, countTokens, createCachedContent, batchGenerateContent | available_generateContent_candidate |
| models/gemini-pro-latest |  | Gemini Pro Latest | Gemini Pro Latest | 1048576 | 65536 | generateContent, countTokens, createCachedContent, batchGenerateContent | available_generateContent_candidate |
| models/gemini-2.5-flash-lite |  | 001 | Gemini 2.5 Flash-Lite | 1048576 | 65536 | generateContent, countTokens, createCachedContent, batchGenerateContent | cheap_fallback_candidate |
| models/gemini-2.5-flash-image |  | 2.0 | Nano Banana | 32768 | 32768 | generateContent, countTokens, batchGenerateContent | available_generateContent_candidate |
| models/gemini-3-pro-preview |  | 3-pro-preview-11-2025 | Gemini 3 Pro Preview | 1048576 | 65536 | generateContent, countTokens, createCachedContent, batchGenerateContent | TAG_NORMALIZATION_PRIMARY,ARTICLE_COMPILATION_PRIMARY,QA_AUDIT_HARD |
| models/gemini-3-flash-preview |  | 3-flash-preview-12-2025 | Gemini 3 Flash Preview | 1048576 | 65536 | generateContent, countTokens, createCachedContent, batchGenerateContent | TAGGING_PRIMARY,EVIDENCE_EXTRACTION_PRIMARY,FOLDER_HIERARCHY_PRIMARY,QA_AUDIT_PRIMARY |
| models/gemini-3.1-pro-preview |  | 3.1-pro-preview-01-2026 | Gemini 3.1 Pro Preview | 1048576 | 65536 | generateContent, countTokens, createCachedContent, batchGenerateContent | available_generateContent_candidate |
| models/gemini-3.1-pro-preview-customtools |  | 3.1-pro-preview-01-2026 | Gemini 3.1 Pro Preview Custom Tools | 1048576 | 65536 | generateContent, countTokens, createCachedContent, batchGenerateContent | available_generateContent_candidate |
| models/gemini-3.1-flash-lite-preview |  | 3.1-flash-lite-preview-03-2026 | Gemini 3.1 Flash Lite Preview | 1048576 | 65536 | generateContent, countTokens, createCachedContent, batchGenerateContent | available_generateContent_candidate |
| models/gemini-3-pro-image-preview |  | 3.0 | Nano Banana Pro | 131072 | 32768 | generateContent, countTokens, batchGenerateContent | available_generateContent_candidate |
| models/nano-banana-pro-preview |  | 3.0 | Nano Banana Pro | 131072 | 32768 | generateContent, countTokens, batchGenerateContent | available_generateContent_candidate |
| models/gemini-3.1-flash-image-preview |  | 3.0 | Nano Banana 2 | 65536 | 65536 | generateContent, countTokens, batchGenerateContent | available_generateContent_candidate |
| models/lyria-3-clip-preview |  | lyria-3-clip-preview | Lyria 3 Clip Preview | 1048576 | 65536 | generateContent, countTokens | available_generateContent_candidate |
| models/lyria-3-pro-preview |  | lyria-3-pro-preview | Lyria 3 Pro Preview | 1048576 | 65536 | generateContent, countTokens | available_generateContent_candidate |
| models/gemini-3.1-flash-tts-preview |  | 3.1-flash-tts-preview | Gemini 3.1 Flash TTS Preview | 8192 | 16384 | generateContent, countTokens, batchGenerateContent | available_generateContent_candidate |
| models/gemini-robotics-er-1.5-preview |  | 1.5-preview | Gemini Robotics-ER 1.5 Preview | 1048576 | 65536 | generateContent, countTokens | available_generateContent_candidate |
| models/gemini-robotics-er-1.6-preview |  | 1.6-preview | Gemini Robotics-ER 1.6 Preview | 131072 | 65536 | generateContent, countTokens, createCachedContent, batchGenerateContent | available_generateContent_candidate |
| models/gemini-2.5-computer-use-preview-10-2025 |  | Gemini 2.5 Computer Use Preview 10-2025 | Gemini 2.5 Computer Use Preview 10-2025 | 131072 | 65536 | generateContent, countTokens | available_generateContent_candidate |
| models/deep-research-max-preview-04-2026 |  | deepthink-exp-05-20 | Deep Research Max Preview (Apr-21-2026) | 131072 | 65536 | generateContent, countTokens | available_generateContent_candidate |
| models/deep-research-preview-04-2026 |  | deepthink-exp-05-20 | Deep Research Preview (Apr-21-2026) | 131072 | 65536 | generateContent, countTokens | available_generateContent_candidate |
| models/deep-research-pro-preview-12-2025 |  | deepthink-exp-05-20 | Deep Research Pro Preview (Dec-12-2025) | 131072 | 65536 | generateContent, countTokens | available_generateContent_candidate |
| models/gemini-embedding-001 |  | 001 | Gemini Embedding 001 | 2048 | 1 | embedContent, countTextTokens, countTokens, asyncBatchEmbedContent | not_for_pipeline |
| models/gemini-embedding-2-preview |  | 2 | Gemini Embedding 2 Preview | 8192 | 1 | embedContent, countTextTokens, countTokens, asyncBatchEmbedContent | not_for_pipeline |
| models/gemini-embedding-2 |  | 2 | Gemini Embedding 2 | 8192 | 1 | embedContent, countTextTokens, countTokens, asyncBatchEmbedContent | not_for_pipeline |
| models/aqa |  | 001 | Model that performs Attributed Question Answering. | 7168 | 1024 | generateAnswer | not_for_pipeline |
| models/imagen-4.0-generate-001 |  | 001 | Imagen 4 | 480 | 8192 | predict | not_for_pipeline |
| models/imagen-4.0-ultra-generate-001 |  | 001 | Imagen 4 Ultra | 480 | 8192 | predict | not_for_pipeline |
| models/imagen-4.0-fast-generate-001 |  | 001 | Imagen 4 Fast | 480 | 8192 | predict | not_for_pipeline |
| models/veo-2.0-generate-001 |  | 2.0 | Veo 2 | 480 | 8192 | predictLongRunning | not_for_pipeline |
| models/veo-3.0-generate-001 |  | 3.0 | Veo 3 | 480 | 8192 | predictLongRunning | not_for_pipeline |
| models/veo-3.0-fast-generate-001 |  | 3.0 | Veo 3 fast | 480 | 8192 | predictLongRunning | not_for_pipeline |
| models/veo-3.1-generate-preview |  | 3.1 | Veo 3.1 | 480 | 8192 | predictLongRunning | not_for_pipeline |
| models/veo-3.1-fast-generate-preview |  | 3.1 | Veo 3.1 fast | 480 | 8192 | predictLongRunning | not_for_pipeline |
