# Quality status (not an independent benchmark)

- Allowed evidence: original FAST DEV development regression on synthetic or
  previously known development PDFs. No gold/holdout/G4 files were tested.
- The M09 scoring implementation is present in `qa/evaluate.py` and unit-tested.
  Reports expose TP/FP/FN, numerator/denominator, abstention and unknown labels.
- `qa/dev_run.py` exercises a 3-PDF fictional package with 9 labelled
  candidates and 3 known question types; see `DEV_METRICS.json` when run.
- The evidence checker validates each source SHA linkage, physical page,
  normalized text span, exact match, quote inclusion and bbox sanity.
- **M09 independent holdout evaluation: BLOCKED**. No human-reviewed frozen
  independent labels, no blind first pass, no sample-size based uncertainty or
  independently audited false-positive rate. No independent precision/recall.
- Human usability pilot of 2-3 external users: **NOT PERFORMED**. Scripted
  developer API tests are not substitutes for user testing.
- Flask tests need target Mac with Flask installed. If skipped, acceptance is
  blocked; they were not runnable in the source build container.
- Neither positive regression cases nor synthetic metric values may be
  described as deployment-grade quality or accuracy on unseen tenders.
