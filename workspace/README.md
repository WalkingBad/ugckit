# UGCKit Workspace

## Структура

```
workspace/
├── scripts/        ← Markdown скрипты
├── avatars/        ← Видео от Higgsfield
├── screencasts/    ← Скринкасты приложения
└── output/         ← Готовые видео
```

## Как использовать

### 1. Напиши скрипт
Скопируй `scripts/A1.md` и отредактируй под себя.

### 2. Сгенери аватар-видео
В Higgsfield создай видео для каждого Clip. Скачай в `avatars/`.

### 3. Запиши скринкасты (опционально)
Запиши экран приложения, сохрани в `screencasts/`.

### 4. Проверь скрипт
```bash
cd /Volumes/SSD/Repos/ugckit
ugckit show-script --script A1 --scripts-dir ./workspace/scripts/
```

### 5. Собери видео
```bash
ugckit compose \
  --script A1 \
  --avatars ./workspace/avatars/a1-seg1.mp4 ./workspace/avatars/a1-seg2.mp4 ./workspace/avatars/a1-seg3.mp4 \
  --screencasts ./workspace/screencasts/ \
  --scripts-dir ./workspace/scripts/ \
  --output ./workspace/output/
```

## Формат скрипта

```markdown
### Script ID: "Название"

**Clip 1 (8s):**
Says: "Текст первого клипа"

**Clip 2 (8s):**
[screencast: filename @ start-end]
Says: "Текст со скринкастом"
```

- `Clip N` — сегмент, нужно одно видео от Higgsfield
- `[screencast: NAME @ START-END]` — показать скринкаст NAME.mp4 с START по END секунду
- `Says:` — текст для понимания (аватар его проговаривает)
