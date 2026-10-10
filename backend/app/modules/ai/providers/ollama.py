"""Ollama provider — a free, local model served by ``ollama serve``.

Talks to Ollama's native HTTP API (``POST /api/chat``) with ``httpx``; no SDK and no
API key. Nothing leaves the machine: ``OLLAMA_BASE_URL`` defaults to localhost.

* ``complete_json`` passes the task's JSON schema as ``format`` (Ollama structured
  outputs), so the model is constrained to the expected shape. Without a schema it
  falls back to ``format: "json"``. ``extract_json`` still parses the reply, and one
  retry with a "return only JSON" nudge covers a reply that is not usable.
* Constructing the provider never touches the network, so the app boots even when the
  Ollama server is down; the first request reports that clearly instead.
* Instantiated lazily (only when ``LLM_PROVIDER=ollama``).
"""
from __future__ import annotations

import logging
from typing import Any

import httpx
from pydantic import BaseModel, ValidationError

from app.core.config import settings
from app.core.exceptions import ExternalServiceError
from app.modules.ai.provider import LLMProvider, extract_json, schema_to_dict

logger = logging.getLogger(__name__)

#: Fits a 4 GB GPU with room for an 8k context and follows JSON instructions well.
DEFAULT_MODEL = "qwen2.5:3b-instruct"
#: Local models are slower than hosted APIs; used unless LLM_TIMEOUT_SECONDS is set.
DEFAULT_TIMEOUT_SECONDS = 120.0
#: Structured tasks want stable, literal output.
JSON_TEMPERATURE = 0.1
#: Health probes (``is_configured`` / ``describe`` / ``GET /ai/status``) must stay snappy.
PROBE_TIMEOUT_SECONDS = 3.0
CONNECT_TIMEOUT_SECONDS = 5.0

JSON_ONLY_INSTRUCTION = "Reply with a single JSON object and nothing else: no prose, no markdown fences."
JSON_RETRY_NUDGE = (
    "Your previous reply was not usable: {problem}. Return only the JSON object, matching the "
    "requested schema, with no prose and no markdown fences."
)


def timeout_for(configured: float, *, explicit: bool) -> float:
    """An explicitly set timeout is respected as is; the global default is raised to
    :data:`DEFAULT_TIMEOUT_SECONDS` because a local model is slower than a hosted API."""
    return float(configured) if explicit else max(float(configured), DEFAULT_TIMEOUT_SECONDS)


def resolve_timeout() -> float:
    """``LLM_TIMEOUT_SECONDS`` when it is set (env or ``.env``), else at least 120 seconds."""
    return timeout_for(settings.LLM_TIMEOUT_SECONDS, explicit="LLM_TIMEOUT_SECONDS" in settings.model_fields_set)


def _keep_alive(value: str | int | None) -> str | int | None:
    """Ollama takes a duration (``"10m"``) or a number of seconds (``0`` unloads at once,
    ``-1`` keeps the model loaded); a bare number must be sent as a number."""
    if value is None or isinstance(value, int):
        return value
    text = str(value).strip()
    if not text:
        return None
    try:
        return int(text)
    except ValueError:
        return text


def _is_nullable(prop: Any) -> bool:
    if not isinstance(prop, dict):
        return False
    kind = prop.get("type")
    if kind == "null" or (isinstance(kind, list) and "null" in kind):
        return True
    return any(_is_nullable(option) for option in prop.get("anyOf") or prop.get("oneOf") or [])


def strict_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """A copy of ``schema`` in which every *non-nullable* property is required.

    Pydantic marks fields with defaults as optional, and Ollama's grammar then lets a
    small model *omit* them: in the prompt-fit check ``qwen2.5:3b-instruct`` returned a
    parsed resume without its experience/education/projects lists and an email
    classification without ``reason`` or ``confidence``. Requiring those keys makes the
    model emit them (``[]`` stays valid).

    Nullable fields (``str | None`` and friends) stay optional on purpose: forcing a key
    the model has nothing to put in made it start a string and never finish it (a
    ``question_key`` ran to the token limit). Only the ``format`` grammar sees this copy.
    """

    def visit(node: Any) -> Any:
        if isinstance(node, dict):
            out = {key: visit(value) for key, value in node.items()}
            properties = out.get("properties")
            if isinstance(properties, dict) and properties:
                required = list(out.get("required") or [])
                required += [name for name, prop in properties.items() if name not in required and not _is_nullable(prop)]
                if required:
                    out["required"] = required
            return out
        if isinstance(node, list):
            return [visit(item) for item in node]
        return node

    return visit(schema)


def _same_model(wanted: str, available: str) -> bool:
    """``qwen2.5`` and ``qwen2.5:latest`` name the same model in Ollama."""

    def norm(name: str) -> str:
        name = name.strip().lower()
        return name if ":" in name else f"{name}:latest"

    return norm(wanted) == norm(available)


