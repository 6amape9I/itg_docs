PROMPT_VERSION: tagging_v2_compact

Return only compact JSON. No markdown. No explanations.

Output shape:

{
  "docs": [
    {
      "d": "DOC_ID",
      "e": [
        {
          "s": "surface",
          "ru": "Russian canonical candidate",
          "t": "entity_type",
          "r": "article|context|folder",
          "c": 0.93,
          "q": "short exact quote"
        }
      ]
    }
  ]
}

Rules:

1. Extract only main standalone medical entities.
2. Do not extract every medical word.
3. Do not extract incidental examples as article entities.
4. Use `drug_trade_name` only for commercial/trade product names.
5. Use `drug_class` for classes such as antibiotics, macrolides, fluoroquinolones, beta-lactams.
6. Use `biological_substance` for lysozyme, interferons, properdin, fibronectin and similar substances.
7. Use `immunobiological_preparation` for vaccines, sera, immunoglobulins as preparation types.
8. Use `microorganism` for bacteria, viruses, prions, viroids, fungi, protozoa and concrete species/genera.
9. Use `cell_or_biological_structure` for cell wall, nucleoid, ribosomes, T cells, B cells, NK cells.
10. Use `diagnostic_method` for diagnostic and lab methods.
11. Wide structural entities should be `r = folder` or `r = context`, not `article`, unless the document is truly about that broad entity.
12. `q` must be a continuous exact substring from the document text.
13. Do not paraphrase `q`.
14. Do not join distant fragments in `q`.
15. Do not use ellipsis in `q`.
16. Recommended `q` length: 40-180 characters.
17. If no exact quote exists, do not return the entity.

Allowed `t`:

disease, drug_trade_name, drug_class, supplement, immunobiological_preparation, biological_substance, symptom, medical_device, procedure, diagnostic_method, organ_or_body_system, microorganism, cell_or_biological_structure, medical_concept, instruction, other

Allowed `r`:

article, context, folder
