import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:math' as math;
import 'dart:ui' as ui;

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

const bg = Color(0xFF090909);
const panelSoft = Color(0x8A181818);
const line = Color(0x42FFFFFF);
const muted = Color(0xFFA7A7A7);
const yellow = Color(0xFFFFCC00);
const orange = Color(0xFFFF8A00);
const pink = Color(0xFFFF2D7A);
const red = Color(0xFFFF3B30);

String defaultMusicDirectory() {
  final home = Platform.environment['USERPROFILE'];
  if (home != null && home.trim().isNotEmpty) {
    return '$home${Platform.pathSeparator}Music';
  }
  return 'Music';
}

void main() {
  WidgetsFlutterBinding.ensureInitialized();
  runApp(const YmdApp());
}

class YmdApp extends StatelessWidget {
  const YmdApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      debugShowCheckedModeBanner: false,
      title: 'Yandex Music Downloader',
      theme: ThemeData(
        brightness: Brightness.dark,
        scaffoldBackgroundColor: bg,
        colorScheme: const ColorScheme.dark(primary: yellow, secondary: pink),
        fontFamily: 'Segoe UI',
        inputDecorationTheme: InputDecorationTheme(
          filled: true,
          fillColor: const Color(0xA6111111),
          contentPadding: const EdgeInsets.symmetric(
            horizontal: 16,
            vertical: 14,
          ),
          enabledBorder: OutlineInputBorder(
            borderRadius: BorderRadius.circular(12),
            borderSide: const BorderSide(color: line),
          ),
          focusedBorder: OutlineInputBorder(
            borderRadius: BorderRadius.circular(12),
            borderSide: const BorderSide(color: yellow, width: 1.4),
          ),
          border: OutlineInputBorder(borderRadius: BorderRadius.circular(12)),
        ),
      ),
      home: const HomePage(),
    );
  }
}

class DownloadEntry {
  DownloadEntry({
    required this.title,
    required this.subtitle,
    required this.path,
    required this.when,
    this.cover = '',
    this.kind = 'track',
    List<DownloadEntry>? children,
  }) : children = children ?? [];
  final String title;
  final String subtitle;
  final String path;
  final DateTime when;
  final String cover;
  final String kind;
  final List<DownloadEntry> children;
  bool expanded = false;

  bool get isCollection => kind != 'track';

  Map<String, dynamic> toJson() => {
    'title': title,
    'subtitle': subtitle,
    'path': path,
    'when': when.toIso8601String(),
    'cover': cover,
    'kind': kind,
    'children': children.map((e) => e.toJson()).toList(),
  };

  factory DownloadEntry.fromJson(Map<String, dynamic> item) => DownloadEntry(
    title: item['title']?.toString() ?? 'Track',
    subtitle: item['subtitle']?.toString() ?? '',
    path: item['path']?.toString() ?? '',
    when: DateTime.tryParse(item['when']?.toString() ?? '') ?? DateTime.now(),
    cover: item['cover']?.toString() ?? '',
    kind: item['kind']?.toString() ?? 'track',
    children:
        (item['children'] as List<dynamic>? ?? const [])
            .whereType<Map<String, dynamic>>()
            .map(DownloadEntry.fromJson)
            .toList(),
  );
}

class AppSettings {
  String directory = defaultMusicDirectory();
  String quality = '1';
  String lyrics = 'embed';
  String cover = '400';
  String delay = '0';
  String timeout = '20';
  String tries = '3';
  String retryDelay = '2';
  String compatibility = '1';
  bool skipExisting = false;
  bool embedCover = true;
  bool onlyMusic = false;
  bool stickToArtist = false;
  bool unsafePath = false;
  bool monochrome = false;
  bool saveHistory = true;
  bool openFolderWhenDone = false;
  String language = 'en';

  Map<String, dynamic> toJson() => {
    'directory': directory,
    'quality': quality,
    'lyrics': lyrics,
    'cover': cover,
    'delay': delay,
    'timeout': timeout,
    'tries': tries,
    'retryDelay': retryDelay,
    'compatibility': compatibility,
    'skipExisting': skipExisting,
    'embedCover': embedCover,
    'onlyMusic': onlyMusic,
    'stickToArtist': stickToArtist,
    'unsafePath': unsafePath,
    'monochrome': monochrome,
    'saveHistory': saveHistory,
    'openFolderWhenDone': openFolderWhenDone,
    'language': language,
  };

  void read(Map<String, dynamic> j) {
    directory = j['directory']?.toString() ?? directory;
    quality = j['quality']?.toString() ?? quality;
    lyrics = j['lyrics']?.toString() ?? lyrics;
    cover = j['cover']?.toString() ?? cover;
    delay = j['delay']?.toString() ?? delay;
    timeout = j['timeout']?.toString() ?? timeout;
    tries = j['tries']?.toString() ?? tries;
    retryDelay = j['retryDelay']?.toString() ?? retryDelay;
    compatibility = j['compatibility']?.toString() ?? compatibility;
    skipExisting = j['skipExisting'] as bool? ?? skipExisting;
    embedCover = j['embedCover'] as bool? ?? embedCover;
    onlyMusic = j['onlyMusic'] as bool? ?? onlyMusic;
    stickToArtist = j['stickToArtist'] as bool? ?? stickToArtist;
    unsafePath = j['unsafePath'] as bool? ?? unsafePath;
    monochrome = j['monochrome'] as bool? ?? monochrome;
    saveHistory = j['saveHistory'] as bool? ?? saveHistory;
    openFolderWhenDone = j['openFolderWhenDone'] as bool? ?? openFolderWhenDone;
    language = j['language']?.toString() == 'en' ? 'en' : 'ru';
  }
}

class HomePage extends StatefulWidget {
  const HomePage({super.key});

  @override
  State<HomePage> createState() => _HomePageState();
}

