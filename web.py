"""Web search via DuckDuckGo's HTML page (no API key, no account).

Only the query text leaves your computer. If DuckDuckGo can't be reached or
changes its page, search() raises and the crab opens your browser instead.
"""

import html
import re
import urllib.parse
import urllib.request
from dataclasses import dataclass

SEARCH_PAGE = "https://html.duckduckgo.com/html/?"
BROWSER_PAGE = "https://duckduckgo.com/?"
USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/605.1.15 (KHTML, like Gecko)"

# Typing one of these switches a search to the web, e.g. "google best pla settings".
WEB_PREFIXES = ("search the web for ", "search online for ", "look up ", "google ", "web: ", "web ")


@dataclass(frozen=True)
class WebHit:
    title: str
    url: str
    snippet: str

    @property
    def domain(self):
        return urllib.parse.urlparse(self.url).netloc.removeprefix("www.")


def split_web_prefix(text):
    """('google pla temps') -> ('pla temps', True); anything else -> (text, False)."""
    lower = text.lower()
    for prefix in WEB_PREFIXES:
        if lower.startswith(prefix) and len(text) > len(prefix):
            return text[len(prefix):].strip(), True
    return text, False


def browser_url(query):
    return BROWSER_PAGE + urllib.parse.urlencode({"q": query})


def clean(fragment):
    return html.unescape(re.sub(r"<[^>]+>", "", fragment)).strip()


def real_url(href):
    """DuckDuckGo wraps links as //duckduckgo.com/l/?uddg=<real url>."""
    href = html.unescape(href)
    if "duckduckgo.com/l/" in href:
        target = urllib.parse.parse_qs(urllib.parse.urlparse(href).query).get("uddg")
        if target:
            return target[0]
    return "https:" + href if href.startswith("//") else href


def search(query, limit=6):
    request = urllib.request.Request(
        SEARCH_PAGE + urllib.parse.urlencode({"q": query}), headers={"User-Agent": USER_AGENT}
    )
    with urllib.request.urlopen(request, timeout=8) as response:
        page = response.read().decode("utf-8", "ignore")

    hits = []
    # Each organic result is a "result__body" block holding a title link and a snippet.
    for block in re.split(r'<div[^>]+class="[^"]*result__body', page)[1:]:
        link = re.search(r'<a[^>]+class="[^"]*result__a[^"]*"[^>]*>(.*?)</a>', block, re.S)
        if not link:
            continue
        href = re.search(r'href="([^"]+)"', link.group(0))
        url = real_url(href.group(1)) if href else ""
        if not url.startswith("http") or "duckduckgo.com/y.js" in url:  # skip ads
            continue
        snippet = re.search(r'class="[^"]*result__snippet[^"]*"[^>]*>(.*?)</(?:a|div)>', block, re.S)
        hits.append(WebHit(clean(link.group(1)), url, clean(snippet.group(1)) if snippet else ""))
        if len(hits) >= limit:
            break
    if not hits and "result__body" not in page:
        raise RuntimeError("DuckDuckGo returned no parsable results")
    return hits
