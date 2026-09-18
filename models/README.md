# Локальные модели

Модели не загружаются при запуске приложения. Скопируйте проверенные файлы в эту папку, затем создайте `config.json` по примеру `docs/models.example.json` (пути внутри Docker начинаются с `/models`).

* `vad`: Silero VAD ONNX, окно 512 сэмплов, 16 кГц.
* `partial`: совместимая с sherpa-onnx модель `nemo_ctc` (GigaAM CTC) и её `tokens.txt`.
* `final`: необязательная совместимая `transducer`-модель с encoder, decoder, joiner и tokens. При отсутствии используется CTC; нормализация и пунктуация не обещаются.
* FRIDA: экспорт **T5EncoderModel** в ONNX с int64 `input_ids`, `attention_mask`, выходом float32 `last_hidden_state` `[1,tokens,dimension]`. Также нужен локальный `tokenizer.json`. Приложение использует `categorize_topic: `, CLS pooling, L2-нормализацию и максимум 512 токенов. FP16-выход надо привести к FP32 при экспорте. Экспорт с external data должен включать файлы внешних весов.

Для JNI установите оба JAR одной версии в `native/`:

```sh
docker run --rm -v "${PWD}/native:/native" -w /native maven:3.9.9-eclipse-temurin-21 mvn dependency:copy-dependencies -DoutputDirectory=/native
```

В контейнере нужны библиотеки **Linux x64**, даже если хост Windows. Для запуска Java непосредственно в Windows передайте `-Dnative.platform=win-x64`. Используйте проверенный внутренний Maven mirror в закрытом контуре. Если конкретный релиз недоступен в JitPack, соберите JVM и native-артефакты из одного тега официального репозитория и положите JAR сюда вручную.

Совместимость конкретных весов GigaAM-v3 e2e-RNNT с выбранной версией sherpa требует проверки: обычный PyTorch checkpoint не является готовой ONNX-моделью для этого API. До успешной проверки используйте CTC для обеих ветвей. `MODE=live` прекращает запуск при несовместимых моделях и выполняет два прогревочных прогона до readiness.

Источники интерфейсов: [sherpa Java](https://k2-fsa.github.io/sherpa/onnx/java-api/non-android-java.html), [FRIDA model card](https://huggingface.co/ai-forever/FRIDA). Контрольная запись для проверки WER и задержек должна быть вашей; приложение не подменяет её синтетическими метриками.
