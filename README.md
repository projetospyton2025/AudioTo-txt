# AudioTo-txt.

Aplicação web local para transcrever áudio em texto. O usuário abre o navegador, arrasta um MP3 (ou outro formato), acompanha a transcrição e copia ou baixa o resultado em TXT. O processamento roda neste computador com Whisper e FFmpeg.

O script original de linha de comando permanece em `transcribe.py`.

## Requisitos

- Windows
- Python 3
- FFmpeg instalado
- Ambiente `audio` (já contém PyTorch)

Caminho padrão de fallback do FFmpeg:

`D:\ffmpeg_\bin\ffmpeg.exe`

A aplicação primeiro tenta localizar `ffmpeg` no PATH. Se não encontrar, usa o caminho acima.

## Qual ambiente usar

Use a pasta **`audio`**, não o `venv`.

- `audio` — ambiente do Whisper/PyTorch (correto para transcrever)
- `venv` — ambiente só com Flask, criado na etapa de conversão para MP3

## Como verificar o FFmpeg

```powershell
ffmpeg -version
```

Se o comando não for reconhecido:

```powershell
& "D:\ffmpeg_\bin\ffmpeg.exe" -version
```

## Como iniciar (Windows PowerShell)

Não use `py app.py` — o launcher `py` pode abrir outro Python, sem Whisper.

Use o Python da pasta `audio`:

```powershell
cd "H:\Meu Drive\ProjetosPython\Audio\AudioTo-txt"
.\audio\Scripts\python.exe app.py
```

Ou dê dois cliques em `iniciar.bat`.

Para encerrar, dê dois cliques em `encerrar.bat`. Ele para o processo na porta 5000 e o `app.py` desta pasta.

No terminal deve aparecer:

```text
AudioTo-txt iniciado!
Acesse: http://127.0.0.1:5000
```

Abra esse endereço no navegador.

Na primeira transcrição o Whisper pode baixar o modelo `base`. Isso ocorre só uma vez.

## Como alterar configurações

Edite `config.py`:

- `FFMPEG_FALLBACK_CANDIDATES`
- `UPLOAD_FOLDER`
- `TRANSCRIPTS_FOLDER`
- `MAX_FILE_SIZE`
- `ALLOWED_EXTENSIONS`
- `WHISPER_MODEL`
- `WHISPER_LANGUAGE`

## Estrutura do projeto

```text
AudioTo-txt/
├── app.py
├── config.py
├── transcriber.py
├── transcribe.py
├── requirements.txt
├── README.md
├── templates/
│   └── index.html
├── static/
│   ├── css/
│   │   └── style.css
│   └── js/
│       └── app.js
├── uploads/
└── transcripts/
```

## Uso

1. Arraste um áudio ou vídeo (MP3, WAV, MP4, M4A, MOV, WEBM...) ou clique para selecionar.
2. A aplicação detecta o formato automaticamente pelos bytes do arquivo e pelo FFprobe.
3. Clique em **Transcrever para TXT**.
4. Leia o texto, copie ou baixe o TXT.
