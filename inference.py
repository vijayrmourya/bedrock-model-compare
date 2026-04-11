"""inference.py — Invokes Bedrock models and collects comparison results."""

import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, TimeElapsedColumn

from boto3_helpers.bedrock import runtime as _bedrock_rt

from listing import get_pricing
import listing as lst

console = Console()

# Error message fragments that indicate account-level access restriction.
_ACCESS_DENIED_FRAGMENTS = (
    "use case details have not been submitted",
    "fill out the",
    "AccessDeniedException",
)


def _is_access_restricted(error_msg: str) -> bool:
    low = error_msg.lower()
    return any(f.lower() in low for f in _ACCESS_DENIED_FRAGMENTS)


_MAX_WORKERS = 5  # concurrent Bedrock Converse calls

_PROFILE_PREFIX = "us"

_PROFILE_PROVIDERS = {
    "Amazon",
    "Anthropic",
    "Meta",
    "Mistral AI",
    "Cohere",
    "AI21 Labs",
    "Stability AI",
    "DeepSeek",
    "TwelveLabs",
    "Writer",
    "Google",
    "NVIDIA",
    "Qwen",
    "Moonshot AI",
    "Z.AI",
    "MiniMax",
    "OpenAI",
}


def _to_invoke_id(model: dict) -> str:
    model_id = model["modelId"]
    if re.match(r"^[a-z]{2}\.", model_id):
        return model_id
    supported = model.get("inferenceTypesSupported", [])
    provider  = model.get("providerName", "")
    if "INFERENCE_PROFILE" in supported and provider in _PROFILE_PROVIDERS:
        return f"{_PROFILE_PREFIX}.{model_id}"
    return model_id


def invoke_text_model(
    model: dict,
    prompt: str,
    max_tokens: int = 250,
    temperature: float | None = None,
    top_p: float | None = None,
    top_k: int | None = None,
    system_prompt: str | None = None,
) -> dict:
    """Send a text prompt to a single model via the Bedrock Converse API."""
    model_id  = model["modelId"]
    invoke_id = _to_invoke_id(model)

    start    = time.time()
    response = _bedrock_rt.converse(
        invoke_id,
        [{"role": "user", "content": [{"text": prompt}]}],
        max_tokens=max_tokens,
        temperature=temperature,
        top_p=top_p,
        top_k=top_k,
        system_prompt=system_prompt,
    )
    latency  = time.time() - start

    output_text = response["output"]["message"]["content"][0]["text"]
    usage   = response["usage"]
    in_tok  = usage["inputTokens"]
    out_tok = usage["outputTokens"]

    in_p, out_p = get_pricing(model_id)
    in_cost  = (in_tok  / 1000) * in_p
    out_cost = (out_tok / 1000) * out_p

    return {
        "model_name":      model["modelName"],
        "model_id":        model_id,
        "provider":        model.get("providerName", ""),
        "size":            model.get("_size", "?"),
        "input_tokens":    in_tok,
        "output_tokens":   out_tok,
        "latency":         latency,
        "in_price_per_k":  in_p,
        "out_price_per_k": out_p,
        "input_cost":      in_cost,
        "output_cost":     out_cost,
        "total_cost":      in_cost + out_cost,
        "output":          output_text,
        "error":           None,
    }


def _invoke_one(
    model: dict,
    prompt: str,
    max_tokens: int,
    temperature: float | None,
    top_p: float | None,
    top_k: int | None,
    system_prompt: str | None,
) -> dict:
    """Wrapper used by the thread pool — returns a result dict (never raises)."""
    try:
        return invoke_text_model(model, prompt, max_tokens, temperature, top_p, top_k, system_prompt)
    except Exception as exc:
        err_str = str(exc)
        if _is_access_restricted(err_str):
            lst.save_restricted_id(model["modelId"])
        return {
            "model_name":      model["modelName"],
            "model_id":        model["modelId"],
            "provider":        model.get("providerName", ""),
            "size":            model.get("_size", "?"),
            "input_tokens":    0,
            "output_tokens":   0,
            "latency":         0.0,
            "in_price_per_k":  0.0,
            "out_price_per_k": 0.0,
            "input_cost":      0.0,
            "output_cost":     0.0,
            "total_cost":      0.0,
            "output":          "",
            "error":           err_str,
            "_restricted":     _is_access_restricted(err_str),
        }


def run_comparison(
    models: list[dict],
    prompt: str,
    inference_type: str = "TEXT",
    max_tokens: int = 250,
    temperature: float | None = None,
    top_p: float | None = None,
    top_k: int | None = None,
    system_prompt: str | None = None,
) -> list[dict]:
    """
    Run inference on every selected model in parallel (up to 5 concurrent).
    Returns a list of result dicts; failed models include an 'error' key.
    """
    console.print()
    total  = len(models)
    done   = 0
    # map future → model for progress labelling
    future_to_model: dict = {}

    results_map: dict[str, dict] = {}  # model_id → result, preserves final order

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        TimeElapsedColumn(),
        console=console,
        transient=False,
    ) as progress:
        task = progress.add_task(
            f"Querying {total} model(s) — up to {_MAX_WORKERS} at a time...",
            total=total,
        )

        with ThreadPoolExecutor(max_workers=_MAX_WORKERS) as pool:
            for m in models:
                f = pool.submit(_invoke_one, m, prompt, max_tokens, temperature, top_p, top_k, system_prompt)
                future_to_model[f] = m

            for future in as_completed(future_to_model):
                m      = future_to_model[future]
                result = future.result()
                done  += 1

                if result.get("error"):
                    restricted = result.pop("_restricted", False)
                    suffix = (
                        "[dim]⊘ restricted — hidden from future runs[/dim]"
                        if restricted
                        else f"[red]✗ {result['error'][:60]}[/red]"
                    )
                    progress.print(
                        f"  [yellow]▶[/yellow] {m['modelName'][:42]:42s}  {suffix}"
                    )
                else:
                    cost_str = f"${result['total_cost']:.8f}" if result["total_cost"] else "N/A"
                    progress.print(
                        f"  [green]✓[/green] {m['modelName'][:42]:42s}  "
                        f"{result['latency']:.2f}s  "
                        f"{result['input_tokens']}→{result['output_tokens']} tok  "
                        f"cost {cost_str}"
                    )

                results_map[m["modelId"]] = result
                progress.advance(task)

    # Return in the original model selection order
    return [results_map[m["modelId"]] for m in models if m["modelId"] in results_map]

