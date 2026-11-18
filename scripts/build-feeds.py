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
    r"^(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{4}$"
)
MONTH_ID_PATTERN = re.compile(
    r'^(january|february|march|april|may|june|july|august|september|october|november|december)-\d{4}$',
    re.IGNORECASE
)

def parse_month_header(text):

    text = text.strip()

    if not MONTH_PATTERN.match(text):
        return None

    try:

        return datetime.strptime(text, "%B %Y").replace(tzinfo=timezone.utc)

    except Exception:

        return None

def parse_month_id(id_text):

    if not id_text:
        return None

    if not MONTH_ID_PATTERN.match(id_text):
        return None

    try:

        month_name, year = id_text.split("-")

        return datetime.strptime(
            f"{month_name.title()} {year}",
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

                dt = parsedate_to_datetime(
                    entry[field]
                )

                if dt.tzinfo is None:

                    dt = dt.replace(
                        tzinfo=timezone.utc
                    )

                return dt

            except Exception:
                pass

    return datetime.now(
        timezone.utc
    )

def fetch_whatsnew_feed(feed):

    records = []

    print(
        f"Loading What's New page: {feed['name']}"
    )

    try:

        headers = {
            "User-Agent":
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
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

        month_headers = soup.find_all(
            "h2"
        )

        print(
            f"Found {len(month_headers)} h2 headers"
        )

        for h2 in month_headers:

            month_text = h2.get_text(
                strip=True
            )

            month_id = h2.get(
                "id",
                ""
            )

            month_date = parse_month_id(
                month_id
            )

            if not month_date:

                month_date = parse_month_header(
                    month_text
                )

            if not month_date:
                continue

            print(
                f"Month: {month_text}"
            )

            for current in h2.next_elements:

                #
                # Stop when we hit the next month
                #

                if (
                    getattr(current, "name", None) == "h2"
                    and current is not h2
                ):
                    break

                #
                # H3 items
                #

                if getattr(current, "name", None) == "h3":

                    title = current.get_text(
                        strip=True
                    )

                    if len(title) < 5:
                        continue

                    entry_id = current.get(
                        "id",
                        ""
                    )

                    article_url = feed["url"]

                    if entry_id:
                        article_url += (
                            f"#{entry_id}"
                        )

                    records.append(
                        {
                            "title": title,
                            "summary": "",
                            "url": article_url,
                            "published": month_date,
                            "source": feed["name"],
                            "product": feed.get(
                                "product",
                                feed["name"]
                            ),
                            "category": feed["category"]
                        }
                    )

                    print(
                        f"H3 Entry: {title}"
                    )

                #
                # LI items
                #

                elif getattr(current, "name", None) == "li":

                    #
                    # Ignore nested list items
                    #

                    if current.find_parent("li"):
                        continue

                    bold = current.find("b")

                    if bold:

                        title = bold.get_text(
                            strip=True
                        )

                        full_text = current.get_text(
                            " ",
                            strip=True
                        )

                        summary = (
                            full_text
                            .replace(
                                title,
                                "",
                                1
                            )
                            .strip()
                            .lstrip(".")
                            .strip()
                        )

                    else:

                        full_text = current.get_text(
                            " ",
                            strip=True
                        )

                        title = full_text
                        summary = ""

                    if len(title) < 5:
                        continue

                    records.append(
                        {
                            "title": title,
                            "summary": summary,
                            "url":
                                f"{feed['url']}#{month_id}",
                            "published":
                                month_date,
                            "source":
                                feed["name"],
                            "product":
                                feed.get(
                                    "product",
                                    feed["name"]
                                ),
                            "category":
                                feed["category"]
                        }
                    )

                    print(
                        f"LI Entry: {title}"
                    )

        print(
            f"Parsed {len(records)} entries"
        )

    except Exception as ex:

        print(
            f"ERROR loading {feed['name']}: {ex}"
        )

    return records
def fetch_rss_feed(feed):

    records = []

    print(f"Loading RSS feed: {feed['name']}")

    try:

        rss = feedparser.parse(feed["url"])

        for entry in rss.entries:

            published = parse_date(entry)

            records.append(
                {
                    "title": entry.get("title", "Untitled"),
                    "url": entry.get("link", ""),
                    "published": published,
                    "source": feed["name"],
                    "product": feed.get("product", feed["name"]),
                    "category": feed["category"],
                }
            )

    except Exception as ex:

        print(f"ERROR: {feed['name']} : {ex}")

    return records


def deduplicate(items):

    unique = {}

    for item in items:

        key = (
    item["product"]
    .strip()
    .lower(),

    item["title"]
    .strip()
    .lower()
)

        if key not in unique:
            unique[key] = item

    return list(unique.values())


def to_json_article(item):

    return {
        "title": item["title"],
        "summary": item.get(
            "summary",
            ""
        ),
        "url": item["url"],
        "source": item["source"],
        "product": item["product"],
        "published": item["published"].isoformat(),
    }
    
def build_release_summary(articles, max_items):

    releases = [x for x in articles if x["category"] == "releases"]

    releases.sort(key=lambda x: x["published"], reverse=True)

    return [to_json_article(x) for x in releases[:max_items]]


def build_release_activity(articles):

    releases = [x for x in articles if x["category"] == "releases"]

    counts = Counter(x["product"] for x in releases)

    output = []

    for product, count in sorted(counts.items(), key=lambda x: x[1], reverse=True):

        output.append({"product": product, "count": count})

    return output


def build_categories(categories, articles, max_items_per_category):

    output = {}

    for category in categories:

        cat_id = category["id"]

        entries = [x for x in articles if x["category"] == cat_id]

        entries.sort(key=lambda x: x["published"], reverse=True)

        output[cat_id] = {
            "title": category["title"],
            "items": [to_json_article(x) for x in entries[:max_items_per_category]],
        }

    return output


def main():

    config = load_config()

    settings = config.get("settings", {})

    days_to_keep = settings.get("days_to_keep", 90)

    max_items_per_category = settings.get("max_items_per_category", 20)

    max_release_summary = settings.get("max_release_summary", 10)

    categories = config["categories"]

    feeds = config["feeds"]

    cutoff = datetime.now(timezone.utc) - timedelta(days=days_to_keep)

    articles = []


    for feed in feeds:

        feed_type = feed.get("type", "rss")

        if feed_type == "rss":

            feed_articles = fetch_rss_feed(feed)

        elif feed_type == "whatsnew":

            feed_articles = fetch_whatsnew_feed(feed)

        else:

            print(f"Unsupported feed type: {feed_type}")

            continue

        for article in feed_articles:

            if article["published"] >= cutoff:

                articles.append(article)

    articles = deduplicate(articles)

    articles.sort(key=lambda x: x["published"], reverse=True)

    output = {
        "generated": datetime.now(timezone.utc).isoformat(),
        "article_count": len(articles),
        "days_to_keep": days_to_keep,
        "latest_releases": build_release_summary(articles, max_release_summary),
        "release_activity": build_release_activity(articles),
        "categories": build_categories(categories, articles, max_items_per_category),
    }

    Path(OUTPUT_FILE).parent.mkdir(parents=True, exist_ok=True)

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:

        json.dump(
    output,
    f,
    indent=2,
    ensure_ascii=False
)

    print(f"Generated {OUTPUT_FILE}")

    print(f"Articles: {len(articles)}")


if __name__ == "__main__":
    main()
