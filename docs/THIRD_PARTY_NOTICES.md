# Third-party licenses and notices

The application source repository **does not vendor wheels, installed Python
packages, PyMuPDF/MuPDF binaries, or any production procurement PDFs**.
Dependencies are resolved and installed by pip on each user's machine.

| Direct dependency | Pinned version | Upstream license | Upstream source / terms |
| --- | --- | --- | --- |
| PyMuPDF (MuPDF) | 1.28.2 | AGPLv3 or commercial license | https://pymupdf.io/licensing / https://github.com/pymupdf/PyMuPDF |
| Flask | 3.1.2 | BSD-3-Clause (© 2010 Pallets) | https://flask.palletsprojects.com/en/stable/license/ |

Flask's transitive dependencies include Werkzeug, Jinja2, MarkupSafe,
itsdangerous, Click and Blinker. Their own licenses are retained in their
separately installed distributions. Run `python -m pip list` and inspect the
installed package metadata for an environment-specific inventory.

**TenderLens** is licensed under AGPL-3.0-only for the original source. A
project's source license does not relicense separately obtained third-party
libraries, sample fonts or OS libraries. This notice is not legal advice.
