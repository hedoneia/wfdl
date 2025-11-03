import asyncio
import logging
from typing import Optional

import httpx

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


async def fetch(
    url: str,
    timeout: float = 10.0,
    backoff: float = 3.0,
    max_retries: int = 5,
    max_backoff: float = 30.0,
    exponential_backoff: bool = True,
    proxy: Optional[str | httpx.Proxy] = None,
    logger: logging.Logger = logging.getLogger("WikiFeetClient"),
) -> Optional[httpx.Response]:
    """Fetch the URL and return the response, with retries and backoff."""

    attempt = 1
    delay = backoff

    async with httpx.AsyncClient(
        timeout=httpx.Timeout(timeout),
        proxy=proxy
    ) as client:
        while attempt <= max_retries:
            try:
                response = await client.get(url)
                response.raise_for_status()
                logger.info(
                    f"Fetched URL successfully "
                    f"({response.status_code}): `{url}` "
                )
                return response

            except TRANSIENT_ERRORS as exc:
                status = getattr(
                    getattr(exc, "response", None), "status_code", None
                )
                # Special handling for HTTPStatusError!
                if (
                    isinstance(exc, httpx.HTTPStatusError)
                    and status is not None
                ):
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
                    f"{type(exc).__name__} "
                    f"fetching URL: `{url}`, "
                    "giving up!"
                )
                return None

    logger.error(f"Max retries exceeded for URL: `{url}`, giving up.")
    return None
