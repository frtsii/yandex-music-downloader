#!/bin/python3
import argparse
import itertools
import logging
import os
import json
import re
import time
import typing
from argparse import ArgumentTypeError
from collections.abc import Callable, Generator, Iterable
from pathlib import Path
from typing import Optional, Union
from urllib.parse import urlparse

from yandex_music import Album, Playlist, Track

from ymd import core

DEFAULT_DELAY = 0

TRACK_RE = re.compile(r"track/(\d+)")
ALBUM_RE = re.compile(r"album/(\d+)$")
ARTIST_RE = re.compile(r"artist/(\d+)$")
PLAYLIST_RE = re.compile(r"([\w\-._@]+)/playlists/(\d+)$")
PLAYLIST_UUID_RE = re.compile(r"playlists/([\w.\-]+)$")

FETCH_PAGE_SIZE = 10

logger = logging.getLogger("yandex-music-downloader")


def gui_event(event: str, **payload) -> None:
    if os.environ.get("YMD_GUI_EVENTS") == "1":
        print("@YMD " + json.dumps({"event": event, **payload}, ensure_ascii=False), flush=True)


def image_url(uri: Optional[str]) -> str:
    if not uri:
        return ""
    return "https://" + uri.replace("%%", "300x300").lstrip("/")


def show_default(text: Optional[str] = None) -> str:
    default = "по умолчанию: %(default)s"
    if text is None:
        return default
    return f"{text} ({default})"


def checked_int_arg(
    min_value: int, max_value: Optional[int] = None
) -> Callable[[str], int]:
    def func(astr: str) -> int:
        aint = int(astr)
        if aint >= min_value and (max_value is None or aint <= max_value):
            return aint
        error_text = f"Значение должен быть >= {min_value}"
        if max_value is not None:
            error_text += f" и <= {max_value}"
        raise ArgumentTypeError(error_text)

    return func


def cover_resolution_arg(astr: str) -> int:
    if astr == "original":
        return -1
    return checked_int_arg(100)(astr)


def lyrics_format_arg(astr: str) -> core.LyricsFormat:
    try:
        return core.LyricsFormat(astr)
    except ValueError:
        raise ArgumentTypeError(f"Допустимые значения: {','.join(core.LyricsFormat)}")


def parse_url(value: str) -> tuple[str, str]:
    parsed = urlparse(value.strip())
    if parsed.scheme not in ("http", "https") or parsed.hostname not in {
        "music.yandex.ru", "music.yandex.com", "music.yandex.kz",
        "music.yandex.by", "music.yandex.uz",
    }:
        raise ValueError("Нужна ссылка на music.yandex.ru (или .com, .kz, .by, .uz)")
    path = parsed.path.rstrip("/")
    for kind, pattern in (("track", TRACK_RE), ("artist", ARTIST_RE),
                          ("album", ALBUM_RE), ("playlist", PLAYLIST_RE),
                          ("playlist_uuid", PLAYLIST_UUID_RE)):
        if match := pattern.search(path):
            identifier = "/".join(match.groups())
            if kind == "playlist_uuid":
                return "playlist", f"uuid:{identifier}"
            return kind, identifier
    raise ValueError("Поддерживаются ссылки на трек, альбом, исполнителя и плейлист")


def contained_path(root: Path, value: Path) -> Path:
    target = (root / value).resolve()
    if not target.is_relative_to(root.resolve()):
        raise ValueError("Путь должен оставаться внутри папки проекта")
    return target


