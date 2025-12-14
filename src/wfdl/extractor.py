import json
import logging
import re
from datetime import datetime, timezone
from typing import Optional

from bs4 import BeautifulSoup


class WikiFeetExtractor:

    GENDER_MAP = {
        0: "female",
        1: "male",
        2: "female",
    }

    TAG_MAP = {
        "T": "toes",
        "S": "soles",
        "A": "Arches",
        "C": "close-up",
        "B": "barefoot",
        "N": "nylons",
    }

    def __init__(
        self,
        logger: logging.Logger = logging.getLogger("WikiFeetClient"),
    ) -> None:
        self.logger = logger

    def _pid_to_url(self, pid: int) -> str:
        """Convert a photo ID to the full Wikifeet image URL."""
        return f"https://pics.wikifeet.com/{pid}.jpg"

    def _fetchname_to_url(self, fetchname: str, source: str) -> str:
        base = {
            "prime": "https://wikifeet.com",
            "x": "https://wikifeetx.com",
            "men": "https://men.wikifeet.com",
        }.get(source, "https://men.wikifeet.com")
        return f"{base}/{fetchname}"

    def _parse_birth_date(
        self,
        birth_date: Optional[str],
    ) -> Optional[tuple[str, int]]:
        if not birth_date:
            return None
        try:
            birth = datetime.fromisoformat(birth_date.replace("Z", "+00:00"))
            birth_date = birth.strftime("%Y-%m-%d")
            today = datetime.now(timezone.utc)
            age = (
                today.year
                - birth.year
                - ((today.month, today.day) < (birth.month, birth.day))
            )
            return birth_date, age
        except Exception:
            return None

    def _parse_gender(self, gender_index: Optional[int]) -> Optional[str]:
        if gender_index is None:
            return None
        return self.GENDER_MAP.get(gender_index, None)

    def _parse_height(
        self,
        height_us: Optional[str],
    ) -> Optional[dict[str, str | int]]:
        if not height_us or len(height_us) != 2:
            return None
        try:
            feet, inches = int(height_us[0]), int(height_us[1])
            cm = round((feet * 12 + inches) * 2.54)
            return {"imperial": f"{feet} ft {inches} in", "cm": cm}
        except Exception:
            return None

    def _parse_tags(self, tag: Optional[str]) -> Optional[list[str]]:
        if not tag:
            return None
        return [self.TAG_MAP[c] for c in tag if c in self.TAG_MAP] or None

    def _extract_subject_profile(self, html: str) -> Optional[dict]:
        soup = BeautifulSoup(html, "html.parser")
        script_tag = soup.find(
            "script",
            src=False,
            string=re.compile(r"tdata\s*="),
        )
        if not script_tag:
            self.logger.warning("No <script> tag with tdata found in HTML.")
            return None
        data_match = re.search(
            r"tdata\s*=\s*(\{.*?\});",
            script_tag.string,
            re.DOTALL,
        )
        if not data_match:
            self.logger.warning("tdata variable not found in script content.")
            return None
        try:
            data = json.loads(data_match.group(1))
            self.logger.debug("tdata JSON parsed successfully.")
        except json.JSONDecodeError as e:
            self.logger.error("Failed to parse tdata JSON: %s", e)
            return None

        images = [
            {
                "url": self._pid_to_url(item["pid"]),
                "tags": self._parse_tags(item.get("tags")),
            }
            for item in data.get("gallery", [])
        ] or None
        birth_info = self._parse_birth_date(data.get("bdate"))
        result = {
            "name": data.get("cname"),
            "gender": self._parse_gender(data.get("gender")),
            "birth_place": data.get("bplace"),
            "birth_date": birth_info[0] if birth_info else None,
            "age": birth_info[1] if birth_info else None,
            "score": data.get("score"),
            "rating_distribution": data.get("edata", {}).get("stats"),
            "height": self._parse_height(data.get("height_us")),
            "images": images,
            "image_count": len(images) if images else 0,
            "shoe_size": ((data.get("ssize") + 3) / 2 if data.get("ssize") else None),
        }

        return result

    def _parse_search_page(self, html: str, source: str) -> dict[str]:
        results = []
        soup = BeautifulSoup(html, "html.parser")
        script_tag = soup.find(
            "script",
            src=False,
            string=re.compile(r"tdata\s*="),
        )
        if not script_tag:
            self.logger.warning("No <script> tag with tdata found in HTML.")
            return None
        data_match = re.search(
            r"tbody\s*=\s*(\[\s*.*?\s*\]);",
            script_tag.string,
            re.DOTALL,
        )
        if not data_match:
            self.logger.warning("tdata variable not found in script content.")
            return None
        try:
            data = json.loads(data_match.group(1))
            self.logger.debug("tdata JSON parsed successfully.")
        except json.JSONDecodeError as e:
            self.logger.error("Failed to parse tdata JSON: %s", e)
            return None

        boxes = None
        for node in data[0]:
            if (
                isinstance(node, list)
                and node
                and node[0] == "div"
                and isinstance(node[1], dict)
                and node[1].get("className") == "notchpad"
            ):
                boxes = [item[1] for item in node[2] if item[0] == "CelebBox"]
                break

        if not boxes:
            return None

        for box in boxes:
            results.append(
                {
                    "name": box["name"],
                    "url": self._fetchname_to_url(
                        box["fetchname"],
                        source,
                    ),
                    "rank": box["rank"],
                    # `thumbnails` is for future features!
                    "thumbnails": box["pics"],
                }
            )

        return results
