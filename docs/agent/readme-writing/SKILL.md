---
name: readme-writing
description: Write and review concise, welcoming, accurate GitHub READMEs for BioCall Studio and researcher-facing scientific software without turning the homepage into an audit report.
argument-hint: "<README path> [intended audience or change]"
disable-model-invocation: true
---

# README writing — researcher-first product introduction

Use this skill for new or revised public GitHub README files. **The README is a product front door, not a release checklist, test report, specification, legal analysis, or scientific provenance ledger.** Write for a researcher encountering the application for the first time.

For BioCall Studio, read the actual root `README.md`, [product vision](../../VISION.md), [development instructions](../../DEVELOPMENT.md), and the relevant existing visual evidence before editing. Use only the source contracts needed to verify claims. Do not reload the whole historical spec archive.

## Reader questions and information hierarchy

In order, help a newcomer answer:

1. **What is this?** Give the product name, a one-sentence value proposition, and a short plain-language explanation of who it helps.
2. **What can I do with it?** Show its primary workflow with concrete verbs, user-visible results, and a few carefully chosen authentic images.
3. **How do I try it?** Provide the shortest working entry point and link to maintained installation instructions.
4. **Where can I learn more?** Link to a small set of useful researcher and contributor guides.
5. **What should I know about availability and licensing?** State only material limitations in one or two short factual sentences.

Put the product and screenshots before contributor internals. The reader should understand the purpose and core workflow after a quick scan.

## Write for people, not acceptance gates

- Prefer **plain, active language**: “Listen to detected calls and mark the ones you want to keep,” not “consume a versioned eligible-candidate projection.”
- One short paragraph per capability. Limit detailed algorithms, data schemas, cache keys, queue behavior, precise test counts, commit SHAs, wheel hashes, CI matrices, and release evidence to linked technical documents.
- Avoid defensive narration: “not fabricated,” “this screenshot is not installer proof,” and “these candidates are not negatives” are generally **not README copy**. Do not repeat legal or qualification caveats under each image.
- Never exaggerate: avoid “accurate,” “production-ready,” “fully verified,” or “available for download” without matching evidence. Keep scientific terms when they help the intended reader (e.g., CNN, Random Forest, Raven TSV); explain unfamiliar terms in context.
- Use informative headings, restrained bolding, short sentences, and generous whitespace. Do not cram a list of implementation features into the opening paragraph.
- The README does not have to advertise every feature. Link to user documentation for the details.

## Images: show the real product

- Reuse **tracked, genuine native screenshots**, not stock art, generated UI, browser prototypes, fabricated data, or generic fresh captures. BioCall Studio's release-facing screenshots and provenance live in [release-real-data](../../design/evidence/release-real-data/README.md), with JSON metadata in the same folder.
- Aim for **three strong workflow images** rather than a screenshot dump. For BioCall Studio: Train `02a-train-training-in-progress.png`, Detect `05-detect-results.png`, and Review `09-review-one-by-one.png`. The tracked BioCall Studio header is `assets/branding/on-background/readme-header.png`.
- Use GitHub-supported relative image paths, consistent widths (around 900 px when appropriate), and descriptive alt text saying what is visible.
- Keep technical screenshot provenance with its existing capture metadata, referenced through a single optional gallery/documentation link. **Do not copy raw specimen counts, identifiers, SHA-256 hashes, training run percentages, or the capture methodology into the product story.**
- Do not edit, regenerate, crop, or replace an original evidence image without explicit authorization and corresponding provenance review.

## Truthful availability and licensing

- Source-run instructions may be shown when verified. Link to `docs/DEVELOPMENT.md` for platform-specific setup and dependency pin/hash verification rather than embedding a long developer installation log.
- Never imply that a native installer, signed binary, tagged release, field validation, or full acceptance suite exists because screenshots or source tests exist.
- **Do not invent an application license or badge.** If an actual license has not been declared, a simple “License not yet specified” note is sufficient. Keep third-party redistribution analysis in the release process/legal documentation.
- Check that each link points to a tracked target. A README link to an absent release, binary, document or license is worse than omitting it.

## Recommended outline

```markdown
[Real product header or logo]

# Product name
One-sentence user benefit.
Short explanation of the problem it solves.

## Explore the workflow
### Train
One paragraph + real screenshot
### Detect
One paragraph + real screenshot
### Review
One paragraph + real screenshot

## Getting started
Real prerequisites, link to installation guide, shortest launch command.

## Documentation
A few links to user guides and contributor instructions.

## License
One concise and factually verified statement.
```

Adapt the outline to the software and audience; do not fill sections with filler. README text should not duplicate entire guides.

## Editing and review procedure

1. **Inspect before writing.** Check the live branch, root README, actual product names/actions, image files, links, and current installation/release status. Do not infer what a screenshot shows from its filename alone.
2. **Draft from user value.** Lead with purpose; trim anything that sounds like a developer handoff, QA disclaimer, internal spec, or changelog. Read the first 200 words as someone who has never seen the repository.
3. **Keep documentation layered.** Move proof, provenance, source-version pins, license analysis and detailed instructions to appropriate existing docs. Preserve those records; never silently delete evidence.
4. **Verify.** Check local links and asset paths with `python scripts/audit_docs.py`; when test indexes are touched, also run `python scripts/audit_test_ids.py`. Inspect GitHub Markdown rendering and alt text; confirm no invented release/license claims. The docs audit does not validate external URLs, heading anchors or the actual native application.
5. **Report only the documentation changes.** Do not claim source tests, native installers or release qualification from an editorial change.

## Quick self-review

- Could a new researcher explain the tool's purpose in one sentence?
- Do the real screenshots help them understand **Train → Detect → Review**?
- Is the shortest viable first-run instruction easy to find?
- Would removing a paragraph of hashes, counts, implementation caveats or test evidence make the README clearer? If yes, move it to linked docs.
- Are all images authentic, all links valid, all limitations accurately stated and the license note truthful?
- Does the page invite exploration rather than try to preempt every audit objection?