def check_server(base_url: str, model: str, *, client: httpx.Client | None = None) -> dict[str, Any]:
    """Probe an Ollama server: is it up, which version, and is ``model`` pulled?

    Never raises; failures are reported in the returned ``error``.
    """
    status: dict[str, Any] = {
        "base_url": base_url,
        "model": model,
        "reachable": False,
        "model_pulled": False,
        "version": None,
        "error": None,
    }
    owns_client = client is None
    http = client or httpx.Client(base_url=base_url, timeout=PROBE_TIMEOUT_SECONDS)
    try:
        tags = http.get("/api/tags")
        tags.raise_for_status()
        status["reachable"] = True
        names = [
            str(entry.get("name") or entry.get("model") or "")
            for entry in (tags.json().get("models") or [])
            if isinstance(entry, dict)
        ]
        status["model_pulled"] = any(_same_model(model, name) for name in names if name)
        if not status["model_pulled"]:
            status["error"] = f"model {model!r} is not pulled; run: ollama pull {model}"
        try:
            version = http.get("/api/version")
            if version.status_code == 200:
                status["version"] = version.json().get("version")
        except (httpx.HTTPError, ValueError):  # the version is informational only
            pass
    except httpx.ConnectError:
        status["error"] = f"Ollama is not running at {base_url} (connection refused); start it with: ollama serve"
    except httpx.TimeoutException:
        status["error"] = f"Ollama at {base_url} did not answer within {PROBE_TIMEOUT_SECONDS:.0f}s"
    except (httpx.HTTPError, ValueError) as exc:
        status["error"] = f"Ollama at {base_url} returned an unexpected response: {exc}"
    finally:
        if owns_client:
            http.close()
    return status


