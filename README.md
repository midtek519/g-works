# G-Works

G-Works is a local desktop suite for Rutgers Mathematics instructors.

| App | Purpose | Chrome companion |
| --- | --- | --- |
| G-Whiz | Course materials, questions and handouts | G-View |
| G-Scope | Scans, rubrics and grading | G-Rater |
| G-Vault | Course grades, recommendations and integrity records | G-Report |

This is the reviewed program-source snapshot for release **1.0.0-beta.3.3**.
`SOURCE_MANIFEST.json` records the origin and SHA-256 of every exported file.
Installable releases supply the required Python, desktop and PDF runtimes and
optional course packages. Those dependencies, third-party vendor files, course
content, compiled binaries and user records are excluded from this source tree.

G-Scope currently requires G-Whiz. G-Vault starts with empty libraries and lets
each instructor configure their profile and course databases. The Rutgers
Mathematics framework and institutional letterhead remain available.

The shared application source is in `Shared/TeachingApp/Current`; app entries and
Vault module sources use their release-package layouts under `Apps`.
Build the Windows launcher with `Maintenance/Installer/Hub/build.ps1`.
This source snapshot is not a complete offline installer build environment:
release assembly and signing require the matching runtime packages and signing
configuration. No signing secrets or installed user configuration are included.

To create a new snapshot from a reviewed local release, run:

```powershell
python Maintenance/Installer/export_sources.py --release <release-folder> --destination <new-snapshot-folder>
```

The exporter only reads approved public package inputs and explicitly named
launcher sources. It refuses existing output directories and does not push Git.
