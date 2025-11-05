import json
import logging
from datetime import datetime, timezone

import pytest

from wfdl.extractor import WikiFeetExtractor


@pytest.fixture
def sample_html():
    return """
    <html>
        <head></head>
        <body>
            <script>
                tdata = {
                    "cname": "Test Name",
                    "gender": 0,
                    "bplace": "Test Place",
                    "bdate": "2000-01-01T00:00:00Z",
                    "score": 42,
                    "edata": {"stats": {"5": 10, "4": 5}},
                    "height_us": "57",
                    "gallery": [
                        {"pid": 123, "tags": "TS"},
                        {"pid": 456, "tags": "AB"}
                    ]
                };
            </script>
        </body>
    </html>
    """


@pytest.fixture
def extractor():
    return WikiFeetExtractor(logger=logging.getLogger("test"))


class TestWikiFeetExtractor:

    def test_pid_to_url(self, extractor):
        url = extractor._pid_to_url(123)
        assert url == "https://pics.wikifeet.com/123.jpg"

    def test_parse_birth_date_valid(self, extractor):
        birth, age = extractor._parse_birth_date("2000-01-01T00:00:00Z")
        assert birth == "2000-01-01"
        today = datetime.now(timezone.utc)
        expected_age = today.year - 2000 - ((today.month, today.day) < (1, 1))
        assert age == expected_age

    def test_parse_birth_date_invalid(self, extractor):
        assert extractor._parse_birth_date("invalid") is None
        assert extractor._parse_birth_date(None) is None

    def test_parse_gender(self, extractor):
        assert extractor._parse_gender(0) == "female"
        assert extractor._parse_gender(1) == "male"
        assert extractor._parse_gender(2) == "female"
        assert extractor._parse_gender(99) is None
        assert extractor._parse_gender(None) is None

    def test_parse_height(self, extractor):
        result = extractor._parse_height("57")
        assert result["imperial"] == "5 ft 7 in"
        assert result["cm"] == round((5 * 12 + 7) * 2.54)
        assert extractor._parse_height("5") is None
        assert extractor._parse_height(None) is None

    def test_parse_tags(self, extractor):
        assert extractor._parse_tags("TS") == ["toes", "soles"]
        assert extractor._parse_tags("XYZ") is None
        assert extractor._parse_tags("") is None
        assert extractor._parse_tags(None) is None

    def test_extract_subject_profile_success(self, extractor, sample_html):
        profile = extractor._extract_subject_profile(sample_html)
        assert profile["name"] == "Test Name"
        assert profile["gender"] == "female"
        assert profile["birth_place"] == "Test Place"
        assert profile["birth_date"] == "2000-01-01"
        assert profile["age"] is not None
        assert profile["score"] == 42
        assert profile["rating_distribution"] == {"5": 10, "4": 5}
        assert profile["height"]["imperial"] == "5 ft 7 in"
        assert profile["images"][0]["url"] == "https://pics.wikifeet.com/123.jpg"
        assert profile["images"][0]["tags"] == ["toes", "soles"]
        assert profile["image_count"] == 2

    def test_extract_subject_profile_missing_script(self, extractor):
        html = "<html><body>No script here</body></html>"
        profile = extractor._extract_subject_profile(html)
        assert profile is None

    def test_extract_subject_profile_malformed_json(self, extractor):
        html = "<script>tdata = { invalid json };</script>"
        profile = extractor._extract_subject_profile(html)
        assert profile is None
