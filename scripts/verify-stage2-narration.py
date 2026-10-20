"""Offline ASR and decoded-waveform checks; does not claim human listening."""
from pathlib import Path
import array
import hashlib
import json
import os
import re
import sys
import wave

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"artifacts/stage2-demo/screencast/audio"
STUDIO=Path(os.environ.get("VOICEDECK_VOICE_STUDIO",r"C:/Users/Admin/dev/project/AsIsSber"))
sys.path.insert(0,str(STUDIO/".tools/audio-transcription/python"))
os.environ["HF_HUB_OFFLINE"]="1"
from faster_whisper import WhisperModel
import av
original_open=av.open
def compatible_open(*args,**kwargs):
    kwargs.pop("metadata_errors",None)
    return original_open(*args,**kwargs)
av.open=compatible_open
model=WhisperModel(str(STUDIO/".tools/audio-transcription/models/models--Systran--faster-whisper-small/snapshots/536b0662742c02347bc0e980a01041f333bce120"),
                   device="cpu",compute_type="int8",cpu_threads=6,local_files_only=True)
manifest=json.loads((OUT/"manifest.json").read_text(encoding="utf-8"))
def words(s):return re.findall(r"[а-яa-z0-9]+",s.lower().replace("ё","е"))
def distance(a,b):
    row=list(range(len(b)+1))
    for i,x in enumerate(a,1):
        following=[i]
        for j,y in enumerate(b,1):following.append(min(following[-1]+1,row[j]+1,row[j-1]+(x!=y)))
        row=following
    return row[-1]
records=[]
for clip in manifest["clips"]:
    path=Path(clip["file"])
    with wave.open(str(path),"rb") as stream:
        assert stream.getsampwidth()==2 and stream.getnchannels()==1
        samples=array.array("h",stream.readframes(stream.getnframes()))
        duration=len(samples)/stream.getframerate()
    assert samples and max(abs(s) for s in samples)>0 and not any(s in (-32768,32767) for s in samples)
    assert hashlib.sha256(path.read_bytes()).hexdigest()==clip["sha256"]
    segments,_=model.transcribe(str(path),language="ru",beam_size=5,vad_filter=True,condition_on_previous_text=False)
    transcript=" ".join(s.text.strip() for s in segments)
    edits=distance(words(clip["text"]),words(transcript))
    record={"name":clip["name"],"expected":clip["text"],"transcript":transcript,"duration":duration,
            "wordEdits":edits,"expectedWords":len(words(clip["text"])),"peak":max(abs(s) for s in samples)/32768,
            "technicalCheck":"passed","speechCheck":"ASR exact" if edits==0 else "Review transcript; ASR may differ"}
    records.append(record)
    (OUT/"asr-verification.json").write_text(json.dumps({"engine":"faster-whisper-small CPU int8 offline","humanListening":False,
            "clips":records,"note":"ASR flags pronunciation/content discrepancies; it does not establish naturalness or certify speech."},ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps({"name":clip["name"],"wordEdits":edits,"duration":duration}),flush=True)
