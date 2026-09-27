# Voice Editor V2

## Scope

This branch changes voice editing only. Existing Live speech-to-slide creation remains available and is not redesigned. Production on 8088/8090 is not used for acceptance.

The generated-deck editor and component editor are different document formats. They retain separate capabilities; a command supported in one is not silently promised in the other.

## Generated Deck Commands

| Operation | Russian phrase | Behavior |
| --- | --- | --- |
| Select | Выбери элемент два / Выбери заголовок | Exact element number or unique title; no guess on ambiguity |
| Navigation | Следующий слайд / Слайд пятнадцать | Existing slide only |
| Literal replacement | Замени текст на ... | Preserves case and punctuation |
| Two-utterance dictation | Измени текст; then the new text | Bound to selected text; selection change cancels |
| Append | Добавь в конец ... | Appends to selected text |
| Font | Размер шрифта двадцать четыре | 6-144 pt, deterministic |
| Style | Сделай текст жирным / Курсив / Убери курсив | Explicit boolean formatting |
| Text alignment | Выровняй текст по центру | Left, center, right |
| Color | Цвет текста красный / Заливка синяя | Hex or supported color words |
| Movement | Вправо на двадцать / В центр / Ещё немного | Pixel steps, normalized persisted coordinates |
| Size | Ширина двести / Высота сто | Valid dimensions, no off-slide overflow |
| Layer | На передний план / На задний план | Persisted HTML and PPTX order |
| Background | Фон слайда белый | Changes background, undoable |
| Insert | Добавь текст ... / Добавь карточку ... / Добавь фигуру | Native editable primitives |
| Table | Добавь таблицу три на два | Up to 5 columns and 8 visible rows including header |
| Cell | Ячейка два один: ... | Visible row 1 is header; column numbering starts at 1 |
| Rows/columns | Добавь строку / Удали строку два / Удали столбец два | Cannot delete header; row numbers match visible cell numbers |
| Notes | Заметки докладчика ... | Saved presenter notes |
| Slides | Добавь слайд / Скопируй слайд / Перемести слайд на три | Existing slide operations |
| Delete | Удали элемент / Удали слайд | Slide deletion requires confirmation |
| Undo | Отмени | Restores persisted prior document state |
| Stop | Стоп / Сбрось очередь | Cancels planning, reconciles saved state |
| Semantic rewrite | Сократи заголовок / Перепиши выбранный текст | Bounded local model; one selected text only |

The examples use the same Russian Cyrillic phrases as the executable tests.

## Boundaries

- Generated-deck cards are two independently selectable native objects: background shape and text. Group operations, arbitrary image/chart insertion and multi-object semantic layout are not implemented in this editor.
- The component editor already supports image/chart components, grouping, locking, rotation, opacity, undo/redo, and typed plans. This branch expands deterministic Russian number, table, alignment, slide and formatting phrases there. Image search/generation providers are separate from local speech/text editing and are not newly certified offline.
- No fuzzy repair of damaged ASR output is performed. An unrecognized command must not be guessed into a destructive edit.
- The normal command path bypasses the model. ASR and model latency are measured separately. No zero-latency promise.
- Free-form generated-deck commands rewrite a single text object. They do not recompose the entire slide or discard unrelated shapes. Explicit invalid names/numbers are rejected. Late model results lose to newer document revisions.
- Editor ASR retains VAD segments with bounded 200 ms pre-roll and 160 ms already-available post-roll; stopping flushes native VAD. Existing generation audio behavior remains unchanged.

## Isolated Local Run

Prerequisites: Docker Desktop; installed project ASR weights/native library; existing voicedeck-designer:editor dependency image; Ollama with qwen3.8:27b and bge-m3-embed already installed. No cloud inference is required for the editing path.

```powershell
cd frontend
npm ci
cd ..
$env:DOCKER_BUILDKIT='0'
./scripts/start-voice-factory.ps1 -Build
```

Open http://localhost:5174/. Ports 8089 and 8091 are isolated service endpoints; the microphone preview is served on 5174. New named volumes do not share production documents. Models/native libraries are mounted read-only from SourceWorkspace. Starting does not enable old factory cron jobs, kill other port owners, or merge branches.

See scripts/voice-factory-README.md for the audio acceptance harness, exact waveform hashes and limitations. Run node scripts/verify-deck-voice-model.mjs for real local-model persistence, stale-write and cancellation checks. Run node scripts/verify-live-generation.mjs separately for the unchanged Live generation regression from transcript input.

For the existing PCM-to-slide regression, use `node scripts/verify-live-generation.mjs --audio <16kHz-mono-PCM16.wav>`. It sends audio without enabling editor mode, checks packet acknowledgements and final speech, waits for each chunk's designer result, and requires at least one rendered slide. An empty designer result for non-content speech is not counted as a rendered slide. The test deletes only its own isolated session. Neither replay mode tests browser microphone capture.

## Release Gate

Synthetic PCM acceptance is not a physical microphone test. Human voice, room noise, microphone capture and real end-to-end latency require representative recordings. Failed synthetic cases remain visible in the report; a passed parser suite cannot turn an ASR failure into a release pass. Merge into stas/master remains a human gate.
