# bedrock-model-compare

Interactive CLI that benchmarks Amazon Bedrock foundation models side-by-side — latency, token usage, and cost — in a single run.

Send the same prompt to any combination of models across Amazon, Anthropic, Meta, Mistral, Google, NVIDIA, DeepSeek, Qwen, and more. Results are saved as a timestamped Markdown report sorted cheapest-first.

---

## How it works

A guided wizard walks through configuration (token limit, sampling params, provider/size filters, model selection, prompt), then calls all selected models in parallel (up to 5 at a time) and writes a Markdown report to `results/`.

```
  ✓ Amazon Nova Micro          0.41s   11→64 tok   $0.00000049
  ✓ Amazon Nova Lite           0.38s   11→64 tok   $0.00000087
  ✓ Claude 3 Haiku             0.52s   11→64 tok   $0.00000951
  ✓ Llama 3 8B Instruct        0.71s   11→64 tok   $0.00000398
  ✓ Mistral 7B Instruct        0.62s   11→64 tok   $0.00000267

✓ Results saved → results/comparison_20260404_104400.md
```

The saved report includes a cost-sorted summary table and each model's full response.

---

## Prerequisites

- **Python 3.10+**
- **AWS account** with Bedrock foundation model access enabled
- **AWS credentials** active in your shell (IAM user, SSO session, or assumed role)

```bash
# Option 1 — environment variables
export AWS_ACCESS_KEY_ID=...
export AWS_SECRET_ACCESS_KEY=...
export AWS_SESSION_TOKEN=...       # if using temporary credentials

# Option 2 — named profile
export AWS_PROFILE=my-bedrock-profile
```

---

## Project structure

```
bedrock-model-compare/
├── main.py             Entry point and event loop
├── menu.py             7-step interactive wizard (Rich UI)
├── inference.py        Parallel Bedrock Converse calls
├── listing.py          Thin shim — delegates to bedrock-tui-helpers
├── output.py           Jinja2 Markdown report renderer
├── catalog.py          Per-model detail pages (24h cache)
├── test_models.py      Model invocability probe
├── requirements.txt    Dependencies (see below)
├── scripts/
│   ├── run.sh          One-command setup + launch
│   └── cleanup.sh      Remove venv and generated files
├── decisions/          Design documentation
│   ├── architecture.md   System diagrams
│   ├── explanation.md    Design rationale
│   └── lld.md            Implementation spec
├── results/            Generated reports (gitignored)
└── catalog/            Cached model detail pages (gitignored)
```

---

## Dependencies

This project depends on two sibling libraries that live in the same parent directory:

| Library | What it provides | Repository |
|---------|-----------------|------------|
| [boto3-helpers](../boto3-helpers/) | Cached boto3 client factory, Bedrock control/runtime API wrappers | Sibling directory |
| [bedrock-tui-helpers](../bedrock-tui-helpers/) | Model pricing (80+ models), listing, filtering, deduplication, invocability probe | Sibling directory |

Third-party dependencies:

