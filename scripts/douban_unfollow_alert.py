#!/usr/bin/env python3
"""
Douban follower snapshot monitor.

The script fetches https://www.douban.com/contacts/rlist pages,
extracts follower profile links, stores the latest snapshot, and reports
followers that disappeared since the previous run.
"""

from __future__ import annotations

import argparse
import html
import json
import re
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any


DOUBAN_BASE = "https://www.douban.com"
PROFILE_RE = re.compile(r"^https?://www\.douban\.com/people/([^/?#]+)/?(?:[?#].*)?$")
FOLLOWER_COUNT_RE = re.compile(r"关注我的人\((\d+)\)")


@dataclass(frozen=True)
class Person:
    user_id: str
    name: str
    url: str


@dataclass(frozen=True)
class Page:
    body: str
    final_url: str


class FollowerParser(HTMLParser):
    def __init__(self, base_url: str) -> None:
        super().__init__()
        self.base_url = base_url
        self.people: dict[str, Person] = {}
        self._capture_href: str | None = None
        self._capture_text: list[str] = []
        self.next_page_url: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr = {key: value or "" for key, value in attrs}
        if tag == "a":
            href = urllib.parse.urljoin(self.base_url, attr.get("href", ""))
            self._capture_href = href
            self._capture_text = []
            classes = set(attr.get("class", "").split())
            rels = set(attr.get("rel", "").split())
            if "next" in rels or "next" in classes:
                self.next_page_url = href

    def handle_data(self, data: str) -> None:
        if self._capture_href:
            self._capture_text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag != "a" or not self._capture_href:
            return

        name = html.unescape(" ".join("".join(self._capture_text).split()))
        match = PROFILE_RE.match(self._capture_href)
        href = self._capture_href
        self._capture_href = None
        self._capture_text = []

        if name in {"后页>", "后页", "下一页", "Next", "next", ">"}:
            self.next_page_url = href

        if not match or not name:
            return

        user_id = match.group(1)
        # Navigation and self links can also match /people/<id>/; keep likely user links.
        if user_id not in self.people:
            self.people[user_id] = Person(user_id=user_id, name=name, url=f"{DOUBAN_BASE}/people/{user_id}/")


