"""Parse real LRC timestamps for ID3 SYLT (milliseconds)."""
import re

STAMP = re.compile(r"\[(?:(\d{1,9}):)?(\d{1,9}):(\d{2})(?:\.(\d{1,3}))?\]")
OFFSET = re.compile(r"\[offset:([+-]?\d{1,12})\]", re.I)


def parse_lrc(source: str) -> list[tuple[str, int]]:
    offsets = OFFSET.findall(source)
    offset = int(offsets[-1]) if offsets else 0
    result = []
    for line in source.lstrip("\ufeff").splitlines():
        line = line.strip()
        stamps = []
        pos = 0
        while match := STAMP.match(line, pos):
            hours, minutes, seconds, fraction = match.groups()
            if int(seconds) < 60 and (hours is None or int(minutes) < 60):
                millis = (
                    (int(hours or 0) * 3600 + int(minutes) * 60 + int(seconds))
                    * 1000 + int((fraction or "0").ljust(3, "0")) + offset
                )
                if 0 <= millis <= 0xFFFFFFFF:
                    stamps.append(millis)
            pos = match.end()
        text = line[pos:].replace("\x00", "")
        result.extend((text, millis) for millis in stamps)
    return sorted(result, key=lambda item: item[1])


def format_lrc(lines: list[tuple[str, int]]) -> str:
    return "\n".join(
        f"[{stamp // 60000:02d}:{stamp // 1000 % 60:02d}.{stamp % 1000:03d}]{text}"
        for text, stamp in lines
    )
