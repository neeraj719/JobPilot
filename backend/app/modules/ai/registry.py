"""Maintained catalog of AI providers and models (spec §7: "use a maintained model registry").

* :data:`PROVIDERS` — every provider JobPilot can route to, with its privacy/billing notes,
  key page and documentation link, and its known models.
* Every model entry has a context window, **estimated** USD prices per 1M input/output
  tokens (``prices_as_of`` per provider), capabilities and the workflows it is recommended
  for. Prices change; the UI always shows them as estimates with the date.
* Live listings (``provider.list_models()``) are merged in by :func:`merge_models`: a model
  the provider lists but the registry does not know is allowed and flagged "not in registry —
  pricing unknown"; a registry model the live listing does not show is flagged unavailable.
* Local models (Ollama, built-in rules) cost nothing.

Updating: edit the tables below (keep ``prices_as_of`` honest). Nothing else hard-codes
model ids except ``factory.DEFAULT_MODELS``.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

#: Workflows (mirrors ``routing.AiWorkflow`` without importing it, to keep this a leaf module).
ALL_WORKFLOWS = ("generation", "analysis", "rewriting", "jd_analysis", "review", "general")

BILLING_NOTE = (
    "API access is billed separately from chat subscriptions: ChatGPT Plus, Gemini Advanced or a Claude "
    "plan do not include API credits. Create a key in the provider's API console and check its billing there."
)
HOSTED_PRIVACY_NOTE = (
    "A hosted provider receives the text of your resume and of the job descriptions you analyse. "
    "Its own data-use and retention policy applies."
)
LOCAL_PRIVACY_NOTE = "Runs on this machine; nothing leaves it and there is no cost."


@dataclass(frozen=True)
class ModelInfo:
    id: str
    display_name: str
    context_window: int | None = None
    input_per_m: Decimal | None = None
    output_per_m: Decimal | None = None
    json_mode: bool = True
    vision: bool = False
    recommended_for: tuple[str, ...] = ()
    #: Accepts ``temperature`` (several current reasoning models reject it with a 400).
    sampling: bool = True
    #: OpenAI reasoning model: ``max_completion_tokens`` + ``reasoning_effort``.
    reasoning: bool = False
    #: Anthropic ``output_config.effort`` is accepted.
    effort: bool = False
    #: Thinks by default; thinking tokens count against ``max_tokens``, so the adapter
    #: raises the floor.
    thinks_by_default: bool = False
    #: Gemini: thinking can be switched off with ``thinking_budget=0``.
    thinking_off: bool = False
    notes: str | None = None


@dataclass(frozen=True)
class ProviderInfo:
    id: str
    name: str
    #: ``builtin`` (rules, no model) | ``local`` | ``hosted`` | ``self_hosted``
    kind: str
    requires_key: bool
    supports_base_url: bool
    default_model: str | None
    docs_url: str | None
    key_url: str | None
    prices_as_of: str | None
    privacy_note: str
    billing_note: str | None
    supports_live_models: bool
    description: str
    models: tuple[ModelInfo, ...] = field(default_factory=tuple)

    def model(self, model_id: str | None) -> ModelInfo | None:
        if not model_id:
            return None
        for model in self.models:
            if model.id == model_id:
                return model
        return None


def _m(id: str, name: str, ctx: int | None, pin: str | None, pout: str | None, **kw: Any) -> ModelInfo:
    return ModelInfo(
        id=id,
        display_name=name,
        context_window=ctx,
        input_per_m=Decimal(pin) if pin is not None else None,
        output_per_m=Decimal(pout) if pout is not None else None,
        **kw,
    )


_GEN_REVIEW = ("generation", "review")
_CHEAP = ("analysis", "rewriting", "jd_analysis", "general")

PROVIDERS: dict[str, ProviderInfo] = {
    "ollama": ProviderInfo(
        id="ollama",
        name="Ollama (local)",
        kind="local",
        requires_key=False,
        supports_base_url=True,
        default_model="qwen2.5:3b-instruct",
        docs_url="https://github.com/ollama/ollama/blob/main/docs/api.md",
        key_url=None,
        prices_as_of=None,
        privacy_note=LOCAL_PRIVACY_NOTE,
        billing_note=None,
        supports_live_models=True,
        description="Free local model served by Ollama. The default: private and zero-configuration.",
        models=(
            _m("qwen2.5:3b-instruct", "Qwen 2.5 3B Instruct", 32768, "0", "0", recommended_for=ALL_WORKFLOWS,
               notes="Fits a 4 GB GPU. Small: every output is checked by JobPilot's rules before use."),
            _m("qwen2.5:7b-instruct", "Qwen 2.5 7B Instruct", 32768, "0", "0", recommended_for=_GEN_REVIEW,
               notes="Needs about 6 GB of GPU memory."),
            _m("llama3.2:3b", "Llama 3.2 3B", 131072, "0", "0"),
        ),
    ),
    "openai": ProviderInfo(
        id="openai",
        name="OpenAI",
        kind="hosted",
        requires_key=True,
        supports_base_url=False,
        default_model="gpt-4o-mini",
        docs_url="https://platform.openai.com/docs/models",
        key_url="https://platform.openai.com/api-keys",
        prices_as_of="2025-08-07",
        privacy_note=HOSTED_PRIVACY_NOTE,
        billing_note=BILLING_NOTE,
        supports_live_models=True,
        description="GPT models through the official OpenAI API (your own API key).",
        models=(
            _m("gpt-5", "GPT-5", 400000, "1.25", "10.00", vision=True, sampling=False, reasoning=True, recommended_for=_GEN_REVIEW),
            _m("gpt-5-mini", "GPT-5 mini", 400000, "0.25", "2.00", vision=True, sampling=False, reasoning=True, recommended_for=_CHEAP),
            _m("gpt-5-nano", "GPT-5 nano", 400000, "0.05", "0.40", vision=True, sampling=False, reasoning=True),
            _m("gpt-4.1", "GPT-4.1", 1047576, "2.00", "8.00", vision=True),
            _m("gpt-4.1-mini", "GPT-4.1 mini", 1047576, "0.40", "1.60", vision=True, recommended_for=("rewriting",)),
            _m("gpt-4.1-nano", "GPT-4.1 nano", 1047576, "0.10", "0.40", vision=True),
            _m("gpt-4o", "GPT-4o", 128000, "2.50", "10.00", vision=True),
            _m("gpt-4o-mini", "GPT-4o mini", 128000, "0.15", "0.60", vision=True, recommended_for=("general",)),
        ),
    ),
    "gemini": ProviderInfo(
        id="gemini",
        name="Google Gemini",
        kind="hosted",
        requires_key=True,
        supports_base_url=False,
        default_model="gemini-2.5-flash",
        docs_url="https://ai.google.dev/gemini-api/docs/models",
        key_url="https://aistudio.google.com/app/apikey",
        prices_as_of="2025-09-01",
        privacy_note=HOSTED_PRIVACY_NOTE
        + " On the free tier Google may use prompts to improve its products.",
        billing_note=BILLING_NOTE,
        supports_live_models=True,
        description="Gemini models through the official Gemini API (google-genai SDK, your own API key).",
        models=(
            _m("gemini-2.5-pro", "Gemini 2.5 Pro", 1048576, "1.25", "10.00", vision=True, thinks_by_default=True,
               recommended_for=_GEN_REVIEW, notes="Price for prompts up to 200k tokens."),
            _m("gemini-2.5-flash", "Gemini 2.5 Flash", 1048576, "0.30", "2.50", vision=True, thinking_off=True,
               recommended_for=_CHEAP),
            _m("gemini-2.5-flash-lite", "Gemini 2.5 Flash-Lite", 1048576, "0.10", "0.40", vision=True, thinking_off=True),
            _m("gemini-2.0-flash", "Gemini 2.0 Flash", 1048576, "0.10", "0.40", vision=True),
        ),
    ),
    "anthropic": ProviderInfo(
        id="anthropic",
        name="Anthropic Claude",
        kind="hosted",
        requires_key=True,
        supports_base_url=False,
        default_model="claude-sonnet-5-5",
        docs_url="https://docs.claude.com/en/docs/about-claude/models/overview",
        key_url="https://console.anthropic.com/settings/keys",
        prices_as_of="2026-10-06",
        privacy_note=HOSTED_PRIVACY_NOTE,
        billing_note=BILLING_NOTE,
        supports_live_models=True,
        description="Claude models through the official Anthropic Messages API (your own API key).",
        models=(
            _m("claude-opus-5-5", "Claude Opus 5.5", 1000000, "4.00", "20.00", vision=True, sampling=False, effort=True,
               thinks_by_default=True, recommended_for=("review",)),
            _m("claude-sonnet-5-5", "Claude Sonnet 5.5", 1000000, "2.00", "10.00", vision=True, sampling=False, effort=True,
               thinks_by_default=True, recommended_for=("generation", "review")),
            _m("claude-haiku-5-5", "Claude Haiku 5.5", 1000000, "0.10", "0.50", vision=True, sampling=False, effort=True,
               thinks_by_default=True, recommended_for=_CHEAP, notes="Price for prompts up to 100k tokens."),
            _m("claude-opus-5", "Claude Opus 5", 1000000, "5.00", "25.00", vision=True, sampling=False, effort=True,
               thinks_by_default=True),
            _m("claude-sonnet-5", "Claude Sonnet 5", 1000000, "2.00", "10.00", vision=True, sampling=False, effort=True,
               thinks_by_default=True),
            _m("claude-opus-4-8", "Claude Opus 4.8", 1000000, "5.00", "25.00", vision=True, sampling=False, effort=True),
            _m("claude-sonnet-4-6", "Claude Sonnet 4.6", 1000000, "3.00", "15.00", vision=True, effort=True),
            _m("claude-haiku-4-5", "Claude Haiku 4.5", 200000, "1.00", "5.00", vision=True),
        ),
    ),
    "openai_compatible": ProviderInfo(
        id="openai_compatible",
        name="OpenAI-compatible server",
        kind="self_hosted",
        requires_key=False,
        supports_base_url=True,
        default_model=None,
        docs_url="https://platform.openai.com/docs/api-reference/chat",
        key_url=None,
        prices_as_of=None,
        privacy_note=(
            "Self-hosted servers (vLLM, LM Studio, llama.cpp) keep data where they run. A hosted gateway such as "
            "OpenRouter receives your resume text like any hosted provider."
        ),
        billing_note="Cost depends on the server; JobPilot cannot estimate it.",
        supports_live_models=True,
        description="Any server speaking the OpenAI chat-completions API: base URL plus an optional key.",
        models=(),
    ),
    "mock": ProviderInfo(
        id="mock",
        name="Built-in rules (no AI)",
        kind="builtin",
        requires_key=False,
        supports_base_url=False,
        default_model="mock-deterministic-v1",
        docs_url=None,
        key_url=None,
        prices_as_of=None,
        privacy_note="Deterministic rules inside JobPilot; no model and no network.",
        billing_note=None,
        supports_live_models=False,
        description="JobPilot's deterministic rules. Fast and private, but it cannot rephrase or generate text.",
        models=(_m("mock-deterministic-v1", "Deterministic rules", None, "0", "0", recommended_for=ALL_WORKFLOWS),),
    ),
}

#: Display order for the settings page.
PROVIDER_ORDER = ("ollama", "openai", "gemini", "anthropic", "openai_compatible", "mock")
HOSTED_KINDS = frozenset({"hosted"})
FREE_KINDS = frozenset({"builtin", "local"})


def provider_info(provider: str | None) -> ProviderInfo | None:
    return PROVIDERS.get(str(provider or ""))


def known_provider(provider: str | None) -> bool:
    return str(provider or "") in PROVIDERS


def model_info(provider: str | None, model: str | None) -> ModelInfo | None:
    info = provider_info(provider)
    return info.model(model) if info else None


def is_free(provider: str | None) -> bool:
    info = provider_info(provider)
    return bool(info and info.kind in FREE_KINDS)


def estimate_cost(provider: str | None, model: str | None, input_tokens: int, output_tokens: int) -> Decimal | None:
    """Estimated USD cost of one call; ``0`` for local models, ``None`` when pricing is unknown."""
    if is_free(provider):
        return Decimal("0")
    entry = model_info(provider, model)
    if entry is None or entry.input_per_m is None or entry.output_per_m is None:
        return None
    cost = (Decimal(max(0, input_tokens)) * entry.input_per_m + Decimal(max(0, output_tokens)) * entry.output_per_m) / Decimal(1_000_000)
    return cost.quantize(Decimal("0.000001"))


def _model_row(provider: ProviderInfo, entry: ModelInfo | None, model_id: str, live: dict[str, Any] | None, *, available: bool | None) -> dict[str, Any]:
    free = provider.kind in FREE_KINDS
    pricing_known = free or (entry is not None and entry.input_per_m is not None)
    recommended = list(entry.recommended_for) if entry else []
    if entry is None:
        group = "unknown_pricing" if not free else "other"
    elif recommended:
        group = "recommended"
    else:
        group = "other"
    return {
        "id": model_id,
        "display_name": (entry.display_name if entry else None) or (live or {}).get("display_name") or model_id,
        "in_registry": entry is not None,
        "pricing_known": pricing_known,
        "input_per_m_usd": float(entry.input_per_m) if entry and entry.input_per_m is not None else (0.0 if free else None),
        "output_per_m_usd": float(entry.output_per_m) if entry and entry.output_per_m is not None else (0.0 if free else None),
        "context_window": (entry.context_window if entry else None) or (live or {}).get("context_window"),
        "json_mode": entry.json_mode if entry else True,
        "vision": entry.vision if entry else False,
        "recommended_for": recommended,
        "group": group,
        "available": available,
        "notes": entry.notes if entry else ("Not in JobPilot's registry — pricing unknown." if not free else None),
    }


def merge_models(provider_id: str, live: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    """Registry models merged with a live listing (``None`` = not reachable / not listed).

    ``available`` is ``True``/``False`` when a live listing exists, ``None`` otherwise.
    Recommended models come first, then the other registry models, then unknown ones.
    """
    provider = PROVIDERS[provider_id]
    live_by_id = {str(m.get("id")): m for m in (live or []) if m.get("id")}
    rows: list[dict[str, Any]] = []
    for entry in provider.models:
        available = None if live is None else entry.id in live_by_id
        if provider.kind == "local" and live is not None and not available:
            continue  # a local model that is not pulled is not an option
        rows.append(_model_row(provider, entry, entry.id, live_by_id.get(entry.id), available=available))
    known = {entry.id for entry in provider.models}
    for model_id, item in sorted(live_by_id.items()):
        if model_id not in known:
            rows.append(_model_row(provider, None, model_id, item, available=True))
    order = {"recommended": 0, "other": 1, "unknown_pricing": 2}
    rows.sort(key=lambda r: (order.get(r["group"], 3), r["available"] is False))
    return rows


def catalog_entry(provider: ProviderInfo) -> dict[str, Any]:
    return {
        "id": provider.id,
        "name": provider.name,
        "kind": provider.kind,
        "hosted": provider.kind in HOSTED_KINDS,
        "requires_key": provider.requires_key,
        "supports_base_url": provider.supports_base_url,
        "default_model": provider.default_model,
        "docs_url": provider.docs_url,
        "key_url": provider.key_url,
        "prices_as_of": provider.prices_as_of,
        "privacy_note": provider.privacy_note,
        "billing_note": provider.billing_note,
        "supports_live_models": provider.supports_live_models,
        "description": provider.description,
        "capabilities": {
            "json_mode": True,
            "vision": any(m.vision for m in provider.models),
            "model_listing": provider.supports_live_models,
        },
    }


__all__ = [
    "ALL_WORKFLOWS",
    "BILLING_NOTE",
    "ModelInfo",
    "PROVIDERS",
    "PROVIDER_ORDER",
    "ProviderInfo",
    "catalog_entry",
    "estimate_cost",
    "is_free",
    "known_provider",
    "merge_models",
    "model_info",
    "provider_info",
]
