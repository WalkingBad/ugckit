# UGCKit - Инструкция по использованию

## Что это такое

UGCKit - инструмент для автоматической сборки коротких вертикальных видео (TikTok/Reels) из:

- **AI-аватар клипов** (Higgsfield) - человек идёт и говорит
- **Скринкастов приложения** - записи экрана приложения

```
┌─────────────────────────┐
│                         │
│      АВАТАР ВИДЕО       │
│    (человек идёт)       │
│                         │
│           ┌────────┐    │
│           │СКРИН-  │    │
│           │КАСТ    │    │
│           └────────┘    │
└─────────────────────────┘
```

## Установка

### Требования

- Python 3.11+
- FFmpeg

```bash
# macOS
brew install ffmpeg

# Установка UGCKit
cd ugckit
pip install -e .

# Или вручную
pip install click pyyaml pydantic
```

## Быстрый старт

### 1. Посмотреть доступные скрипты

```bash
ugckit list-scripts --scripts-dir ./scripts/
```

Вывод:
```
Found 10 scripts:

  A1              | Day 347                  | 3 segments | ~19s
  B1              | Duolingo for Steps       | 2 segments | ~12s
  ...
```

### 2. Посмотреть детали скрипта

```bash
ugckit show-script --script A1 --scripts-dir ./scripts/
```

Вывод:
```
Script: A1
Title: Day 347
Total duration: ~18.7s

Segments:
  [1] (6.0s) Day three forty-seven. I'm still walking to Mordor...
  [2] (7.0s) But I'm twelve hundred miles in. Three hundred to go...
  [3] (5.7s) It's an app called MistyWay. Your steps move you...
```

### 3. Превью таймлайна (без рендера)

```bash
ugckit compose \
  --script A1 \
  --avatars ./avatars/seg1.mp4 \
  --avatars ./avatars/seg2.mp4 \
  --avatars ./avatars/seg3.mp4 \
  --scripts-dir ./scripts/ \
  --dry-run
```

Вывод:
```
Timeline for A1 (total: 18.7s):
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  0.0s -   6.0s │   avatar: seg1.mp4
  6.0s -  13.0s │   avatar: seg2.mp4
 13.0s -  18.7s │   avatar: seg3.mp4
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Output: assets/output/A1.mp4

Dry run - no video will be rendered

FFmpeg command:
ffmpeg -i ./avatars/seg1.mp4 ...
```

### 4. Сборка видео

```bash
ugckit compose \
  --script A1 \
  --avatars ./avatars/seg1.mp4 \
  --avatars ./avatars/seg2.mp4 \
  --avatars ./avatars/seg3.mp4 \
  --screencasts ./assets/screencasts/ \
  --output ./output/
```

## Формат скриптов

Скрипты пишутся в Markdown формате:

```markdown
### Script A1: "Day 347" (Office Worker Mike)

**Clip 1 (VEO 8s):**
Says: "Day three forty-seven. I'm still walking to Mordor."

**Clip 2 (VEO 8s):**
[screencast: stats_screen @ 1.5-4.0]
Says: "My coworkers think I'm crazy. But look at these stats."

**Clip 3 (VEO 8s):**
Says: "It's an app called MistyWay."
```

### Screencast теги

Формат: `[screencast: имя_файла @ начало-конец mode:режим]`

- `имя_файла` - без расширения (добавится `.mp4`)
- `начало-конец` - время в секундах относительно начала клипа
- `mode` - опционально: `overlay` (по умолчанию) или `pip`

Примеры:
```
[screencast: stats_screen @ 1.5-4.0]
[screencast: map_progress @ 0-3s mode:pip]
```

## Конфигурация

Настройки в `ugckit/config/default.yaml`:

```yaml
composition:
  overlay:
    scale: 0.4              # Размер скринкаста (40% от ширины)
    position: bottom-right  # Позиция: top-left, top-right, bottom-left, bottom-right
    margin: 50              # Отступ от края (пиксели)

output:
  fps: 30
  resolution: [1080, 1920]  # 9:16 вертикальный формат
  codec: libx264
  preset: medium            # ultrafast, fast, medium, slow
  crf: 23                   # Качество (меньше = лучше, 18-28)

audio:
  normalize: true           # Нормализация громкости
  target_loudness: -14      # Целевая громкость (LUFS)
```

## CLI опции

### `ugckit compose`

| Опция | Описание |
|-------|----------|
| `--script, -s` | ID скрипта или путь к .md файлу (обязательно) |
| `--avatars, -a` | Видео аватара, по одному на сегмент (обязательно, несколько) |
| `--screencasts, -c` | Папка со скринкастами |
| `--scripts-dir` | Папка со скриптами |
| `--output, -o` | Папка или путь для вывода |
| `--config` | Путь к YAML конфигу |
| `--mode, -m` | Режим: `overlay` (по умолчанию) или `pip` (Phase 2, пока выдаёт warning) |
| `--head-position` | Позиция головы для PiP режима (Phase 2) |
| `--dry-run` | Показать таймлайн без рендера |

## Рабочий процесс

### 1. Подготовка скриптов

Создайте Markdown файл со скриптами в формате выше.

### 2. Генерация аватаров

Используйте Higgsfield для генерации видео-клипов по тексту из скрипта.

**Важно:** Один клип = один сегмент (Clip 1, Clip 2, ...)

### 3. Запись скринкастов

Запишите скринкасты приложения:
- `stats_screen.mp4` - экран статистики
- `map_progress.mp4` - карта прогресса
- и т.д.

### 4. Добавление тегов

Добавьте `[screencast: ...]` теги в скрипт, указывая когда показывать скринкасты.

### 5. Сборка

```bash
# Превью
ugckit compose --script A1 --avatars seg*.mp4 --dry-run

# Рендер
ugckit compose --script A1 --avatars seg*.mp4 --output ./final/
```

## Структура проекта

```
ugckit/
├── ugckit/             # Python пакет
│   ├── cli.py          # CLI команды
│   ├── parser.py       # Парсер Markdown
│   ├── composer.py     # FFmpeg композиция
│   ├── config.py       # Загрузка конфига
│   ├── models.py       # Pydantic модели
│   └── config/
│       └── default.yaml # Настройки по умолчанию
├── assets/
│   ├── screencasts/    # Скринкасты приложения
│   ├── avatars/        # AI аватар клипы
│   └── output/         # Готовые видео
└── docs/
    ├── ARCHITECTURE.md # Архитектура
    └── USAGE_RU.md     # Эта инструкция
```

## Частые вопросы

### Как добавить несколько скринкастов в один клип?

Пока поддерживается только один скринкаст на клип. Для нескольких - разбейте на отдельные клипы.

### Почему таймлайн показывает другую длительность?

При `--dry-run` используется оценка по количеству слов (3 слова/сек). Реальная длительность берётся из видео файла.

### Как изменить позицию скринкаста?

В `ugckit/config/default.yaml` измените `composition.overlay.position`.

### Почему не работает PiP режим?

PiP режим будет реализован в Phase 2 (требует MediaPipe и rembg).

## Roadmap

| Фаза | Статус | Функции |
|------|--------|---------|
| Phase 1: MVP | **Готово** | CLI, парсер, overlay, --dry-run |
| Phase 2: PiP | В планах | Вырезка головы, PiP режим |
| Phase 3: Smart Sync | В планах | Whisper timestamps, авто-триггеры |
