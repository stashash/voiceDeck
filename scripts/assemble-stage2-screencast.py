"""Edit the genuine Playwright capture with measured local narration; never synthesize UI."""
from pathlib import Path
import json
import subprocess
import wave
import imageio_ffmpeg

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "artifacts/stage2-demo/screencast"
FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()
capture = json.loads((OUT / "capture-manifest.json").read_text(encoding="utf-8"))
narration = json.loads((OUT / "audio/manifest.json").read_text(encoding="utf-8"))
if capture.get("status") != "passed" or capture.get("browserErrors"):
    raise RuntimeError("Only a successful actual browser run can be published")
stages = capture["stages"]
def time_of(name, **match):
    return next(s["seconds"] for s in stages if s["name"] == name and all(s.get(k) == v for k,v in match.items()))
def interval(start, end):
    return (start, max(start + .2, end))
windows = {
    "intro": interval(0, time_of("home")),
    "template": interval(time_of("home"), time_of("template-upload-end")),
    "brand": interval(time_of("template-upload-end"), time_of("brandbook-applied")),
    "content": interval(time_of("brandbook-applied"), time_of("analysis-ready")),
}
previous = time_of("analysis-ready")
for clip, file in [("analysis-trend","time_series.xlsx"),("analysis-shares","category_shares.json"),
                   ("analysis-comparison","category_comparison.csv"),("analysis-missing","missing_zero.csv"),
                   ("analysis-reference","reference_201.csv")]:
    end = time_of("analysis-dataset", file=file)
    windows[clip] = interval(previous, end)
    previous = end
windows["generate"] = interval(previous, time_of("generation-wait-start"))
windows["waiting"] = interval(time_of("generation-wait-start"), time_of("generation-wait-end"))
windows["editor"] = interval(time_of("generation-wait-end"), time_of("editor-ready"))
previous = time_of("editor-ready")
for name in ["trend","shares","comparison","missing","appendix"]:
    end = time_of("result-slide", kind=name)
    windows["result-"+name] = interval(previous, end)
    previous = end
windows["export"] = interval(previous, time_of("complete")-1)
windows["complete"] = interval(time_of("complete")-1, time_of("complete"))
sources={}

def run(args):
    result = subprocess.run([FFMPEG,"-hide_banner","-loglevel","error","-y",*args],cwd=OUT,capture_output=True,text=True)
    if result.returncode:
        raise RuntimeError(result.stderr[-5000:])

def stamp(seconds):
    millis=round(seconds*1000)
    return f"{millis//3600000:02}:{millis//60000%60:02}:{millis//1000%60:02},{millis%1000:03}"

parts = OUT / "edit"
parts.mkdir(exist_ok=True)
timeline=[]
subtitles=[]
elapsed=0.
for index, clip in enumerate(narration["clips"]):
    name=clip["name"]
    start,end=windows[name]
    with wave.open(clip["file"],"rb") as stream:
        audio_length=stream.getnframes()/stream.getframerate()
    duration=audio_length+.45
    source_duration=end-start
    # Preserve normal actions. Hold the last actual frame when narration needs more time.
    speed=min(1.,duration/source_duration)
    filters=f"setpts={speed:.8f}*(PTS-STARTPTS),fps=24,scale=1920:1080,tpad=stop_mode=clone:stop_duration={duration:.4f}"
    if name=="waiting":
        filters+=",drawbox=x=30:y=30:w=920:h=60:color=black@0.78:t=fill,drawtext=fontfile='../../../designer/fonts/Play-Regular.ttf':text='Ожидание локальной модели ускорено':x=48:y=43:fontsize=32:fontcolor=white"
    target=parts/f"{index:02}-{name}.mp4"
    raw_source=sources.get(name,capture["rawVideo"])
    run(["-ss",str(start),"-t",str(source_duration),"-i",raw_source,"-i",clip["file"],
         "-vf",filters,"-af","apad","-t",str(duration),"-c:v","libx264","-preset","fast","-crf","20",
         "-pix_fmt","yuv420p","-c:a","aac","-ar","48000","-ac","2",str(target)])
    words=clip["text"].split()
    chunks=[" ".join(words[i:i+8]) for i in range(0,len(words),8)]
    for j,chunk in enumerate(chunks):
        a=elapsed+audio_length*j/len(chunks)
        b=elapsed+audio_length*(j+1)/len(chunks)
        subtitles.append(f"{len(subtitles)+1}\n{stamp(a)} --> {stamp(b)}\n{chunk}\n")
    timeline.append({"name":name,"sourceVideo":raw_source,"sourceStart":start,"sourceEnd":end,"outputStart":elapsed,
                     "outputDuration":duration,"sourcePlaybackFactor":1/speed,"audio":clip})
    elapsed+=duration
    print(f"{name}: {duration:.1f}s",flush=True)
if elapsed>300:
    raise RuntimeError(f"Narration exceeds the five-minute limit: {elapsed:.1f}s")
(OUT/"subtitles.srt").write_text("\n".join(subtitles),encoding="utf-8")
(parts/"concat.txt").write_text("\n".join(f"file '{i:02}-{c['name']}.mp4'" for i,c in enumerate(narration["clips"])),encoding="utf-8")
run(["-f","concat","-safe","0","-i",str(parts/"concat.txt"),"-c","copy",str(OUT/"narrated-unsubtitled.mp4")])
run(["-i",str(OUT/"narrated-unsubtitled.mp4"),"-vf","subtitles=subtitles.srt:fontsdir=../../../designer/fonts:force_style='Fontname=Play,Fontsize=19,Outline=2,MarginV=26'",
     "-c:v","libx264","-preset","fast","-crf","20","-c:a","copy","-movflags","+faststart",str(OUT/"VoiceDeck-stage2-screencast.mp4")])
manifest={"actualUiCapture":True,"networkMocks":False,"narrationLocalOnly":True,"duration":elapsed,
          "sourceVideo":capture["rawVideo"],"timeline":timeline,"longWaitCompressed":True,
          "generationWaitSeconds":windows["waiting"][1]-windows["waiting"][0],
          "finalVideo":str(OUT/"VoiceDeck-stage2-screencast.mp4")}
(OUT/"edit-manifest.json").write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding="utf-8")
print(manifest["finalVideo"])
