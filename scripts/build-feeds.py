#!/usr/bin/env python3

import json
import yaml
import feedparser
import requests
import re

from bs4 import BeautifulSoup
from pathlib import Path
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
from collections import Counter

CONFIG_FILE = "config/feeds.yaml"
OUTPUT_FILE = "data/news.json"

MONTH_PATTERN = re.compile(
    r'^(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{4}$'
)

def parse_month_header(text):

    text = text.strip()

    if not MONTH_PATTERN.match(text):
        return None

    try:

        return datetime.strptime(
            text,
            "%B %Y"
        ).replace(
            tzinfo=timezone.utc
        )

    except Exception:

        return None

def load_config():
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def parse_date(entry):

    for field in [
        "published",
        "updated",
        "created"
    ]:

        if field in entry:

            try:
                return parsedate_to_datetime(
                    entry[field]
                )

            except Exception:
                pass

    return datetime.now(timezone.utc)

def fetch_whatsnew_feed(feed):

    records = []

    print(
        f"Loading What's New page: {feed['name']}"
    )

    try:

        headers = {
            "User-Agent":
            "Mozilla/5.0 RSS Collector"
        }

        response = requests.get(
            feed["url"],
            headers=headers,
            timeout=30
        )

        response.raise_for_status()

        soup = BeautifulSoup(
            response.text,
            "html.parser"
        )

        current_month = None

        headings = soup.find_all(
            ["h2", "h3"]
        )

        for heading in headings:

            text = heading.get_text(
                strip=True
            )

            month = parse_month_header(
                text
            )

            #
            # Month/Year heading
            #

            if month:

                current_month = month
                continue

            #
            # Ignore headings before
            # first month section
            #

            if not current_month:
                continue

            #
            # Create entry
            #

            records.append(
                {
                    "title": text,
                    "url": feed["url"],
                    "published": current_month,
                    "source": feed["name"],
                    "product": feed.get(
                        "product",
                        feed["name"]
                    ),
                    "category": feed["category"]
                }
            )

    except Exception as ex:

        print(
            f"ERROR loading {feed['name']}: {ex}"
        )

    return records

def fetch_rss_feed(feed):

    records = []

    print(
        f"Loading RSS feed: {feed['name']}"
    )

    try:

        rss = feedparser.parse(
            feed["url"]
        )

        for entry in rss.entries:

            published = parse_date(
                entry
            )

            records.append(
                {
                    "title": entry.get(
                        "title",
                        "Untitled"
                    ),
                    "url": entry.get(
                        "link",
                        ""
                    ),
                    "published": published,
                    "source": feed["name"],
                    "product": feed.get(
                        "product",
                        feed["name"]
                    ),
                    "category": feed["category"]
                }
            )

    except Exception as ex:

        print(
            f"ERROR: {feed['name']} : {ex}"
        )

    return records

def deduplicate(items):

    unique = {}

    for item in items:

        key = (
            item["title"]
            .strip()
            .lower(),
            item["url"]
            .strip()
            .lower()
        )

        if key not in unique:
            unique[key] = item

    return list(
        unique.values()
    )


def to_json_article(item):

    return {
        "title": item["title"],
        "url": item["url"],
        "source": item["source"],
        "product": item["product"],
        "published": item[
            "published"
        ].isoformat()
    }


def build_release_summary(
    articles,
    max_items
):

    releases = [

        x

        for x in articles

        if x["category"]
        == "releases"

    ]

    releases.sort(
        key=lambda x: x["published"],
        reverse=True
    )

    return [

        to_json_article(x)

        for x in releases[
            :max_items
        ]

    ]


def build_release_activity(
    articles
):

    releases = [

        x

        for x in articles

        if x["category"]
        == "releases"

    ]

    counts = Counter(
        x["product"]
        for x in releases
    )

    output = []

    for product, count in sorted(
        counts.items(),
        key=lambda x: x[1],
        reverse=True
    ):

        output.append(
            {
                "product": product,
                "count": count
            }
        )

    return output


def build_categories(
    categories,
    articles,
    max_items_per_category
):

    output = {}

    for category in categories:

        cat_id = category["id"]

        entries = [

            x

            for x in articles

            if x["category"]
            == cat_id

        ]

        entries.sort(
            key=lambda x: x[
                "published"
            ],
            reverse=True
        )

        output[cat_id] = {
            "title": category[
                "title"
            ],
            "items": [
                to_json_article(x)

                for x in entries[
                    :max_items_per_category
                ]
            ]
        }

    return output


def main():

    config = load_config()

    settings = config.get(
        "settings",
        {}
    )

    days_to_keep = settings.get(
        "days_to_keep",
        90
    )

    max_items_per_category = (
        settings.get(
            "max_items_per_category",
            20
        )
    )

    max_release_summary = (
        settings.get(
            "max_release_summary",
            10
        )
    )

    categories = config[
        "categories"
    ]

    feeds = config[
        "feeds"
    ]

    cutoff = (
        datetime.now(
            timezone.utc
        )
        - timedelta(
            days=days_to_keep
        )
    )

    articles = []

for feed in feeds:

    feed_type = feed.get(
        "type",
        "rss"
    )

    if feed_type == "rss":

        feed_articles = (
            fetch_rss_feed(feed)
        )

    elif feed_type == "whatsnew":

        feed_articles = (
            fetch_whatsnew_feed(feed)
        )

    else:

        print(
            f"Unsupported feed type: {feed_type}"
        )

        continue

    for article in feed_articles:

        if (
            article["published"]
            >= cutoff
        ):

            articles.append(
                article
            )

    articles = deduplicate(
        articles
    )

    articles.sort(
        key=lambda x: x[
            "published"
        ],
        reverse=True
    )

    output = {

        "generated": datetime.now(
            timezone.utc
        ).isoformat(),

        "article_count": len(
            articles
        ),

        "days_to_keep":
            days_to_keep,

        "latest_releases":
            build_release_summary(
                articles,
                max_release_summary
            ),

        "release_activity":
            build_release_activity(
                articles
            ),

        "categories":
            build_categories(
                categories,
                articles,
                max_items_per_category
            )
    }

    Path(
        OUTPUT_FILE
    ).parent.mkdir(
        parents=True,
        exist_ok=True
    )

    with open(
        OUTPUT_FILE,
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            output,
            f,
            indent=2
        )

    print(
        f"Generated {OUTPUT_FILE}"
    )

    print(
        f"Articles: {len(articles)}"
    )


if __name__ == "__main__":
    main()