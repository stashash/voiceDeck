"""Generate offline Russian acceptance speech with an explicitly supplied eSpeak binary."""
from __future__ import annotations

import argparse
import audioop
import hashlib
import json
import os
from pathlib import Path
import subprocess
import wave


CASES = [
    ("select", "Выбери элемент один", "element"),
    ("size", "Размер шрифта двадцать четыре", "style"),
    ("color", "Сделай текст красным", "style"),
    ("move", "Вправо на двадцать", "move"),
    ("replace", "Замени текст на План запуска", "text"),
    ("append", "Добавь в конец Готово", "appendText"),
    ("undo", "Отмени", "undo"),
    ("next", "Следующий слайд", "next"),
    ("previous", "Предыдущий слайд", "previous"),
]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--espeak", required=True, type=Path)
    parser.add_argument("--speed", type=int, default=135)
    parser.add_argument("--voice", default="ru")
    parser.add_argument("--amplitude", type=int, default=100)
    parser.add_argument("--leading-silence-ms", type=int, default=0)
    parser.add_argument("--label", default="audio")
    args = parser.parse_args()
    assert args.label and all(c in "abcdefghijklmnopqrstuvwxyz0123456789-" for c in args.label)
    assert 80 <= args.speed <= 250 and 1 <= args.amplitude <= 200 and 0 <= args.leading_silence_ms <= 2000
    args.espeak = args.espeak.resolve()
    environment = {**os.environ, "ESPEAK_DATA_PATH": str(args.espeak.parent)}
    output = Path(__file__).resolve().parent / "voice-factory-output" / args.label
    output.mkdir(parents=True, exist_ok=True)
    version = subprocess.run([str(args.espeak), "--version"], env=environment, check=True, capture_output=True, text=True).stdout.strip()
    cases = []
    for case_id, phrase, kind in CASES:
        source = output / f"{case_id}.txt"
        source.write_text(phrase, encoding="utf-8")
        raw = output / f"{case_id}-source.wav"
        destination = output / f"{case_id}.wav"
        subprocess.run([str(args.espeak), "-v", args.voice, "-s", str(args.speed), "-a", str(args.amplitude), "-f", str(source), "-w", str(raw)], env=environment, check=True)
        with wave.open(str(raw), "rb") as stream:
            assert stream.getnchannels() == 1 and stream.getsampwidth() == 2
            pcm = stream.readframes(stream.getnframes())
            source_rate = stream.getframerate()
        pcm, _ = audioop.ratecv(pcm, 2, 1, source_rate, 16000, None)
        pcm = bytes(args.leading_silence_ms * 32) + pcm
        with wave.open(str(destination), "wb") as stream:
            stream.setnchannels(1)
            stream.setsampwidth(2)
            stream.setframerate(16000)
            stream.writeframes(pcm)
        cases.append({"id": case_id, "text": phrase, "expectedKind": kind, "wav": str(destination),
                      "sha256": hashlib.sha256(destination.read_bytes()).hexdigest(), "durationMs": len(pcm) / 32})
    manifest = {"mode": "offline-synthetic-tts", "engine": version, "voice": args.voice, "speed": args.speed,
                "amplitude": args.amplitude, "leadingSilenceMs": args.leading_silence_ms,
                "microphoneCaptureTested": False, "cases": cases}
    manifest_path = output / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(manifest_path)


if __name__ == "__main__":
    main()
