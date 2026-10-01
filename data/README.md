# Dataset Documentation

## Source
English Wikipedia articles about Olympic events (Summer & Winter, 1988–2023).
Licensed [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/).

## Files

| File | Records | Size | Description |
|------|---------|------|-------------|
| `Dataset/corpus/corpus.jsonl` | 2,951 | ~22 MB | Document corpus |
| `Dataset/questions/eval_public.jsonl` | 100 | ~36 KB | Public evaluation questions with answers |
| `Dataset/questions/eval_hidden.jsonl` | 50 | ~8 KB | Hidden evaluation questions (no answers) |
| `data/splits.json` | — | — | Dev/val/test splits (seed 42) |

## Corpus Schema (`corpus.jsonl`)
```json
{
  "doc_id": "Q303623",
  "title": "Canoeing at the 2012 Summer Olympics — Men's K-2 1000 metres",
  "url": "https://en.wikipedia.org/wiki/...",
  "wikidata_qid": "Q303623",
  "wikipedia_pageid": 35771859,
  "approx_tokens": 704,
  "text": "..."
}
```

- **doc_id**: Wikidata QID (unique, stable identifier)
- **title**: Wikipedia article title
- **text**: Plain text with infobox data and results tables
- Content includes: event infoboxes (gold/silver/bronze, venue, date, competitors, nations), competition format descriptions, schedules, and detailed results tables

## Question Schema (`eval_public.jsonl`)
```json
{
  "qid": "pub-001",
  "question": "How many biathlon events at the 2018 Winter Olympics had more than 73 competitors?",
  "qtype": "aggregation",
  "answer_named_in_question": false,
  "guess_baseline": 0.0,
  "gold_doc_ids": ["Q47091419", "Q47105341", ...],
  "answer_verified": true,
  "answer": ["5"]
}
```

## Question Type Distribution

### Public (100 questions)
| Type | Count | Description |
|------|-------|-------------|
| multi_hop | 28 | Chain 2+ facts across documents |
| temporal | 22 | Time reasoning (before/after/sequence) |
| aggregation | 21 | Count/sum across multiple documents |
| lookup | 19 | Single-document fact retrieval |
| superlative | 10 | Find max/min across a set |

### Hidden (50 questions)
| Type | Count |
|------|-------|
| aggregation | 15 |
| superlative | 10 |
| multi_hop | 10 |
| temporal | 8 |
| lookup | 7 |

## Splits (`data/splits.json`)
Stratified by `qtype`, seed 42:
- **dev**: 60 questions (for tuning)
- **val**: 20 questions (for checking, never tune on this)
- **test**: 20 questions (untouched until final report)

## Key Observations
1. **Domain-specific**: All documents are about Olympic events. Entity types are predictable: Athlete, Event, Country/NOC, Venue, Games, Sport.
2. **Aggregation questions reference many documents**: Some `gold_doc_ids` lists have 40+ entries — requires exhaustive retrieval.
3. **Temporal questions need date arithmetic**: "Before 2016" → "2012 Olympics".
4. **Multi-hop requires entity linking**: Venue → Event → Winner chains.
5. **Encoding issues**: Some names contain encoding artifacts (e.g. control characters). Handle gracefully.
6. **Answer is always `list[str]`**: Usually length 1, occasionally multi-answer.
