import asyncio
import logging
import os
from typing import Optional, Sequence
from urllib.parse import quote

from .extractor import WikiFeetExtractor
from .utils import _download, _fetch


class WikiFeetClient:
    def __init__(
        self,
        log_path: Optional[str] = None,
        semaphore: int = 100,
    ) -> None:
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
        self._semaphore = asyncio.Semaphore(semaphore)
        self.logger.info(f"Semaphore: {self._semaphore}")

    async def _solo_download(
        self,
        url: str,
        path: Optional[str] = os.getcwd(),
    ) -> None:
        response = await _fetch(url)
        data = self.extractor._extract_subject_profile(response.text)
        path = os.path.join(path, url.rstrip("/").split("/")[-1])
        async with asyncio.TaskGroup() as tg:
            for image in data["images"]:
                filename = image["url"].split("/")[-1]

                async def _semaphore_download(
                    url=image["url"],
                    filename=filename,
                ):
                    async with self._semaphore:
                        await _download(url, os.path.join(path, filename))

                tg.create_task(_semaphore_download())

    async def _multi_download(
        self, urls: Sequence[str], path: Optional[str] = os.getcwd()
    ) -> None:
        async with asyncio.TaskGroup() as tg:
            for url in urls:

                async def _semaphore_download(url=url):
                    async with self._semaphore:
                        await self._solo_download(url, path)

                tg.create_task(_semaphore_download())

    def download(self, urls: Sequence[str], path: str) -> None:
        asyncio.run(self._multi_download(urls, path))

    async def _search(
        self,
        keyword: Optional[str] = None,
        sources: Optional[list[str]] = None,
        verbose: bool = False,
    ) -> list[str]:
        if not keyword:
            return []

        encoded_keyword = quote(keyword)

        all_sources = {
            "prime": f"https://wikifeet.com/search/{encoded_keyword}",
            "x": f"https://wikifeetx.com/search/{encoded_keyword}",
            "men": f"https://men.wikifeet.com/search/{encoded_keyword}",
        }

        if sources:
            urls = [(s, all_sources[s]) for s in sources if s in all_sources]
        else:
            urls = list(all_sources.items())

        results = []

        async def _fetch_and_extract(source: str, url: str):
            page = 1
            while True:

                async with self._semaphore:
                    response = await _fetch(f"{url}?{page}")

                content = self.extractor._parse_search_page(
                    response.text,
                    source,
                )

                if not content:
                    break

                if verbose:
                    async with self._semaphore:
                        for item in content:
                            response = await _fetch(item["url"])
                            data = self.extractor._extract_subject_profile(
                                response.text,
                            )

                            extra = [
                                "gender",
                                "image_count",
                                "birth_place",
                                "shoe_size",
                            ]

                            data = {k: data[k] for k in extra if k in data}

                            item.update(data)

                page += 1

                results.append(content)

        async with asyncio.TaskGroup() as tg:
            for url in urls:
                tg.create_task(_fetch_and_extract(*url))

        return results

    def search(
        self,
        keyword: Optional[str] = None,
        sources: Optional[list[str]] = None,
        verbose: bool = False,
    ) -> list[str]:
        """Sync wrapper for the async _search method."""
        return asyncio.run(self._search(keyword, sources, verbose))
