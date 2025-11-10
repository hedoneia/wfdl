from unittest.mock import patch

import httpx
import pytest
import respx

from wfdl.utils import _download, _fetch


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
            response = await _fetch(
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
            response = await _fetch(
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
            response = await _fetch(
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
            response = await _fetch(
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

        response = await _fetch(
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

        response = await _fetch(
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

        response = await _fetch(
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
            response = await _fetch(
                url,
                max_retries=5,
                backoff=0.1,
                exponential_backoff=False
            )

        assert response is not None
        assert response.status_code == 200
        assert slept == [0.1, 0.1]  # constant backoff

    @pytest.mark.asyncio
    async def test_download_successful(self, tmp_path):
        url = "https://example.com/image.jpg"
        content = b"fakejpegcontent"

        async def fake_fetch(url, **kwargs):
            return httpx.Response(
                200,
                headers={"content-type": "image/jpeg"},
                content=content,
                request=httpx.Request("GET", url),
            )

        path = tmp_path / "image.jpg"
        result = await _download(
            str(url),
            str(path),
            fetch_func=fake_fetch,
            fetch_kwargs={},
            sanitize=False
        )

        assert result is str(path)
        assert path.exists()
        assert path.read_bytes() == content

    @pytest.mark.asyncio
    async def test_download_file_exists_skips(self, tmp_path):
        path = tmp_path / "existing.jpg"
        path.write_bytes(b"exists")

        async def fake_fetch(url, **kwargs):
            raise AssertionError("Should not call fetch")

        result = await _download(
            "https://example.com/image.jpg",
            str(path),
            fetch_func=fake_fetch, fetch_kwargs={}
        )

        assert result is str(path)
        assert path.read_bytes() == b"exists"

    @pytest.mark.asyncio
    async def test_download_non_jpeg_warns(self, tmp_path, caplog):
        content = b"pngcontent"

        async def fake_fetch(url, **kwargs):
            return httpx.Response(
                200,
                headers={"content-type": "image/png"},
                content=content,
                request=httpx.Request("GET", url),
            )

        path = tmp_path / "image.png"

        with caplog.at_level("WARNING"):
            result = await _download(
                "https://example.com/image.png",
                str(path),
                fetch_func=fake_fetch, fetch_kwargs={}
            )

        assert result == str(path)
        assert any("not JPEG" in msg for msg in caplog.messages)
        assert path.read_bytes() == content

    @pytest.mark.asyncio
    async def test_download_fetch_returns_none(self, tmp_path, caplog):
        async def fake_fetch(url, **kwargs):
            return None

        path = tmp_path / "image.jpg"

        with caplog.at_level("ERROR"):
            result = await _download(
                "https://example.com/image.jpg",
                str(path),
                fetch_func=fake_fetch, fetch_kwargs={}
            )

        assert result is None
        assert not path.exists()
        assert any("Failed to fetch" in msg for msg in caplog.messages)

    @pytest.mark.asyncio
    async def test_download_sanitize_called(self, tmp_path, monkeypatch):
        url = "https://example.com/image.jpg"
        content = b"fakejpegcontent"

        async def fake_fetch(url, **kwargs):
            return httpx.Response(
                200,
                headers={"content-type": "image/jpeg"},
                content=content,
                request=httpx.Request("GET", url),
            )

        path = tmp_path / "image.jpg"

        sanitize_called = {}

        # Patch _sanitize_jpeg to track call
        def fake_sanitize(p):
            sanitize_called["called"] = p

        monkeypatch.setattr("wfdl.utils._sanitize_jpeg", fake_sanitize)

        result = await _download(
            str(url),
            str(path),
            fetch_func=fake_fetch,
            fetch_kwargs={},
            sanitize=True
        )

        assert result == str(path)
        assert path.exists()
        assert sanitize_called.get("called") == str(path)
