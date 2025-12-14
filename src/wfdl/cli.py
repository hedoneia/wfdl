import argparse
import os
from pathlib import Path
from typing import List

from .client import WikiFeetClient


def parse_urls_from_file(filepath: str) -> List[str]:
    return [
        line.strip() for line in Path(filepath).read_text().splitlines() if line.strip()
    ]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="WFDL",
        description="WikiFeet Downloader CLI",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    download = subparsers.add_parser(
        "download",
        help="Download images from URLs or a file.",
    )
    group = download.add_mutually_exclusive_group(required=True)
    group.add_argument("--url", nargs="+", help="One or more URLs.")
    group.add_argument("--file", help="A text file containing URLs.")
    download.add_argument("--path", default=None, help="Destination directory.")

    search = subparsers.add_parser(
        "search",
        help="Search WikiFeet.",
    )
    search.add_argument("keyword", help="Celebrity keyword to search for.")
    search.add_argument(
        "--sources",
        nargs="+",
        choices=["prime", "x", "men"],
        help="Limit search to specific sources.",
    )
    search.add_argument(
        "--verbose",
        action="store_true",
        help="Fetch extra details (gender, birth place, etc.).",
    )
    search.add_argument("--max", type=int, help="Max results per source.")

    return parser


def display_results(results: list[list[dict]]) -> None:
    flat_results = [item for sublist in results for item in sublist]
    flat_results.sort(key=lambda x: x.get("rank", 0), reverse=True)

    for celeb in flat_results:
        print()
        print(f"Name: {celeb['name']}")
        print(f"URL: {celeb['url']}")
        print(f"Score: {celeb.get('rank', 'N/A')}")
        if "gender" in celeb:
            print(f"Gender: {celeb['gender']}")
        if "image_count" in celeb:
            print(f"Images: {celeb['image_count']}")
        if "birth_place" in celeb:
            print(f"Birthplace: {celeb['birth_place']}")
        if "shoe_size" in celeb and celeb["shoe_size"] is not None:
            print(f"Shoe size: {celeb['shoe_size']}")
        print()  # Blank line between each celeb


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    client = WikiFeetClient()

    if args.command == "download":
        urls = args.url or parse_urls_from_file(args.file)
        out_dir = args.path or os.getcwd()
        try:
            client.download(urls, out_dir)
        except KeyboardInterrupt:
            pass

    elif args.command == "search":
        results = client.search(
            keyword=args.keyword,
            sources=args.sources,
            verbose=args.verbose,
        )

        # Apply --max if specified
        if args.max is not None:
            results = [r[: args.max] if isinstance(r, list) else r for r in results]

        display_results(results)
