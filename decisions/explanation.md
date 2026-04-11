# Explanation

This document explains the design decisions behind each module and the reasoning for non-obvious implementation choices.

**Related docs:** [architecture.md](architecture.md) (diagrams), [lld.md](lld.md) (implementation spec)  
**Sibling libraries:** [boto3-helpers](../../boto3-helpers/), [bedrock-tui-helpers](../../bedrock-tui-helpers/)

---

## Table of contents

1. [How the application fits together](#1-how-the-application-fits-together)
2. [main.py — Entry point and event loop](#2-mainpy--entry-point-and-event-loop)
3. [listing.py — Thin shim over bedrock-tui-helpers](#3-listingpy--thin-shim-over-bedrock-tui-helpers)
4. [inference.py — Parallel Bedrock calls](#4-inferencepy--parallel-bedrock-calls)
5. [menu.py — Interactive wizard](#5-menupy--interactive-wizard)
6. [output.py — Markdown report generation](#6-outputpy--markdown-report-generation)
7. [catalog.py — Per-model detail pages](#7-catalogpy--per-model-detail-pages)
8. [Caching strategy](#8-caching-strategy)
9. [Cross-region inference profiles](#9-cross-region-inference-profiles)
10. [Restricted model system](#10-restricted-model-system)
11. [Navigation via exceptions](#11-navigation-via-exceptions)
12. [Size inference regex system](#12-size-inference-regex-system)
13. [Why Jinja2 for Markdown](#13-why-jinja2-for-markdown)
14. [Thread pool design](#14-thread-pool-design)

---

## 1. How the application fits together

The tool solves a specific problem: choosing a Bedrock model requires calling each candidate with a real prompt and comparing latency, cost, and output quality. Without automation, this means writing a throw-away script every time.

This CLI automates the process:

- `listing.py` knows every available model and its cost (via [bedrock-tui-helpers](../../bedrock-tui-helpers/))
- `menu.py` walks the user through configuration
- `inference.py` calls all selected models in parallel
- `output.py` writes a cost-sorted Markdown report

The two sibling libraries handle shared concerns:

- [boto3-helpers](../../boto3-helpers/) — cached boto3 client factory. Call `configure(region=...)` once; every subsequent `get_client()` call reuses the same client object
- [bedrock-tui-helpers](../../bedrock-tui-helpers/) — model pricing table (80+ models), listing with a 3-layer cache, filtering, deduplication, and an invocability probe

---

## 2. `main.py` — Entry point and event loop

### Two nested loops

```python
while True:                          # outer: full app lifecycle
    selected, prompt, ... = run_menu()
    results = run_comparison(...)
    filepath = save_results(...)

    while True:                      # inner: post-run options
        action = post_run_menu()
        if action == "read":  print_responses(results); continue
        break                        # "home" → restart outer loop
```

The outer loop runs successive comparisons. The inner loop handles post-run actions (read responses, run again, exit). `GoExit` (raised when the user types `x`) breaks out of both loops via exception propagation — no flags needed.

### Region configuration

```python
boto3_helpers.configure(region="us-west-2")
```

Called once at module load. Sets a process-wide default for all boto3 clients created through [boto3-helpers](../../boto3-helpers/). Override without code changes:

```bash
export AWS_DEFAULT_REGION=eu-west-1
```

---

## 3. `listing.py` — Thin shim over bedrock-tui-helpers

All core model logic (pricing, caching, filtering, deduplication) was extracted into [bedrock-tui-helpers](../../bedrock-tui-helpers/) so multiple CLI projects can share it. `listing.py` is now a thin delegation layer that:

1. **Re-exports shared symbols** (`MODEL_PRICING`, `get_pricing`, `filter_models`, `ensure_probe`, etc.) so other modules in this project import from `listing` without needing to know the shared library exists
2. **Owns the restricted-IDs file** (`results/.restricted_ids.json`) — account-specific data that belongs in this project, not the shared library

### How filtering works

```python
def filter_models(models, *, provider=None, size=None, modality="TEXT"):
    restricted = load_restricted_ids() | load_disabled_ids()
    return _tui.filter_models(models, ..., restricted_ids=restricted)
```

Two sources of exclusion are merged:
- `load_restricted_ids()` — model IDs that returned `AccessDeniedException` at runtime (local file)
- `load_disabled_ids()` — model IDs that failed the invocability probe (from [bedrock-tui-helpers](../../bedrock-tui-helpers/) cache)

The shared library never reads either file directly — callers inject the merged set, keeping it stateless.

---

## 4. `inference.py` — Parallel Bedrock calls

### Invoke IDs

AWS has two coexisting model ID formats: base IDs (`amazon.nova-micro-v1:0`) and inference profile IDs (`us.amazon.nova-micro-v1:0`). The correct format depends on the account and model. [bedrock-tui-helpers](../../bedrock-tui-helpers/) resolves this in `list_models()` and stores the result as `model["_invoke_id"]`, so inference.py reads the correct ID directly.

### Parallel execution

```python
with ThreadPoolExecutor(max_workers=5) as pool:
    futures = {pool.submit(_invoke_one, m, ...): m for m in models}
    for future in as_completed(futures):
        result = future.result()
```

`as_completed()` yields futures in completion order (not submission order), so fast models display results immediately instead of waiting for slower ones. The Rich progress bar updates in real time as each model responds.

### AccessDenied detection

```python
_ACCESS_DENIED_FRAGMENTS = (
    "use case details have not been submitted",
    "fill out the",
    "AccessDeniedException",
)
```

AWS returns different error messages for different restriction types. Substring matching handles all variants. On detection, the model ID is persisted via `save_restricted_id()` and excluded from future runs automatically.

---

## 5. `menu.py` — Interactive wizard

### Central input function

All user input flows through `_ask()`, which handles:
- Navigation keys: `b` (back), `h` (home), `x` (exit)
- Input validation against an allowed list
- Default values and freeform text

Centralising input means adding a new feature (like `?` for help) requires a single change.

### Wizard state machine

```python
step = 1
while step <= 7:
    try:
        if step == 1: max_tokens = choose_max_tokens()
        elif step == 2: ...
        step += 1
    except GoBack:
        step = max(1, step - 1)
    except GoHome:
        step = 1
```

Each step is a function that either returns a value or raises a navigation exception. The step counter is the state. Back decrements it, home resets it. Adding new steps means adding a new `elif` and updating the total.

### Inline catalog command

At the model selection step, typing `r 4` fetches the full Bedrock API details for model #4 (via `catalog.py`), displays them, and returns to the selection prompt — an inline sub-command within the input loop.

---

## 6. `output.py` — Markdown report generation

### Why Jinja2

Jinja2's inline filters keep the template readable as it grows:

```jinja
{% for r in successful | sort(attribute='total_cost') %}
| {{ loop.index }} | {{ r.model_name }} | {{ "%.8f" % r.total_cost }} |
{% endfor %}
```

`%.8f` is necessary because model costs can be sub-cent ($0.00000049 for Nova Micro). Fewer decimal places would round everything to $0.00.

The template is an inline string constant (not a separate file) because there is only one template and it is small enough to read in context.

### Filename convention

```python
f"comparison_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
```

`YYYYMMDD_HHMMSS` sorts chronologically with `ls` and avoids special characters.

---

## 7. `catalog.py` — Per-model detail pages

`GetFoundationModel` returns more detail than `ListFoundationModels`: ARN, modalities, inference types, customisation support, streaming support, and lifecycle status. The `r <num>` command in the wizard fetches this on demand and caches the result to `catalog/<model-id>.md` for 24 hours.

Model IDs contain colons (`amazon.nova-micro-v1:0`) which are invalid in filenames on some systems. `_safe_filename()` replaces non-alphanumeric characters with underscores.

---

## 8. Caching strategy

Four independent caches at different layers:

| Cache | TTL | Purpose |
|-------|-----|---------|
| In-process memory | Process lifetime | Instant re-access when the wizard restarts via `h` |
| Disk model list (`.model_list.json`) | 24 hours | Avoids repeated `ListFoundationModels` calls across runs |
| Probe results (`.probe_results.json`) | Manual refresh (`--refresh`) | Skips inaccessible models without re-probing every run |
| Restricted IDs (`.restricted_ids.json`) | Permanent | Grows as runtime failures are encountered |
| Catalog pages (`catalog/*.md`) | 24 hours | Caches expensive per-model API calls |

The model list cache and probe cache are managed by [bedrock-tui-helpers](../../bedrock-tui-helpers/) and shared across all projects using that library. The restricted IDs and catalog pages are project-local.

---

## 9. Cross-region inference profiles

`to_invoke_id()` in [bedrock-tui-helpers](../../bedrock-tui-helpers/) detects which models need a `us.` prefix at runtime by checking `inferenceTypesSupported`. A provider allowlist (`_PROFILE_PROVIDERS`) prevents incorrect prefixing that would cause `ValidationException`.

The result is stored as `model["_invoke_id"]` during `list_models()`, so downstream code never needs to handle ID translation.

---

## 10. Restricted model system

A self-improving feedback loop:

1. `inference.py` detects an `AccessDeniedException` during a comparison run
2. `save_restricted_id()` persists the model ID to `results/.restricted_ids.json`
3. On the next run, `filter_models()` merges this with the probe cache and excludes those models from the wizard

The first run might hit multiple access-denied errors. Every subsequent run only shows models the account can actually use. Delete `.restricted_ids.json` to reset (e.g., after requesting access to new models in the AWS console).

---

## 11. Navigation via exceptions

Three exception classes handle wizard navigation:

```python
class GoBack(Exception): pass   # caught by wizard → decrement step
class GoHome(Exception): pass   # caught by wizard → reset to step 1
class GoExit(Exception): pass   # caught by main() → terminate
```

The alternative — return codes — would require every intermediate function to check and propagate a status value. Exceptions propagate naturally through the call stack. This is the same pattern Python uses for `StopIteration` in generators and `KeyboardInterrupt` for Ctrl+C.

---

## 12. Size inference regex system

Models are classified into sizes (XS/S/M/L/XL) by regex on the model name. This logic lives in [bedrock-tui-helpers](../../bedrock-tui-helpers/).

Key details:
- **Word boundaries (`\b`)** are required: without them, `7b` matches `8x7b` (Mixtral, 46.7B params — should be M not S) and `1b` matches `11b`
- **Negative lookahead** for Command R variants: `command-r(?!-plus)\b` matches `command-r` but not `command-r-plus`
- Rules are checked top-to-bottom (XS first, XL last); first match wins

---

## 13. Why Jinja2 for Markdown

F-strings become unreadable as the report grows. Jinja2 provides:
- Inline loops and conditionals (`{% for %}`, `{% if %}`)
- Built-in filters (`sort`, `selectattr`, `sum`)
- Clean separation of data processing from formatting

---

## 14. Thread pool design

### Why 5 workers

Bedrock has per-account rate limits (typically 5–60 TPS depending on the model). Five concurrent workers stay safely under limits without needing a quota increase.

### Why `ThreadPoolExecutor`, not asyncio

boto3 is synchronous. Using asyncio would require `asyncio.run_in_executor()` (which is a thread pool anyway) or `aiobotocore` (added complexity). `ThreadPoolExecutor` is standard library, handles blocking I/O natively, and boto3 clients are thread-safe.

### Why `as_completed()`, not `pool.map()`

`pool.map()` returns results in submission order — all results appear at once after the slowest model finishes. `as_completed()` yields results in completion order, so the progress display updates in real time.
