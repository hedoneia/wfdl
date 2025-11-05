# import asyncio
import logging
from typing import Optional

from .utils import fetch


class WikiFeetClient:
    def __init__(self, log_path: Optional[str] = None) -> None:
        self.logger = logging.getLogger("WikiFeetClient")
        self.logger.setLevel(logging.INFO)
        self.logger.propagate = False
        formatter = logging.Formatter(
            "[%(asctime)s - %(name)s - %(levelname)s] %(message)s",
            "%Y-%m-%d %H:%M:%S",
        )
        if not self.logger.handlers:
            if log_path:
                handler = logging.FileHandler(log_path)
            else:
                handler = logging.StreamHandler()
            handler.setFormatter(formatter)
            self.logger.addHandler(handler)

    async def download(self, url: str | tuple[str, ...]) -> None:

        await fetch(url, logger=self.logger)

    def search(
        self,
        keyword: Optional[str] = None,
        filters: Optional[dict[str, str]] = None
    ) -> list[str]:
        pass


# TODO:
# Add sync wrapper (e.g. `download()`) around async (`__async_download`)
# so API and args like `--download` work without users handling asyncio.
# Keep async private to hint that direct import is advanced usage.
if __name__ == "__main__":
    pass
