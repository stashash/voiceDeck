"""Decode the current narrated capture and bind media evidence to its SHA-256."""
from pathlib import Path
import hashlib
import json
import re
import shutil
import subprocess
import wave

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "artifacts/stage2-demo"
video = OUT / "screencast/VoiceDeck-stage2-screencast.mp4"
try:
    import imageio_ffmpeg
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
except ImportError:
    ffmpeg = shutil.which("ffmpeg")
if not ffmpeg:
    raise RuntimeError("Install imageio-ffmpeg in the recording environment or provide ffmpeg in PATH")

edit = json.loads((OUT / "screencast/edit-manifest.json").read_text(encoding="utf-8"))
audio_checks = []
for part in edit["timeline"]:
    clip = part["audio"]
    path = Path(clip["file"])
    assert hashlib.sha256(path.read_bytes()).hexdigest() == clip["sha256"]
    with wave.open(str(path), "rb") as stream:
        duration = stream.getnframes() / stream.getframerate()
        assert stream.getnframes() > 0 and stream.getnchannels() in (1, 2)
        assert abs(duration - clip["duration"]) < .05
    audio_checks.append({"clip": part["name"], "seconds": duration, "sha256": clip["sha256"]})

result = subprocess.run([ffmpeg, "-hide_banner", "-i", str(video), "-af", "volumedetect", "-f", "null", "-"],
                        capture_output=True, text=True)
assert result.returncode == 0, result.stderr[-3000:]
match = re.search(r"Duration: (\d+):(\d+):([\d.]+)", result.stderr)
assert match, "Missing video duration"
h, m, s = match.groups()
duration = int(h) * 3600 + int(m) * 60 + float(s)
assert 0 < duration <= 300 and abs(duration - edit["duration"]) < 1
assert "Video: h264" in result.stderr and "Audio: aac" in result.stderr and "1920x1080" in result.stderr
peak = float(re.search(r"max_volume: ([\-\d.]+) dB", result.stderr)[1])
mean = float(re.search(r"mean_volume: ([\-\d.]+) dB", result.stderr)[1])
assert mean > -60 and -30 < peak < 0, "Silent or clipped final audio"
subprocess.run([ffmpeg, "-v", "error", "-y", "-i", str(video), "-vf",
                "fps=1/25,scale=480:270,tile=2x4", "-frames:v", "1",
                str(OUT / "screencast/video-contact-sheet.jpg")], check=True)
evidence = {"file": str(video), "sha256": hashlib.sha256(video.read_bytes()).hexdigest(),
            "status": "passed", "fullDecode": "passed", "bytes": video.stat().st_size,
            "duration": duration, "videoCodec": "h264", "audioCodec": "aac", "width": 1920, "height": 1080,
            "meanVolumeDb": mean, "maxVolumeDb": peak, "audioClips": audio_checks, "humanListening": False}
(OUT / "presubmission-video-verification.json").write_text(json.dumps(evidence, indent=2), encoding="utf-8")
print(json.dumps({"status": "passed", "seconds": duration, "audioClips": len(audio_checks), "sha256": evidence["sha256"]}))
