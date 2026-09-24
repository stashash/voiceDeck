# Русская речь для проверки живого режима без микрофона: голос Windows, WAV 16 кГц, моно, 16 бит.
# Запуск: pwsh scripts/speech-sample.ps1 [-Out путь.wav]
# Дальше: node scripts/live-smoke.mjs путь.wav
param([string]$Out = (Join-Path $env:TEMP 'voicedeck-speech.wav'))

Add-Type -AssemblyName System.Speech
$synth = New-Object System.Speech.Synthesis.SpeechSynthesizer
$voice = $synth.GetInstalledVoices() | Where-Object { $_.VoiceInfo.Culture.Name -eq 'ru-RU' } | Select-Object -First 1
if (-not $voice) { throw 'Нет русского голоса Windows: Параметры > Время и язык > Речь > Добавить голоса.' }
$synth.SelectVoice($voice.VoiceInfo.Name)
$format = New-Object System.Speech.AudioFormat.SpeechAudioFormatInfo(16000, [System.Speech.AudioFormat.AudioBitsPerSample]::Sixteen, [System.Speech.AudioFormat.AudioChannel]::Mono)
$synth.SetOutputToWaveFile($Out, $format)
$prompt = New-Object System.Speech.Synthesis.PromptBuilder
$phrases = @(
  'Коллеги, добрый день. Сегодня расскажу про ночные отчёты.',
  'Сейчас отчёт по продажам готов только к одиннадцати утра. Директора получают данные с опозданием и принимают решения вслепую.',
  'Мы перевели две витрины с пакетной загрузки на потоковую. Пилот занял шесть недель. Теперь отчёт готов к восьми тридцати.',
  'Число инцидентов с опозданием отчёта упало с девяти до двух в месяц. Затраты на инфраструктуру выросли на двенадцать процентов.',
  'Просим решение руководства: перевести остальные четырнадцать витрин до конца квартала.'
)
foreach ($phrase in $phrases) {
  $prompt.AppendText($phrase)
  $prompt.AppendBreak([TimeSpan]::FromMilliseconds(1800))
}
$synth.Speak($prompt)
$synth.Dispose()
Write-Output $Out
