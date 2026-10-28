# Agent routing

Read `AGENTS.md` → [stage sequence](../IMPLEMENTATION_SEQUENCE.md) → **one active spec**. Do not preload future specs or entire sibling repositories. Check Git state and actual implementation before choosing work.

| Task | Authority |
|---|---|
| Current stage: native Studio shell and Train integration | [ST-02 native shell](../specs/ST-02-native-shell.md) |
| Future Studio/Detect stages | [ST-03…ST-11 outcomes](../IMPLEMENTATION_SEQUENCE.md); write a focused spec only when that stage is next |
| New Studio/Detect UX | [UX parity matrix](../design/UX_PARITY_MATRIX.md), [prototype acceptance](../design/PROTOTYPE_ACCEPTANCE.md) |
| Detect data, model, lineage, export | [Detect contract](../PREDICTION.md) |
| Existing Train implementation | Relevant sections of [architecture](../ARCHITECTURE.md), [Model export](../science/MODEL_EXPORT_CONTRACT.md), and actual Python code |
| Qt components/theme | [alp-ui mapping](../design/ALP_UI_CONSUMER_CONTRACT.md), installed `../alp-ui` public API and `gallery/showcase.py` |
| Unit/integration case selection | Relevant indexed entries in [unit index](../UNIT_TESTING.md), [integration index](../INTEGRATION_TEST_BEHAVIORS.md), [test data](../INTEGRATION_TEST_DATA.md) |
| Scientific upstream interfaces | [source map](SOURCE_MAP.md), then exact involved `../bioacoustics-dl-toolbox` or `../alpaca-pipelines` code |
| Git and delivery | [Git delivery](GIT_DELIVERY.md) |
| Platform packaging | [Release process](../RELEASE_PROCESS.md), only at ST-11 or an explicitly approved release stage |

**Execution:** inspect → test/implement only owned scope → verify observed behavior → update impacted docs/evidence → commit and stop. An absent historical document is not a reason to invent its content.
