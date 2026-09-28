import pytest
from unittest.mock import AsyncMock, patch, MagicMock
import httpx
from app.services.nvidia_service import (
    NvidiaService,
    NvidiaAuthError,
    NvidiaRateLimitError,
    NvidiaServiceError
)
from app.config import settings


@pytest.mark.asyncio
async def test_nvidia_service_missing_api_key():
    """Verify NvidiaAuthError is raised when API key is missing or blank."""
    service = NvidiaService(api_key="")
    service._api_key = ""
    with patch.object(settings, "nvidia_api_key", ""):
        with pytest.raises(NvidiaAuthError) as exc_info:
            await service.generate_chat_completion(
                system_prompt="system",
                user_prompt="user"
            )
        assert "NVIDIA API key is not configured" in str(exc_info.value)


@pytest.mark.asyncio
async def test_nvidia_service_successful_completion():
    """Verify chat completion succeeds when NVIDIA API returns 200."""
    service = NvidiaService(api_key="nvapi-test-key")
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "choices": [
            {"message": {"content": "Generated summary from NVIDIA."}}
        ]
    }

    mock_client = AsyncMock()
    mock_client.post.return_value = mock_response
    service._client = mock_client

    result = await service.generate_chat_completion(
        system_prompt="You are a helpful study assistant.",
        user_prompt="Summarize this text."
    )

    assert result == "Generated summary from NVIDIA."
    mock_client.post.assert_called_once()
    await service.close()


@pytest.mark.asyncio
async def test_nvidia_service_rate_limit_error():
    """Verify NvidiaRateLimitError is raised on HTTP 429 after retries."""
    service = NvidiaService(api_key="nvapi-test-key")
    mock_response = MagicMock()
    mock_response.status_code = 429
    mock_response.text = "Rate limit exceeded"

    mock_client = AsyncMock()
    mock_client.post.return_value = mock_response
    service._client = mock_client

    with patch.object(settings, "nvidia_max_retries", 0):
        with pytest.raises(NvidiaRateLimitError):
            await service.generate_chat_completion(
                system_prompt="system",
                user_prompt="user"
            )


@pytest.mark.asyncio
async def test_nvidia_service_auth_error():
    """Verify NvidiaAuthError is raised on HTTP 401 without retries."""
    service = NvidiaService(api_key="nvapi-test-key")
    mock_response = MagicMock()
    mock_response.status_code = 401
    mock_response.text = "Unauthorized"

    mock_client = AsyncMock()
    mock_client.post.return_value = mock_response
    service._client = mock_client

    with pytest.raises(NvidiaAuthError):
        await service.generate_chat_completion(
            system_prompt="system",
            user_prompt="user"
        )


@pytest.mark.asyncio
async def test_nvidia_service_retry_and_recover():
    """Verify NvidiaService successfully retries transient 503 and returns on recovery."""
    service = NvidiaService(api_key="nvapi-test-key")
    
    mock_503 = MagicMock()
    mock_503.status_code = 503
    mock_503.text = "Service Temporarily Unavailable"

    mock_200 = MagicMock()
    mock_200.status_code = 200
    mock_200.json.return_value = {
        "choices": [{"message": {"content": "Recovered response"}}]
    }

    mock_client = AsyncMock()
    mock_client.post.side_effect = [mock_503, mock_200]
    service._client = mock_client

    with patch.object(settings, "nvidia_max_retries", 2), \
         patch.object(settings, "nvidia_retry_delay_seconds", 0.001):
        result = await service.generate_chat_completion(
            system_prompt="system",
            user_prompt="user"
        )
        assert result == "Recovered response"
        assert mock_client.post.call_count == 2
