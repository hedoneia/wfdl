from unittest.mock import patch

import httpx
import pytest
import respx

from wfdl.utils import fetch


class TestFetchHTTPStatus:

    @respx.mock
    @pytest.mark.asyncio
    async def test_fetch_5xx_retries_then_success(self):
        url = "https://example.com"
        call_count = 0
        slept = []

        async def fake_sleep(duration):
            slept.append(duration)

        async def side_effect(request):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                response = httpx.Response(502, request=request)
                raise httpx.HTTPStatusError(
                    "Bad Gateway",
                    request=request,
                    response=response
                )
            return httpx.Response(200, text="OK", request=request)

        respx.get(url).mock(side_effect=side_effect)

        with patch("asyncio.sleep", side_effect=fake_sleep):
            response = await fetch(
                url,
                max_retries=5,
                backoff=0.1,
                exponential_backoff=True
            )

        assert response is not None
        assert response.status_code == 200
        assert call_count == 3
        assert slept == [0.1, 0.2]

    @respx.mock
    @pytest.mark.asyncio
    async def test_fetch_4xx_client_error_gives_up(self, caplog):
        url = "https://example.com"
        respx.get(url).mock(
            return_value=httpx.Response(404, request=httpx.Request("GET", url))
        )

        with caplog.at_level("ERROR"):
            response = await fetch(
                url,
                max_retries=3,
                backoff=0.1
            )

        assert response is None
        assert any("404" in msg for msg in caplog.messages)

    @respx.mock
    @pytest.mark.asyncio
    async def test_fetch_fatal_error_stops_retries(self, caplog):
        url = "https://example.com"
        respx.get(url).mock(side_effect=httpx.InvalidURL("bad url"))

        with caplog.at_level("ERROR"):
            response = await fetch(
                url,
                max_retries=5,
                backoff=0.1
            )

        assert response is None
        assert any("InvalidURL" in msg for msg in caplog.messages)

    @respx.mock
    @pytest.mark.asyncio
    async def test_fetch_max_retries_exceeded(self, caplog):
        url = "https://example.com"
        call_count = 0
        slept = []

        async def fake_sleep(duration):
            slept.append(duration)

        async def side_effect(request):
            nonlocal call_count
            call_count += 1
            response = httpx.Response(502, request=request)
            raise httpx.HTTPStatusError(
                "Server Error",
                request=request,
                response=response
            )

        respx.get(url).mock(side_effect=side_effect)

        with patch("asyncio.sleep", side_effect=fake_sleep):
            response = await fetch(
                url,
                max_retries=3,
                backoff=0.1
            )

        assert response is None
        assert call_count == 3
        assert any("Max retries exceeded" in msg for msg in caplog.messages)
        # Sleep occurs before each retry, so the last attempt also sleeps
        assert slept == [0.1, 0.2, 0.4]

    @respx.mock
    @pytest.mark.asyncio
    async def test_fetch_timeout_retries(self):
        url = "https://example.com"
        call_count = 0

        async def side_effect(request):
            nonlocal call_count
            call_count += 1
            raise httpx.ConnectTimeout("Timeout")

        respx.get(url).mock(side_effect=side_effect)

        response = await fetch(
            url,
            max_retries=3,
            backoff=0.1,
            exponential_backoff=False
        )

        assert response is None
        assert call_count == 3

    @respx.mock
    @pytest.mark.asyncio
    async def test_fetch_non_httpstatus_transient_error(self):
        url = "https://example.com"
        call_count = 0

        async def side_effect(request):
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise httpx.ConnectError("Connection error")
            return httpx.Response(200, text="OK", request=request)

        respx.get(url).mock(side_effect=side_effect)

        response = await fetch(
            url,
            max_retries=3,
            backoff=0.1,
            exponential_backoff=False
        )

        assert response is not None
        assert response.status_code == 200
        assert call_count == 2

    @respx.mock
    @pytest.mark.asyncio
    async def test_fetch_success_first_attempt(self):
        url = "https://example.com"
        call_count = 0

        async def side_effect(request):
            nonlocal call_count
            call_count += 1
            return httpx.Response(200, text="OK", request=request)

        respx.get(url).mock(side_effect=side_effect)

        response = await fetch(
            url,
            max_retries=3,
            backoff=0.1
        )

        assert response is not None
        assert response.status_code == 200
        assert call_count == 1

    @respx.mock
    @pytest.mark.asyncio
    async def test_fetch_no_exponential_backoff(self):
        url = "https://example.com"
        call_count = 0
        slept = []

        async def fake_sleep(duration):
            slept.append(duration)

        async def side_effect(request):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                response = httpx.Response(502, request=request)
                raise httpx.HTTPStatusError(
                    "Server Error",
                    request=request,
                    response=response
                )
            return httpx.Response(200, text="OK", request=request)

        respx.get(url).mock(side_effect=side_effect)

        with patch("asyncio.sleep", side_effect=fake_sleep):
            response = await fetch(
                url,
                max_retries=5,
                backoff=0.1,
                exponential_backoff=False
            )

        assert response is not None
        assert response.status_code == 200
        assert slept == [0.1, 0.1]  # constant backoff
