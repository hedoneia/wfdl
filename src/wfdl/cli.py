import argparse
import os

from .client import WikiFeetClient


def main():
    parser = argparse.ArgumentParser(
        prog="WFDL",
        description="WikiFeet Downloader CLI"
    )
    parser.add_argument(
        "urls",
        nargs="+"
    )
    parser.add_argument(
        "--path",
        default=None,
    )

    args = parser.parse_args()

    client = WikiFeetClient()
    client.download(args.urls, args.path or os.getcwd())
