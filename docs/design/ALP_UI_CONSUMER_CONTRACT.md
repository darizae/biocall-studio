# Trainer as an `alp-ui` consumer — verified library contract

**Source inspected:** uploaded `alp-ui` 0.1.0a0 checkout, public `src/alp_ui/components/__init__.py`, `docs/components.md`, `gallery/showcase.py`, and `docs/images/showcase.png`. A local **visual evidence snapshot** from that checkout is [showcase PNG](references/alp-ui-showcase.png), with [form controls](references/alp-ui-gallery-fields.png) and [data controls](references/alp-ui-gallery-data.png). In development the **actual source** is sibling `../alp-ui` (when available), not this snapshot. Recheck API/installed wheel before implementation and record the inspected commit SHA. Library owns themed presentation, **Trainer** owns all domain decisions, navigation, data, worker progress and persistence.

## API crosswalk / ownership

| Prototype need | Public `alp-ui` API (actual) | Trainer responsibilities / important non-feature |
|---|---|---|
| Select Collection | `FolderPicker(label="Collection folder")`, `.folderChanged(str)`, `.folderPath()`, `.setFolderPath(str)` | Native directory dialog is **inside** FolderPicker. Cancellation leaves previous value unchanged. Selected path is **not** validated, scanned, stored or resolved by the component. Controller consumes signal and keeps last verified Collection separate from pending selection. Do **not** use a second hand-built QFileDialog for this surface. |
| Brief help beside mining, splits and hyperparameters | `HelpHint(help_text, subject="...")`, `.setHelpText(...)` | Help text is concise and factual; native hover tooltip and keyboard Space/What's This; accessible description persists. Full instructions route to Wiki. Label/field focus buddy remains consumer-owned. |
| Source lists, validation issues, Datasets/Models/Runs | `DataTable(model=QAbstractItemModel)` | Lazy/paged, application-owned Qt model; selection/filter/proxy logic and accessible table name belong to Trainer; no per-row widgets. |
| Dataset/Training config | `NumberInput(kind="integer"/"decimal", minimum=..., maximum=..., value=..., label=...)`, `SelectInput(items=..., label=...)`, `CheckBox`, `Switch` | Own validation, scientific units, help placement, error states, enabled/disabled states. No invented magic `setUnit` API. |
| Actions and busy states | `Button(text, variant="primary"/"secondary"/"outline"/"danger")`, `.setLoading(bool)` | Only enable when valid; loading label does not start work; cancellation is controlled by application/Worker. |
| Artifact summaries and statuses | `Text(role="title"/"heading"/"body"/...)`, `Card.content_layout`, `Badge(intent=...)`, `Alert(..., intent=...)`, `EmptyState(...)`, `ProgressBar` | Use semantically correct status and actual counts, accessible alternatives and bounded update rate. |
| CNN loss history | `Plot(kind="line", x_label="Epoch", y_label="Loss")`, `.setLines({"Train": [(epoch, loss),...], "Validation": [...]})` | Pass **finite measured** real numeric loss, exclude/label absent epochs, keep full numeric summary/table for accessibility. No implied precision or fabricated metrics. |
| RF feature importances | `Plot(kind="bar", x_label="Feature", y_label="Importance")`, `.setBars([("feature", importance),...])` | Supply ordered actual feature names/values and separate readable numeric table; undefined importances show explanatory state instead of invented zeros. |
| UI frame and sidebar | ordinary `QMainWindow`, `QWidget`, Qt layouts and model/view, **not** a public Sidebar/navigation component | Borrow composition/density/typography guidance from sibling `gallery/showcase.py`. No custom global stylesheet cloning `alp-ui` internals. |

`Plot` supports **only** `kind="line"` with ordered mapping of finite `(x,y)` points, or `kind="bar"` with ordered finite `(label,value)` pairs. It does not implement waveform/spectrogram/ROC heatmap, live stream, smoothing, tooltips per point, exporting or metric calculation. Use native alternatives only when backed by an actual spec; do not add plotting frameworks to solve nonexistent needs.

## Visual and accessibility gate

The **HTML prototype defines navigation, state transitions, content hierarchy and interaction intent**; sibling `gallery/showcase.py` / `docs/images/showcase.png` defines credible native `alp-ui` styling/composition. The agent should open/inspect both; reproduce comparable native screen states, not fake a pixel-perfect CSS port. At minimum compare initial Select, Reading, Collection overview/validation errors, Builder/config, Run, Model detail, Wiki and empty lists at normal/compact windows. Use real Qt screenshots and recorded review against prototype `*-preview.png`; exercise keyboard Tab order, native folder cancel, disabled state, scroll, labels, help access, plot numeric alternatives and 100%/150% DPI where native environment exists. Any deliberate discrepancy requires short explanation and an acceptance check.

### Native API example, **illustrative only**

```python
from alp_ui.components import FolderPicker, HelpHint, Plot

folder = FolderPicker(label="Collection folder")
folder.folderChanged.connect(controller.request_collection_scan)

margin_help = HelpHint("Protects source-time around positives during negative mining.", subject="Exclusion margin")

loss = Plot(kind="line", x_label="Epoch", y_label="Loss")
loss.setLines({"Train": [(1, 0.78), (2, 0.53)], "Validation": [(1, 0.82), (2, 0.64)]})
# Values shown above demonstrate API shape; NEVER use them as native Run evidence.
```

**Library compatibility:** source checkout is pre-release; pin observed SHA + built-wheel hash for packaging, and report incompatibility explicitly. Library tests/exports remain in `../alp-ui`; Trainer integration tests assert composition and user-facing flow, not re-test every theme primitive.
