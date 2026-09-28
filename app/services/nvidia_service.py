import asyncio
import logging
from typing import Optional, Dict, Any
import httpx
from app.config import settings

logger = logging.getLogger(__name__)


class NvidiaServiceError(Exception):
    """Base exception for NVIDIA NIM API interactions."""
    pass


class NvidiaAuthError(NvidiaServiceError):
    """Raised when NVIDIA API key is invalid or unauthorized."""
    pass


class NvidiaRateLimitError(NvidiaServiceError):
    """Raised when NVIDIA API rate limits or quota are exceeded."""
    pass


class NvidiaService:
    """
    Production-grade NVIDIA NIM API Client with:
    - Connection pooling (reusable persistent async client)
    - Automatic exponential backoff retries on transient errors
    - Fully configurable request options & timeouts
    - Safe error handling & detailed telemetry logging
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        default_model: Optional[str] = None
    ):
        self._api_key = api_key
        self._base_url = (base_url or settings.nvidia_base_url).rstrip("/")
        self._default_model = default_model or settings.nvidia_model
        self._client: Optional[httpx.AsyncClient] = None

    @property
    def api_key(self) -> str:
        key = self._api_key or settings.nvidia_api_key
        if not key or not key.strip() or key.strip() == "your_nvidia_api_key_here":
            raise NvidiaAuthError(
                "NVIDIA API key is not configured. Please set NVIDIA_API_KEY in your .env file."
            )
        return key.strip()

    def _get_client(self) -> httpx.AsyncClient:
        """
        Maintains an optimized, persistent connection pool for HTTP/2 and keep-alive.
        Avoids socket exhaustion and eliminates TLS handshake overhead on every call.
        """
        if self._client is None or getattr(self._client, "is_closed", False) is True:
            limits = httpx.Limits(
                max_connections=settings.nvidia_max_connections,
                max_keepalive_connections=settings.nvidia_max_keepalive_connections,
                keepalive_expiry=30.0
            )
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(settings.nvidia_timeout_seconds),
                limits=limits,
                follow_redirects=True
            )
        return self._client

    async def close(self):
        """Cleanly releases connection pool resources upon shutdown."""
        if self._client is not None and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    async def generate_chat_completion(
        self,
        system_prompt: str,
        user_prompt: str,
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        stream: bool = False
    ) -> str:
        """
        Executes an asynchronous chat completion request to NVIDIA NIM API
        with exponential backoff retries on transient HTTP and network faults.
        """
        active_model = model or self._default_model or settings.nvidia_model
        active_temp = temperature if temperature is not None else settings.nvidia_temperature
        active_max_tokens = max_tokens if max_tokens is not None else settings.nvidia_max_tokens
        endpoint_url = f"{self._base_url}/chat/completions"

        headers: Dict[str, str] = {
            "Authorization": f"Bearer {self.api_key}",
            "Accept": "application/json",
            "Content-Type": "application/json"
        }

        payload: Dict[str, Any] = {
            "model": active_model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            "temperature": active_temp,
            "max_tokens": active_max_tokens,
            "stream": stream
        }

        client = self._get_client()
        max_attempts = max(1, settings.nvidia_max_retries + 1)
        delay = settings.nvidia_retry_delay_seconds

        for attempt in range(1, max_attempts + 1):
            try:
                logger.info(
                    "Calling NVIDIA NIM API (Model: %s, Attempt %d/%d, Temp: %.2f)",
                    active_model, attempt, max_attempts, active_temp
                )
                response = await client.post(endpoint_url, headers=headers, json=payload)

                if response.status_code == 200:
                    data = response.json()
                    choices = data.get("choices", [])
                    if not choices or not choices[0].get("message", {}).get("content"):
                        raise NvidiaServiceError("NVIDIA API returned an empty completion.")
                    return choices[0]["message"]["content"].strip()

                # Handle specific error status codes
                if response.status_code in (401, 403):
                    raise NvidiaAuthError(f"NVIDIA API authentication failed ({response.status_code}): {response.text}")
                elif response.status_code == 429:
                    # Rate limit encountered - retry with backoff if attempts remain
                    if attempt < max_attempts:
                        logger.warning("NVIDIA API rate limited (429). Retrying in %.2fs...", delay)
                        await asyncio.sleep(delay)
                        delay *= 2
                        continue
                    raise NvidiaRateLimitError(f"NVIDIA API rate limit exceeded: {response.text}")
                elif response.status_code in (500, 502, 503, 504):
                    # Transient server error - retry with backoff
                    if attempt < max_attempts:
                        logger.warning("NVIDIA transient server error (%d). Retrying in %.2fs...", response.status_code, delay)
                        await asyncio.sleep(delay)
                        delay *= 2
                        continue
                    raise NvidiaServiceError(f"NVIDIA API server error ({response.status_code}): {response.text}")
                else:
                    raise NvidiaServiceError(f"NVIDIA API error ({response.status_code}): {response.text}")

            except httpx.TimeoutException as te:
                if attempt < max_attempts:
                    logger.warning("NVIDIA API timeout on attempt %d. Retrying in %.2fs...", attempt, delay)
                    await asyncio.sleep(delay)
                    delay *= 2
                    continue
                raise NvidiaServiceError(f"NVIDIA API timed out after {settings.nvidia_timeout_seconds}s") from te

            except (NvidiaAuthError, NvidiaRateLimitError, NvidiaServiceError):
                raise
            except Exception as e:
                if attempt < max_attempts:
                    logger.warning("NVIDIA communication error (%s). Retrying in %.2fs...", str(e), delay)
                    await asyncio.sleep(delay)
                    delay *= 2
                    continue
                raise NvidiaServiceError(f"Failed to communicate with NVIDIA API: {str(e)}") from e

        raise NvidiaServiceError("Exhausted maximum retry attempts calling NVIDIA API.")


# Singleton instance for high-throughput connection pooling
nvidia_service = NvidiaService()
