import asyncio
import logging
from typing import Optional

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

    async def download(self, url: str | tuple[str, ...]) -> None:
        extractor = WikiFeetExtractor()
        response = await _fetch(url)
        data = extractor._extract_subject_profile(response.text)

        async with asyncio.TaskGroup() as tg:
            for image in data["images"]:
                tg.create_task(
                    _download(
                        image["url"],
                        f"./_tmp/{image['url'].split('/')[-1]}"
                    )
                )

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
    import sys

    wf = WikiFeetClient()
    asyncio.run(wf.download(sys.argv[1]))
