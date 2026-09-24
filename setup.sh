#!/usr/bin/env bash
# Мастер установки voiceDeck для macOS: Docker, модель, веса распознавания речи, .env, запуск стека.
# Запуск из корня репозитория: ./setup.sh
# Без вопросов: VD_MODEL=lmstudio|api|none VD_YES=1 [VD_API_URL=... VD_API_MODEL=... VD_API_KEY=...] ./setup.sh
# Написан под bash 3.2, который стоит в macOS.
set -euo pipefail
cd "$(dirname "$0")"
ROOT="$(pwd)"

APP_URL=http://localhost:8088
QWEN=qwen/qwen3.8-27b
BGE_URL=https://huggingface.co/lm-kit/bge-m3-gguf/blob/main/bge-m3-Q8_0.gguf
MODEL="${VD_MODEL:-}"
API_URL="${VD_API_URL:-}"
API_MODEL="${VD_API_MODEL:-}"
API_KEY="${VD_API_KEY:-}"
YES="${VD_YES:-}"
OS="$(uname -s)"

step() { printf '\n\033[36m[%s/6] %s\033[0m\n' "$1" "$2"; }
ok() { printf '  \033[32mготово: %s\033[0m\n' "$1"; }
note() { printf '  \033[33m%s\033[0m\n' "$1"; }
die() {
  printf '\n  \033[31mОстановлено: %s\033[0m\n' "$1"
  printf '  Исправьте и запустите ./setup.sh снова: сделанные шаги он пропустит.\n'
  exit 1
}
confirm() {
  [ -n "$YES" ] && return 0
  printf '  %s [Д/н] ' "$1"
  read -r answer
  case "$answer" in ""|д|Д|да|Да|y|Y|yes) return 0 ;; *) return 1 ;; esac
}
have() { command -v "$1" >/dev/null 2>&1; }
wait_for() {
  local seconds=$1; shift
  local end=$(( $(date +%s) + seconds ))
  while [ "$(date +%s)" -lt "$end" ]; do
    if "$@" >/dev/null 2>&1; then return 0; fi
    sleep 3
  done
  return 1
}
find_lms() {
  if have lms; then command -v lms
  elif [ -x "$HOME/.lmstudio/bin/lms" ]; then echo "$HOME/.lmstudio/bin/lms"
  else return 1; fi
}
brew_install() {
  have brew || die "нет Homebrew (https://brew.sh): поставьте $2 вручную и запустите мастер снова"
  confirm "Поставить $2 через Homebrew?" || die "без $2 этот путь не работает"
  brew install --cask "$1" || die "Homebrew не поставил $2"
}
sha256() { if have shasum; then shasum -a 256 "$1"; else sha256sum "$1"; fi | awk '{print toupper($1)}'; }
fetch() {
  local dest="$ROOT/$1"
  mkdir -p "$(dirname "$dest")"
  if [ ! -f "$dest" ]; then
    echo "  Скачиваю $1"
    curl -fsSL "$2" -o "$dest.part" || die "не скачался $1"
    mv "$dest.part" "$dest"
  fi
  [ "$(sha256 "$dest")" = "$3" ] || { rm -f "$dest"; die "контрольная сумма не совпала: $1"; }
}
# .env: меняется строка KEY= или дописывается новая, остальные строки остаются.
set_env() {
  local file="$ROOT/.env" tmp
  [ -f "$file" ] || cp "$ROOT/.env.example" "$file"
  tmp="$(mktemp)"
  awk -v k="$1" -v v="$2" 'index($0, k "=") == 1 { print k "=" v; done = 1; next } { print } END { if (!done) print k "=" v }' "$file" > "$tmp"
  mv "$tmp" "$file"
}
http_ok() { curl -fsS --max-time 5 "$@" >/dev/null; }

echo 'Мастер установки voiceDeck'
echo 'Шаги: Docker, модель, веса распознавания речи, настройки, запуск, проверка. Повторный запуск пропускает сделанное.'

# ---------- 1. Docker ----------
step 1 'Docker Desktop'
if ! have docker; then
  note 'Docker Desktop не найден.'
  [ "$OS" = Darwin ] || die 'поставьте Docker Engine и docker compose: https://docs.docker.com/engine/install/'
  brew_install docker-desktop 'Docker Desktop'
fi
if ! docker info >/dev/null 2>&1; then
  if [ "$OS" = Darwin ]; then
    open -a Docker || true
    note 'Запускаю Docker Desktop. При первом запуске примите соглашение в его окне. Жду до 5 минут.'
  fi
  wait_for 300 docker info || die 'Docker не отвечает: откройте Docker Desktop и дождитесь надписи Engine running'
fi
docker compose version >/dev/null 2>&1 || die 'нет docker compose: обновите Docker'
ok 'Docker работает'

