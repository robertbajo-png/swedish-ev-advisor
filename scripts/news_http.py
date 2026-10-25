"""Bounded public-web collection. Access reservations are failures, never bypasses."""
import hashlib
import ipaddress
import re
import socket
import ssl
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from urllib.error import HTTPError
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit
from urllib.request import HTTPRedirectHandler, HTTPSHandler, Request, build_opener
from urllib.robotparser import RobotFileParser

AGENT = "SeekEVNews/1.0 (+https://seekev.se/nyheter)"
MAX_BYTES = 2_000_000


def canonical_url(url):
    p = urlsplit(str(url))
    if p.scheme != "https" or not p.hostname or p.username or p.password or p.port not in (None, 443):
        raise ValueError("unsafe_url")
    query = [(k, v) for k, v in parse_qsl(p.query) if not k.lower().startswith("utm_") and k.lower() not in {"fbclid", "gclid"}]
    return urlunsplit(("https", p.hostname.lower(), p.path or "/", urlencode(sorted(query)), ""))


def safe_host(url, allowed_host):
    url = canonical_url(url)
    host = urlsplit(url).hostname
    if host.removeprefix("www.") != allowed_host.removeprefix("www."):
        raise ValueError("cross_domain_redirect")
    for result in socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM):
        if not ipaddress.ip_address(result[4][0]).is_global:
            raise ValueError("non_public_address")
    return url


def reserved(headers, text=""):
    h = {str(k).lower(): str(v).lower() for k, v in headers.items()}
    if h.get("tdm-reservation", "").strip() in {"1", "true"}:
        return True
    signals = h.get("content-signal", "") + " " + text.lower()
    if re.search(r"(?:ai-input|tdm)\s*=\s*no", signals):
        return True
    if any(token in h.get("x-robots-tag", "") for token in ("noai", "notdm")):
        return True
    parser = PageText()
    parser.feed(text)
    return parser.reservation


class PageText(HTMLParser):
    def __init__(self):
        super().__init__()
        self.skip = 0
        self.text = []
        self.links = []
        self.reservation = False
        self.paywall = False
        self.regions = []
        self.article_texts = []
        self.main_texts = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag in {"script", "style", "noscript", "nav", "footer", "header"}:
            self.skip += 1
        if tag in {"article", "main"}:
            self.regions.append((tag, []))
        if tag == "a" and a.get("href"):
            self.links.append(a["href"])
        if tag == "meta":
            name = (a.get("name") or a.get("http-equiv") or "").lower()
            value = a.get("content", "").lower()
            if name == "tdm-reservation" and value in {"1", "true"}:
                self.reservation = True
            if name in {"robots", "googlebot"} and any(t in value for t in ("noai", "notdm")):
                self.reservation = True
        if a.get("itemprop") == "isAccessibleForFree" and a.get("content", "").lower() == "false":
            self.paywall = True

    def handle_endtag(self, tag):
        if tag in {"script", "style", "noscript", "nav", "footer", "header"}:
            self.skip = max(0, self.skip - 1)
        if tag in {"article", "main"}:
            for index in range(len(self.regions) - 1, -1, -1):
                if self.regions[index][0] == tag:
                    _, parts = self.regions.pop(index)
                    (self.article_texts if tag == "article" else self.main_texts).append(" ".join(parts))
                    break

    def handle_data(self, data):
        if not self.skip:
            self.text.append(data)
            for _, parts in self.regions:
                parts.append(data)

    def plain(self):
        candidates = [text for text in self.article_texts if len(text.split()) >= 80]
        if not candidates:
            candidates = [text for text in self.main_texts if len(text.split()) >= 80]
        text = max(candidates, key=len) if candidates else " ".join(self.text)
        return re.sub(r"\s+", " ", text).strip()


def plain(html):
    parser = PageText()
    parser.feed(html)
    return parser.plain()


class SafeRedirect(HTTPRedirectHandler):
    def __init__(self, host, policy=None):
        self.host = host
        self.policy = policy

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        safe_host(newurl, self.host)
        if reserved(headers):
            raise ValueError('tdm_reserved')
        if self.policy and not self.policy.can_fetch(AGENT, newurl):
            raise ValueError("redirect_robots_disallowed")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class EditorialPolicy:
    """Apply the same mining policy to initial, intermediate and final URLs."""
    def __init__(self, robots):
        self.robots = robots

    def can_fetch(self, agent, url):
        if not self.robots.can_fetch(agent, url):
            return False
        if any(not self.robots.can_fetch(bot, url) for bot in ('GPTBot', 'CCBot')):
            raise ValueError('ai_mining_robots_reserved')
        return True


