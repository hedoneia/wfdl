import asyncio
import importlib.metadata
import logging
import os
from typing import Any, Callable, Optional

import httpx
import piexif
from PIL import Image

# Transient errors (retryable)
TRANSIENT_ERRORS = (
    *[
        httpx.ConnectTimeout,
        httpx.ReadTimeout,
        httpx.WriteTimeout,
        httpx.PoolTimeout,
        httpx.ConnectError,
        httpx.ReadError,
        httpx.WriteError,
        httpx.CloseError,
        httpx.RemoteProtocolError,
        httpx.ProxyError,
        httpx.TooManyRedirects,
        httpx.DecodingError,
    ],
    # This error type is an exception :)
    # HTTPStatusError can be both transient (5xx) or fatal (4xx);
    # handled specially in fetch() to retry only on 5xx.
    httpx.HTTPStatusError,
)

# Fatal errors (non-retryable)
FATAL_ERRORS = (
    *[
        httpx.LocalProtocolError,
        httpx.UnsupportedProtocol,
        httpx.InvalidURL,
        httpx.CookieConflict,
        httpx.StreamConsumed,
        httpx.ResponseNotRead,
        httpx.RequestNotRead,
        httpx.StreamClosed,
    ],
)


def _sanitize_jpeg(path: str) -> bool:
    try:
        piexif.remove(path, path)
    except piexif._exceptions.InvalidImageDataError:
        return False

    try:
        with Image.open(path) as img:
            img.verify()
    except Exception:
        return False

    try:
        image = Image.open(path)
    except Exception:
        return False

    # Determine WFDL version
    try:
        version = importlib.metadata.version("wfdl")
    except importlib.metadata.PackageNotFoundError:
        version = "unknown"

    comment = f"Downloaded with WFDL v{version}".encode("utf-8")

    try:
        image.save(path, "JPEG", comment=comment)
    except Exception:
        return False

    return True


async def _fetch(
    url: str,
    timeout: float = 50.0,
    backoff: float = 1.0,
    max_retries: int = 10,
    max_backoff: float = 30.0,
    exponential_backoff: bool = True,
    proxy: Optional[str | httpx.Proxy] = None,
    logger: logging.Logger = logging.getLogger("WikiFeetClient"),
) -> Optional[httpx.Response]:
    """Fetch the URL and return the response, with retries and backoff."""

    attempt = 1
    delay = backoff

    # TODO: Reuse one AsyncClient for all fetches for speed.
    async with httpx.AsyncClient(timeout=httpx.Timeout(timeout), proxy=proxy) as client:
        while attempt <= max_retries:
            try:
                response = await client.get(url)
                response.raise_for_status()
                logger.info(
                    f"Fetched URL successfully " f"({response.status_code}): `{url}` "
                )
                return response

            except TRANSIENT_ERRORS as exc:
                status = getattr(getattr(exc, "response", None), "status_code", None)
                # Special handling for HTTPStatusError!
                if isinstance(exc, httpx.HTTPStatusError) and status is not None:
                    if 500 <= status < 600:
                        logger.warning(
                            f"{type(exc).__name__} ({status}) "
                            f"fetching URL: `{url}`, "
                            f"retrying in {delay:.1f}s "
                            f"(attempt {attempt}/{max_retries})"
                        )
                    else:
                        logger.error(
                            f"{type(exc).__name__} ({status}) "
                            f"fetching URL: `{url}`, "
                            "giving up!"
                        )
                        return None
                else:
                    logger.warning(
                        f"{type(exc).__name__} "
                        f"fetching URL: `{url}`, "
                        f"retrying in {delay:.1f}s "
                        f"(attempt {attempt}/{max_retries})"
                    )

                # Retry if transient
                if not isinstance(exc, httpx.HTTPStatusError) or (
                    500 <= getattr(exc.response, "status_code", 0) < 600
                ):
                    await asyncio.sleep(delay)
                    attempt += 1
                    if exponential_backoff:
                        delay = min(delay * 2, max_backoff)
                else:
                    return None

            except FATAL_ERRORS as exc:
                logger.error(
                    f"{type(exc).__name__} " f"fetching URL: `{url}`, " "giving up!"
                )
                return None

    logger.error(f"Max retries exceeded for URL: `{url}`, giving up.")
    return None


async def _download(
    url: str,
    path: str,
    fetch_func: Callable[..., Any] = _fetch,
    fetch_kwargs: dict[str, Any] = {},
    logger: logging.Logger = logging.getLogger("WikiFeetClient"),
    force_download: bool = False,
    sanitize: bool = True,
) -> Optional[str]:
    """Download a file to the given path using the provided fetch function."""

    os.makedirs(os.path.dirname(path), exist_ok=True)

    if not force_download and os.path.exists(path):
        logger.info(f"File already exists, skipping: {path}")
        return path

    response = await fetch_func(url, **fetch_kwargs)
    if not response:
        logger.error(f"Failed to fetch `{url}`, skipping download.")
        return

    content_type = response.headers.get("content-type", "").split(";")[0].lower()
    if content_type != "image/jpeg":
        is_jpeg = False
        logger.warning(
            f"Downloaded content from `{url}` is not JPEG "
            f"(Content-Type: {content_type})"
        )
    else:
        is_jpeg = True

    content = await response.aread()

    with open(path, "wb") as f:
        f.write(content)

    if is_jpeg and sanitize:
        sanitized = _sanitize_jpeg(path)
        if not sanitized:
            logger.warning(f"Sanitization failed, dropping file: {path}")

    logger.info(f"Downloaded successfully: {path}")
    return path
