"""Best-effort synchronized lyrics. No Yandex token or account is used here."""
import base64
import html
import json
import logging
import queue
import re
import threading
import time
import unicodedata
from dataclasses import dataclass
from typing import Optional

import requests

from ymd.lyrics import parse_lrc

log = logging.getLogger(__name__)
SOURCE_ORDER = ("NetEase", "LRCLIB", "QQ Music", "KuGou")
SOURCE_TIMEOUT = 3.0
TOTAL_TIMEOUT = 8.0
MAX_BODY = 1_500_000


@dataclass(frozen=True)
class Song:
    title: str
    artists: tuple[str, ...]
    album: str = ""
    duration: float = 0

    @property
    def query(self):
        return f"{self.artists[0] if self.artists else ''} {self.title}".strip()


@dataclass(frozen=True)
class SyncedLyrics:
    source: str
    lrc: str
    url: str


def normalize(value):
    value = unicodedata.normalize("NFKC", html.unescape(str(value))).casefold().replace("ё", "е")
    value = re.sub(r"\((?:explicit|clean)\)", "", value)
    return " ".join(re.findall(r"\w+", value))


def matches(song, title, artists, duration):
    if normalize(song.title) != normalize(title):
        return False
    if not {normalize(a) for a in song.artists} & {normalize(a) for a in artists}:
        return False
    try:
        return not song.duration or abs(float(duration) - song.duration) <= 3
    except (TypeError, ValueError):
        return False


def valid_lrc(text, duration=0):
    if not isinstance(text, str) or len(text) > MAX_BODY:
        return False
    lines = parse_lrc(text)
    timed_text = [(text, stamp) for text, stamp in lines if text.strip()]
    return (
        len(timed_text) >= 2
        and len({stamp for _, stamp in timed_text}) >= 2
        and (not duration or all(stamp <= (duration + 3) * 1000 for _, stamp in lines))
    )


class Http:
    """A separate unauthenticated session, bounded by time and response size."""
    def __init__(self, deadline):
        self.deadline = deadline
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "YMD-Lyrics/1.0", "Accept": "application/json"})

    def request(self, method, url, **kwargs):
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("Lyrics deadline")
        with self.session.request(
            method, url, timeout=(min(1.2, remaining), min(1.5, remaining)),
            stream=True, **kwargs,
        ) as response:
            response.raise_for_status()
            data = bytearray()
            for chunk in response.iter_content(16384):
                if time.monotonic() > self.deadline:
                    raise TimeoutError("Lyrics deadline")
                data.extend(chunk)
                if len(data) > MAX_BODY:
                    raise ValueError("Lyrics response too large")
            return json.loads(data)

    def close(self):
        self.session.close()


def netease(song, http):
    data = http.request("POST", "https://music.163.com/api/search/get",
                        data={"s": song.query, "type": 1, "limit": 10, "offset": 0},
                        headers={"Referer": "https://music.163.com/"})
    candidates = data.get("result", {}).get("songs", [])
    for item in candidates[:10]:
        if not matches(song, item.get("name"), [a["name"] for a in item.get("artists", [])],
                       item.get("duration", 0) / 1000):
            continue
        result = http.request("GET", "https://music.163.com/api/song/lyric",
                              params={"id": item["id"], "lv": -1, "kv": -1, "tv": -1},
                              headers={"Referer": "https://music.163.com/"})
        text = result.get("lrc", {}).get("lyric", "")
        if valid_lrc(text, song.duration):
            return SyncedLyrics("NetEase", text, f"https://music.163.com/song?id={item['id']}")
    return None


def lrclib(song, http):
    results = http.request("GET", "https://lrclib.net/api/search", params={"q": song.query})
    for item in results:
        if (matches(song, item.get("trackName"), [item.get("artistName", "")], item.get("duration"))
                and valid_lrc(item.get("syncedLyrics"), song.duration)):
            return SyncedLyrics("LRCLIB", item["syncedLyrics"], f"https://lrclib.net/api/get/{item['id']}")
    return None