def load_config(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise SystemExit(
            f"Config not found: {path}\n"
            "Run the local web app and fill in the first-time setup, or create config.json with douban_user_id and cookie."
        )
    with path.open("r", encoding="utf-8") as fh:
        config = json.load(fh)
    if not config.get("douban_user_id"):
        raise SystemExit("Missing config value: douban_user_id")
    if not config.get("cookie"):
        raise SystemExit("Missing config value: cookie")
    return config


def request_page(url: str, cookie: str, referer: str | None = None) -> Page:
    headers = {
        "Cookie": cookie,
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Cache-Control": "no-cache",
    }
    if referer:
        headers["Referer"] = referer
    req = urllib.request.Request(
        url,
        headers=headers,
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            content_type = response.headers.get_content_charset() or "utf-8"
            return Page(
                body=response.read().decode(content_type, errors="replace"),
                final_url=response.geturl(),
            )
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"Douban returned HTTP {exc.code} for {url}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Could not reach Douban: {exc.reason}") from exc


def parse_follower_count(body: str) -> int | None:
    match = FOLLOWER_COUNT_RE.search(body)
    if not match:
        return None
    return int(match.group(1))


def fetch_followers(
    config: dict[str, Any],
    verbose: bool = False,
    progress: Any | None = None,
) -> dict[str, Person]:
    user_id = str(config["douban_user_id"]).strip().strip("/")
    cookie = str(config["cookie"]).strip()
    delay = float(config.get("request_delay_seconds", 1.5))
    max_pages = int(config.get("max_pages", 80))
    followers: dict[str, Person] = {}
    # This entry URL redirects to /contacts/rlist. Going through it is less likely
    # to be rejected than requesting /contacts/rlist directly, but pagination must
    # continue from the redirected URL so ?start=... is not lost.
    current_url = f"{DOUBAN_BASE}/people/{urllib.parse.quote(user_id)}/rev_contacts"
    referer: str | None = None
    seen_urls: set[str] = set()
    expected_total: int | None = None

    for page_index in range(max_pages):
        if current_url in seen_urls:
            break
        seen_urls.add(current_url)

        page = request_page(current_url, cookie, referer=referer)
        if is_login_wall(page.body):
            raise RuntimeError("豆瓣返回了登录或验证页面。请在浏览器里重新登录豆瓣，然后更新 config.json 里的 Cookie。")
        if expected_total is None:
            expected_total = parse_follower_count(page.body)

        parser = FollowerParser(page.final_url)
        parser.feed(page.body)
        before = len(followers)
        followers.update(parser.people)
        added = len(followers) - before

        if verbose:
            print(
                f"page={page_index + 1} found={len(parser.people)} "
                f"added={added} total={len(followers)} url={current_url} final_url={page.final_url}",
                file=sys.stderr,
            )

        if progress:
            progress(
                {
                    "page": page_index + 1,
                    "found_on_page": len(parser.people),
                    "added": added,
                    "total": len(followers),
                    "expected_total": expected_total,
                    "url": current_url,
                    "final_url": page.final_url,
                }
            )

        if len(followers) == before or not parser.people:
            break
        if not parser.next_page_url:
            break
        referer = page.final_url
        current_url = parser.next_page_url
        time.sleep(delay)

    return followers


def is_login_wall(body: str) -> bool:
    markers = [
        "登录豆瓣",
        "安全验证",
        "captcha",
        "accounts.douban.com/passport/login",
        "禁止访问",
        "/misc/sorry",
    ]
    return any(marker in body for marker in markers)


def resolve_state_path(config_path: Path, config: dict[str, Any]) -> Path:
    raw = Path(config.get("state_file", ".state/followers.json"))
    if raw.is_absolute():
        return raw
    return config_path.parent / raw


def load_state(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def people_to_state_payload(followers: dict[str, Person]) -> dict[str, Any]:
    return {
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "followers": {
            user_id: {"name": person.name, "url": person.url}
            for user_id, person in sorted(followers.items())
        },
    }


def save_state(path: Path, followers: dict[str, Person]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = people_to_state_payload(followers)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2, sort_keys=True)
        fh.write("\n")
    tmp.replace(path)


def validate_snapshot(previous: dict[str, Any] | None, current: dict[str, Person], allow_shrink: bool = False) -> None:
    if not previous or allow_shrink:
        return
    old_count = len(previous.get("followers", {}))
    current_count = len(current)
    if old_count >= 50 and current_count < old_count * 0.8:
        raise RuntimeError(
            "Current snapshot is much smaller than the previous snapshot "
            f"({current_count} vs {old_count}); refusing to save because the scrape may be incomplete. "
            "Re-run with --verbose, or use --allow-shrink if this drop is expected."
        )


def diff_unfollowers(previous: dict[str, Any] | None, current: dict[str, Person]) -> list[Person]:
    if not previous:
        return []
    old_followers = previous.get("followers", {})
    missing_ids = sorted(set(old_followers) - set(current))
    return [
        Person(
            user_id=user_id,
            name=str(old_followers[user_id].get("name") or user_id),
            url=str(old_followers[user_id].get("url") or f"{DOUBAN_BASE}/people/{user_id}/"),
        )
        for user_id in missing_ids
    ]


def notify(config: dict[str, Any], unfollowers: list[Person], current_count: int) -> None:
    notify_config = config.get("notify", {})
    if not unfollowers:
        if notify_config.get("terminal", True):
            print(f"No unfollows detected. Current follower count: {current_count}")
        return

    lines = ["Douban unfollow alert:"]
    lines.extend(f"- {person.name} ({person.url})" for person in unfollowers)
    message = "\n".join(lines)

    if notify_config.get("terminal", True):
        print(message)
    if notify_config.get("macos", False):
        send_macos_notification(unfollowers)
    webhook_url = str(notify_config.get("webhook_url") or "").strip()
    if webhook_url:
        send_webhook(webhook_url, message, unfollowers)


def send_macos_notification(unfollowers: list[Person]) -> None:
    title = "豆瓣取关提醒"
    if len(unfollowers) == 1:
        body = f"{unfollowers[0].name} 取消关注了你"
    else:
        body = f"{len(unfollowers)} 个人取消关注了你"
    script = f'display notification {json.dumps(body)} with title {json.dumps(title)}'
    try:
        subprocess.run(["osascript", "-e", script], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError:
        pass


def send_webhook(webhook_url: str, message: str, unfollowers: list[Person]) -> None:
    payload = json.dumps(
        {
            "text": message,
            "unfollowers": [person.__dict__ for person in unfollowers],
        },
        ensure_ascii=False,
    ).encode("utf-8")
    req = urllib.request.Request(
        webhook_url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=15):
        pass


def main() -> int:
    parser = argparse.ArgumentParser(description="Check Douban followers and alert on unfollows.")
    parser.add_argument("--config", default="config.json", help="Path to config.json")
    parser.add_argument("--init", action="store_true", help="Create or replace the baseline snapshot without alerting")
    parser.add_argument("--json", action="store_true", help="Print a machine-readable result")
    parser.add_argument("--verbose", action="store_true", help="Print per-page fetch diagnostics to stderr")
    parser.add_argument("--allow-shrink", action="store_true", help="Save even if the new snapshot is much smaller")
    args = parser.parse_args()

    config_path = Path(args.config).expanduser().resolve()
    config = load_config(config_path)
    state_path = resolve_state_path(config_path, config)
    previous = load_state(state_path)
    current = fetch_followers(config, verbose=args.verbose)
    validate_snapshot(previous, current, allow_shrink=args.allow_shrink or args.init)
    unfollowers = [] if args.init else diff_unfollowers(previous, current)
    save_state(state_path, current)

    result = {
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "state_file": str(state_path),
        "initialized": previous is None or args.init,
        "current_count": len(current),
        "unfollowers": [person.__dict__ for person in unfollowers],
    }

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        if result["initialized"] and not unfollowers:
            print(f"Baseline saved with {len(current)} followers: {state_path}")
        notify(config, unfollowers, len(current))

    return 2 if unfollowers else 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        raise SystemExit(130)
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(1)
