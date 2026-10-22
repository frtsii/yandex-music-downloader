"""Attach synchronized lyrics to an existing local file without downloading audio."""
from pathlib import Path

import mutagen
from mutagen.flac import FLAC
from mutagen.id3 import SYLT, USLT
from mutagen.mp3 import MP3
from mutagen.mp4 import MP4

from ymd.cli import contained_path
from ymd.core import write_via_temporary_file
from ymd.lyrics import format_lrc, parse_lrc
from ymd.lyrics_sources import Song, resolver, valid_lrc


def read_song(path):
    audio = mutagen.File(path)
    if audio is None or not audio.tags:
        raise ValueError("Файл не содержит метаданных песни")

    def text(*keys):
        for key in keys:
            try:
                value = audio.tags.get(key)
            except (KeyError, ValueError):
                continue
            if value:
                return str(value[0]) if isinstance(value, list) else str(value)
        return ""

    artist = text("\xa9ART", "artist", "TPE1")
    return Song(text("\xa9nam", "title", "TIT2"),
                tuple(a.strip() for a in artist.split(";") if a.strip()),
                text("\xa9alb", "album", "TALB"), audio.info.length)


def embed_existing(path: Path, lrc: str, root: Path):
    path = contained_path(root, path)
    song = read_song(path)
    if not valid_lrc(lrc, song.duration):
        raise ValueError("Текст не содержит подходящих таймкодов")
    lines = parse_lrc(lrc)
    canonical = format_lrc(lines)
    backup = contained_path(root, root / "lyrics-backups" / path.relative_to(root.resolve()))
    backup.parent.mkdir(parents=True, exist_ok=True)
    original = path.read_bytes()
    if not backup.exists():
        write_via_temporary_file(original, backup)

    def update(temp):
        audio = mutagen.File(temp)
        if isinstance(audio, MP3):
            audio.tags.add(SYLT(encoding=3, lang="und", format=2, type=1,
                                desc="Lyrics", text=lines))
            audio.tags.add(USLT(encoding=3, lang="und", text="\n".join(text for text, _ in lines)))
        elif isinstance(audio, MP4):
            audio["\xa9lyr"] = canonical
        elif isinstance(audio, FLAC):
            audio["lyrics"] = canonical
        else:
            raise ValueError("Поддерживаются MP3, M4A и FLAC")
        audio.save()

    write_via_temporary_file(original, path, update)


def update_lyrics(path: Path, root: Path):
    path = contained_path(root, path)
    result = resolver.find(read_song(path))
    if result:
        embed_existing(path, result.lrc, root)
    return result
