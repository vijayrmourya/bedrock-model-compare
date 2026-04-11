# Architecture

## Overview

bedrock-model-compare is a Python CLI that sends the same prompt to multiple Amazon Bedrock foundation models in parallel and produces a cost-sorted Markdown report. It relies on two sibling libraries:

- [boto3-helpers](../boto3-helpers/) — cached boto3 client factory and Bedrock API wrappers
- [bedrock-tui-helpers](../bedrock-tui-helpers/) — model pricing, listing, filtering, probe cache, and interactive TUI widgets

---

## System diagram

```mermaid
flowchart TD
    User["User (terminal)"]

    subgraph CLI["bedrock-model-compare"]
        MAIN["main.py — entry point, event loop"]
        MENU["menu.py — interactive wizard"]
        LIST["listing.py — delegates to bedrock-tui-helpers, owns restricted-IDs"]
        INF["inference.py — parallel Bedrock calls"]
        OUT["output.py — Jinja2 Markdown renderer"]
        CAT["catalog.py — per-model detail pages"]
    end

    subgraph Libs["Sibling libraries"]
        BH["boto3-helpers — cached client factory"]
        BTH["bedrock-tui-helpers — pricing, model list, filtering, probe"]
    end

    subgraph Cache["Disk cache"]
        ML[".model_list.json (24h TTL)"]
        PR[".probe_results.json (permanent until refresh)"]
        RI[".restricted_ids.json (permanent)"]
        RPT["comparison_*.md reports"]
        CAC["catalog/*.md (24h TTL)"]
    end

    subgraph AWS["Amazon Bedrock"]
        BC["Control plane — ListFoundationModels, GetFoundationModel"]
        BR["Runtime — Converse API (up to 5 parallel)"]
    end

    User -->|"python3 main.py"| MAIN
    MAIN --> MENU
    MAIN --> INF
    MAIN --> OUT
    MENU --> LIST
    MENU --> CAT
    LIST --> BTH
    BTH --> BH
    INF --> BH
    CAT --> BH
    BH --> BC
    BH --> BR
    LIST <--> ML
    BTH <--> PR
    INF --> RI
    OUT --> RPT
    CAT <--> CAC
```

---

## Request flow

```mermaid
sequenceDiagram
    participant U as User
    participant M as main.py
    participant W as menu.py
    participant L as listing.py
    participant I as inference.py
    participant BK as Amazon Bedrock
    participant O as output.py

    U->>M: python3 main.py
    M->>W: run_menu()
    W->>W: ensure_probe() (no-op if cache exists)
    W->>L: get_models()
    L->>BK: ListFoundationModels (or cache)
    BK-->>L: model summaries
    L-->>W: filtered model list

    W-->>M: selected_models, prompt, max_tokens, system_prompt

    M->>I: run_comparison(...)
    loop up to 5 models in parallel
        I->>BK: Converse(modelId, messages)
        BK-->>I: response + token usage
    end
    I-->>M: list of ComparisonResult

    M->>O: save_results(...)
    O-->>M: results/comparison_*.md
    M-->>U: report path + post-run menu
```

---

## Caching layers

| Cache | Location | TTL | Purpose |
|-------|----------|-----|---------|
| In-process memory | RAM | Process lifetime | Instant re-access on wizard restart |
| Model list | `.model_list.json` (via bedrock-tui-helpers) | 24 hours | Avoid repeated ListFoundationModels calls |
| Probe results | `~/.cache/bedrock-tui-helpers/.probe_results.json` | Manual refresh | Skip inaccessible models automatically |
| Restricted IDs | `results/.restricted_ids.json` | Permanent | Remember AccessDenied failures across runs |
| Catalog pages | `catalog/*.md` | 24 hours | Cache per-model GetFoundationModel detail |

---

## Module dependency graph

```mermaid
flowchart TD
    MAIN["main.py"]
    MENU["menu.py"]
    LIST["listing.py"]
    INF["inference.py"]
    OUT["output.py"]
    CAT["catalog.py"]
    BH["boto3-helpers"]
    BTH["bedrock-tui-helpers"]

    MAIN --> MENU
    MAIN --> INF
    MAIN --> OUT
    MENU --> LIST
    MENU --> CAT
    INF --> LIST
    INF --> BH
    LIST --> BTH
    BTH --> BH
    CAT --> BH
```