class _HomePageState extends State<HomePage>
    with SingleTickerProviderStateMixin {
  final links = TextEditingController();
  final token = TextEditingController();
  final search = TextEditingController();
  final settings = AppSettings();
  final logs = <String>[];
  final history = <DownloadEntry>[];
  late final AnimationController animation;
  Process? worker;
  bool running = false;
  bool settingsOpen = false;
  int tab = 0;
  int linkIndex = 0;
  int linkCount = 0;
  double progress = 0;
  String status = 'Готов к загрузке';
  String detailStatus = '';

  String tr(String ru, String en) => settings.language == 'en' ? en : ru;
  Color get accent => settings.monochrome ? Colors.white : yellow;

  String get appDir => File(Platform.resolvedExecutable).parent.path;
  String get settingsPath => '$appDir${Platform.pathSeparator}settings.json';
  String get oauthPath => '$appDir${Platform.pathSeparator}oauth-token.txt';
  String get historyPath => '$appDir${Platform.pathSeparator}history.json';
  String get workerPath =>
      '$appDir${Platform.pathSeparator}YandexMusicWorker.exe';

  @override
  void initState() {
    super.initState();
    animation = AnimationController(
      vsync: this,
      duration: const Duration(seconds: 48),
    )..repeat();
    _loadSettings();
  }

  @override
  void dispose() {
    animation.dispose();
    links.dispose();
    token.dispose();
    search.dispose();
    super.dispose();
  }

  Future<void> _loadSettings() async {
    try {
      final file = File(settingsPath);
      if (await file.exists()) {
        settings.read(
          jsonDecode(await file.readAsString()) as Map<String, dynamic>,
        );
      }
      final savedToken = File(oauthPath);
      if (await savedToken.exists()) {
        token.text = (await savedToken.readAsString()).trim();
      }
      final savedHistory = File(historyPath);
      if (await savedHistory.exists()) {
        final rows =
            jsonDecode(await savedHistory.readAsString()) as List<dynamic>;
        history.addAll(
          rows.take(300).map((row) {
            return DownloadEntry.fromJson(row as Map<String, dynamic>);
          }),
        );
      }
    } catch (_) {}
    status = tr('Готов к загрузке', 'Ready to download');
    if (mounted) setState(() {});
  }

  Future<void> _saveSettings() async {
    final file = File(settingsPath);
    await file.parent.create(recursive: true);
    await file.writeAsString(
      const JsonEncoder.withIndent('  ').convert(settings.toJson()),
      flush: true,
    );
    final savedToken = File(oauthPath);
    final value = token.text.trim();
    if (value.isEmpty) {
      if (await savedToken.exists()) await savedToken.delete();
    } else {
      await savedToken.writeAsString(value, flush: true);
    }
    if (!settings.saveHistory) {
      history.clear();
      final savedHistory = File(historyPath);
      if (await savedHistory.exists()) await savedHistory.delete();
    }
  }

  Future<void> _saveHistory() async {
    if (!settings.saveHistory) return;
    final file = File(historyPath);
    await file.parent.create(recursive: true);
    final rows = history.take(300).map((e) => e.toJson()).toList();
    await file.writeAsString(jsonEncode(rows), flush: true);
  }

  void _log(String text) {
    final clean = text.trimRight();
    if (clean.isEmpty) return;
    if (clean.contains('pkg_resources is deprecated as an API') ||
        clean.contains('PyInstaller\\loader\\pyimod02_importers.py')) {
      return;
    }
    setState(() {
      logs.add('${DateTime.now().toString().substring(11, 19)}  $clean');
      if (running) detailStatus = clean;
      if (logs.length > 1500) logs.removeRange(0, logs.length - 1500);
    });
  }

  Future<void> _start() async {
    if (running) return;
    final queue =
        links.text
            .split(RegExp(r'[\r\n]+'))
            .map((e) => e.trim())
            .where((e) => e.isNotEmpty)
            .toList();
    if (queue.isEmpty) {
      setState(
        () =>
            status = tr(
              'Добавьте хотя бы одну ссылку',
              'Add at least one link',
            ),
      );
      return;
    }
    if (token.text.trim().isEmpty) {
      setState(() {
        status = tr(
          'Укажите токен в настройках',
          'Enter the token in Settings',
        );
        settingsOpen = true;
      });
      return;
    }
    if (!await File(workerPath).exists()) {
      setState(() => status = 'Не найден YandexMusicWorker.exe');
      return;
    }
    await _saveSettings();
    setState(() {
      running = true;
      linkCount = 0;
      linkIndex = 0;
      progress = 0;
      status = tr('Подготовка очереди', 'Preparing queue');
      detailStatus = '';
    });
    var failed = 0;
    for (var i = 0; i < queue.length && running; i++) {
      setState(() {
        linkIndex = 0;
        linkCount = 0;
        progress = 0;
        status = tr('Подготовка загрузки', 'Preparing download');
        detailStatus = queue[i];
      });
      _log('Ссылка ${i + 1}/${queue.length}: ${queue[i]}');
      final code = await _runWorker(queue[i], i, queue.length);
      if (code != 0) {
        failed++;
        _log('Ошибка ссылки: код $code. Переходим к следующей.');
      }
    }
    if (!mounted) return;
    final completed = running;
    setState(() {
      worker = null;
      progress = running ? 1 : progress;
      status =
          running
              ? (failed == 0
                  ? tr('Готово', 'Done')
                  : tr(
                    'Готово · ошибок ссылок: $failed',
                    'Done · failed links: $failed',
                  ))
              : tr('Остановлено', 'Stopped');
      running = false;
      detailStatus = tr('Все треки обработаны', 'All tracks processed');
    });
    if (completed && settings.openFolderWhenDone) _openFolder();
  }

  Future<int> _runWorker(String url, int queueIndex, int queueTotal) async {
    DownloadEntry? collection;
    final outDir = _absolute(settings.directory);
    final args = <String>[
      '--url',
      url,
      '--dir',
      outDir,
      '--quality',
      settings.quality,
      '--lyrics-format',
      settings.lyrics,
      '--cover-resolution',
      settings.cover,
      '--delay',
      settings.delay,
      '--timeout',
      settings.timeout,
      '--tries',
      settings.tries,
      '--retry-delay',
      settings.retryDelay,
      '--compatibility-level',
      settings.compatibility,
      if (settings.skipExisting) '--skip-existing',
      if (settings.embedCover) '--embed-cover',
      if (settings.onlyMusic) '--only-music',
      if (settings.stickToArtist) '--stick-to-artist',
      if (settings.unsafePath) '--unsafe-path',
    ];
    try {
      worker = await Process.start(
        workerPath,
        args,
        workingDirectory: appDir,
        environment: {
          ...Platform.environment,
          'YMD_TOKEN': token.text.trim(),
          'YMD_GUI_EVENTS': '1',
          'PYTHONUTF8': '1',
          'PYTHONIOENCODING': 'utf-8',
          'PYTHONWARNINGS': 'ignore',
        },
      );
      final stdoutDone = worker!.stdout
          .transform(const Utf8Decoder(allowMalformed: true))
          .transform(const LineSplitter())
          .forEach((lineText) {
            if (lineText.startsWith('@YMD ')) {
              try {
                final event =
                    jsonDecode(lineText.substring(5)) as Map<String, dynamic>;
                if (event['event'] == 'collection') {
                  final kind = event['kind']?.toString() ?? 'track';
                  collection = DownloadEntry(
                    title:
                        event['title']?.toString() ??
                        tr('Загрузка', 'Download'),
                    subtitle: event['artist']?.toString() ?? '',
                    path: event['path']?.toString() ?? '',
                    when: DateTime.now(),
                    cover: event['cover']?.toString() ?? '',
                    kind: kind,
                  );
                  final total = (event['total'] as num?)?.toInt() ?? 0;
                  setState(() {
                    linkIndex = 0;
                    linkCount = total;
                    progress = 0;
                    status = collection!.title;
                    detailStatus = tr(
                      'Подготовка треков…',
                      'Preparing tracks…',
                    );
                    if (kind != 'track') history.insert(0, collection!);
                  });
                  if (kind != 'track' && settings.saveHistory) {
                    unawaited(_saveHistory());
                  }
                } else if (event['event'] == 'progress') {
                  final current = (event['index'] as num?)?.toInt() ?? 1;
                  final total = (event['total'] as num?)?.toInt() ?? current;
                  setState(() {
                    linkIndex = math.max(0, current - 1);
                    linkCount = total;
                    progress = math.max(0, current - 1) / math.max(1, total);
                    status = tr('Загрузка треков', 'Downloading tracks');
                    detailStatus =
                        '${event['status'] ?? ''}: ${event['title'] ?? ''}';
                  });
                } else if (event['event'] == 'downloaded') {
                  final current = (event['index'] as num?)?.toDouble() ?? 1;
                  final total = (event['total'] as num?)?.toDouble() ?? current;
                  final entry = DownloadEntry(
                    title: event['title']?.toString() ?? 'Track',
                    subtitle: [event['artist'], event['album'], event['source']]
                        .where((e) => e != null && e.toString().isNotEmpty)
                        .join(' · '),
                    path: event['path']?.toString() ?? '',
                    when: DateTime.now(),
                    cover: event['cover']?.toString() ?? '',
                  );
                  setState(() {
                    linkIndex = current.toInt();
                    linkCount = total.toInt();
                    progress = current / math.max(1, total);
                    detailStatus = entry.title;
                    if (collection != null && collection!.isCollection) {
                      collection!.children.add(entry);
                    } else {
                      history.insert(0, entry);
                    }
                  });
                  if (settings.saveHistory) unawaited(_saveHistory());
                }
              } catch (_) {
                _log(lineText);
              }
            } else {
              _log(lineText);
            }
          });
      final stderrDone = worker!.stderr
          .transform(const Utf8Decoder(allowMalformed: true))
          .transform(const LineSplitter())
          .forEach(_log);
      final exitCode = await worker!.exitCode;
      await Future.wait([stdoutDone, stderrDone]);
      return exitCode;
    } catch (e) {
      _log('Не удалось запустить worker: $e');
      return -1;
    }
  }

  String _absolute(String value) {
    if (RegExp(r'^[A-Za-z]:[\\/]').hasMatch(value) || value.startsWith(r'\\')) {
      return value;
    }
    return '$appDir${Platform.pathSeparator}$value';
  }

  Future<void> _stop() async {
    if (!running) return;
    setState(() {
      running = false;
      status = tr('Остановка…', 'Stopping…');
    });
    worker?.kill();
  }

  Future<void> _pickFolder() async {
    const script =
        r'''Add-Type -AssemblyName System.Windows.Forms; $d=New-Object System.Windows.Forms.FolderBrowserDialog; $d.Description='Папка для музыки'; if($d.ShowDialog() -eq 'OK'){[Console]::OutputEncoding=[Text.Encoding]::UTF8; Write-Output $d.SelectedPath}''';
    final result = await Process.run('powershell.exe', [
      '-NoProfile',
      '-STA',
      '-WindowStyle',
      'Hidden',
      '-Command',
      script,
    ], stdoutEncoding: utf8);
    final value = result.stdout.toString().trim();
    if (value.isNotEmpty) setState(() => settings.directory = value);
  }

  void _openFolder([String? path]) {
    final target =
        path == null || path.isEmpty
            ? _absolute(settings.directory)
            : File(path).parent.path;
    Directory(target).createSync(recursive: true);
    Process.start('explorer.exe', [target]);
  }

  void _openGithub() {
    Process.start('explorer.exe', ['https://github.com/frtsii']);
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: ColorFiltered(
        colorFilter: ColorFilter.matrix(
          settings.monochrome
              ? const <double>[
                .2126,
                .7152,
                .0722,
                0,
                0,
                .2126,
                .7152,
                .0722,
                0,
                0,
                .2126,
                .7152,
                .0722,
                0,
                0,
                0,
                0,
                0,
                1,
                0,
              ]
              : const <double>[
                1,
                0,
                0,
                0,
                0,
                0,
                1,
                0,
                0,
                0,
                0,
                0,
                1,
                0,
                0,
                0,
                0,
                0,
                1,
                0,
              ],
        ),
        child: Stack(
          children: [
            Positioned.fill(
              child: AnimatedBuilder(
                animation: animation,
                builder:
                    (_, __) => CustomPaint(
                      painter: YandexBackdropPainter(animation.value),
                    ),
              ),
            ),
            SafeArea(
              child: Padding(
                padding: const EdgeInsets.all(16),
                child: Column(
                  children: [
                    _header(),
                    const SizedBox(height: 12),
                    Expanded(
                      child: LayoutBuilder(
                        builder: (_, c) {
                          if (c.maxWidth < 900) return _compact();
                          return Row(
                            crossAxisAlignment: CrossAxisAlignment.stretch,
                            children: [
                              Expanded(
                                flex: 9,
                                child: Column(
                                  children: [
                                    Expanded(flex: 6, child: _downloadCard()),
                                    const SizedBox(height: 14),
                                    Expanded(flex: 4, child: _progressCard()),
                                  ],
                                ),
                              ),
                              const SizedBox(width: 14),
                              Expanded(flex: 11, child: _resultsCard()),
                            ],
                          );
                        },
                      ),
                    ),
                  ],
                ),
              ),
            ),
            Positioned.fill(
              child: IgnorePointer(
                ignoring: !settingsOpen,
                child: AnimatedOpacity(
                  opacity: settingsOpen ? 1 : 0,
                  duration: const Duration(milliseconds: 220),
                  curve: Curves.easeOutCubic,
                  child: AnimatedScale(
                    scale: settingsOpen ? 1 : .96,
                    duration: const Duration(milliseconds: 260),
                    curve: Curves.easeOutBack,
                    child: _settingsOverlay(),
                  ),
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _header() => Row(
    children: [
      Container(
        width: 48,
        height: 48,
        padding: const EdgeInsets.all(6),
        decoration: BoxDecoration(
          color: Colors.black,
          borderRadius: BorderRadius.circular(14),
          border: Border.all(color: const Color(0x33FFFFFF)),
          boxShadow: const [
            BoxShadow(color: Color(0x66FFBC0D), blurRadius: 22),
          ],
        ),
        child: Image.asset('assets/yandex_music_icon.png'),
      ),
      const SizedBox(width: 13),
      Expanded(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              tr('ЗАГРУЗЧИК С ЯНДЕКС МУЗЫКИ', 'YANDEX MUSIC DOWNLOADER'),
              style: const TextStyle(
                fontSize: 20,
                fontWeight: FontWeight.w800,
                letterSpacing: .6,
              ),
            ),
            const SizedBox(height: 3),
            Text(
              tr(
                'Некоммерческое ПО с открытым исходным кодом от frtsii.',
                'Non-commercial open-source software by frtsii.',
              ),
              style: const TextStyle(color: muted, fontSize: 13),
            ),
          ],
        ),
      ),
      _iconButton(
        Icons.tune_rounded,
        tr('Настройки', 'Settings'),
        () => setState(() => settingsOpen = true),
      ),
    ],
  );

  Widget _compact() => ListView(
    children: [
      SizedBox(height: 360, child: _downloadCard()),
      const SizedBox(height: 14),
      SizedBox(height: 210, child: _progressCard()),
      const SizedBox(height: 14),
      SizedBox(height: 500, child: _resultsCard()),
    ],
  );

  Widget _card({required Widget child}) => ClipRRect(
    borderRadius: BorderRadius.circular(20),
    child: BackdropFilter(
      filter: ui.ImageFilter.blur(sigmaX: 24, sigmaY: 24),
      child: Container(
        decoration: BoxDecoration(
          gradient: const LinearGradient(
            begin: Alignment.topLeft,
            end: Alignment.bottomRight,
            colors: [Color(0x2FFFFFFF), Color(0x10141414), Color(0x12FFBC0D)],
            stops: [0, .58, 1],
          ),
          borderRadius: BorderRadius.circular(20),
          border: Border.all(color: const Color(0x29FFFFFF)),
          boxShadow: const [
            BoxShadow(
              color: Color(0x70000000),
              blurRadius: 30,
              offset: Offset(0, 14),
            ),
          ],
        ),
        child: child,
      ),
    ),
  );

  Widget _downloadCard() => _card(
    child: Padding(
      padding: const EdgeInsets.all(17),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              const Icon(Icons.link_rounded, color: yellow, size: 21),
              const SizedBox(width: 9),
              Text(
                tr('ССЫЛКИ ЯНДЕКС МУЗЫКИ', 'YANDEX MUSIC LINKS'),
                style: const TextStyle(
                  fontWeight: FontWeight.w700,
                  letterSpacing: .5,
                ),
              ),
            ],
          ),
          const SizedBox(height: 14),
          Expanded(
            child: TextField(
              controller: links,
              enabled: !running,
              maxLines: null,
              expands: true,
              textAlignVertical: TextAlignVertical.top,
              decoration: InputDecoration(
                hintText: tr(
                  'Трек, альбом, исполнитель или плейлист\nКаждая ссылка — с новой строки',
                  'Track, album, artist or playlist\nOne link per line',
                ),
                hintStyle: const TextStyle(color: Color(0xFF707070)),
              ),
            ),
          ),
          const SizedBox(height: 12),
          MotionButton(
            onTap: running ? null : _pickFolder,
            child: Container(
              height: 44,
              padding: const EdgeInsets.symmetric(horizontal: 14),
              decoration: BoxDecoration(
                color: const Color(0xFF111111),
                borderRadius: BorderRadius.circular(12),
                border: Border.all(color: line),
              ),
              child: Row(
                children: [
                  const Icon(Icons.folder_rounded, color: muted, size: 20),
                  const SizedBox(width: 10),
                  Expanded(
                    child: Text(
                      settings.directory,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: const TextStyle(color: Color(0xFFD8D8D8)),
                    ),
                  ),
                  const Icon(Icons.more_horiz, color: muted),
                ],
              ),
            ),
          ),
          const SizedBox(height: 14),
          MotionButton(
            onTap: running ? _stop : _start,
            glowColor: running ? red : yellow,
            child: SizedBox(
              width: double.infinity,
              height: 46,
              child: AnimatedContainer(
                duration: const Duration(milliseconds: 240),
                curve: Curves.easeOutCubic,
                decoration: BoxDecoration(
                  color: running ? red : yellow,
                  borderRadius: BorderRadius.circular(13),
                  boxShadow: [
                    BoxShadow(
                      color: (running ? red : yellow).withValues(alpha: .28),
                      blurRadius: 18,
                    ),
                  ],
                ),
                child: Row(
                  mainAxisAlignment: MainAxisAlignment.center,
                  children: [
                    AnimatedSwitcher(
                      duration: const Duration(milliseconds: 180),
                      transitionBuilder:
                          (child, a) => ScaleTransition(scale: a, child: child),
                      child: Icon(
                        running ? Icons.stop_rounded : Icons.download_rounded,
                        key: ValueKey(running),
                        color: Colors.black,
                      ),
                    ),
                    const SizedBox(width: 8),
                    Text(
                      running
                          ? tr('ОСТАНОВИТЬ', 'STOP')
                          : tr('СКАЧАТЬ', 'DOWNLOAD'),
                      style: const TextStyle(
                        color: Colors.black,
                        fontWeight: FontWeight.w800,
                        letterSpacing: .7,
                      ),
                    ),
                  ],
                ),
              ),
            ),
          ),
        ],
      ),
    ),
  );

  Widget _progressCard() => _card(
    child: Padding(
      padding: const EdgeInsets.all(17),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              AnimatedContainer(
                duration: const Duration(milliseconds: 350),
                width: 9,
                height: 9,
                decoration: BoxDecoration(
                  color: running ? yellow : const Color(0xFF6B6B6B),
                  shape: BoxShape.circle,
                  boxShadow:
                      running
                          ? const [BoxShadow(color: yellow, blurRadius: 9)]
                          : null,
                ),
              ),
              const SizedBox(width: 10),
              Text(
                tr('СОСТОЯНИЕ', 'STATUS'),
                style: const TextStyle(
                  fontWeight: FontWeight.w700,
                  letterSpacing: .5,
                ),
              ),
              const Spacer(),
              if (linkCount > 0)
                Text(
                  '$linkIndex / $linkCount',
                  style: const TextStyle(color: muted),
                ),
            ],
          ),
          const Spacer(),
          AnimatedSwitcher(
            duration: const Duration(milliseconds: 240),
            transitionBuilder:
                (child, a) => SlideTransition(
                  position: Tween(
                    begin: const Offset(0, .3),
                    end: Offset.zero,
                  ).animate(CurvedAnimation(parent: a, curve: Curves.easeOut)),
                  child: FadeTransition(opacity: a, child: child),
                ),
            child: Text(
              status,
              key: ValueKey(status),
              style: const TextStyle(fontSize: 17, fontWeight: FontWeight.w600),
            ),
          ),
          const SizedBox(height: 15),
          TweenAnimationBuilder<double>(
            tween: Tween(begin: 0, end: running || progress > 0 ? progress : 0),
            duration: const Duration(milliseconds: 420),
            curve: Curves.easeOutCubic,
            builder:
                (_, value, __) => ClipRRect(
                  borderRadius: BorderRadius.circular(8),
                  child: LinearProgressIndicator(
                    value: value,
                    minHeight: 8,
                    backgroundColor: const Color(0x55333333),
                    valueColor: const AlwaysStoppedAnimation(yellow),
                  ),
                ),
          ),
          const SizedBox(height: 11),
          AnimatedSwitcher(
            duration: const Duration(milliseconds: 180),
            child: Text(
              detailStatus,
              key: ValueKey(detailStatus),
              maxLines: 2,
              overflow: TextOverflow.ellipsis,
              style: const TextStyle(color: muted, fontSize: 11.5),
            ),
          ),
          const Spacer(),
        ],
      ),
    ),
  );

  Widget _resultsCard() => _card(
    child: Column(
      children: [
        Padding(
          padding: const EdgeInsets.fromLTRB(18, 15, 12, 0),
          child: Row(
            children: [
              _tab(tr('История', 'History'), 0, Icons.history_rounded),
              const SizedBox(width: 6),
              _tab(tr('Журнал', 'Log'), 1, Icons.terminal_rounded),
              const Spacer(),
              if ((tab == 0 ? history : logs).isNotEmpty)
                _iconButton(
                  Icons.delete_sweep_outlined,
                  tr('Очистить', 'Clear'),
                  () {
                    setState(() {
                      if (tab == 0) {
                        history.clear();
                      } else {
                        logs.clear();
                      }
                    });
                    if (tab == 0) {
                      unawaited(_saveHistory());
                    }
                  },
                ),
            ],
          ),
        ),
        Padding(
          padding: const EdgeInsets.all(14),
          child: TextField(
            controller: search,
            onChanged: (_) => setState(() {}),
            decoration: InputDecoration(
              prefixIcon: const Icon(Icons.search_rounded, color: muted),
              hintText: tr('Фильтр', 'Filter'),
              isDense: true,
            ),
          ),
        ),
        Expanded(
          child: AnimatedSwitcher(
            duration: const Duration(milliseconds: 220),
            transitionBuilder:
                (child, a) => FadeTransition(
                  opacity: a,
                  child: SlideTransition(
                    position: Tween(
                      begin: const Offset(.03, 0),
                      end: Offset.zero,
                    ).animate(a),
                    child: child,
                  ),
                ),
            child: KeyedSubtree(
              key: ValueKey(tab),
              child: tab == 0 ? _history() : _logs(),
            ),
          ),
        ),
      ],
    ),
  );

  Widget _tab(String label, int value, IconData icon) => MotionButton(
    onTap: () => setState(() => tab = value),
    child: AnimatedContainer(
      duration: const Duration(milliseconds: 160),
      padding: const EdgeInsets.symmetric(horizontal: 13, vertical: 10),
      decoration: BoxDecoration(
        color: tab == value ? const Color(0xFF303030) : Colors.transparent,
        borderRadius: BorderRadius.circular(10),
      ),
      child: Row(
        children: [
          Icon(icon, size: 18, color: tab == value ? yellow : muted),
          const SizedBox(width: 7),
          Text(
            label,
            style: TextStyle(
              fontWeight: FontWeight.w600,
              color: tab == value ? Colors.white : muted,
            ),
          ),
        ],
      ),
    ),
  );

  Widget _history() {
    final q = search.text.toLowerCase();
    final items =
        history
            .where(
              (e) =>
                  '${e.title} ${e.subtitle} ${e.path} ${e.children.map((c) => '${c.title} ${c.subtitle}').join(' ')}'
                      .toLowerCase()
                      .contains(q),
            )
            .toList();
    if (items.isEmpty) {
      return _empty(
        Icons.music_note_rounded,
        tr(
          'Загруженные треки появятся здесь',
          'Downloaded tracks will appear here',
        ),
      );
    }
    return ListView.separated(
      padding: const EdgeInsets.fromLTRB(14, 0, 14, 14),
      itemCount: items.length,
      separatorBuilder: (_, __) => const SizedBox(height: 8),
      itemBuilder: (_, i) {
        final e = items[i];
        return TweenAnimationBuilder<double>(
          tween: Tween(begin: 0, end: 1),
          duration: Duration(milliseconds: 220 + math.min(i, 6) * 55),
          curve: Curves.easeOutCubic,
          builder:
              (_, value, child) => Opacity(
                opacity: value,
                child: Transform.translate(
                  offset: Offset(18 * (1 - value), 0),
                  child: child,
                ),
              ),
          child: Container(
            decoration: BoxDecoration(
              color: panelSoft,
              borderRadius: BorderRadius.circular(13),
              border: Border.all(color: const Color(0xFF2E2E2E)),
            ),
            child: Column(
              children: [
                InkWell(
                  borderRadius: BorderRadius.circular(13),
                  onTap:
                      () =>
                          e.isCollection
                              ? setState(() => e.expanded = !e.expanded)
                              : _openFolder(e.path),
                  child: Padding(
                    padding: const EdgeInsets.all(12),
                    child: Row(
                      children: [
                        _artwork(e, 46),
                        const SizedBox(width: 12),
                        Expanded(
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Text(
                                e.title,
                                maxLines: 1,
                                overflow: TextOverflow.ellipsis,
                                style: const TextStyle(
                                  fontWeight: FontWeight.w600,
                                ),
                              ),
                              const SizedBox(height: 4),
                              Text(
                                e.isCollection
                                    ? '${e.subtitle}${e.subtitle.isEmpty ? '' : ' · '}${e.children.length} ${tr('треков', 'tracks')}'
                                    : e.subtitle,
                                maxLines: 1,
                                overflow: TextOverflow.ellipsis,
                                style: const TextStyle(
                                  color: muted,
                                  fontSize: 12,
                                ),
                              ),
                            ],
                          ),
                        ),
                        if (e.isCollection)
                          AnimatedRotation(
                            turns: e.expanded ? .5 : 0,
                            duration: const Duration(milliseconds: 220),
                            child: const Icon(
                              Icons.keyboard_arrow_down_rounded,
                              color: muted,
                            ),
                          ),
                      ],
                    ),
                  ),
                ),
                AnimatedSize(
                  duration: const Duration(milliseconds: 240),
                  curve: Curves.easeOutCubic,
                  child:
                      e.isCollection && e.expanded
                          ? Column(
                            children:
                                e.children
                                    .map(
                                      (child) => Container(
                                        decoration: const BoxDecoration(
                                          border: Border(
                                            top: BorderSide(color: line),
                                          ),
                                        ),
                                        padding: const EdgeInsets.fromLTRB(
                                          16,
                                          9,
                                          10,
                                          9,
                                        ),
                                        child: Row(
                                          children: [
                                            _artwork(child, 34),
                                            const SizedBox(width: 10),
                                            Expanded(
                                              child: Column(
                                                crossAxisAlignment:
                                                    CrossAxisAlignment.start,
                                                children: [
                                                  Text(
                                                    child.title,
                                                    maxLines: 1,
                                                    overflow:
                                                        TextOverflow.ellipsis,
                                                    style: const TextStyle(
                                                      fontSize: 13,
                                                      fontWeight:
                                                          FontWeight.w600,
                                                    ),
                                                  ),
                                                  Text(
                                                    child.subtitle,
                                                    maxLines: 1,
                                                    overflow:
                                                        TextOverflow.ellipsis,
                                                    style: const TextStyle(
                                                      color: muted,
                                                      fontSize: 11,
                                                    ),
                                                  ),
                                                ],
                                              ),
                                            ),
                                            IconButton(
                                              tooltip: tr(
                                                'Открыть папку',
                                                'Open folder',
                                              ),
                                              onPressed:
                                                  () => _openFolder(child.path),
                                              icon: const Icon(
                                                Icons.folder_open_outlined,
                                                color: muted,
                                                size: 18,
                                              ),
                                            ),
                                          ],
                                        ),
                                      ),
                                    )
                                    .toList(),
                          )
                          : const SizedBox.shrink(),
                ),
              ],
            ),
          ),
        );
      },
    );
  }

  Widget _artwork(DownloadEntry entry, double size) => ClipRRect(
    borderRadius: BorderRadius.circular(size * .2),
    child: SizedBox(
      width: size,
      height: size,
      child:
          entry.cover.isNotEmpty
              ? Image.network(
                entry.cover,
                fit: BoxFit.cover,
                errorBuilder: (_, __, ___) => _artworkFallback(entry),
              )
              : _artworkFallback(entry),
    ),
  );

  Widget _artworkFallback(DownloadEntry entry) => Container(
    color: const Color(0xFF282828),
    child: Icon(
      entry.kind == 'artist' ? Icons.person_rounded : Icons.music_note_rounded,
      color: accent,
    ),
  );

  Widget _logs() {
    final q = search.text.toLowerCase();
    final items = logs.where((e) => e.toLowerCase().contains(q)).toList();
    if (items.isEmpty) {
      return _empty(
        Icons.terminal_rounded,
        tr('Журнал пока пуст', 'The log is empty'),
      );
    }
    return SelectionArea(
      child: ListView.builder(
        reverse: true,
        padding: const EdgeInsets.fromLTRB(16, 0, 16, 16),
        itemCount: items.length,
        itemBuilder:
            (_, i) => Padding(
              padding: const EdgeInsets.symmetric(vertical: 3),
              child: Text(
                items[items.length - 1 - i],
                style: const TextStyle(
                  fontFamily: 'Consolas',
                  fontSize: 12.5,
                  height: 1.35,
                  color: Color(0xFFD4D4D4),
                ),
              ),
            ),
      ),
    );
  }

  Widget _empty(IconData icon, String text) => Center(
    child: Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        AnimatedBuilder(
          animation: animation,
          builder:
              (_, __) => Transform.scale(
                scale: .94 + math.sin(animation.value * math.pi * 2) * .06,
                child: Icon(icon, size: 45, color: const Color(0xFF777777)),
              ),
        ),
        const SizedBox(height: 12),
        Text(text, style: const TextStyle(color: muted)),
      ],
    ),
  );

  Widget _iconButton(IconData icon, String tooltip, VoidCallback onTap) =>
      Tooltip(
        message: tooltip,
        child: MotionButton(
          onTap: onTap,
          child: Container(
            width: 44,
            height: 44,
            decoration: BoxDecoration(
              color: const Color(0x70222222),
              borderRadius: BorderRadius.circular(13),
              border: Border.all(color: line),
            ),
            child: Icon(icon, color: Colors.white),
          ),
        ),
      );

  Widget _settingsOverlay() => Material(
    color: const Color(0xC8000000),
    child: Center(
      child: ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: 590, maxHeight: 520),
        child: MediaQuery(
          data: MediaQuery.of(
            context,
          ).copyWith(textScaler: const TextScaler.linear(.88)),
          child: _card(
            child: Column(
              children: [
                Padding(
                  padding: const EdgeInsets.fromLTRB(18, 12, 10, 9),
                  child: Row(
                    children: [
                      const Icon(Icons.tune_rounded, color: yellow),
                      const SizedBox(width: 10),
                      Text(
                        tr('НАСТРОЙКИ', 'SETTINGS'),
                        style: const TextStyle(
                          fontSize: 18,
                          fontWeight: FontWeight.w800,
                          letterSpacing: .5,
                        ),
                      ),
                      const Spacer(),
                      _iconButton(
                        Icons.close_rounded,
                        tr('Закрыть', 'Close'),
                        () => setState(() => settingsOpen = false),
                      ),
                    ],
                  ),
                ),
                const Divider(height: 1, color: line),
                Expanded(
                  child: SingleChildScrollView(
                    padding: const EdgeInsets.all(12),
                    child: StatefulBuilder(
                      builder: (context, localSet) {
                        void update(VoidCallback fn) {
                          fn();
                          localSet(() {});
                          setState(() {});
                        }

                        return Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Row(
                              children: [
                                Expanded(
                                  child: _select(
                                    tr('Язык', 'Language'),
                                    settings.language,
                                    const {'ru': 'Русский', 'en': 'English'},
                                    (v) => update(() {
                                      settings.language = v;
                                      status =
                                          v == 'en'
                                              ? 'Ready to download'
                                              : 'Готов к загрузке';
                                    }),
                                  ),
                                ),
                                const SizedBox(width: 10),
                                Expanded(
                                  child: _select(
                                    tr('Оформление', 'Appearance'),
                                    settings.monochrome ? 'mono' : 'color',
                                    {
                                      'color': tr('Цветное', 'Color'),
                                      'mono': tr(
                                        'Чёрно-белое',
                                        'Black and white',
                                      ),
                                    },
                                    (v) => update(
                                      () => settings.monochrome = v == 'mono',
                                    ),
                                  ),
                                ),
                              ],
                            ),
                            const SizedBox(height: 12),
                            _label(
                              tr('Токен Яндекс Музыки', 'Yandex Music token'),
                            ),
                            TextField(
                              controller: token,
                              obscureText: true,
                              enableSuggestions: false,
                              autocorrect: false,
                              decoration: InputDecoration(
                                hintText: tr(
                                  'Сохраняется рядом с программой: oauth-token.txt',
                                  'Stored beside the app: oauth-token.txt',
                                ),
                                suffixIcon: const Icon(
                                  Icons.key_rounded,
                                  color: muted,
                                ),
                              ),
                            ),
                            const SizedBox(height: 12),
                            Row(
                              children: [
                                Expanded(
                                  child: _select(
                                    tr('Качество', 'Quality'),
                                    settings.quality,
                                    const {
                                      '0': 'AAC 64 kbps',
                                      '1': 'AAC 192 kbps',
                                      '2': 'FLAC',
                                    },
                                    (v) => update(() => settings.quality = v),
                                  ),
                                ),
                                const SizedBox(width: 14),
                                Expanded(
                                  child: _select(
                                    tr('Текст песни', 'Lyrics'),
                                    settings.lyrics,
                                    {
                                      'embed': tr(
                                        'Встроенный · с таймкодами',
                                        'Embedded · synced',
                                      ),
                                      'lrc': tr(
                                        'Отдельный LRC',
                                        'Separate LRC',
                                      ),
                                      'text': tr('Обычный TXT', 'Plain TXT'),
                                      'none': tr('Не загружать', 'Disabled'),
                                    },
                                    (v) => update(() => settings.lyrics = v),
                                  ),
                                ),
                              ],
                            ),
                            const SizedBox(height: 12),
                            Row(
                              children: [
                                Expanded(
                                  child: _number(
                                    tr('Обложка, px', 'Cover, px'),
                                    settings.cover,
                                    (v) => settings.cover = v,
                                  ),
                                ),
                                const SizedBox(width: 12),
                                Expanded(
                                  child: _number(
                                    tr('Тайм-аут, сек', 'Timeout, sec'),
                                    settings.timeout,
                                    (v) => settings.timeout = v,
                                  ),
                                ),
                                const SizedBox(width: 12),
                                Expanded(
                                  child: _number(
                                    tr('Попытки', 'Retries'),
                                    settings.tries,
                                    (v) => settings.tries = v,
                                  ),
                                ),
                              ],
                            ),
                            const SizedBox(height: 10),
                            Row(
                              children: [
                                Expanded(
                                  child: _number(
                                    tr('Пауза между треками', 'Track delay'),
                                    settings.delay,
                                    (v) => settings.delay = v,
                                  ),
                                ),
                                const SizedBox(width: 12),
                                Expanded(
                                  child: _number(
                                    tr('Пауза повтора', 'Retry delay'),
                                    settings.retryDelay,
                                    (v) => settings.retryDelay = v,
                                  ),
                                ),
                                const SizedBox(width: 12),
                                Expanded(
                                  child: _select(
                                    tr('Совместимость', 'Compatibility'),
                                    settings.compatibility,
                                    {
                                      '0': tr('Современная', 'Modern'),
                                      '1': tr('Максимальная', 'Maximum'),
                                    },
                                    (v) => update(
                                      () => settings.compatibility = v,
                                    ),
                                  ),
                                ),
                              ],
                            ),
                            const SizedBox(height: 10),
                            _switch(
                              tr(
                                'Пропускать существующие файлы',
                                'Skip existing files',
                              ),
                              settings.skipExisting,
                              (v) => update(() => settings.skipExisting = v),
                            ),
                            _switch(
                              tr('Встраивать обложку', 'Embed cover art'),
                              settings.embedCover,
                              (v) => update(() => settings.embedCover = v),
                            ),
                            _switch(
                              tr(
                                'Только музыкальные альбомы',
                                'Music albums only',
                              ),
                              settings.onlyMusic,
                              (v) => update(() => settings.onlyMusic = v),
                            ),
                            _switch(
                              tr(
                                'Для автора брать только его альбомы',
                                'Only albums by the selected artist',
                              ),
                              settings.stickToArtist,
                              (v) => update(() => settings.stickToArtist = v),
                            ),
                            _switch(
                              tr(
                                'Не очищать имена файлов',
                                'Keep unsafe filename characters',
                              ),
                              settings.unsafePath,
                              (v) => update(() => settings.unsafePath = v),
                            ),
                            _switch(
                              tr(
                                'Сохранять историю загрузок',
                                'Save download history',
                              ),
                              settings.saveHistory,
                              (v) => update(() => settings.saveHistory = v),
                            ),
                            _switch(
                              tr(
                                'Открывать папку после завершения',
                                'Open folder when finished',
                              ),
                              settings.openFolderWhenDone,
                              (v) =>
                                  update(() => settings.openFolderWhenDone = v),
                            ),
                            const SizedBox(height: 10),
                            Center(
                              child: MotionButton(
                                onTap: _openGithub,
                                child: Container(
                                  padding: const EdgeInsets.symmetric(
                                    horizontal: 18,
                                    vertical: 10,
                                  ),
                                  decoration: BoxDecoration(
                                    color: const Color(0x301F1F1F),
                                    borderRadius: BorderRadius.circular(11),
                                    border: Border.all(color: line),
                                  ),
                                  child: const Row(
                                    mainAxisSize: MainAxisSize.min,
                                    children: [
                                      Icon(Icons.code_rounded, size: 18),
                                      SizedBox(width: 8),
                                      Text(
                                        'GitHub · frtsii',
                                        style: TextStyle(
                                          fontWeight: FontWeight.w700,
                                        ),
                                      ),
                                    ],
                                  ),
                                ),
                              ),
                            ),
                          ],
                        );
                      },
                    ),
                  ),
                ),
                Padding(
                  padding: const EdgeInsets.all(10),
                  child: Row(
                    children: [
                      Expanded(
                        child: Text(
                          tr(
                            'Настройки сохраняются рядом с программой',
                            'Settings are stored beside the app',
                          ),
                          style: const TextStyle(color: muted, fontSize: 11),
                        ),
                      ),
                      MotionButton(
                        onTap: () async {
                          await _saveSettings();
                          setState(() => settingsOpen = false);
                        },
                        glowColor: yellow,
                        child: Container(
                          padding: const EdgeInsets.symmetric(
                            horizontal: 20,
                            vertical: 12,
                          ),
                          decoration: BoxDecoration(
                            color: yellow,
                            borderRadius: BorderRadius.circular(12),
                          ),
                          child: Text(
                            tr('СОХРАНИТЬ', 'SAVE'),
                            style: const TextStyle(
                              color: Colors.black,
                              fontWeight: FontWeight.w800,
                            ),
                          ),
                        ),
                      ),
                    ],
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    ),
  );

  Widget _label(String text) => Padding(
    padding: const EdgeInsets.only(bottom: 8),
    child: Text(
      text,
      style: const TextStyle(
        color: Color(0xFFDADADA),
        fontWeight: FontWeight.w600,
        fontSize: 13,
      ),
    ),
  );
  Widget _select(
    String labelText,
    String value,
    Map<String, String> values,
    ValueChanged<String> onChanged,
  ) => Column(
    crossAxisAlignment: CrossAxisAlignment.start,
    children: [
      _label(labelText),
      DropdownButtonFormField<String>(
        value: values.containsKey(value) ? value : values.keys.first,
        items:
            values.entries
                .map(
                  (e) => DropdownMenuItem(value: e.key, child: Text(e.value)),
                )
                .toList(),
        onChanged: (v) {
          if (v != null) onChanged(v);
        },
      ),
    ],
  );
  Widget _number(
    String labelText,
    String value,
    ValueChanged<String> onChanged,
  ) => Column(
    crossAxisAlignment: CrossAxisAlignment.start,
    children: [
      _label(labelText),
      TextFormField(
        initialValue: value,
        keyboardType: TextInputType.number,
        inputFormatters: [FilteringTextInputFormatter.digitsOnly],
        onChanged: onChanged,
      ),
    ],
  );
  Widget _switch(String text, bool value, ValueChanged<bool> onChanged) =>
      SwitchListTile.adaptive(
        contentPadding: EdgeInsets.zero,
        dense: true,
        activeColor: yellow,
        title: Text(text, style: const TextStyle(fontSize: 13.5)),
        value: value,
        onChanged: onChanged,
      );
}

class MotionButton extends StatefulWidget {
  const MotionButton({
    super.key,
    required this.child,
    required this.onTap,
    this.glowColor = Colors.white,
  });
  final Widget child;
  final VoidCallback? onTap;
  final Color glowColor;

  @override
  State<MotionButton> createState() => _MotionButtonState();
}

class _MotionButtonState extends State<MotionButton> {
  bool hover = false;
  bool pressed = false;

  @override
  Widget build(BuildContext context) => MouseRegion(
    cursor:
        widget.onTap == null
            ? SystemMouseCursors.basic
            : SystemMouseCursors.click,
    onEnter: (_) => setState(() => hover = true),
    onExit:
        (_) => setState(() {
          hover = false;
          pressed = false;
        }),
    child: GestureDetector(
      behavior: HitTestBehavior.opaque,
      onTap: widget.onTap,
      onTapDown:
          widget.onTap == null ? null : (_) => setState(() => pressed = true),
      onTapUp:
          widget.onTap == null ? null : (_) => setState(() => pressed = false),
      onTapCancel:
          widget.onTap == null ? null : () => setState(() => pressed = false),
      child: AnimatedScale(
        scale: pressed ? .965 : (hover ? 1.025 : 1),
        duration: const Duration(milliseconds: 140),
        curve: Curves.easeOutCubic,
        child: AnimatedContainer(
          duration: const Duration(milliseconds: 180),
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(14),
            boxShadow:
                hover
                    ? [
                      BoxShadow(
                        color: widget.glowColor.withValues(alpha: .16),
                        blurRadius: 18,
                        spreadRadius: 1,
                      ),
                    ]
                    : const [],
          ),
          child: widget.child,
        ),
      ),
    ),
  );
}

class YandexBackdropPainter extends CustomPainter {
  YandexBackdropPainter(this.t);
  final double t;

  Offset drift(Size size, double x, double y, double phase, double amount) =>
      Offset(
        size.width * x +
            math.sin(t * math.pi * 2 + phase) * (size.width * .13 + amount),
        size.height * y +
            math.cos(t * math.pi * 2 * .83 + phase) *
                (size.height * .11 + amount * .7),
      );

  void shape(
    Canvas canvas,
    Size size,
    Offset center,
    double scale,
    double angle,
    Color a,
    Color b,
    Path Function() makePath,
  ) {
    canvas.save();
    canvas.translate(center.dx, center.dy);
    canvas.rotate(angle);
    canvas.scale(scale);
    final path = makePath();
    final bounds = path.getBounds();
    canvas.drawPath(
      path,
      Paint()
        ..color = a.withValues(alpha: .30)
        ..maskFilter = const MaskFilter.blur(BlurStyle.normal, 24),
    );
    canvas.drawPath(
      path,
      Paint()
        ..shader = LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: [a.withValues(alpha: .94), b.withValues(alpha: .72)],
        ).createShader(bounds),
    );
    canvas.restore();
  }

  Path sparkle() =>
      Path()
        ..moveTo(0, -48)
        ..cubicTo(7, -17, 16, -8, 47, 0)
        ..cubicTo(17, 7, 8, 16, 0, 47)
        ..cubicTo(-7, 17, -16, 8, -47, 0)
        ..cubicTo(-17, -7, -8, -16, 0, -48)
        ..close();

  Path blob() =>
      Path()
        ..moveTo(-48, 34)
        ..cubicTo(-57, -7, -35, -48, -7, -46)
        ..cubicTo(22, -44, 48, -21, 46, 8)
        ..cubicTo(44, 37, 12, 48, -48, 34)
        ..close();

  Path bolt() =>
      Path()
        ..moveTo(-45, -28)
        ..lineTo(1, -13)
        ..lineTo(26, -46)
        ..lineTo(19, -8)
        ..lineTo(48, -3)
        ..lineTo(9, 12)
        ..lineTo(21, 46)
        ..lineTo(-8, 19)
        ..lineTo(-42, 39)
        ..lineTo(-25, 7)
        ..close();

  Path ribbon() =>
      Path()
        ..moveTo(-48, -38)
        ..cubicTo(-8, -50, 25, -26, 46, 2)
        ..lineTo(17, 14)
        ..cubicTo(0, -5, -12, -13, -27, -8)
        ..lineTo(-10, 34)
        ..lineTo(-37, 45)
        ..close();

  @override
  void paint(Canvas canvas, Size size) {
    canvas.drawRect(Offset.zero & size, Paint()..color = bg);
    final wash =
        Paint()
          ..shader = const RadialGradient(
            colors: [Color(0x3DFF8A00), Color(0x152C4CFF), Colors.transparent],
            stops: [0, .43, 1],
          ).createShader(
            Rect.fromCircle(
              center: Offset(size.width * .16, size.height * .12),
              radius: size.width * .72,
            ),
          );
    canvas.drawRect(Offset.zero & size, wash);
    shape(
      canvas,
      size,
      drift(size, .08, .22, 0, 18),
      1.12,
      -.14 + math.sin(t * math.pi * 2) * .08,
      const Color(0xFFFF9F43),
      yellow,
      sparkle,
    );
    shape(
      canvas,
      size,
      drift(size, .91, .16, 1.1, 16),
      .88,
      .3 + math.sin(t * math.pi * 2 + 1) * .1,
      orange,
      pink,
      blob,
    );
    shape(
      canvas,
      size,
      drift(size, .12, .82, 2.3, 20),
      1.0,
      -.25 + math.sin(t * math.pi * 2 + 2) * .09,
      const Color(0xFF577CFF),
      const Color(0xFF7A45FF),
      bolt,
    );
    shape(
      canvas,
      size,
      drift(size, .88, .79, 3.4, 22),
      1.08,
      .18 + math.sin(t * math.pi * 2 + 3) * .1,
      const Color(0xFF86B8FF),
      const Color(0xFF385DFF),
      ribbon,
    );
    shape(
      canvas,
      size,
      drift(size, .53, .08, 4.5, 13),
      .55,
      t * math.pi * .12,
      yellow,
      orange,
      sparkle,
    );
    shape(
      canvas,
      size,
      drift(size, .54, .92, 5.2, 15),
      .7,
      -.4 - t * math.pi * .1,
      const Color(0xFF8B5CFF),
      const Color(0xFF385DFF),
      blob,
    );
  }

  @override
  bool shouldRepaint(covariant YandexBackdropPainter oldDelegate) =>
      oldDelegate.t != t;
}
