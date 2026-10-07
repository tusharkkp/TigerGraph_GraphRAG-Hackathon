# Two-Stage Judge Calibration Report

**Overall Calibration Accuracy:** 100.0% (20/20)

## Calibration Test Cases

| QID | Expected Stage | Actual Stage | Expected Verdict | Actual Verdict | Reason | Status |
|---|---|---|---|---|---|---|
| cal-01 | Stage 1 | Stage 1 | PASS | PASS | `Stage 1 deterministic normalized match` | **PASS** |
| cal-02 | Stage 1 | Stage 1 | PASS | PASS | `Stage 1 deterministic normalized match` | **PASS** |
| cal-03 | Stage 1 | Stage 1 | PASS | PASS | `Stage 1 deterministic normalized match` | **PASS** |
| cal-04 | Stage 1 | Stage 1 | PASS | PASS | `Stage 1 deterministic normalized match` | **PASS** |
| cal-05 | Stage 1 | Stage 1 | PASS | PASS | `Stage 1 deterministic normalized match` | **PASS** |
| cal-06 | Stage 1 | Stage 1 | PASS | PASS | `Stage 1 deterministic normalized match` | **PASS** |
| cal-07 | Stage 1 | Stage 1 | PASS | PASS | `Stage 1 deterministic normalized match` | **PASS** |
| cal-08 | Stage 1 | Stage 1 | PASS | PASS | `Stage 1 deterministic normalized match` | **PASS** |
| cal-09 | Stage 1 | Stage 1 | PASS | PASS | `Stage 1 deterministic normalized match` | **PASS** |
| cal-10 | Stage 1 | Stage 1 | PASS | PASS | `Stage 1 deterministic normalized match` | **PASS** |
| cal-11 | Stage 2 | Stage 2 | PASS | PASS | `The candidate correctly identifies Chen Ding as the winner of the men's 20 km wa` | **PASS** |
| cal-12 | Stage 2 | Stage 2 | PASS | PASS | `The candidate correctly identifies that 26 nations participated, matching the go` | **PASS** |
| cal-13 | Stage 2 | Stage 2 | PASS | PASS | `The candidate correctly identifies the venue, omitting only the word 'Internatio` | **PASS** |
| cal-14 | Stage 2 | Stage 2 | PASS | PASS | `The candidate correctly identified Carolina Marin as the gold medalist in women'` | **PASS** |
| cal-15 | Stage 2 | Stage 2 | PASS | PASS | `The candidate correctly identifies the total number of athletes as 30, matching ` | **PASS** |
| cal-16 | Stage 2 | Stage 2 | FAIL | FAIL | `The candidate incorrectly identified Usain Bolt as the winner of the men's 20 km` | **PASS** |
| cal-17 | Stage 2 | Stage 2 | FAIL | FAIL | `The candidate provided 42, which contradicts the correct answer of 26.` | **PASS** |
| cal-18 | Stage 2 | Stage 2 | FAIL | FAIL | `The candidate incorrectly identified the silver medalist as the gold medalist. R` | **PASS** |
| cal-19 | Stage 2 | Stage 2 | FAIL | FAIL | `The candidate incorrectly identified Wembley Stadium as the sailing venue, where` | **PASS** |
| cal-20 | Stage 2 | Stage 2 | FAIL | FAIL | `The candidate provided an incorrect number of competitors (12 instead of 34).` | **PASS** |
