# Публичный доступ к локальному VoiceDeck

Эта схема публикует VoiceDeck с компьютера через HTTPS. Для постоянного
бесплатного адреса используется закреплённый dev-домен ngrok. Временный
`*.trycloudflare.com` остаётся запасным вариантом. Порты роутера и Windows
открывать не требуется.

Снаружи используется один адрес. Nginx направляет запросы приложения в `app`,
а запросы `/designer/*` — в `designer`. Это сохраняет единый origin для UI,
API, изображений слайдов и WebSocket голосового режима.

## Требования

- Windows 11 и PowerShell;
- запущенный Docker Desktop;
- настроенный VoiceDeck (`setup.cmd` уже выполнен);
- запущенные локальные модели, если нужны генерация и голосовое управление;
- исходящие HTTPS- и QUIC-соединения не заблокированы сетью.

## Постоянный бесплатный адрес через ngrok

Создайте бесплатный аккаунт ngrok и закрепите dev-домен в разделе `Domains`.
В локальный `.env` добавьте адрес и токен, полученный через `Show authtoken`:

```env
PUBLIC_DEMO_URL=https://example.ngrok-free.dev
NGROK_AUTHTOKEN=secret-token
```

`.env` исключён из Git. Не добавляйте токен в compose-файл, документацию,
команды CI или сообщения.

Запуск и перезапуск всего публичного контура:

```powershell
docker compose -f compose.yaml -f compose.public-demo.yaml --profile ngrok up -d --build
```

Проверка:

```powershell
$publicUrl = (Select-String -Path .env -Pattern '^PUBLIC_DEMO_URL=').Line.Split('=', 2)[1]
Invoke-RestMethod "$publicUrl/health" -Headers @{
  Origin = $publicUrl
  'ngrok-skip-browser-warning' = '1'
}
docker compose -f compose.yaml -f compose.public-demo.yaml --profile ngrok ps
```

Откройте `$publicUrl/#/voice-editor`. Бесплатный ngrok показывает каждому
новому посетителю одноразовую защитную страницу: нужно проверить адрес и нажать
`Visit Site`. После этого UI, API и WebSocket работают на том же origin.

Остановить внешний доступ:

```powershell
docker compose -f compose.yaml -f compose.public-demo.yaml --profile ngrok stop stable-tunnel
```

Контейнер имеет `restart: unless-stopped`, поэтому после обычного перезапуска
Docker адрес не меняется и туннель поднимается автоматически. Если контейнер
был явно остановлен командой выше, запустите его через `up -d`.

## Временный адрес через Cloudflare Quick Tunnel

## Первый запуск

Откройте PowerShell в корне репозитория.

```powershell
# 1. Собрать приложение для работы через единый reverse proxy.
$env:PUBLIC_DEMO_URL = 'http://localhost:8087'
docker compose -f compose.yaml -f compose.public-demo.yaml up -d --build app designer public-proxy

# 2. Создать временный публичный туннель.
docker run -d --name voicedeck-public-tunnel --restart unless-stopped `
  cloudflare/cloudflared:latest tunnel --no-autoupdate `
  --url http://host.docker.internal:8087

# 3. Получить выданный Cloudflare адрес.
Start-Sleep -Seconds 5
$tunnelLog = docker logs voicedeck-public-tunnel 2>&1 | Out-String
$match = [regex]::Matches($tunnelLog, 'https://[a-z0-9-]+\.trycloudflare\.com')
if ($match.Count -eq 0) { throw 'Cloudflare не выдал публичный URL. Проверьте docker logs voicedeck-public-tunnel' }
$publicUrl = $match[$match.Count - 1].Value
$publicUrl

# 4. Разрешить точный публичный origin в backend и designer.
$env:PUBLIC_DEMO_URL = $publicUrl
docker compose -f compose.yaml -f compose.public-demo.yaml up -d --force-recreate app designer public-proxy
```

Откройте голосовой редактор:

```powershell
Start-Process "$publicUrl/#/voice-editor"
```

При первом включении микрофона браузер запросит разрешение. Разрешение нужно
выдать для публичного HTTPS-адреса, а не только для `localhost`.

## Проверка перед отправкой ссылки

```powershell
# Контейнеры приложения должны быть в состоянии Up.
docker compose -f compose.yaml -f compose.public-demo.yaml ps
docker ps --filter name=voicedeck-public-tunnel

# Backend должен вернуть status=ready и mode=live.
Invoke-RestMethod "$publicUrl/health" -Headers @{ Origin = $publicUrl }

# Designer должен отвечать через тот же адрес.
Invoke-RestMethod "$publicUrl/designer/health" -Headers @{ Origin = $publicUrl }
```

Затем откройте ссылку в приватном окне или на телефоне через мобильный интернет.
Проверьте загрузку списка презентаций, открытие голосового редактора, разрешение
на микрофон и выполнение одной команды редактирования.

## Повторный запуск

Если контейнер туннеля существует и был только остановлен:

```powershell
docker start voicedeck-public-tunnel
Start-Sleep -Seconds 5
$tunnelLog = docker logs voicedeck-public-tunnel 2>&1 | Out-String
$match = [regex]::Matches($tunnelLog, 'https://[a-z0-9-]+\.trycloudflare\.com')
$publicUrl = $match[$match.Count - 1].Value
$env:PUBLIC_DEMO_URL = $publicUrl
docker compose -f compose.yaml -f compose.public-demo.yaml up -d --force-recreate app designer public-proxy
$publicUrl
```

После перезапуска или пересоздания Quick Tunnel URL может измениться. Всегда
берите последний адрес из логов и повторно запускайте шаг с
`PUBLIC_DEMO_URL`, иначе защита origin заблокирует браузерные команды и
WebSocket.

Для создания полностью нового туннеля сначала удалите старый контейнер:

```powershell
docker rm -f voicedeck-public-tunnel
```

После этого повторите первый запуск со второго шага.

## Остановка

Закрыть внешний доступ, не останавливая VoiceDeck:

```powershell
docker stop voicedeck-public-tunnel
```

Остановить также публичный reverse proxy:

```powershell
docker compose -f compose.yaml -f compose.public-demo.yaml stop public-proxy
```

## Ограничения и безопасность

- Quick Tunnel предназначен для демонстрации и не имеет гарантии доступности.
- Ссылка публичная. В VoiceDeck пока нет полноценной учётной записи и контроля
  доступа, поэтому ссылку следует передавать только проверяющим.
- Не публикуйте `.env`, ключи API, токены моделей и содержимое Docker volumes.
- Компьютер, Docker Desktop, интернет и локальные серверы моделей должны
  оставаться включёнными весь период демонстрации.
- Для постоянного адреса и эксплуатации после демонстрации нужен Cloudflare
  Named Tunnel с доменом и аутентификацией доступа.

## Диагностика

```powershell
docker logs --tail 100 voicedeck-public-tunnel
docker compose -f compose.yaml -f compose.public-demo.yaml logs --tail 100 app designer public-proxy
```

`502 Bad Gateway` сразу после запуска обычно означает, что Java backend ещё
загружает ASR-модели. Подождите 10–20 секунд и повторите `/health`. Если UI
открывается, но голосовая команда не отправляется, проверьте, что текущий URL
совпадает с `PUBLIC_DEMO_URL`, и пересоздайте три сервиса командой из шага 4.
