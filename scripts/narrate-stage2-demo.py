"""Local-only Russian narration for the real Stage 2 UI recording."""
from pathlib import Path
import hashlib
import json
import os
import time
import gc
from importlib.metadata import version

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "artifacts/stage2-demo/screencast/audio"
OUT.mkdir(parents=True, exist_ok=True)
previous = json.loads((OUT / "manifest.json").read_text(encoding="utf-8")) if (OUT / "manifest.json").is_file() else {}
cached = {clip["name"]: clip for clip in previous.get("clips", [])}
os.environ["HF_HOME"] = os.environ.get("VOICEDECK_HF_HOME", r"C:/Users/Admin/dev/project/AsIsSber/.tools/qwen3-tts/hf-cache")
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
import numpy as np
import soundfile as sf
import torch
from qwen_tts import Qwen3TTSModel
torch.set_num_threads(1)

CLIPS = [
 ("intro", "Это реальный прогон VoiceDeck. Создадим презентацию по данным на неизвестном шаблоне из открытого источника."),
 ("template", "Загружаем PowerPoint. Шаблон не входит в набор задания. Сервис извлекает доступный стиль; готовые слайды образца не подставляются вместо нашего содержания."),
 ("brand", "Добавляем брендбук: цвета, шрифт Play, сетку, стиль диаграмм и логотип с охранным полем. При конфликте приоритет у брендбука."),
 ("content", "Передаём семь синтетических наборов: CSV, Excel, JSON и текст со встроенной таблицей. В брифе задаём контекст и просим сохранить единицы и период."),
 ("analysis-trend", "В Excel найдены шесть месяцев и выручка. Линия раскрывает динамику. От января к июню значение выросло со ста двадцати до ста пятидесяти шести тысяч долларов — на тридцать процентов."),
 ("analysis-shares", "В JSON три исхода обращений и общий итог — тысяча. Поэтому уместны доли: шестьдесят два, двадцать пять и тринадцать процентов."),
 ("analysis-comparison", "Здесь категории каналов и согласованные показатели факта и плана. Группы столбцов позволяют сравнить оба значения внутри каждого канала."),
 ("analysis-missing", "Пропуски не заменяются нулями. Для неполных пар сервис предлагает таблицу: так наблюдаемое значение восемь сохраняется, а отсутствующие значения остаются пустыми."),
 ("analysis-reference", "Справочник содержит двести одну строку. В основной части будет краткий обзор, а все строки без потерь попадут в приложение."),
 ("generate", "Запускаем генерацию трёх вариантов. Способ визуализации выбирается по данным; оформление определяется шаблоном и брендбуком."),
 ("waiting", "Ожидание локальной модели в этом фрагменте ускорено. Полная исходная запись и журнал времени сохранены рядом с роликом."),
 ("editor", "Презентация готова. Открываем редактор и проверяем содержательные слайды, источники и применённое оформление."),
 ("result-trend", "На временном ряду есть вывод о росте на тридцать процентов, подписи, валюта и источник. Сам вывод рассчитан по исходным значениям."),
 ("result-shares", "Для обращений показана структура долей. Заголовок сообщает основной результат, а цвет и шрифт согласованы с брендбуком."),
 ("result-comparison", "Сравнение каналов показывает факт и план отдельными рядами. Это сопоставление показателей, без произвольного суммирования и выдуманных причин."),
 ("result-missing", "В таблице видны и наблюдаемые нули, и пропуски. Известные значения сохранены; источник позволяет проверить их происхождение."),
 ("result-appendix", "Полный справочник вынесен после основной истории. Страницы содержат диапазоны строк, поэтому можно проверить полноту всех двухсот одной записи."),
 ("export", "Результат можно скачать в PowerPoint, PDF или HTML. Здесь скачиваем PDF прямо через интерфейс."),
 ("complete", "Этот прогон использовал неизвестный шаблон и брендбук. Отдельно подготовлены девять презентаций: три варианта на каждом из трёх выданных шаблонов. Все демонстрационные данные синтетические."),
]
INSTRUCTION = "Clear Russian documentary narrator, calm and conversational, precise diction, natural pauses, medium pace. No dramatic exaggeration."
model_path = os.environ.get("VOICEDECK_TTS_MODEL", r"C:/Users/Admin/dev/project/AsIsSber/.tools/qwen3-tts/models/VoiceDesign")
if not torch.cuda.is_available():
    raise RuntimeError("CUDA unavailable; CPU fallback is not enabled")