class OllamaProvider(LLMProvider):
    name = "ollama"

    def __init__(
        self,
        *,
        base_url: str | None = None,
        model: str | None = None,
        timeout: float | None = None,
        keep_alive: str | int | None = None,
        num_ctx: int | None = None,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.base_url = (base_url or settings.OLLAMA_BASE_URL).rstrip("/")
        self.model = model or settings.LLM_MODEL or DEFAULT_MODEL
        self._timeout = float(timeout) if timeout is not None else resolve_timeout()
        self._keep_alive = _keep_alive(keep_alive if keep_alive is not None else settings.OLLAMA_KEEP_ALIVE)
        self._num_ctx = int(num_ctx if num_ctx is not None else settings.OLLAMA_NUM_CTX)
        self._client = httpx.Client(
            base_url=self.base_url,
            timeout=httpx.Timeout(self._timeout, connect=CONNECT_TIMEOUT_SECONDS),
            transport=transport,
        )
        self._probe_client = httpx.Client(base_url=self.base_url, timeout=PROBE_TIMEOUT_SECONDS, transport=transport)
        logger.info("Ollama provider initialised (model=%s, base_url=%s)", self.model, self.base_url)

    # ------------------------------------------------------------------ transport

    def _chat(
        self,
        messages: list[dict[str, str]],
        *,
        max_tokens: int,
        temperature: float,
        response_format: str | dict[str, Any] | None = None,
    ) -> tuple[str, str | None]:
        """``(content, done_reason)`` for one non-streaming chat call. The provider is a
        process-wide singleton, so nothing per-request is kept on ``self``."""
        body: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "options": {"temperature": temperature, "num_predict": max_tokens, "num_ctx": self._num_ctx},
        }
        if self._keep_alive is not None:
            body["keep_alive"] = self._keep_alive
        if response_format is not None:
            body["format"] = response_format
        try:
            response = self._client.post("/api/chat", json=body)
        except httpx.ConnectError as exc:
            raise ExternalServiceError(
                f"Ollama is not running at {self.base_url} (connection refused). Start it with 'ollama serve' "
                "or switch LLM_PROVIDER to 'mock'.",
                code="llm_unavailable",
            ) from exc
        except httpx.TimeoutException as exc:
            raise ExternalServiceError(
                f"Ollama model {self.model!r} did not answer within {self._timeout:.0f}s. Raise LLM_TIMEOUT_SECONDS "
                "or use a smaller model.",
                code="llm_timeout",
            ) from exc
        except httpx.HTTPError as exc:
            raise ExternalServiceError(f"Ollama request failed: {exc}", code="llm_request_failed") from exc

        if response.status_code == 404:
            raise ExternalServiceError(
                f"Ollama model {self.model!r} is not pulled. Run: ollama pull {self.model}",
                code="llm_model_missing",
                details={"ollama_error": _error_text(response)},
            )
        if response.status_code >= 400:
            raise ExternalServiceError(
                f"Ollama returned HTTP {response.status_code}: {_error_text(response)}",
                code="llm_request_failed",
            )
        try:
            data = response.json()
        except ValueError as exc:
            raise ExternalServiceError("Ollama returned a non-JSON HTTP body", code="llm_request_failed") from exc
        message = data.get("message") if isinstance(data, dict) else None
        content = message.get("content") if isinstance(message, dict) else None
        done_reason = data.get("done_reason") if isinstance(data, dict) else None
        return (content or "").strip(), done_reason

    @staticmethod
    def _messages(prompt: str, system: str | None) -> list[dict[str, str]]:
        messages: list[dict[str, str]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        return messages

    # ------------------------------------------------------------------ API

    def complete(
        self,
        prompt: str,
        *,
        system: str | None = None,
        max_tokens: int = 800,
        temperature: float = 0.2,
    ) -> str:
        text, _ = self._chat(self._messages(prompt, system), max_tokens=max_tokens, temperature=temperature)
        if not text:
            raise ExternalServiceError("Ollama returned an empty response", code="llm_empty_response")
        return text

    def complete_json(
        self,
        prompt: str,
        *,
        schema: dict[str, Any] | type[BaseModel] | None = None,
        system: str | None = None,
        max_tokens: int = 1500,
        temperature: float | None = None,
    ) -> dict[str, Any]:
        schema_dict = schema_to_dict(schema)
        # Structured outputs: Ollama turns the schema into a grammar, so a small model
        # cannot drift from the expected keys and types (and, via strict_schema, cannot
        # skip a non-nullable key). "json" only guarantees syntax.
        response_format: str | dict[str, Any] = strict_schema(schema_dict) if schema_dict else "json"
        system_prompt = f"{system}\n\n{JSON_ONLY_INSTRUCTION}" if system else JSON_ONLY_INSTRUCTION
        messages = self._messages(prompt, system_prompt)
        temp = JSON_TEMPERATURE if temperature is None else temperature
        model_cls = schema if isinstance(schema, type) and issubclass(schema, BaseModel) else None

        problem = ""
        for attempt in (1, 2):
            raw, done_reason = self._chat(messages, max_tokens=max_tokens, temperature=temp, response_format=response_format)
            try:
                data = extract_json(raw)
            except ValueError as exc:
                problem = f"not valid JSON ({exc})"
                if done_reason == "length":
                    problem = (
                        f"it was cut off at the {max_tokens}-token limit before the JSON object was complete; "
                        "keep every value short and stay within the requested number of items"
                    )
            else:
                if model_cls is None:
                    return data
                try:
                    model_cls.model_validate(data)
                    return data
                except ValidationError as exc:
                    problem = f"JSON did not match the schema ({_summarise(exc)})"
                    if attempt == 2:
                        # Parseable JSON: hand it back and let the task decide (it falls
                        # back to the deterministic implementation on a validation error).
                        return data
            logger.info("Ollama %s attempt %d unusable: %s", self.model, attempt, problem)
            messages = [
                *messages,
                {"role": "assistant", "content": raw},
                {"role": "user", "content": JSON_RETRY_NUDGE.format(problem=problem)},
            ]
        raise ExternalServiceError(
            f"Ollama model {self.model!r} returned unusable JSON after a retry: {problem}",
            code="llm_bad_json",
        )

    # ------------------------------------------------------------------ introspection

    def status(self) -> dict[str, Any]:
        return check_server(self.base_url, self.model, client=self._probe_client)

    @property
    def is_configured(self) -> bool:
        status = self.status()
        return bool(status["reachable"] and status["model_pulled"])

    def describe(self) -> dict[str, Any]:
        status = self.status()
        return {
            "provider": self.name,
            "model": self.model,
            "configured": bool(status["reachable"] and status["model_pulled"]),
            "base_url": self.base_url,
            "reachable": status["reachable"],
            "model_pulled": status["model_pulled"],
            "version": status["version"],
            "error": status["error"],
        }

    def close(self) -> None:
        self._client.close()
        self._probe_client.close()


def _error_text(response: httpx.Response) -> str:
    try:
        body = response.json()
        if isinstance(body, dict) and body.get("error"):
            return str(body["error"])
    except ValueError:
        pass
    return (response.text or "").strip()[:300] or response.reason_phrase


def _summarise(exc: ValidationError, limit: int = 3) -> str:
    parts = []
    for error in exc.errors()[:limit]:
        location = ".".join(str(p) for p in error.get("loc", ())) or "<root>"
        parts.append(f"{location}: {error.get('msg')}")
    return "; ".join(parts)


__all__ = ["DEFAULT_MODEL", "OllamaProvider", "check_server", "resolve_timeout", "strict_schema", "timeout_for"]