def automatic_path_pattern(
    kind: str, title: str = "", artist: str = "", unsafe_path: bool = False
) -> Path:
    title = core.safe_path_component(title, unsafe_path)
    artist = core.safe_path_component(artist, unsafe_path)
    if kind == "playlist":
        return Path(f"{title}/#track-artist - #title")
    if kind == "album":
        return Path(f"{artist} - {title}/#number-padded - #title")
    if kind == "artist":
        return Path(f"{artist} - дискография/#album/#number-padded - #title")
    return Path("#track-artist - #title")


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Загрузчик музыки с сервиса Яндекс.Музыка",
        formatter_class=argparse.RawTextHelpFormatter,
    )

    common_group = parser.add_argument_group("Общие параметры")
    common_group.add_argument(
        "--quality",
        metavar="<Качество>",
        default=0,
        type=checked_int_arg(0, 2),
        help="Качество трека:\n0 - Низкое (AAC 64kbps)\n1 - Оптимальное (AAC 192kbps)\n2 - Лучшее (FLAC)\n(по умолчанию: %(default)s)",
    )
    common_group.add_argument(
        "--skip-existing", action="store_true", help="Пропускать уже загруженные треки"
    )
    common_group.add_argument(
        "--lyrics-format",
        type=lyrics_format_arg,
        default=core.LyricsFormat.EMBED,
        help=show_default("Формат текста песни"),
        choices=core.LyricsFormat,
    )
    common_group.add_argument(
        "--lyrics", choices=("true", "false"), nargs="?", const="true",
        default="true", help="Получать тексты песен (по умолчанию: true)",
    )
    common_group.add_argument(
        "--add-lyrics", action="store_true", help=argparse.SUPPRESS
    )
    common_group.add_argument(
        "--embed-cover", action="store_true", help="Встраивать обложку в аудиофайл"
    )
    common_group.add_argument(
        "--cover-resolution",
        default=core.DEFAULT_COVER_RESOLUTION,
        metavar="<Разрешение обложки>",
        type=cover_resolution_arg,
        help=show_default(
            'Разрешение обложки (в пикселях). Передайте "original" для загрузки в оригинальном (наилучшем) разрешении'
        ),
    )
    common_group.add_argument(
        "--delay",
        default=DEFAULT_DELAY,
        metavar="<Задержка>",
        type=checked_int_arg(0),
        help=show_default("Задержка между запросами, в секундах"),
    )
    common_group.add_argument(
        "--stick-to-artist",
        action="store_true",
        help="Загружать альбомы, созданные только данным исполнителем",
    )
    common_group.add_argument(
        "--only-music",
        action="store_true",
        help="Загружать только музыкальные альбомы (пропускать подкасты и аудиокниги)",
    )
    common_group.add_argument(
        "--compatibility-level",
        metavar="<Уровень совместимости>",
        default=1,
        type=checked_int_arg(
            core.MIN_COMPATIBILITY_LEVEL, core.MAX_COMPATIBILITY_LEVEL
        ),
        help=show_default(
            f"Уровень совместимости, от {core.MIN_COMPATIBILITY_LEVEL} до {core.MAX_COMPATIBILITY_LEVEL}. См. README для подробного описания"
        ),
    )

    network_group = parser.add_argument_group("Сетевые параметры")
    network_group.add_argument(
        "--timeout",
        metavar="<Время ожидания>",
        default=20,
        type=checked_int_arg(1),
        help=show_default(
            "Время ожидания ответа от сервера, в секундах. Увеличьте если возникают сетевые ошибки"
        ),
    )
    network_group.add_argument(
        "--tries",
        metavar="<Количество попыток>",
        default=20,
        type=checked_int_arg(0),
        help=show_default(
            "Количество попыток при возникновении сетевых ошибок. 0 - бесконечное количество попыток"
        ),
    )
    network_group.add_argument(
        "--retry-delay",
        metavar="<Задержка>",
        default=5,
        type=checked_int_arg(0),
        help=show_default("Задержка между повторными запросами при сетевых ошибках"),
    )
    common_group.add_argument("--debug", action="store_true", help=argparse.SUPPRESS)

    id_group_meta = parser.add_argument_group("ID")
    id_group = id_group_meta.add_mutually_exclusive_group(required=True)
    id_group.add_argument("--artist-id", metavar="<ID исполнителя>")
    id_group.add_argument("--album-id", metavar="<ID альбома>")
    id_group.add_argument("--track-id", metavar="<ID трека>")
    id_group.add_argument(
        "--playlist-id",
        metavar="<владелец плейлиста>/<тип плейлиста>",
    )
    id_group.add_argument("-u", "--url", help="URL исполнителя/альбома/трека/плейлиста")

    path_group = parser.add_argument_group("Указание пути")
    path_group.add_argument(
        "--workspace-root", type=Path, help=argparse.SUPPRESS,
    )
    path_group.add_argument(
        "--unsafe-path",
        action="store_true",
        help="Не очищать путь от недопустимых символов",
    )
    path_group.add_argument(
        "--dir",
        default=".",
        metavar="<Папка>",
        help=show_default("Папка для загрузки музыки"),
        type=Path,
    )
    path_group.add_argument(
        "--path-pattern",
        default=core.DEFAULT_PATH_PATTERN,
        metavar="<Паттерн>",
        type=Path,
        help=show_default(
            "Поддерживает следующие заполнители:"
            " #number, #track-artist, #album-artist, #title,"
            " #album, #year, #artist-id, #album-id, #track-id, #number-padded"
        ),
    )

    auth_group = parser.add_argument_group("Авторизация")
    auth_group.add_argument(
        "--token",
        default=os.environ.get("YMD_TOKEN"),
        metavar="<Токен>",
        help="Токен для авторизации. См. README для способов получения",
    )

    args = parser.parse_args(argv)
    if not args.token:
        parser.error("Укажите --token или переменную окружения YMD_TOKEN")
    if args.workspace_root:
        args.dir = contained_path(args.workspace_root, args.dir)

    logging.basicConfig(
        format="%(asctime)s |%(levelname)s| %(name)s: %(message)s",
        datefmt="%H:%M:%S",
        level=logging.DEBUG if args.debug else logging.INFO,
    )

    if args.add_lyrics:
        print(
            "Аргумент --add-lyrics устарел и будет удален в будущем. Используйте --lyrics-format"
        )
        args.lyrics_format = core.LyricsFormat.TEXT
    if args.lyrics == "false":
        args.lyrics_format = core.LyricsFormat.NONE

    if args.url is not None:
        try:
            kind, identifier = parse_url(args.url)
            setattr(args, kind + "_id", identifier)
        except ValueError as error:
            parser.error(str(error))

    client = core.init_client(
        token=args.token,
        timeout=args.timeout,
        max_try_count=args.tries,
        retry_delay=args.retry_delay,
    )
    result_tracks: Iterable[Track]

    def album_tracks_gen(album_ids: Iterable[Union[int, str]]) -> Generator[Track]:
        for album_id in album_ids:
            if full_album := client.albums_with_tracks(album_id):
                if volumes := full_album.volumes:
                    yield from itertools.chain.from_iterable(volumes)

    total_track_count = None
    automatic_pattern = Path("#track-artist - #title")
    collection_kind = "track"
    collection_title = "Трек"
    collection_artist = ""
    collection_cover = ""
    collection_path = args.dir
    if args.artist_id is not None:
        collection_kind = "artist"

        def filter_album(album: Album) -> bool:
            title = album.title
            if album.id is None or not album.available:
                print(f'Альбом "{title}" не доступен для скачивания')
            elif args.only_music and album.meta_type != "music":
                print(f'Альбом "{title}" пропущен т.к. не является музыкальным')
            elif args.stick_to_artist and album.artists[0].id != int(args.artist_id):
                print(f'Альбом "{title}" пропущен из-за флага --stick-to-artist')
            else:
                return True
            return False

        def albums_id_gen() -> Generator[int]:
            has_next = True
            page = 0
            while has_next:
                if albums_info := client.artists_direct_albums(args.artist_id, page):
                    for album in albums_info.albums:
                        if filter_album(album):
                            assert album.id
                            yield album.id
                        else:
                            nonlocal total_track_count
                            if (
                                track_count := album.track_count
                            ) and total_track_count is not None:
                                total_track_count -= track_count
                else:
                    break
                if pager := albums_info.pager:
                    page = pager.page + 1
                    has_next = pager.per_page * page < pager.total
                else:
                    break

        result_tracks = album_tracks_gen(albums_id_gen())
        artist = client.artists(args.artist_id)[0]
        automatic_pattern = automatic_path_pattern(
            "artist", artist=artist.name or "Исполнитель", unsafe_path=args.unsafe_path
        )
        collection_title = f"{artist.name or 'Исполнитель'} - дискография"
        collection_artist = artist.name or ""
        collection_cover = image_url(
            getattr(getattr(artist, "cover", None), "uri", None)
            or getattr(artist, "og_image", None)
        )
        collection_path = args.dir / core.safe_path_component(
            collection_title, args.unsafe_path
        )
        if counts := artist.counts:
            total_track_count = counts.tracks

    elif args.album_id is not None:
        collection_kind = "album"
        result_tracks = album_tracks_gen((args.album_id,))
        if album := client.albums_with_tracks(args.album_id):
            total_track_count = album.track_count
            automatic_pattern = automatic_path_pattern(
                "album",
                title=core.full_title(album),
                artist=album.artists[0].name if album.artists else "Исполнитель",
                unsafe_path=args.unsafe_path,
            )
            collection_title = core.full_title(album)
            collection_artist = album.artists[0].name if album.artists else ""
            collection_cover = image_url(
                getattr(album, "cover_uri", None) or getattr(album, "og_image", None)
            )
            collection_path = args.dir / core.safe_path_component(
                f"{collection_artist or 'Исполнитель'} - {collection_title}",
                args.unsafe_path,
            )
    elif args.track_id is not None:
        track = client.tracks(args.track_id)
        result_tracks = track
        total_track_count = 1
        if track:
            first_track = track[0]
            collection_title = core.full_title(first_track)
            collection_artist = ", ".join(
                a.name for a in first_track.artists if a.name
            )
            first_album = first_track.albums[0] if first_track.albums else None
            collection_cover = image_url(
                getattr(first_album, "cover_uri", None)
                or getattr(first_album, "og_image", None)
            )
    elif args.playlist_id is not None:
        collection_kind = "playlist"
        if args.playlist_id.startswith("uuid:"):
            playlist = typing.cast(Playlist, client.playlist(args.playlist_id[5:]))
        else:
            user, kind = args.playlist_id.split("/")
            playlist = typing.cast(Playlist, client.users_playlists(kind, user))
        if playlist is None:
            raise ValueError("Плейлист не найден или недоступен")
        total_track_count = playlist.track_count
        automatic_pattern = automatic_path_pattern(
            "playlist", title=playlist.title or "Плейлист", unsafe_path=args.unsafe_path
        )
        collection_title = playlist.title or "Плейлист"
        collection_cover = image_url(
            getattr(getattr(playlist, "cover", None), "uri", None)
            or getattr(playlist, "og_image", None)
        )
        collection_path = args.dir / core.safe_path_component(
            collection_title, args.unsafe_path
        )

        def playlist_tracks_gen() -> Generator[Track]:
            tracks = playlist.fetch_tracks()
            for i in range(0, len(tracks), FETCH_PAGE_SIZE):
                yield from client.tracks(
                    [track.id for track in tracks[i : i + FETCH_PAGE_SIZE]]
                )

        result_tracks = playlist_tracks_gen()
    else:
        raise ValueError("Invalid ID argument")

    gui_event(
        "collection",
        kind=collection_kind,
        title=collection_title,
        artist=collection_artist,
        cover=collection_cover,
        path=str(collection_path.resolve()),
        total=total_track_count,
    )

    track_counter = 0
    failures = 0
    progress_status = ""
    covers_cache = {}
    for track in result_tracks:
        track_counter += 1
        if total_track_count:
            progress_status = f"[{track_counter}/{total_track_count}] "

        if not track.available:
            print(f"{progress_status}Трек {track.title} не доступен для скачивания")
            continue

        gui_event(
            "progress",
            index=track_counter,
            total=total_track_count,
            title=core.full_title(track),
            status="Подготовка трека",
        )

        relative_path = core.prepare_base_path(
            automatic_pattern, track, args.unsafe_path
        )
        if args.playlist_id is not None:
            width = len(str(total_track_count or track_counter))
            relative_path = relative_path.parent / (
                f"{str(track_counter).zfill(width)} - {relative_path.name}"
            )
        save_path = args.dir / relative_path
        if args.workspace_root:
            save_path = contained_path(args.workspace_root, save_path)
        if args.skip_existing:
            if any(
                Path(str(save_path) + s).is_file() for s in core.AUDIO_FILE_SUFFIXES
            ):
                continue

        save_dir = save_path.parent
        if not save_dir.is_dir():
            save_dir.mkdir(parents=True, exist_ok=True)

        try:
            downloadable = core.to_downloadable_track(track, args.quality, save_path)
            bitrate = downloadable.download_info.bitrate
            format_info = "[" + downloadable.download_info.file_format.codec.name
            if bitrate > 0:
                format_info += f" {bitrate}kbps"
            format_info += "]"
            print(f"{progress_status}{format_info} Загружается {downloadable.path}")
            source = core.download_track(
                track_info=downloadable,
                lyrics_format=args.lyrics_format,
                embed_cover=args.embed_cover,
                cover_resolution=args.cover_resolution,
                covers_cache=covers_cache,
                compatibility_level=args.compatibility_level,
            )
            first_album = track.albums[0] if track.albums else None
            gui_event(
                "downloaded", title=core.full_title(track),
                artist=", ".join(a.name for a in track.artists if a.name),
                album=first_album.title if first_album else "",
                cover=image_url(
                    getattr(first_album, "cover_uri", None)
                    or getattr(first_album, "og_image", None)
                ),
                path=str(downloadable.path.resolve()), source=source,
                index=track_counter, total=total_track_count,
            )
        except Exception as error:
            failures += 1
            print(f"Не удалось скачать {track.title}: {type(error).__name__}. Продолжаем очередь.")
            logger.error("%s", error)
        if args.delay > 0:
            time.sleep(args.delay)
    return 1 if failures else 0
