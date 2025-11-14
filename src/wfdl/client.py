import asyncio
import logging
import os
from typing import Optional, Sequence

from .extractor import WikiFeetExtractor
from .utils import _download, _fetch


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
        self.extractor = WikiFeetExtractor()

    async def _solo_download(
        self,
        url: str,
        path: Optional[str] = os.getcwd()
    ) -> None:
        response = await _fetch(url)
        data = self.extractor._extract_subject_profile(response.text)
        path = os.path.join(path, url.rstrip("/").split("/")[-1])
        async with asyncio.TaskGroup() as tg:
            for image in data["images"]:
                filename = image['url'].split('/')[-1]
                tg.create_task(
                    _download(
                        image["url"],
                        os.path.join(path, filename)
                    )
                )

    async def _multi_download(
        self,
        urls: Sequence[str],
        path: Optional[str] = os.getcwd()
    ) -> None:
        async with asyncio.TaskGroup() as tg:
            for url in urls:
                tg.create_task(
                    self._solo_download(url, path)
                )

    def download(self, urls: Sequence[str], path: str) -> None:
        asyncio.run(self._multi_download(urls, path))

    def search(
        self,
        keyword: Optional[str] = None,
        filters: Optional[dict[str, str]] = None
    ) -> list[str]:
        pass
