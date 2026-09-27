# Voice Factory Acceptance

Current measured result: [voice-factory-verdict.md](voice-factory-verdict.md). Fixed ru135 replay passes 5/9 complete commands, with four ASR failures intentionally retained.

Run from the isolated `voice-factory/voiceDeck` checkout. No commits or production data are needed. The harness refuses designer ports other than 8091 and ASR ports other than 8089, and only accepts loopback URLs. Main owns runtime startup and original generation regression.

## Reproduce

```powershell
# Installed Node 22+ and frontend npm dependencies are required.
./scripts/voice-factory-run.ps1 -Mode text

# Optional portable offline TTS setup: official eSpeak NG 1.52.0, 12.8 MB.
# Administrative extraction only; no system voice installation or cloud TTS.
./scripts/voice-factory-prepare-tts.ps1 -DownloadEspeak
& 'C:/Users/Admin/AppData/Local/Programs/Python/Python312/python.exe' scripts/voice-factory-synthesize.py --espeak 'scripts/voice-factory-output/espeak-ng-1.52.0/eSpeak NG/espeak-ng.exe'
& 'C:/Users/Admin/AppData/Local/Programs/Python/Python312/python.exe' scripts/voice-factory-waveform-check.py scripts/voice-factory-output/audio/manifest.json

# Exact fixed ru135, amplitude100 corpus. Failed commands remain failures.
./scripts/voice-factory-run.ps1 -Mode audio -RunLabel acceptance-audio-final
# Same complete WAVs, stop immediately after their last frame; no added silence.
./scripts/voice-factory-run.ps1 -Mode stop -RunLabel acceptance-stop-final

# Independent direct ASR/VAD evidence; no network, service restart or model download.
# Requires the existing local Maven/JDK Docker image and isolated app container.
./scripts/voice-factory-diagnose.ps1 -Label asr-ranges-final
```

Python 3.12 is intentional: its standard-library `audioop.ratecv` is used for 22050-to-16000 Hz resampling. No neural TTS weights are installed. The initial Windows inventory contained only English Zira; no Russian SAPI/OneCore voice was found. `ESPEAK_DATA_PATH` must reference the portable eSpeak directory; without it the extracted executable crashes on this machine.

The eSpeak MSI source is `https://github.com/espeak-ng/espeak-ng/releases/download/1.52.0/espeak-ng.msi`, SHA256 `7F673C709EA5DD579D3B5EBB98688CC575328A6AB7438D2BC405B88CEDAEAFB9`. The synthesis manifest records engine, voice, speed, waveform SHA256 and duration. Output under `scripts/voice-factory-output` is generated evidence, not source to commit.

## What Is Asserted

- Holdout text checks preserve literal punctuation/case and explicit invalid targets.
- Live tests copy a seeded isolated demo deck with the production library API and verify the source deck remains unchanged. They call the same `parseDeckVoice` and `executeDeckVoice` used by the editor, then independently GET and compare persisted scenes/plan. Literal text is also checked in live HTML.
- State assertions cover invalid-target no-write behavior, literal replacement/append, undo, style/geometry, element insertion/duplication/deletion, notes, background, and table header/body cells.
- Audio sends authenticated binary PCM at 512 samples per 32 ms. No text is injected into ASR, and no prefix or typo is repaired. All packets must be acknowledged. All events/transcripts are retained; warnings, resyncs, generation events, absent phrases or incomplete commands fail acceptance.
- ASR punctuation and spelled-versus-numeric 1/20/24 are normalized only for full-command comparison. Actual unmodified recognized text is parsed/executed. Expected kind, parameters and final persisted state are asserted separately.
- The supplied `text-command.wav` is optionally replayed read-only. Its two-utterance dictation flow uses the production textStart result, then forwards the next transcript literally to the production executor, asserting persisted text and live HTML. This is a harness adapter for dictation, not a browser microphone test.

## Evidence And Limits

Each report contains source/copy deck IDs, complete before/after state, transcript/action, all ASR events, fixture hash, raw timings and failures. Parser/executor timing is separate from ASR. Executor timing includes its real HTTP save; fresh-state GET is measured separately. p95 uses nearest rank and reports the 250 ms target honestly. Timing from setup text commands is not an ASR latency claim.

The Java diagnostic uses the installed production Models and Audio classes. It compares full PCM, native VAD segments, old heuristic cropping, candidate bounded 200 ms pre-roll/160 ms available post-roll, and actual Audio callbacks with speech time ranges. It also probes stop with zero appended silence. These offline candidate decodes are diagnostic evidence, not proof that production changed until the HTTP replay passes after restart.

Preserved reports `acceptance-audio.json` and `asr-ranges-baseline.json` expose the original failures. `acceptance-audio-ru-175.json` is an exploratory speed175/amplitude175/prefix600ms run, not a controlled before/after comparison; do not use it to claim improvement. Fixed-corpus comparisons use the original ru135 WAV hashes. `acceptance-audio-nocrop.json` records the first production change without heuristic cropping.

This proves synthetic PCM replay through local ASR where tests pass. Physical microphone capture, browser AudioWorklet/device behavior, human speakers, room noise, accent coverage and real microphone end-to-end latency remain NOT TESTED. Preview checks inspect saved production HTML, not rendered browser pixels or export fidelity. The original voice-to-slide/live generation smoke is performed separately by main.
