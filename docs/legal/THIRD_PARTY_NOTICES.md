# BioCall Studio — third-party notices and redistribution gate

**Candidate date: 2026-11-08. This file is an attribution and compliance checklist,
not a license grant for BioCall Studio and not an authorization to distribute binaries.**
BioCall Studio has no declared application-level license or root `LICENSE` as of
this candidate. No GPL/MIT application badge or package `License` metadata is asserted.

## Upstream components used by the proposed `0.1.0a1` candidate

| Component | Published artifact | License and obligations |
|---|---|---|
| [bioacoustics-dl-toolbox](https://github.com/darizae/bioacoustics-dl-toolbox/releases/tag/v0.3.0) | `v0.3.0`, tag target `7027bd84cc5a44a27bf201332af540f090c38365` | **GPL-3.0-only**. Preserve its `LICENSE` and `NOTICE.md`, source availability and any GPL obligations for combined distribution; verify compatibility of Studio's as-yet undeclared license before any public binary. |
| [alp-ui](https://github.com/darizae/alp-ui/releases/tag/v0.1.0a1) | `v0.1.0a1`, tag target `41bac72971b96d352da752cc0ff140afe3ac312a` | **MIT**. Retain copyright and MIT text from its `LICENSE`. Its wheel carries fonts and their separate OFL notices. |
| PySide6 / Qt | `PySide6-Addons>=6.11,<6.12` via Studio and `PySide6-Essentials>=6.11,<6.12` via alp-ui | Qt for Python community modules expose LGPLv3/GPLv3 licensing choices, subject to the actual installed modules and versions. Before redistribution confirm permitted path, include legal texts, Qt source route and LGPL user relinking/replacement rights where applicable, and inspect Qt plugins shipped by the freezer. |
| DM Sans / JetBrains Mono | Bundled by published alp-ui wheel | **SIL Open Font License 1.1**. Retain the respective unmodified upstream OFL text and font attribution; see [alp-ui third-party notices](https://github.com/darizae/alp-ui/blob/v0.1.0a1/docs/legal/THIRD_PARTY_NOTICES.md). |

The toolbox retains adapted work from **Christian Bergler et al.,
[ANIMAL-SPOT](https://github.com/ChristianBergler/ANIMAL-SPOT)** (GPLv3);
the audited upstream revision reported in its notice is
`fee8b4ba789947a40b89c03eb6fc61e351115e90`.
Keep that provenance and the toolbox's full notice and license with any
redistribution. Relevant research citation: Bergler et al., *Scientific Reports*
12, 21966 (2022), https://doi.org/10.1038/s41598-022-26429-y.
No ANIMAL-SPOT field data or datasets are included in this application candidate.

## What must be cleared before public installers

1. Owner/legal decision on the **BioCall Studio application license** and whether
   Studio, its linked GPL-3.0-only toolbox and Qt runtime may be distributed together
   on the selected terms. Do not create an inferred root license.
2. Bundle the complete upstream toolbox GPL-3.0 text and attribution, MIT
   copyright/license, Qt/PySide6/Qt-plugin license texts and applicable source,
   relinking/replacement and offer instructions, and font OFL files. Retain the
   upstream wheels' `*.dist-info/licenses` and `alp_ui` font notices rather
   than relying on this summary alone.
3. Validate the actual frozen macOS and Windows dependency closure, plugins,
   native bundle contents, source-availability route and legal review record.
   Record each third-party component in the final manifest/SBOM.
4. Obtain owner approval for public distribution **after** specs 04 and 05
   qualify the immutable same-SHA source, both native installers and final local
   Studio suite.

The source/wheel embeds **this notice** for offline discovery, but it is not a
substitute for the full license documents in the upstream packages and the
future native bundles. See [release process](../RELEASE_PROCESS.md) and
[draft manifest](../releases/v0.1.0a1-manifest.md).