class Collector:
    def __init__(self, tls_context=None):
        if tls_context is not None and (not tls_context.check_hostname or tls_context.verify_mode != ssl.CERT_REQUIRED):
            raise ValueError('verified_tls_required')
        self.tls_context = tls_context
        self.policies = {}
        self.last_fetch = {}

    def request(self, url, host, headers=None, policy=None):
        url = safe_host(url, host)
        wait = max(0, 1 - (time.monotonic() - self.last_fetch.get(host, 0)))
        time.sleep(wait)
        self.last_fetch[host] = time.monotonic()
        req = Request(url, headers={"User-Agent": AGENT, **(headers or {})})
        try:
            handlers = [SafeRedirect(host, policy)]
            if self.tls_context is not None:
                handlers.append(HTTPSHandler(context=self.tls_context))
            with build_opener(*handlers).open(req, timeout=20) as response:
                raw = response.read(MAX_BYTES + 1)
                if len(raw) > MAX_BYTES:
                    raise ValueError("response_too_large")
                return response.status, dict(response.headers), raw.decode("utf-8", errors="replace"), response.url
        except HTTPError as exc:
            if exc.code == 304:
                return 304, dict(exc.headers), "", url
            raise

    def policy(self, website):
        host = urlsplit(website).hostname
        if host not in self.policies:
            robot_url = urljoin(website, "/robots.txt")
            try:
                _, headers, body, _ = self.request(robot_url, host)
            except HTTPError as exc:
                if exc.code != 404:
                    raise ValueError("robots_unavailable") from exc
                headers, body = {}, ""
            if reserved(headers, body):
                raise ValueError("tdm_reserved")
            robots = RobotFileParser()
            robots.parse(body.splitlines())
            self.policies[host] = robots
        return self.policies[host]

    def fetch(self, url, source, conditional=None, editorial=False):
        host = urlsplit(source["website"]).hostname
        robots = self.policy(source["website"])
        policy = EditorialPolicy(robots) if editorial else robots
        if not policy.can_fetch(AGENT, url):
            raise ValueError("robots_disallowed")
        delay = robots.crawl_delay(AGENT) or 1
        if delay > 30:
            raise ValueError("crawl_delay_exceeds_run_budget")
        time.sleep(max(0, delay - (time.monotonic() - self.last_fetch.get(host, 0))))
        result = self.request(url, host, conditional, policy)
        if not policy.can_fetch(AGENT, result[3]):
            raise ValueError("redirect_robots_disallowed")
        if reserved(result[1], result[2]):
            raise ValueError("tdm_reserved")
        return result


def iso_date(value):
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        try:
            dt = parsedate_to_datetime(value)
        except (ValueError, TypeError, IndexError):
            return None
    return dt.replace(tzinfo=dt.tzinfo or timezone.utc).astimezone(timezone.utc).isoformat()


def require_recent_publication(value, now=None):
    published = iso_date(value)
    if not published:
        raise ValueError('missing_publication_date')
    age = ((now or datetime.now(timezone.utc)) - datetime.fromisoformat(published)).total_seconds()
    if age > 7 * 86400:
        raise ValueError('stale_report')
    if age < -3600:
        raise ValueError('future_report')
    return published


def parse_feed(xml, source):
    if "<!DOCTYPE" in xml.upper() or "<!ENTITY" in xml.upper():
        raise ValueError("unsafe_xml")
    root = ET.fromstring(xml)
    local = lambda tag: tag.rsplit("}", 1)[-1]
    if local(root.tag) not in {"rss", "feed", "RDF"}:
        raise ValueError("not_a_feed")
    rows = []
    for item in root.iter():
        if local(item.tag) not in {"item", "entry"}:
            continue
        fields = {}
        for child in item:
            name = local(child.tag)
            value = "".join(child.itertext()).strip()
            if name == "link" and child.get("rel", "alternate") == "alternate":
                fields["url"] = child.get("href") or value
            elif name not in fields:
                fields[name] = value
        if not fields.get("url") or not fields.get("title"):
            continue
        try:
            url = canonical_url(urljoin(source["website"], fields["url"]))
            if urlsplit(url).hostname.removeprefix("www.") != urlsplit(source["website"]).hostname.removeprefix("www."):
                continue
        except ValueError:
            continue
        summary = fields.get("summary") or fields.get("description") or ""
        content = fields.get("encoded") or fields.get("content") or summary
        rows.append({
            "url": url, "title": plain(fields["title"]),
            "published_at": iso_date(fields.get("published") or fields.get("pubDate") or fields.get("updated")),
            "summary": plain(summary)[:1000], "feed_content": plain(content)[:45000],
            "content_hash": hashlib.sha256(content.encode()).hexdigest(),
        })
    return rows