# ---------- 2. Модель ----------
step 2 'Модель'
while [ -z "$MODEL" ]; do
  echo '  1  LM Studio на этой машине: Qwen3.8 27B и bge-m3, около 18 ГБ, нужен Mac на Apple Silicon от 32 ГБ памяти'
  echo '  2  Внешний OpenAI-совместимый API с Qwen3.8 27B, например инференс VK'
  echo '  3  Без модели: готовые дизайн-системы и презентации, правка текста, скачивание'
  printf '  Выберите 1, 2 или 3: '
  read -r choice
  case "$choice" in 1) MODEL=lmstudio ;; 2) MODEL=api ;; 3) MODEL=none ;; esac
done

if [ "$MODEL" = lmstudio ]; then
  if [ "$OS" = Darwin ]; then
    [ "$(uname -m)" = arm64 ] || die 'LM Studio для macOS работает только на Apple Silicon: выберите внешний API'
    memory_gb=$(( $(sysctl -n hw.memsize) / 1073741824 ))
    if [ "$memory_gb" -lt 32 ]; then
      note "Памяти $memory_gb ГБ: Qwen3.8 27B может не поместиться."
      confirm 'Продолжить с LM Studio?' || die 'выберите внешний API или режим без модели'
    else
      ok "память $memory_gb ГБ"
    fi
    if ! find_lms >/dev/null; then
      [ -d '/Applications/LM Studio.app' ] || brew_install lm-studio 'LM Studio'
      open -a 'LM Studio' || true
      note 'Открываю LM Studio: при первом запуске он кладёт команду lms. Жду до 3 минут.'
      wait_for 180 find_lms || die 'не появилась команда lms: откройте LM Studio вручную один раз'
    fi
  else
    find_lms >/dev/null || die 'поставьте LM Studio (https://lmstudio.ai) и откройте его один раз'
    note 'На Linux контейнеры ходят на хост не через 127.0.0.1: сервер LM Studio слушает 0.0.0.0 и виден локальной сети.'
    export LMS_SERVER_HOST=0.0.0.0
  fi
  LMS="$(find_lms)"
  "$LMS" server start
  note 'Скачиваю модели, если их ещё нет. Qwen3.8 27B весит около 17 ГБ.'
  "$LMS" get "$QWEN" -y || die "не скачалась $QWEN"
  "$LMS" get "$BGE_URL" -y || die 'не скачались эмбеддинги bge-m3'
  "$LMS" unload --all
  "$LMS" load "$QWEN" --gpu max -c 20480 --parallel 4 -y || die "$QWEN не загрузилась"
  "$LMS" load text-embedding-bge-m3 --identifier text-embedding-bge-m3 -y || die 'bge-m3 не загрузилась'
  set_env DESIGNER_LLM_URL http://host.docker.internal:1234/v1
  set_env DESIGNER_LLM_MODEL "$QWEN"
  set_env DESIGNER_LLM_API_KEY ''
  set_env EMBEDDING_BACKEND ollama
  set_env EMBEDDING_URL http://host.docker.internal:1234/v1
  set_env EMBEDDING_MODEL text-embedding-bge-m3
  ok 'LM Studio с Qwen3.8 27B и bge-m3'
elif [ "$MODEL" = api ]; then
  if [ -z "$API_URL" ]; then printf '  Адрес API, например https://example.com/v1: '; read -r API_URL; fi
  if [ -z "$API_MODEL" ]; then printf '  Имя модели [%s]: ' "$QWEN"; read -r API_MODEL; fi
  [ -n "$API_MODEL" ] || API_MODEL="$QWEN"
  if [ -z "$API_KEY" ] && [ -z "$YES" ]; then printf '  Ключ API (Enter, если ключ не нужен): '; read -rs API_KEY; echo; fi
  API_URL="${API_URL%/}"
  if [ -n "$API_KEY" ]; then probe_ok() { http_ok -H "Authorization: Bearer $API_KEY" "$API_URL/models"; }
  else probe_ok() { http_ok "$API_URL/models"; }; fi
  if probe_ok; then ok "API отвечает: $API_URL"
  else note "API не ответил на $API_URL/models. Проверьте адрес и ключ; настройки всё равно запишу."; fi
  # Сервис работает в контейнере: localhost там свой, адрес хоста называется host.docker.internal.
  container_url="$(printf '%s' "$API_URL" | sed -E 's#//(localhost|127\.0\.0\.1)([:/])#//host.docker.internal\2#')"
  set_env DESIGNER_LLM_URL "$container_url"
  set_env DESIGNER_LLM_MODEL "$API_MODEL"
  set_env DESIGNER_LLM_API_KEY "$API_KEY"
  set_env EMBEDDING_BACKEND disabled
  note 'Эмбеддинги для Live берутся только из локальной сети: границы мыслей в речи пойдут по паузам.'
