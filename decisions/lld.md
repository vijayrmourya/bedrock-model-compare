# Low-Level Design

Implementation-level specification for every module, data structure, and data flow.

**Related docs:** [architecture.md](architecture.md) (diagrams), [explanation.md](explanation.md) (design rationale)  
**Sibling libraries:** [boto3-helpers](../../boto3-helpers/), [bedrock-tui-helpers](../../bedrock-tui-helpers/)

---

## 1. System summary

| Attribute | Value |
|-----------|-------|
| Purpose | Interactive CLI to benchmark Bedrock foundation models side-by-side |
| Interface | Terminal ([Rich](https://github.com/Textualize/rich) UI) |
| Concurrency | `ThreadPoolExecutor`, max 5 workers |
| Default region | `us-west-2` (override via `AWS_DEFAULT_REGION`) |
| Output | Timestamped Markdown report in `results/` |
| Dependencies | [boto3-helpers](../../boto3-helpers/), [bedrock-tui-helpers](../../bedrock-tui-helpers/), boto3, rich, jinja2 |

---

## 2. Module inventory

| File | Responsibility | Key dependencies |
|------|---------------|------------------|
| `main.py` | Entry point, event loop, result orchestration | `menu`, `inference`, `output`, `boto3_helpers` |
| `menu.py` | 7-step interactive wizard, navigation exceptions | `listing`, `catalog`, `rich`, `bedrock_tui_helpers.probe` |
| `listing.py` | Thin shim — re-exports from bedrock-tui-helpers, owns restricted-IDs | `bedrock_tui_helpers.models`, `bedrock_tui_helpers.probe` |
| `inference.py` | Parallel Bedrock calls, AccessDenied detection | `boto3_helpers.bedrock.runtime`, `listing` |
| `output.py` | Jinja2 Markdown report renderer | `jinja2`, `dataclasses` |
| `catalog.py` | Per-model detail pages, 24h file cache | `boto3_helpers.bedrock.control` |

---

## 3. Data structures

### `ComparisonResult` (inference.py)

```python
@dataclass
class ComparisonResult:
    model_id:      str            # base model ID
    model_name:    str            # human-readable name
    provider:      str            # e.g. "Amazon", "Anthropic"
    invoke_id:     str            # actual ID sent to Bedrock (_invoke_id)
    latency_s:     float          # wall-clock seconds
    input_tokens:  int
    output_tokens: int
    input_cost:    float          # USD
    output_cost:   float          # USD
    total_cost:    float          # input_cost + output_cost
    response_text: str            # model's response
    error:         str | None     # error message if call failed
```

### Model dict (from bedrock-tui-helpers)

Each model dict returned by `list_models()` contains:

| Key | Source | Description |
|-----|--------|-------------|
| `modelId` | Bedrock API | Base model ID |
| `modelName` | Bedrock API | Human-readable name |
| `providerName` | Bedrock API | Provider name |
| `modelLifecycle` | Bedrock API | `ACTIVE` or `LEGACY` |
| `inputModalities` | Bedrock API | Filtered to TEXT-only |
| `outputModalities` | Bedrock API | Filtered to TEXT-only |
| `inferenceTypesSupported` | Bedrock API | `ON_DEMAND`, `INFERENCE_PROFILE`, etc. |
| `size` | Inferred | `XS` / `S` / `M` / `L` / `XL` from model name regex |
| `_in_price` | Pricing table | USD per 1K input tokens |
| `_out_price` | Pricing table | USD per 1K output tokens |
| `_invoke_id` | Computed | Correct invoke ID (may include `us.` prefix) |

---

## 4. Module: `main.py`

### Startup

```python
boto3_helpers.configure(region="us-west-2")
```

Sets the default region for all `get_client()` calls. Override via `AWS_DEFAULT_REGION` env var (env beats `configure()` in the resolution chain defined in [boto3-helpers](../../boto3-helpers/)).

### Event loop

```
while True:
    selected, prompt, ... = run_menu()   # raises GoExit to terminate
    results = run_comparison(...)
    filepath = save_results(...)

    while True:                          # post-run loop
        choice = post_run_menu()
        if choice == "run":   break      # outer loop → new comparison
        if choice == "read":  print_responses(results)
        if choice == "exit":  return
```

---

## 5. Module: `menu.py`

### Navigation exceptions

```python
class GoBack(Exception): pass    # caught by wizard → step -= 1
class GoHome(Exception): pass    # caught by wizard → step = 1
class GoExit(Exception): pass    # propagates to main() → terminate
```

### `_ask()` — central input function

All user input flows through `_ask()`. Handles `b`/`h`/`x` navigation, validation, defaults, and freeform input.

### 7-step wizard

| Step | Configures | Key logic |
|------|-----------|-----------|
| 1/7 | `max_tokens` | Presets (64/128/250/512/1024/2048) or custom 1–10,000 |
| 2/7 | Sampling params | Temperature, Top P, Top K (all optional) |
| 3/7 | `system_prompt` | Optional free text |
| 4/7 | Provider filter | Multi-select from available providers |
| 5/7 | Size filter | XS / S / M / L / XL / All |
| 6/7 | Model selection | Range/list syntax; `r N` fetches catalog page |
| 7/7 | Prompt | Free text (required) |

### Model selection syntax

```
2          single model
1,3        multiple
1-5        range
1,3-5,7    mixed
r 4        view catalog page for model #4
```

---

## 6. Module: `listing.py` (thin shim)

### Owned functionality

```
load_restricted_ids()      → reads results/.restricted_ids.json
save_restricted_id(id)     → appends to results/.restricted_ids.json
```

### Delegated to bedrock-tui-helpers

```
list_models()     → bedrock_tui_helpers.models.list_models()
filter_models()   → bedrock_tui_helpers.models.filter_models()
                    injects restricted_ids = load_restricted_ids() | load_disabled_ids()
```

### Re-exports

| Symbol | Origin |
|--------|--------|
| `MODEL_PRICING`, `SIZE_ORDER`, `get_pricing`, `providers`, `sizes_summary`, `to_invoke_id` | `bedrock_tui_helpers.models` |
| `load_disabled_ids`, `ensure_probe` | `bedrock_tui_helpers.probe` |

Other modules import from `listing` — the shared library is an internal detail.

---

## 7. Module: `inference.py`

### Parallel execution

```python
with ThreadPoolExecutor(max_workers=5) as pool:
    futures = {pool.submit(_invoke_one, m, ...): m for m in models}
    for future in as_completed(futures):
        result = future.result()
        results.append(result)
```

`as_completed()` yields in completion order for real-time progress updates.

### AccessDenied handling

Detected via substring match on error messages. On match:
1. `save_restricted_id(model_id)` persists to `results/.restricted_ids.json`
2. `ComparisonResult` returned with `error` field set
3. Model excluded from all future runs automatically

---

## 8. Module: `output.py`

### Jinja2 template structure

Two sections in the generated report:
1. **Summary table** — all models sorted by `total_cost` ascending
2. **Full responses** — successful models (cost-sorted), then errored models

Key Jinja2 filters:
- `sort(attribute='total_cost')` — cost-ascending ranking
- `selectattr('error', 'none')` — split successful from errored
- `"%.8f" % value` — 8 decimal places for sub-cent costs

### Output path

```
results/comparison_YYYYMMDD_HHMMSS.md
```

---

## 9. Module: `catalog.py`

### `get_catalog_page(model_id)`

```
1. _safe_filename(model_id) → replace non-alphanumeric chars with '_'
2. Check catalog/<filename>.md mtime < 24h
   Hit  → return cached markdown
   Miss → call GetFoundationModel via boto3-helpers
3. Format response as Markdown
4. Write to catalog/<filename>.md
5. Return markdown string
```

---

## 10. File layout at runtime

```
bedrock-model-compare/
├── main.py
├── menu.py
├── inference.py
├── listing.py                     thin shim
├── output.py
├── catalog.py
├── requirements.txt               includes -e ../boto3-helpers, -e ../bedrock-tui-helpers
├── scripts/
│   ├── run.sh                     create venv + install deps + launch
│   └── cleanup.sh                 remove venv + generated files
├── decisions/
│   ├── architecture.md
│   ├── explanation.md
│   └── lld.md
├── results/                       (created on first run)
│   ├── .restricted_ids.json       permanent access-denied list
│   └── comparison_*.md            generated reports
└── catalog/                       (created on first catalog request)
    └── <model-id>.md              cached detail pages (24h TTL)
```

---

## 11. Error handling

| Error | Where caught | Behaviour |
|-------|-------------|-----------|
| `GoBack` | wizard state machine | decrement step |
| `GoHome` | `run_menu()` | restart from step 1 |
| `GoExit` | `main()` | terminate cleanly |
| `AccessDeniedException` (account restriction) | `_invoke_one()` | persist to `.restricted_ids.json`, return error result |
| `ClientError` (other) | `_invoke_one()` | return error result |
| Disk cache read error | `listing.py` / `catalog.py` | fall through to API call |
| JSON decode error | cache load | fall through to API call |

---

## 12. Extension points

| Change | Where |
|--------|-------|
| Add model pricing | `MODEL_PRICING` in [bedrock-tui-helpers](../../bedrock-tui-helpers/) `models.py` |
| Support new cross-region provider | `_PROFILE_PROVIDERS` in [bedrock-tui-helpers](../../bedrock-tui-helpers/) `models.py` |
| Change parallel worker count | `_MAX_WORKERS` in `inference.py` |
| Change model list cache TTL | `_CACHE_MAX_AGE` in [bedrock-tui-helpers](../../bedrock-tui-helpers/) `models.py` |
| Change catalog cache TTL | TTL constant in `catalog.py` |
| Add wizard step | New step in `menu.py`, update `run_menu()` signature |
| Change report format | Jinja2 template in `output.py` |
| Add size classification rule | `_SIZE_RULES` in [bedrock-tui-helpers](../../bedrock-tui-helpers/) `models.py` |