model = Qwen3TTSModel.from_pretrained(model_path, device_map="cuda:0", dtype=torch.bfloat16,
                                      attn_implementation="sdpa", local_files_only=True)
manifest = {"engine": "local Qwen3-TTS 1.7B VoiceDesign reference + Base stable narrator", "localOnly": True,
            "paidServicesUsed": False, "instruction": INSTRUCTION, "clips": [], "humanListening": "not assessed"}
manifest["runtime"] = {name: version(name) for name in ["torch", "transformers", "qwen-tts"]}
manifest["models"] = []
for provenance_file in ["model-provenance.json", "base-model-provenance.json"]:
    provenance_path = Path(model_path).parents[1] / provenance_file
    provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
    manifest["models"].append({key: provenance.get(key) for key in ["modelId", "revision", "source"]})
for index, (name, text) in enumerate(CLIPS):
    if index == 1:
        # A VoiceDesign seed does not preserve speaker identity across takes.
        # Reuse the locally synthesized intro as the Base narrator reference.
        del model
        gc.collect()
        torch.cuda.empty_cache()
        base_path = str(Path(model_path).parent / "Base")
        model = Qwen3TTSModel.from_pretrained(base_path, device_map="cuda:0", dtype=torch.bfloat16,
                                             attn_implementation="sdpa", local_files_only=True)
        reference = OUT / "intro.wav"
        prompt = model.create_voice_clone_prompt(ref_audio=str(reference), ref_text=CLIPS[0][1], x_vector_only_mode=False)
        manifest["syntheticReferenceSha256"] = hashlib.sha256(reference.read_bytes()).hexdigest()
    path = OUT / (name + ".wav")
    saved = cached.get(name, {})
    valid_cache = (path.is_file() and saved.get("text") == text and previous.get("instruction") == INSTRUCTION
                   and saved.get("sha256") == hashlib.sha256(path.read_bytes()).hexdigest())
    if valid_cache:
        audio, rate = sf.read(path, dtype="float32")
        elapsed = None
    else:
        if path.is_file():
            history = OUT / "previous"
            history.mkdir(exist_ok=True)
            path.replace(history / (name + "-" + hashlib.sha256(path.read_bytes()).hexdigest()[:12] + ".wav"))
        torch.manual_seed(20261019 + index)
        start = time.monotonic()
        with torch.inference_mode():
            if index == 0:
                waves, rate = model.generate_voice_design(text=text, language="Russian", instruct=INSTRUCTION,
                                                           temperature=.65, top_p=.9, repetition_penalty=1.05, max_new_tokens=1200)
            else:
                waves, rate = model.generate_voice_clone(text=text, language="Russian", voice_clone_prompt=prompt,
                                                          temperature=.65, top_p=.9, repetition_penalty=1.05, max_new_tokens=1200)
        audio = np.asarray(waves[0], dtype=np.float32)
        if audio.ndim != 1 or not np.isfinite(audio).all() or len(audio) < rate:
            raise RuntimeError("Invalid audio: " + name)
        audio *= min(1., .89 / max(float(np.max(np.abs(audio))), 1e-9))
        audio = np.concatenate([audio, np.zeros(round(.5 * rate), dtype=np.float32)])
        sf.write(path, audio, rate, subtype="PCM_16")
        elapsed = time.monotonic() - start
    record = {"name": name, "text": text, "file": str(path), "duration": len(audio) / rate,
              "sampleRate": rate, "generationSeconds": elapsed, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
    manifest["clips"].append(record)
    (OUT / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"clip": name, "seconds": record["duration"]}), flush=True)
