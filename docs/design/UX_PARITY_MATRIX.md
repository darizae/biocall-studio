# BioCall Studio — UX parity matrix

**Native visual anchor:** current Train Python UI + genuine screenshots under `docs/design/evidence/spec-*-native/`; `../alp-ui/gallery/showcase.py` and installed public components. **New interaction reference:** ST-01's `docs/design/prototypes/studio-detect/` once accepted. Train must retain its present navigation, controls and behavior. Browser data/progress are illustrative, never scientific proof.

| Surface | Implemented ST-01 route and reachable Demo states | Verification when implemented natively |
|---|---|---|
| Studio launchpad | `#studio`; keyboard buttons for Train, Detect and Review; suite-level branding; local/read-only boundary | ST-02 Qt visual + navigation tests |
| Train entry/return | `#train-reference`; genuine `spec-01-native/select.png` and `spec-05-native/train-cnn.png`; explicit native-entry boundary; return to `#studio` | ST-02 actual Train regression + native screenshots |
| Review placeholder | `#review`; Coming later only; return to `#studio` | Remains a placeholder until separately specified |
| Detect setup | `#detect/setup`; independent `#model-state` values `valid`, `loading`, `empty`, `incompatible`, `missing`; `#root-state` values `valid`, `loading`, `empty`, `invalid`, `changed`, `missing`; readiness alert and disabled Start | ST-03/05/08 native integration |
| Source inventory | `#detect/recordings`; `#inventory-state` values `ready`, `scanning`, `cancelled`, `invalid`, `stale`, `missing`; hierarchy, folder decisions, included/undecided/excluded/invalid rows, duplicate, progress, cancel and rescan | ST-04 real-WAV integration |
| Detection configuration | `#detect/setup`; three concise CNN controls, keyboard/click HelpHints, collapsed `details` section; RF absent as a recording-wide option | ST-05/07 scientific and Qt tests |
| Detection Run | `#detect/run`; `#run-state` values `idle`, `preparing`, `running`, `cancelling`, `cancelled`, `interrupted`, `failed`, `completed`, `file-errors`; Run header persists across routes | ST-06/07 real Worker tests |
| Results | `#detect/results`; `#result-state` values `populated`, `empty`, `error`; recording list, source-time interval table, provenance, source navigation boundary | ST-08 Qt/model tests and native screenshots |
| Second-layer RF | `#detect/results`; compatible/incompatible RF choices; derived `rf-demo-001` with accepted/rejected/unscored states and selectable unchanged `cnn-demo-001` parent | ST-09 real science and persistence tests |
| Corpus export | `#detect/export`; `snippets`, `concat`, `both`; explicit destination and source-time/output mapping; `ready`, `conflict`, `stale`, `cancelled`, `error`, `success`; Show in folder boundary | ST-10 audio/parity/Qt integration |
| Path relinking | `#detect/recordings`; `stale`/`missing` inventory states, missing/proposed roots, inventory comparison confirmation, cancel, explicit rebind + rescan | ST-03 freshness and permission tests |

**Deliberate ST-01 boundaries:** browser buttons fill clearly marked Demo paths instead of opening native file dialogs, because JavaScript cannot verify Model packages or source inventories. Train remains a screenshot-backed reference rather than a browser clone. Result audio playback/waveforms are omitted: Results are metadata-first, while source navigation is represented as an explicit boundary. Export demonstrates plans and outcomes without materializing audio. All illustrative values remain labelled Demo.

**Evidence:** the prototype uses the genuine Train screenshots above. The environment used for ST-01 had no connected browser, so no prototype screenshot is recorded as browser evidence; use [prototype acceptance](PROTOTYPE_ACCEPTANCE.md) and the route/state IDs in this table for the required interactive review. Browser interaction does not establish scientific or native correctness.
