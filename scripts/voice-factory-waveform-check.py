"""Verify the audio sent to ASR equals the documented offline resampling, without truncation."""
import argparse
import audioop
import hashlib
import json
from pathlib import Path
import wave


def read(file):
    with wave.open(str(file), "rb") as stream:
        assert stream.getnchannels() == 1 and stream.getsampwidth() == 2
        return stream.getframerate(), stream.readframes(stream.getnframes())


parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("manifest", type=Path)
args = parser.parse_args()
manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
rows = []
for case in manifest["cases"]:
    file = Path(case["wav"])
    source_rate, source = read(file.with_name(file.stem + "-source.wav"))
    rate, pcm = read(file)
    converted, _ = audioop.ratecv(source, 2, 1, source_rate, 16000, None)
    expected = bytes(manifest.get("leadingSilenceMs", 0) * 32) + converted
    assert rate == 16000 and pcm == expected
    assert hashlib.sha256(file.read_bytes()).hexdigest() == case["sha256"]
    samples = [int.from_bytes(pcm[i:i + 2], "little", signed=True) for i in range(0, len(pcm), 2)]
    nonzero = [i for i, value in enumerate(samples) if abs(value) > 32]
    rows.append({"id": case["id"], "sourceRate": source_rate, "targetRate": rate,
                 "sourceSamples": len(source) // 2, "targetSamples": len(samples),
                 "sourceDurationMs": len(source) * 500 / source_rate,
                 "targetDurationMs": len(pcm) / 32, "exactDocumentedResampling": True,
                 "firstSignalMs": nonzero[0] / 16, "lastSignalMs": nonzero[-1] / 16,
                 "rmsPcm16": audioop.rms(pcm, 2), "peakPcm16": audioop.max(pcm, 2),
                 "replayPacketsWithTrailingSilence": (len(pcm) + 32000 + 1023) // 1024})
report = args.manifest.parent / "waveform-check.json"
report.write_text(json.dumps({"result": "PASS", "cases": rows}, indent=2), encoding="utf-8")
print(report)
