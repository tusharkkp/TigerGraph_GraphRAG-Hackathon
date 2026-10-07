# Structured Parser Factual Accuracy Report

**Overall Factual Accuracy:** 88.4% (61/69)

## Accuracy by Field Type
| Field | Evaluated Questions | Exact Matches | Accuracy % |
|---|---|---|---|
| `gold_medalist` | 50 | 42 | **84.0%** |
| `nations` | 19 | 19 | **100.0%** |

## Sample Question Audits
| QID | Field | Extracted Value | Gold Answer | Result |
|---|---|---|---|---|
| pub-002 | `gold_medalist` | Chen Ding | ['Chen Ding'] | PASS |
| pub-005 | `gold_medalist` | Naim Süleymanoğlu | ['Naim Süleymanoğlu'] | PASS |
| pub-006 | `gold_medalist` | Rafaela Silva | ['Rafaela Silva'] | PASS |
| pub-007 | `gold_medalist` | Renaud Lavillenie | ['Renaud Lavillenie'] | PASS |
| pub-009 | `nations` | 26 | ['26'] | PASS |
| pub-011 | `gold_medalist` | Martina Sáblíková | ['Martina Sáblíková'] | PASS |
| pub-013 | `gold_medalist` | Allison Schmitt | ['Allison Schmitt'] | PASS |
| pub-014 | `gold_medalist` | Carolina Marín | ['Carolina Marín'] | PASS |
| pub-015 | `gold_medalist` | Dani King | ['Dani KingLaura TrottJoanna Rowsell'] | FAIL |
| pub-016 | `gold_medalist` | Johannes Thingnes Bø | ['Arnd Peiffer'] | FAIL |
| pub-017 | `gold_medalist` | Yi Siling | ['Yi Siling'] | PASS |
| pub-018 | `gold_medalist` | Kevin Jackson | ['Kevin Jackson'] | PASS |
| pub-022 | `gold_medalist` | Ayumi Tanimoto | ['Ayumi Tanimoto'] | PASS |
| pub-023 | `gold_medalist` | Hwang Young-Cho | ['Hwang Young-Cho'] | PASS |
| pub-025 | `nations` | 23 | ['23'] | PASS |
| pub-026 | `gold_medalist` | Jaroslav Kulhavý | ['Jaroslav Kulhavý'] | PASS |
| pub-028 | `gold_medalist` | Michael Phelps | ['Michael Phelps'] | PASS |
| pub-029 | `nations` | 28 | ['28'] | PASS |
| pub-030 | `gold_medalist` | Emese Szász | ['Emese Szász'] | PASS |
| pub-031 | `gold_medalist` | Dmitry Berestov | ['Dmitry Berestov'] | PASS |
| pub-032 | `nations` | 34 | ['34'] | PASS |
| pub-034 | `nations` | 23 | ['23'] | PASS |
| pub-035 | `nations` | 30 | ['30'] | PASS |
| pub-036 | `gold_medalist` | Zou Shiming | ['Zou Shiming'] | PASS |
| pub-038 | `gold_medalist` | Pyrros Dimas | ['Pyrros Dimas'] | PASS |
