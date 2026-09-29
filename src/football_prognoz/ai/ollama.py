"""Direct Ollama chat client (cloud at ollama.com or a local server). No SDK, no LangChain."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import httpx

from football_prognoz.config import FREE_OLLAMA_MODELS, OLLAMA_CLOUD_HOST

log = logging.getLogger(__name__)

# Status codes after which the fallback model is worth one more try.
# 402: "this model is not included in your free usage" / extra usage only.
_FALLBACK_STATUSES = frozenset({402, 404, 500, 502, 503, 504})
_PLAN_WORDS = ("subscription", "upgrade", "plan", "usage", "credit")


class LLMError(Exception):
    """LLM call failed. `message` is safe to show in the UI (Russian, no secrets)."""

    def __init__(
        self,
        message: str,
        status_code: int | None = None,
        *,
        fallback_ok: bool | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        if fallback_ok is None:
            fallback_ok = status_code in _FALLBACK_STATUSES
        self.fallback_ok = fallback_ok


@dataclass(frozen=True)
class LLMReply:
    text: str
    model: str
    notice: str = ""  # Russian, set when a fallback model answered instead of OLLAMA_MODEL


def fallback_notice(requested: str, used: str, first_error: LLMError | None) -> str:
    """Short Russian notice shown under the AI block when another model answered."""
    if first_error is not None and first_error.status_code == 402:
        why = "не входит в бесплатный тариф Ollama (402)"
    elif first_error is not None and first_error.status_code == 403:
        why = "требует подписку Ollama (403)"
    elif first_error is not None and first_error.status_code == 404:
        why = "не найдена (404)"
    elif first_error is not None and first_error.status_code:
        why = f"недоступна (HTTP {first_error.status_code})"
    else:
        why = "не ответила"
    return f"Модель {requested} {why} — ответила {used}. Сменить модель: Настройки → OLLAMA_MODEL."


def think_for_model(model: str) -> bool | str | None:
    """`think` value per model family (docs.ollama.com/capabilities/thinking).

    deepseek-v4.1-flash can switch thinking off; gpt-oss only accepts levels, so "low".
    Unknown models get no `think` field at all.
    """
    name = model.strip().lower()
    if name.startswith("deepseek"):
        return False
    if name.startswith("gpt-oss"):
        return "low"
    return None


class OllamaClient:
    """POST {host}/api/chat with `stream: false`. Tries the fallback model once on 404/5xx."""

    def __init__(
        self,
        *,
        model: str,
        host: str = OLLAMA_CLOUD_HOST,
        api_key: str = "",
        fallback_model: str | None = None,
        http: httpx.Client | None = None,
        timeout: float = 90.0,
        free_models: tuple[str, ...] | None = None,
    ) -> None:
        self._host = (host.strip() or OLLAMA_CLOUD_HOST).rstrip("/")
        self._api_key = api_key.strip()
        self.model = model.strip()
        fallback = (fallback_model or "").strip()
        self.fallback_model = fallback if fallback and fallback != self.model else None
        if free_models is None:
            free_models = FREE_OLLAMA_MODELS if self._is_cloud() else ()
        self.free_models = tuple(free_models)
        self._owns = http is None
        self._http = http or httpx.Client(timeout=httpx.Timeout(timeout, connect=10.0))

    @property
    def host(self) -> str:
        return self._host

    def _is_cloud(self) -> bool:
        hostname = (httpx.URL(self._host).host or "").lower()
        return hostname == "ollama.com" or hostname.endswith(".ollama.com")

    def model_chain(self) -> list[str]:
        """OLLAMA_MODEL → OLLAMA_FALLBACK_MODEL → free cloud models, without repeats."""
        chain = [self.model] if self.model else []
        if self.fallback_model:
            chain.append(self.fallback_model)
        chain.extend(self.free_models)
        return list(dict.fromkeys(m for m in chain if m))

    def close(self) -> None:
        if self._owns:
            self._http.close()

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        return headers

    def _payload(
        self, model: str, system: str, user: str, temperature: float, json_mode: bool
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "stream": False,
            "options": {"temperature": temperature},
        }
        think = think_for_model(model)
        if think is not None:
            payload["think"] = think
        if json_mode:
            # Best-effort hint: Ollama Cloud does not guarantee structured outputs.
            payload["format"] = "json"
        return payload

    def chat(
        self,
        system: str,
        user: str,
        *,
        temperature: float = 0.2,
        json_mode: bool = True,
    ) -> LLMReply:
        models = self.model_chain()
        if not models:
            raise LLMError("Не задана модель Ollama. Укажите OLLAMA_MODEL в Настройках.")
        first_error: LLMError | None = None
        for index, model in enumerate(models):
            try:
                reply = self._chat_once(model, system, user, temperature, json_mode)
            except LLMError as exc:
                first_error = first_error or exc
                can_retry = index + 1 < len(models) and exc.fallback_ok
                if not can_retry:
                    raise
                log.warning("Ollama model %s failed (%s); trying %s", model, exc, models[index + 1])
                continue
            if index > 0:
                notice = fallback_notice(models[0], model, first_error)
                return LLMReply(text=reply.text, model=reply.model, notice=notice)
            return reply
        raise first_error or LLMError("Ollama не ответил.")

    def _chat_once(
        self, model: str, system: str, user: str, temperature: float, json_mode: bool
    ) -> LLMReply:
        url = f"{self._host}/api/chat"
        try:
            response = self._http.post(
                url,
                headers=self._headers(),
                json=self._payload(model, system, user, temperature, json_mode),
            )
        except httpx.TimeoutException as exc:
            raise LLMError(f"Ollama не ответил вовремя (модель {model}).") from exc
        except httpx.HTTPError as exc:
            raise LLMError(f"Нет соединения с Ollama ({self._host}).") from exc
        if response.status_code >= 400:
            raise _error_for(response, model)
        try:
            data = response.json()
        except ValueError as exc:
            raise LLMError("Ollama вернул не-JSON ответ.", response.status_code) from exc
        if not isinstance(data, dict):
            raise LLMError("Неожиданный ответ Ollama.", response.status_code)
        if data.get("error"):
            raise LLMError(f"Ollama: {data['error']}", response.status_code)
        message = data.get("message") or {}
        content = str(message.get("content") or "").strip() if isinstance(message, dict) else ""
        if not content:
            raise LLMError(f"Ollama вернул пустой ответ (модель {model}).", fallback_ok=True)
        return LLMReply(text=content, model=str(data.get("model") or model))


def _error_for(response: httpx.Response, model: str) -> LLMError:
    status = response.status_code
    detail = ""
    try:
        body = response.json()
        if isinstance(body, dict) and body.get("error"):
            detail = str(body["error"])[:200]
    except ValueError:
        detail = ""
    if status == 401:
        text = "Ollama отклонил запрос (401): проверьте OLLAMA_API_KEY."
    elif status == 402:
        text = f"Модель {model} не входит в бесплатный тариф Ollama (402)."
    elif status == 403:
        text = f"Нет доступа к модели {model} (403): проверьте тариф Ollama."
    elif status == 404:
        text = f"Модель {model} не найдена в Ollama (404)."
    elif status == 429:
        text = "Лимит Ollama исчерпан или очередь занята (429). Попробуйте позже."
    elif status == 502:
        text = f"Облачная модель {model} сейчас недоступна (502)."
    else:
        text = f"Ошибка Ollama: HTTP {status}."
    if detail and status not in {401}:
        text = f"{text} {detail}"
    plan_limited = status == 403 and any(word in detail.lower() for word in _PLAN_WORDS)
    return LLMError(text, status, fallback_ok=True if plan_limited else None)