def qqmusic(song, http):
    data = http.request("GET", "https://c.y.qq.com/soso/fcgi-bin/client_search_cp",
                        params={"w": song.query, "format": "json", "p": 1, "n": 10},
                        headers={"Referer": "https://y.qq.com/"})
    if data.get("code") != 0:
        raise ValueError("QQ search unavailable")
    for item in data.get("data", {}).get("song", {}).get("list", [])[:10]:
        if not matches(song, item.get("songname"), [a["name"] for a in item.get("singer", [])],
                       item.get("interval")):
            continue
        result = http.request("GET", "https://c.y.qq.com/lyric/fcgi-bin/fcg_query_lyric_new.fcg",
                              params={"songmid": item["songmid"], "format": "json", "nobase64": 1},
                              headers={"Referer": "https://y.qq.com/"})
        if result.get("code", 0) != 0:
            raise ValueError("QQ lyrics unavailable")
        text = html.unescape(result.get("lyric", ""))
        if valid_lrc(text, song.duration):
            return SyncedLyrics("QQ Music", text, f"https://y.qq.com/n/ryqq/songDetail/{item['songmid']}")
    return None


def kugou(song, http):
    data = http.request("GET", "https://lyrics.kugou.com/search",
                        params={"ver": 1, "man": "yes", "client": "pc",
                                "keyword": song.query, "duration": round(song.duration * 1000)})
    for item in data.get("candidates", [])[:10]:
        if not matches(song, item.get("song"), re.split(r"[、/&]", item.get("singer", "")),
                       float(item.get("duration", 0)) / 1000):
            continue
        result = http.request("GET", "https://lyrics.kugou.com/download",
                              params={"ver": 1, "client": "pc", "id": item["id"],
                                      "accesskey": item["accesskey"], "fmt": "lrc", "charset": "utf8"})
        text = base64.b64decode(result.get("content", ""), validate=True).decode("utf-8-sig")
        if valid_lrc(text, song.duration):
            return SyncedLyrics("KuGou", text, "https://www.kugou.com/")
    return None


class LyricsResolver:
    def __init__(self, source_timeout=SOURCE_TIMEOUT, total_timeout=TOTAL_TIMEOUT, providers=None):
        self.source_timeout = source_timeout
        self.total_timeout = total_timeout
        self.providers = providers or list(zip(SOURCE_ORDER, (netease, lrclib, qqmusic, kugou)))
        self.cache = {}
        self.cooldowns = {}
        self.active = {}

    def find(self, song: Song) -> Optional[SyncedLyrics]:
        cached = self.cache.get(song)
        if cached and cached[0] > time.monotonic():
            return cached[1]
        deadline = time.monotonic() + self.total_timeout
        for name, provider in self.providers:
            if self.cooldowns.get(name, 0) > time.monotonic():
                continue
            if name in self.active and self.active[name].is_alive():
                continue  # Never accumulate hung network threads across an album.
            budget = min(self.source_timeout, deadline - time.monotonic())
            if budget <= 0:
                break
            replies = queue.Queue(maxsize=1)

            def work(fn=provider, mailbox=replies, stop=time.monotonic() + budget):
                http = Http(stop)
                try:
                    mailbox.put((fn(song, http), None))
                except Exception as error:
                    mailbox.put((None, type(error).__name__))
                finally:
                    http.close()

            thread = threading.Thread(target=work, name=f"lyrics-{name}", daemon=True)
            self.active[name] = thread
            thread.start()
            try:
                result, error = replies.get(timeout=budget)
            except queue.Empty:
                result, error = None, "Timeout"
            if error:
                self.cooldowns[name] = time.monotonic() + 60
                log.info("%s: временно недоступен (%s), следующий источник", name, error)
                continue
            if result and valid_lrc(result.lrc, song.duration):
                self.cache[song] = (time.monotonic() + 3600, result)
                log.info("Текст с таймкодами: %s", name)
                return result
        self.cache[song] = (time.monotonic() + 60, None)
        log.warning("LRC не найден за отведённое время; загрузка музыки продолжается")
        return None


resolver = LyricsResolver()


def find_lyrics(track):
    return resolver.find(Song(
        title=track.title or "",
        artists=tuple(a.name for a in track.artists if a.name),
        album=track.albums[0].title or "" if track.albums else "",
        duration=(track.duration_ms or 0) / 1000,
    ))
