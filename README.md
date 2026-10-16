# TenderLens

**Local-first, evidence-backed analysis of procurement PDFs.**

![Python](https://img.shields.io/badge/Python-3.11%2B-blue) ![License](https://img.shields.io/badge/license-AGPL--3.0-orange)

TenderLens is a Python + Flask + SQLite application that helps reviewers work
through procurement document packs. It extracts *candidate* conditions from
text PDFs, compares wording across documents, and lets a person examine the
source evidence and record decisions. The PDF processing and web interface run
locally; documents are not sent to an external service.

### Features

- Multiple local projects; import up to 10 text PDFs per batch (30 MB each).
- Extraction of selected deadlines, SRO requirements, advances, payment terms,
  quantities and warranties using rules designed for Russian procurement text.
- Cross-document review questions for contradictory or differing wording.
- Source traceability: original file SHA-256, page, excerpt and text coordinates.
- SQLite history of analyses and append-only human reviews.
- Local Russian-language browser UI; ZIP exports with JSON, CSV and HTML.
- Reproducible synthetic fixtures, tests, security-focused input handling and
  a development-only quality/evidence-checking toolkit.

### Quick start

Python **3.11+** is required. Internet access is only needed to install
Python dependencies on first setup; actual PDF processing is local.

```bash
bash RUN_LOCAL_TESTS.sh
bash RUN_LOCAL_DEMO.sh
```

Open **http://127.0.0.1:8765/**. To stop the server, press `Ctrl+C`.
The local demo preloads three **fictional, generated** PDF documents. To run
against another allowed text-PDF pack, create a project in the UI and import it.
`RUN_LOCAL_DEMO.sh` uses a new temporary SQLite workspace on each run.
Do not expose the Flask development server outside your local machine.

### Demonstration

In the fictional pack, the notice requires SRO membership and mentions a
20% advance with a 10-working-day payment period, while the draft contract
says membership and advance are not required and payment is due within
20 working days. TenderLens reports **three review questions**, with links
to the passages in both files. The reviewer decides what they mean.

### Architecture

`PDF -> bounded PyMuPDF extraction -> evidence-backed candidate fields ->
cross-document questions -> SQLite -> loopback Flask UI -> export`

- `tender_screen/domain_pipeline.py`: candidate extraction and supporting evidence.
- `tender_screen/storage.py`: projects, versions, reviews and SQLite persistence.
- `tender_screen/web/`: Flask API, worker and local UI.
- `qa/`: development-only evaluation and source integrity checks.

See [Architecture](docs/ARCHITECTURE.md),
[Demo guide](docs/DEMO_GUIDE_RU.md) and
[Quality status](docs/QUALITY_STATUS.md).

### Limitations

**This is an experimental local research tool, not legal advice.**
There is no OCR for scanned documents without text, no integration with
procurement exchanges, no determination of legally effective contract
revisions, and no automated decision whether to bid. Results require human
verification. **Independent accuracy on unseen procurement documents has not
been measured.** Synthetic regression results must not be presented as an
independent benchmark. The local UI is not a public production server.

No real procurement documents, client files, private G4 corpus, gold/holdout,
credentials or user databases are included in this repository. Fixture PDFs
are generated as fictional development examples.

### License

TenderLens original code and documentation: **GNU Affero General Public License
v3.0 only (AGPL-3.0-only)**, © 2026 Dito Bukia. See [LICENSE](LICENSE).

PyMuPDF/MuPDF are separately developed and offered under AGPLv3 or commercial
licensing; Flask is BSD-3-Clause. Dependencies are installed separately with
pip, not vendored into this source repository. See
[Third-party notices](docs/THIRD_PARTY_NOTICES.md). Network users of AGPL
versions should be offered the corresponding source code as required by the
license; get legal advice for deployment-specific questions.
