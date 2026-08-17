import whisper

# Carrega o modelo
model = whisper.load_model("base")

# Arquivo de áudio
audio_file = "audio.mp3"

# Transcreve para português
result = model.transcribe(audio_file, language="pt")

# Mostra o texto
print(result["text"])

# Salva em um arquivo TXT
with open("transcricao.txt", "w", encoding="utf-8") as f:
    f.write(result["text"])

print("Transcrição salva em transcricao.txt")