else
  set_env EMBEDDING_BACKEND disabled
  ok 'без модели: генерация и Live заработают, когда модель подключат и запустят мастер снова'
fi

# ---------- 3. Веса распознавания речи ----------
step 3 'Веса распознавания речи'
RELEASE=https://github.com/k2-fsa/sherpa-onnx/releases/download
HF=https://huggingface.co/Xenova/paraphrase-multilingual-MiniLM-L12-v2/resolve/2c4055b12046f11709e9df2c122e59ffbdc2f900
# Контейнеры на Apple Silicon собираются под arm64: библиотека распознавания нужна той же архитектуры.
case "$(uname -m)" in
  arm64|aarch64) NATIVE=linux-aarch64; NATIVE_SHA=5123D2E48AE1A7CE82BA89CE153906C651BF418A63DB2F7DFF82265E6D49C104 ;;
  *) NATIVE=linux-x64; NATIVE_SHA=30C93B59381113F9C20AEDBBF9FC1AD399158F6BC03DDDC0F8934A6E28E069BA ;;
esac
fetch native/sherpa-onnx-jvm-1.13.8.jar "$RELEASE/v1.13.8/sherpa-onnx-jvm-1.13.8.jar" 77B7B047FADE4EADADA96B568EB92615049AAF1DC317C7244E46C1EA38B9A63B
fetch "native/sherpa-onnx-native-lib-$NATIVE-1.13.8.jar" "$RELEASE/v1.13.8/sherpa-onnx-native-lib-$NATIVE-1.13.8.jar" "$NATIVE_SHA"
fetch models/vad/silero_vad.onnx "$RELEASE/asr-models/silero_vad.onnx" 9E2449E1087496D8D4CABA907F23E0BD3F78D91FA552479BB9C23AC09CBB1FD6
fetch models/gigaam.tar.bz2 "$RELEASE/asr-models/sherpa-onnx-nemo-ctc-punct-giga-am-v3-russian-2025-12-16.tar.bz2" 20E41E160EFA6F2460A7EF6554CDBBB9E8FFFB2B92E6BC708E9406BD8B9256EA
fetch models/semantic/model.onnx "$HF/onnx/model_quantized.onnx" 66FC00F5F29AFCAFF34092E1BDD20008CA3918265A82FB9695A551E510CC4EBC
fetch models/semantic/tokenizer.json "$HF/tokenizer.json" B60B6B43406A48BF3638526314F3D232D97058BC93472FF2DE930D43686FA441
if [ ! -f models/sherpa-onnx-nemo-ctc-punct-giga-am-v3-russian-2025-12-16/model.int8.onnx ]; then
  tar -xjf models/gigaam.tar.bz2 -C models || die 'не распаковалась модель GigaAM'
fi
[ -f models/config.json ] || cp docs/live-models.json models/config.json
ok 'GigaAM-v3, Silero VAD, sherpa-onnx'

# ---------- 4. Настройки ----------
step 4 'Настройки в .env'
set_env MODE live
set_env SLIDE_MODE designer
ok '.env записан'

# ---------- 5. Запуск ----------
step 5 'Сборка и запуск контейнеров'
note 'Первая сборка идёт несколько минут.'
docker compose up --build -d || die 'docker compose не поднял стек'

# ---------- 6. Проверка ----------
step 6 'Проверка'
wait_for 600 http_ok http://127.0.0.1:8090/health || die 'сервис designer не ответил: docker compose logs designer'
wait_for 300 http_ok http://127.0.0.1:8088/health || die 'сервис app не ответил: docker compose logs app'
systems=$(curl -fsS http://127.0.0.1:8090/design-systems | sed -n 's/.*"ids":\[\([^]]*\)\].*/\1/p' | tr ',' '\n' | grep -c . || true)
decks=$(curl -fsS http://127.0.0.1:8090/decks | grep -o '"design_system_id"' | wc -l | tr -d ' ')
ok "дизайн-систем: $systems, презентаций: $decks"
if curl -fsS http://127.0.0.1:8090/health | grep -q '"model_ok":true'; then
  ok 'модель отвечает: генерация и Live доступны'
elif [ "$MODEL" != none ]; then
  note 'Модель пока не отвечает: проверьте LM Studio или API. Просмотр и скачивание работают.'
fi

echo
printf '\033[32mvoiceDeck работает: %s\033[0m\n' "$APP_URL"
echo '  Остановить: docker compose stop. Запустить снова: docker compose start.'
if [ "$MODEL" = lmstudio ]; then echo '  После перезагрузки компьютера запустите ./setup.sh снова: он загрузит модели в LM Studio и поднимет стек.'; fi
if [ -z "$YES" ]; then
  if have open; then open "$APP_URL"; elif have xdg-open; then xdg-open "$APP_URL"; fi
fi
