(() => {
    const config = window.APP_CONFIG || {};
    const knownMedia = new Set([
        "mp3", "wav", "wave", "m4a", "aac", "flac", "ogg", "opus", "wma", "webm",
        "mp4", "mov", "mkv", "avi", "mpeg", "mpg", "3gp", "3gpp", "3g2", "m4v",
        "m4b", "amr", "aiff", "aif", "caf", "weba", "ts", "mts", "m2ts", "flv", "wmv",         "mpga",
        "3gpp",
        ...(config.allowedExtensions || []),
    ].map((item) => String(item).toLowerCase()));
    const blocked = new Set([
        "exe", "bat", "cmd", "com", "ps1", "js", "msi", "dll", "scr", "vbs",
        "pdf", "doc", "docx", "xls", "xlsx", "ppt", "pptx", "zip", "rar", "7z",
        "png", "jpg", "jpeg", "gif", "bmp", "webp", "svg", "txt", "html", "htm", "csv",
    ]);
    const maxSize = Number(config.maxFileSize || 500 * 1024 * 1024);

    const card = document.getElementById("app-card");
    const dropzone = document.getElementById("upload-form");
    const fileInput = document.getElementById("file-input");
    const selectBtn = document.getElementById("select-btn");
    const changeFileBtn = document.getElementById("change-file-btn");
    const convertBtn = document.getElementById("convert-btn");
    const anotherBtn = document.getElementById("another-btn");
    const retryBtn = document.getElementById("retry-btn");
    const downloadBtn = document.getElementById("download-btn");
    const copyBtn = document.getElementById("copy-btn");
    const chatgptBtn = document.getElementById("chatgpt-btn");
    const sourcePlayer = document.getElementById("source-player");
    const sourceVideo = document.getElementById("source-video");
    const fileNameEl = document.getElementById("file-name");
    const fileSizeEl = document.getElementById("file-size");
    const fileExtEl = document.getElementById("file-ext");
    const fileDetectedEl = document.getElementById("file-detected");
    const convertingTitle = document.getElementById("converting-title");
    const convertingFile = document.getElementById("converting-file");
    const progressBar = document.getElementById("progress-bar");
    const progressFill = document.getElementById("progress-fill");
    const progressLabel = document.getElementById("progress-label");
    const progressValue = document.getElementById("progress-value");
    const progressPercent = document.getElementById("progress-percent");
    const resultMeta = document.getElementById("result-meta");
    const transcriptText = document.getElementById("transcript-text");
    const errorMessage = document.getElementById("error-message");

    const state = {
        mode: "idle",
        file: null,
        objectUrl: null,
        jobId: null,
        busy: false,
        pollTimer: null,
        xhr: null,
        text: "",
    };

    const messages = {
        invalid_file: "Arquivo inválido. Selecione um áudio suportado.",
        unsupported_format: "Formato não suportado. Envie áudio ou vídeo com faixa de som (MP3, WAV, MP4, M4A, WEBM e similares).",
        no_audio: "Este arquivo não tem faixa de áudio. Envie um som ou um vídeo com áudio.",
        file_too_large: "O arquivo é muito grande. O limite é 500 MB.",
        ffmpeg_missing: "FFmpeg não encontrado. Verifique a instalação e o caminho configurado.",
        whisper_missing: "O Whisper não está instalado neste ambiente. Ative a pasta audio e instale as dependências.",
        conversion_failed: "Não foi possível transcrever este arquivo. Verifique se o áudio está válido e tente novamente.",
        corrupted: "O arquivo parece corrompido ou incompleto. Tente outro áudio.",
        unexpected: "Ocorreu um erro inesperado. Tente novamente.",
        busy: "Já existe uma transcrição em andamento. Aguarde a conclusão.",
    };

    function extensionOf(name) {
        const parts = String(name || "").toLowerCase().split(".");
        return parts.length > 1 ? parts.pop() : "";
    }

    const videoKinds = new Set(["MP4", "MOV", "MKV", "AVI", "WEBM", "MPEG", "3GP", "M4V"]);

    function sniffBytes(bytes) {
        const ascii = (start, end) => String.fromCharCode(...bytes.slice(start, end));
        if (ascii(0, 3) === "ID3") return "MP3";
        if (bytes[0] === 0xff && [0xfb, 0xf3, 0xf2, 0xe3].includes(bytes[1])) return "MP3";
        if (ascii(0, 4) === "RIFF" && ascii(8, 12) === "WAVE") return "WAV";
        if (ascii(0, 4) === "RIFF" && ascii(8, 12) === "AVI ") return "AVI";
        if (ascii(0, 4) === "fLaC") return "FLAC";
        if (ascii(0, 4) === "OggS") return "OGG";
        if (ascii(0, 4) === "FORM" && (ascii(8, 12) === "AIFF" || ascii(8, 12) === "AIFC")) return "AIFF";
        if (ascii(4, 8) === "ftyp") {
            const brand = ascii(8, 12).toLowerCase();
            if (brand.startsWith("m4a") || brand === "m4b " || brand === "m4p ") return "M4A";
            if (brand.startsWith("qt")) return "MOV";
            if (brand.startsWith("3gp") || brand.startsWith("3g2")) return "3GP";
            return "MP4";
        }
        if (bytes[0] === 0x1a && bytes[1] === 0x45 && bytes[2] === 0xdf && bytes[3] === 0xa3) return "WEBM";
        if (bytes[0] === 0x30 && bytes[1] === 0x26 && bytes[2] === 0xb2 && bytes[3] === 0x75) return "WMA";
        if (ascii(0, 5) === "#!AMR") return "AMR";
        return null;
    }

    function sniffFromMime(type) {
        const mime = String(type || "").toLowerCase();
        if (mime.includes("mp4")) return "MP4";
        if (mime.includes("quicktime")) return "MOV";
        if (mime.includes("webm")) return "WEBM";
        if (mime.includes("wav")) return "WAV";
        if (mime.includes("mpeg") || mime.includes("mp3")) return "MP3";
        if (mime.includes("flac")) return "FLAC";
        if (mime.includes("ogg")) return "OGG";
        if (mime.includes("aac")) return "AAC";
        if (mime.startsWith("video/")) return "VÍDEO";
        if (mime.startsWith("audio/")) return "ÁUDIO";
        return null;
    }

    async function detectClientFormat(file) {
        try {
            const buf = await file.slice(0, 16).arrayBuffer();
            const sniffed = sniffBytes(new Uint8Array(buf));
            if (sniffed) return sniffed;
        } catch (_error) {
            // segue para MIME/extensão
        }
        return sniffFromMime(file.type) || (extensionOf(file.name).toUpperCase() || "ARQUIVO");
    }

    function isLikelyMedia(file, sniffed) {
        const ext = extensionOf(file.name);
        if (blocked.has(ext)) return false;
        return true;
    }

    async function validateFile(file) {
        if (!file) return "invalid_file";
        if (file.size <= 0) return "corrupted";
        if (file.size > maxSize) return "file_too_large";
        const ext = extensionOf(file.name);
        if (blocked.has(ext)) return "unsupported_format";
        return null;
    }

    function showPreview(file, kind) {
        revoke(state.objectUrl);
        state.objectUrl = URL.createObjectURL(file);
        const isVideo = videoKinds.has(kind);
        if (isVideo && sourceVideo) {
            sourcePlayer.hidden = true;
            sourcePlayer.removeAttribute("src");
            sourceVideo.hidden = false;
            sourceVideo.src = state.objectUrl;
        } else {
            if (sourceVideo) {
                sourceVideo.hidden = true;
                sourceVideo.removeAttribute("src");
            }
            sourcePlayer.hidden = false;
            sourcePlayer.src = state.objectUrl;
        }
    }

    function formatSize(bytes) {
        if (!Number.isFinite(bytes) || bytes < 0) return "0 B";
        const units = ["B", "KB", "MB", "GB"];
        let value = bytes;
        let unit = 0;
        while (value >= 1024 && unit < units.length - 1) {
            value /= 1024;
            unit += 1;
        }
        const digits = value >= 10 || unit === 0 ? 0 : 1;
        return `${value.toFixed(digits)} ${units[unit]}`;
    }

    function wordCount(text) {
        const words = String(text || "").trim().split(/\s+/).filter(Boolean);
        return words.length;
    }

    function revoke(url) {
        if (url) URL.revokeObjectURL(url);
    }

    function setState(mode) {
        state.mode = mode;
        card.dataset.state = mode;
        card.querySelectorAll("[data-panel]").forEach((panel) => {
            panel.hidden = panel.dataset.panel !== mode;
        });
    }

    function showError(codeOrMessage) {
        stopPolling();
        state.busy = false;
        if (convertBtn) convertBtn.disabled = false;
        let text = messages.unexpected;
        if (typeof codeOrMessage === "string") {
            text = messages[codeOrMessage] || codeOrMessage;
        }
        if (errorMessage) errorMessage.textContent = text;
        setState("error");
    }

    async function assignFile(file) {
        const error = await validateFile(file);
        if (error) {
            showError(error);
            return;
        }

        stopPolling();
        const detected = await detectClientFormat(file);
        state.file = file;
        state.jobId = null;
        state.text = "";
        fileNameEl.textContent = file.name;
        fileSizeEl.textContent = formatSize(file.size);
        fileExtEl.textContent = detected;
        if (fileDetectedEl) {
            fileDetectedEl.textContent = `detectado: ${detected} · vai virar TXT`;
        }
        showPreview(file, detected);
        convertBtn.disabled = false;
        setState("file-selected");
    }

    function resetToIdle() {
        stopPolling();
        if (state.xhr) {
            state.xhr.abort();
            state.xhr = null;
        }
        if (state.jobId) {
            fetch(`/reset/${state.jobId}`, { method: "POST" }).catch(() => {});
        }
        revoke(state.objectUrl);
        sourcePlayer.removeAttribute("src");
        if (sourceVideo) sourceVideo.removeAttribute("src");
        fileInput.value = "";
        transcriptText.value = "";
        state.file = null;
        state.objectUrl = null;
        state.jobId = null;
        state.text = "";
        state.busy = false;
        convertBtn.disabled = false;
        if (copyBtn) copyBtn.textContent = "Copiar texto";
        setState("idle");
    }

    function setProgress(percent, label, indeterminate) {
        progressLabel.textContent = label;
        if (indeterminate || percent === null || percent === undefined) {
            progressBar.classList.add("is-indeterminate");
            progressFill.style.width = "36%";
            progressBar.setAttribute("aria-valuenow", "0");
            progressValue.textContent = "";
            if (progressPercent) progressPercent.textContent = "...";
            return;
        }
        const value = Math.max(0, Math.min(100, Number(percent)));
        const shown = `${Math.round(value)}%`;
        progressBar.classList.remove("is-indeterminate");
        progressFill.style.width = `${value}%`;
        progressBar.setAttribute("aria-valuenow", String(Math.round(value)));
        progressValue.textContent = shown;
        if (progressPercent) progressPercent.textContent = shown;
    }

    function stopPolling() {
        if (state.pollTimer) {
            clearTimeout(state.pollTimer);
            state.pollTimer = null;
        }
    }

    function parseError(data, fallback) {
        if (data && data.code && messages[data.code]) return messages[data.code];
        if (data && data.error) return data.error;
        return fallback;
    }

    function stageLabel(stage) {
        if (stage === "loading_model") return "Carregando o modelo Whisper";
        if (stage === "queued") return "Preparando o arquivo TXT";
        return "Transcrevendo para TXT";
    }

    async function pollStatus(jobId) {
        try {
            const response = await fetch(`/status/${jobId}`);
            const data = await response.json();
            if (!response.ok || data.status === "error") {
                showError(parseError(data, messages.conversion_failed));
                return;
            }
            if (data.status === "converting") {
                convertingTitle.textContent = "Gerando o TXT...";
                if (data.progress === null || data.progress === undefined) {
                    setProgress(null, stageLabel(data.stage), true);
                } else {
                    setProgress(data.progress, stageLabel(data.stage), false);
                }
                state.pollTimer = setTimeout(() => pollStatus(jobId), 600);
                return;
            }
            if (data.status === "done") {
                finishSuccess(data);
                return;
            }
            state.pollTimer = setTimeout(() => pollStatus(jobId), 900);
        } catch (_error) {
            showError("unexpected");
        }
    }

    function finishSuccess(data) {
        stopPolling();
        state.busy = false;
        state.text = data.text || "";
        transcriptText.value = state.text || "Nenhuma fala foi reconhecida neste áudio.";
        downloadBtn.href = data.download_url;
        downloadBtn.setAttribute("download", data.download_name || "transcricao.txt");
        const words = wordCount(state.text);
        resultMeta.textContent = `${data.download_name || "transcricao.txt"} · ${words} palavra${words === 1 ? "" : "s"}`;
        if (copyBtn) copyBtn.textContent = "Copiar texto";
        setState("success");
    }

    async function startConversion() {
        if (!state.file || state.busy) return;
        const error = await validateFile(state.file);
        if (error) {
            showError(error);
            return;
        }

        state.busy = true;
        convertBtn.disabled = true;
        convertingFile.textContent = state.file.name;
        convertingTitle.textContent = "Enviando áudio...";
        setProgress(0, "Enviando áudio", false);
        setState("converting");

        const formData = new FormData();
        formData.append("file", state.file, state.file.name);

        const xhr = new XMLHttpRequest();
        state.xhr = xhr;
        xhr.open("POST", "/transcribe");
        xhr.responseType = "json";

        xhr.upload.onprogress = (event) => {
            if (!event.lengthComputable) {
                setProgress(null, "Enviando áudio", true);
                return;
            }
            const percent = (event.loaded / event.total) * 100;
            setProgress(percent, "Enviando áudio", false);
        };

        xhr.onload = () => {
            state.xhr = null;
            const data = xhr.response || {};
            if (xhr.status === 413) {
                showError("file_too_large");
                return;
            }
            if (xhr.status >= 400 || data.ok === false) {
                showError(parseError(data, messages.conversion_failed));
                return;
            }
            state.jobId = data.job_id;
            convertingTitle.textContent = "Gerando o TXT...";
            if (data.detected_format) {
                convertingFile.textContent = `${state.file.name} · ${data.detected_format}`;
            }
            setProgress(data.progress ?? 1, "Transcrevendo para arquivo TXT", data.progress == null);
            pollStatus(data.job_id);
        };

        xhr.onerror = () => {
            state.xhr = null;
            showError("unexpected");
        };

        xhr.onabort = () => {
            state.xhr = null;
            state.busy = false;
        };

        xhr.send(formData);
    }

    async function exportToChatGPT() {
        const transcript = (transcriptText && transcriptText.value) || state.text || "";
        const prompt = `Crie um prompt profissional para o texto a seguir:\n\n${transcript}`;
        const encoded = encodeURIComponent(prompt);
        const chatgptUrl = `https://chatgpt.com/?q=${encoded}`;
        if (encoded.length > 7500) {
            try {
                await navigator.clipboard.writeText(prompt);
                if (chatgptBtn) chatgptBtn.textContent = "Texto copiado — cole no ChatGPT";
            } catch (_error) {
                // segue abrindo a aba mesmo assim
            }
            window.open("https://chatgpt.com/", "_blank", "noopener,noreferrer");
            setTimeout(() => {
                if (chatgptBtn) chatgptBtn.textContent = "Enviar para o ChatGPT";
            }, 2200);
            return;
        }
        window.open(chatgptUrl, "_blank", "noopener,noreferrer");
    }

    async function copyTranscript() {
        const text = transcriptText.value || "";
        try {
            await navigator.clipboard.writeText(text);
            copyBtn.textContent = "Copiado";
            setTimeout(() => {
                if (copyBtn) copyBtn.textContent = "Copiar texto";
            }, 1600);
        } catch (_error) {
            transcriptText.focus();
            transcriptText.select();
        }
    }

    let dragDepth = 0;

    dropzone.addEventListener("click", (event) => {
        if (event.target.closest("button")) return;
        fileInput.click();
    });

    dropzone.addEventListener("keydown", (event) => {
        if (event.key === "Enter" || event.key === " ") {
            event.preventDefault();
            fileInput.click();
        }
    });

    ["dragenter", "dragover", "dragleave", "drop"].forEach((type) => {
        dropzone.addEventListener(type, (event) => {
            event.preventDefault();
            event.stopPropagation();
        });
    });

    dropzone.addEventListener("dragenter", () => {
        dragDepth += 1;
        dropzone.classList.add("is-dragover");
    });

    dropzone.addEventListener("dragover", () => {
        dropzone.classList.add("is-dragover");
    });

    dropzone.addEventListener("dragleave", () => {
        dragDepth = Math.max(0, dragDepth - 1);
        if (dragDepth === 0) dropzone.classList.remove("is-dragover");
    });

    dropzone.addEventListener("drop", (event) => {
        dragDepth = 0;
        dropzone.classList.remove("is-dragover");
        const file = event.dataTransfer && event.dataTransfer.files && event.dataTransfer.files[0];
        assignFile(file);
    });

    fileInput.addEventListener("change", () => {
        assignFile(fileInput.files && fileInput.files[0]);
    });

    selectBtn.addEventListener("click", (event) => {
        event.preventDefault();
        event.stopPropagation();
        fileInput.click();
    });

    changeFileBtn.addEventListener("click", () => fileInput.click());
    convertBtn.addEventListener("click", startConversion);
    anotherBtn.addEventListener("click", resetToIdle);
    retryBtn.addEventListener("click", resetToIdle);
    if (copyBtn) copyBtn.addEventListener("click", copyTranscript);
    if (chatgptBtn) chatgptBtn.addEventListener("click", exportToChatGPT);

    window.addEventListener("beforeunload", () => {
        revoke(state.objectUrl);
    });
})();
