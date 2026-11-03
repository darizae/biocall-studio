# Prototype/spec synchronization — 3 November 2026

This owner-review proposal replaces the previous audited prototype. All scientific and native implementation requirements remain in their owning RV-01–RV-08 stages; the design is **not owner-approved**.

Changed Review planning documents (relative to the original supplied archive):

- `docs/specs/review/README.md` — fixed shortcut/tooltip coverage index.
- `docs/specs/review/RV-03-audio-and-spectrograms.md` — link to the RV-05 keyboard/tooltip source of truth.
- `docs/specs/review/RV-05-native-review-ui.md` — fixed F/D/S and J/K/L bindings, arrow/Space and Undo, focus rules, exact tooltips, List search and REV-05 storage wording alignment.
- `docs/specs/review/RV-08-qualification.md` — explicit native shortcut/focus/tooltip qualification.

New/updated prototype: `index.html`, `prototype.js`, `styles.css`, `README.md`, `PROTOTYPE_ACCEPTANCE_CHECKLIST.md`, `SPEC_COVERAGE_AUDIT.md` and browser evidence. All other Review specifications are byte-identical to the original archive. No native Python code, scientific contracts, test indexes or unrelated UX/Train/Detect files changed.

**Approval boundary:** the existing RV-05 HelpHints and consequential warning copy remain unchanged. The proposed keyboard bindings, new tooltip texts, Gallery/List inspect tooltip and recording-search label require your inspection and sign-off. Real `alp-ui`, native accessibility, audio and scientific qualification remain stages RV-03–RV-08.
