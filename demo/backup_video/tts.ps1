Add-Type -AssemblyName System.Speech
$lines = Get-Content -Raw -Encoding UTF8 "$PSScriptRoot\lines.json" | ConvertFrom-Json
$s = New-Object System.Speech.Synthesis.SpeechSynthesizer
$s.SelectVoice("Microsoft Hanhan Desktop"); $s.Rate = 0
for ($i=0; $i -lt $lines.Count; $i++) { $s.SetOutputToWaveFile("$PSScriptRoot\tts\n$($i+1).wav"); $s.Speak($lines[$i]) }
$s.Dispose()