| Library | Role |
|---------|------|
| [boto3](https://boto3.amazonaws.com/v1/documentation/api/latest/index.html) | AWS SDK |
| [rich](https://github.com/Textualize/rich) | Terminal tables, progress bars, Markdown rendering |
| [jinja2](https://jinja.palletsprojects.com/) | Markdown report templating |

All dependencies are declared in `requirements.txt`. The sibling libraries are installed as [editable packages](https://pip.pypa.io/en/stable/topics/local-project-installs/#editable-installs) so changes to them are reflected immediately.

---

## Installation

### Clone the repositories

The sibling libraries must be present in the same parent directory:

```
parent-directory/
├── bedrock-model-compare/    ← this project
├── boto3-helpers/            ← sibling library
└── bedrock-tui-helpers/      ← sibling library
```

### Set up the environment

```bash
cd bedrock-model-compare

python3 -m venv .venv
source .venv/bin/activate

pip install --upgrade pip          # pip ≥ 23 required for editable installs
pip install -r requirements.txt
```

This installs boto3, rich, jinja2, and the two sibling packages as editable installs (`-e ../boto3-helpers`, `-e ../bedrock-tui-helpers`).

---

## Usage

### Quick start

```bash
# One-command setup + launch (creates venv, installs deps, runs main.py):
bash scripts/run.sh

# Or manually:
source .venv/bin/activate
python3 main.py
```

On the first run, an automatic model probe fires (~60 seconds). It tests which models are accessible in your account and caches the results. All subsequent startups are instant.

### Wizard steps

| Step | What you configure |
|------|--------------------|
| 1/7 | **Max output tokens** — preset (64/128/250/512/1024/2048) or custom (1–10,000) |
| 2/7 | **Sampling parameters** — Temperature, Top P, Top K (all optional) |
| 3/7 | **System prompt** — applied to every model, or skip |
| 4/7 | **Provider filter** — Amazon, Anthropic, Meta, Mistral AI, etc. |
| 5/7 | **Size filter** — XS (1–3B) / S (7–11B) / M (sonnet-class) / L (pro-class) / XL (100B+) |
| 6/7 | **Model selection** — pick models by number, range, or comma-separated list |
| 7/7 | **Prompt** — the text sent to all selected models |

**Navigation at every step:** `b` = back one step, `h` = restart from step 1, `x` = exit

**Model selection syntax:**

```
2          single model
1,3        multiple models
1-5        range
1,3-5,7    mixed
r 4        view detailed info for model #4, then return to selection
```

### After the run

```
  1  Run another comparison
  r  Read responses (clean output, no metadata)
  x  Exit
```

---

## Configuration

The default AWS region is `us-west-2`. Override via flag or environment variable:

```bash
python3 main.py --region eu-west-1
# or
export AWS_DEFAULT_REGION=eu-west-1
python3 main.py
```

---

## Model probe

On first launch, the tool probes all available models to find which ones your account can invoke. Results are cached in `~/.cache/bedrock-tui-helpers/.probe_results.json` and shared with all projects that use [bedrock-tui-helpers](../bedrock-tui-helpers/).

Inaccessible models are automatically hidden from the wizard — no flags or configuration needed.

### Refresh the probe

After requesting access to new models in the AWS Console:

```bash
python3 main.py --refresh-probe          # refreshes probe, then launches wizard
python3 test_models.py --refresh         # standalone probe (no wizard)
```

---

## Cost

Every run calls Bedrock with real API requests. Costs depend on the number of models and token limit:

| Run type | Approximate cost |
|----------|-----------------|
| 5 models × 250 tokens | ~$0.001 |
| 20 models × 250 tokens | ~$0.005 |
| 5 models × 2048 tokens | ~$0.008 |

---

## Cleanup

Remove the virtual environment and all generated files:

```bash
bash scripts/cleanup.sh
```

---

## CLI flag reference

### `main.py`

| Flag | What it does |
|------|-------------|
| `--region REGION` | AWS region (default: `us-west-2`). Also overridable via `AWS_DEFAULT_REGION` env var |
| `--refresh` | Bypass **both** the 24h model-list cache and the pricing cache — fetches fresh data from AWS before launching the wizard |
| `--refresh-pricing` | Refresh **only** the pricing cache from the AWS Pricing API (keeps the model list cache) |
| `--refresh-probe` | Force a full model invocability probe (~60s) even if the probe cache already exists |

Flags only apply to the first wizard run. If you choose "Run another comparison" from the post-run menu, caches are reused.

```bash
# Normal launch — uses all caches
python3 main.py

# Fresh everything — new model list, new prices, re-probe access
python3 main.py --refresh --refresh-probe

# Just update prices (e.g. after AWS announces price changes)
python3 main.py --refresh-pricing

# Different region
python3 main.py --region eu-central-1

# Combine flags
python3 main.py --region us-east-1 --refresh --refresh-probe
```

### `test_models.py`

Standalone probe that tests which models your account can invoke, without launching the wizard.

| Flag | What it does |
|------|-------------|
| `--region REGION` | AWS region (default: `us-west-2`) |
| `--refresh` | Bypass model-list and pricing caches before probing |
| `--refresh-pricing` | Refresh only the pricing cache |
| `--workers N` | Number of concurrent probe calls (default: 5) |

```bash
# Default probe
python3 test_models.py

# Full refresh — new model list, new prices, then probe
python3 test_models.py --refresh

# More parallelism for faster probing
python3 test_models.py --workers 10

# Different region
python3 test_models.py --region eu-central-1
```

### Cache locations

All caches are stored under `~/.cache/bedrock-tui-helpers/` and shared with any project that uses [bedrock-tui-helpers](../bedrock-tui-helpers/):

| File | TTL | Refreshed by |
|------|-----|-------------|
| `.model_list.json` | 24 hours | `--refresh` on either script |
| `.pricing.json` | 24 hours | `--refresh` or `--refresh-pricing` |
| `.probe_results.json` | Manual | `--refresh-probe` on `main.py`, or `test_models.py --refresh` |

Project-local caches (under `results/`):

| File | TTL | Purpose |
|------|-----|---------|
| `.restricted_ids.json` | Permanent | Model IDs that returned AccessDeniedException at runtime |
| `disabled.json` | Written by `test_models.py` | Human-readable copy of probe results |
| `comparison_*.md` | Permanent | Generated comparison reports |

### Pricing resolution

Model prices are resolved in order:

1. **AWS Pricing API cache** (`~/.cache/bedrock-tui-helpers/.pricing.json`) — fetched automatically when the model list refreshes, or via `--refresh-pricing`
2. **Hardcoded fallback** (`MODEL_PRICING` in bedrock-tui-helpers) — covers ~100 models, used when the API cache is missing or the model isn't in it
3. **Default** `$0.00` — for completely unknown models (newly launched, not yet in either source)

The Pricing API requires `pricing:GetProducts` IAM permission (read-only). If the call fails (no permission, no credentials, network error), the hardcoded fallback is used silently.

---

## Design documentation

Detailed design docs are in the [decisions/](decisions/) folder:

- [architecture.md](decisions/architecture.md) — system diagrams, request flow, caching layers
- [explanation.md](decisions/explanation.md) — design rationale for every module
- [lld.md](decisions/lld.md) — implementation spec: data structures, error handling, extension points

---

## Contributing

Contributions are welcome! Please see [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines on how to report bugs, suggest features, or submit pull requests.

## License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for the full text. When reusing this software, please ensure that the original copyright notice and attribution to **Vijay Mourya** are included.

