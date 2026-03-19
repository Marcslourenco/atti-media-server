"""src/streaming/audio_stream.py

Streaming de áudio para o frontend.

Funcionalidades:
  - Serve arquivo WAV/MP3 via URL de streaming local
  - Suporta range requests (HTTP 206) para players HTML5
  - Integra com FastAPI via StreamingResponse
  - Geração de URL pública via ATTI_BASE_URL

Uso:
    from src.streaming.audio_stream import AudioStream

    stream = AudioStream("/tmp/audio.wav")
    url = stream.get_stream_url()    # "http://localhost:8000/stream/abc123.wav"

    # No FastAPI, use get_streaming_response() para servir o arquivo:
    @app.get("/stream/{file_id}")
    async def stream_audio(file_id: str):
        stream = AudioStream.from_id(file_id)
        return stream.get_streaming_response()
"""

from __future__ import annotations

import logging
import os
import shutil
import uuid
from pathlib import Path
from typing import AsyncGenerator, Optional

logger = logging.getLogger(__name__)

_STREAM_DIR = os.getenv("ATTI_STREAM_DIR", "/tmp/atti_streams")
_BASE_URL = os.getenv("ATTI_BASE_URL", "http://localhost:8000")
_STREAM_TTL_SECONDS = int(os.getenv("ATTI_STREAM_TTL_SECONDS", "3600"))

# Registro em memória (file_id → path) para lookup rápido
_stream_registry: dict[str, str] = {}


def _ensure_stream_dir() -> str:
    os.makedirs(_STREAM_DIR, exist_ok=True)
    return _STREAM_DIR


class AudioStream:
    """Gerencia streaming de um arquivo de áudio.

    Fluxo:
      1. Copia o arquivo de áudio para o diretório de streams (com ID único)
      2. Registra no registry em memória
      3. Retorna URL pública para o frontend consumir
    """

    def __init__(self, audio_path: str, file_id: Optional[str] = None) -> None:
        if not os.path.isfile(audio_path):
            raise FileNotFoundError(f"Arquivo de áudio não encontrado: {audio_path}")

        self._src_path = audio_path
        self._file_id = file_id or str(uuid.uuid4())
        self._ext = Path(audio_path).suffix or ".wav"
        self._stream_path = self._register()

    def _register(self) -> str:
        """Copia arquivo para stream dir e registra."""
        stream_dir = _ensure_stream_dir()
        filename = f"{self._file_id}{self._ext}"
        dst = os.path.join(stream_dir, filename)

        if not os.path.isfile(dst):
            shutil.copy2(self._src_path, dst)
            logger.info(f"Stream registrado: {filename}")

        _stream_registry[self._file_id] = dst
        return dst

    def get_stream_url(self) -> str:
        """Retorna URL pública de streaming do áudio."""
        filename = f"{self._file_id}{self._ext}"
        return f"{_BASE_URL}/stream/{filename}"

    def get_file_path(self) -> str:
        """Retorna caminho local do arquivo de stream."""
        return self._stream_path

    def cleanup(self) -> None:
        """Remove arquivo de stream (após uso)."""
        try:
            if os.path.isfile(self._stream_path):
                os.remove(self._stream_path)
                logger.info(f"Stream removido: {self._file_id}")
        except Exception as exc:
            logger.warning(f"Falha ao remover stream {self._file_id}: {exc}")
        _stream_registry.pop(self._file_id, None)

    @classmethod
    def from_id(cls, file_id: str) -> "AudioStream":
        """Recupera um AudioStream pelo file_id (do registry em memória)."""
        path = _stream_registry.get(file_id)
        if not path or not os.path.isfile(path):
            raise FileNotFoundError(f"Stream não encontrado: {file_id}")
        ext = Path(path).suffix
        # Sem copiar novamente (já está no stream_dir)
        instance = object.__new__(cls)
        instance._src_path = path
        instance._file_id = file_id
        instance._ext = ext
        instance._stream_path = path
        return instance

    def get_streaming_response(self):
        """Retorna FastAPI StreamingResponse para servir o arquivo.

        Suporta range requests (streaming progressivo).

        Uso no router:
            @app.get("/stream/{file_id}")
            async def stream(file_id: str):
                audio = AudioStream.from_id(file_id)
                return audio.get_streaming_response()
        """
        try:
            from fastapi.responses import FileResponse
            # FileResponse já suporta range requests nativamente
            content_type = "audio/mpeg" if self._ext == ".mp3" else "audio/wav"
            return FileResponse(
                self._stream_path,
                media_type=content_type,
                headers={
                    "Accept-Ranges": "bytes",
                    "Cache-Control": f"max-age={_STREAM_TTL_SECONDS}",
                },
            )
        except ImportError:
            raise ImportError("fastapi necessário. pip install fastapi")

    def cleanup_expired_streams(self, max_age_seconds: int = _STREAM_TTL_SECONDS) -> int:
        """Remove streams mais antigos que max_age_seconds. Retorna contagem removida."""
        import time
        removed = 0
        stream_dir = _ensure_stream_dir()
        now = time.time()
        for fname in os.listdir(stream_dir):
            fpath = os.path.join(stream_dir, fname)
            try:
                if os.path.isfile(fpath) and (now - os.path.getmtime(fpath)) > max_age_seconds:
                    os.remove(fpath)
                    removed += 1
                    # Remove do registry se presente
                    for fid, p in list(_stream_registry.items()):
                        if p == fpath:
                            _stream_registry.pop(fid, None)
            except Exception:
                pass
        if removed:
            logger.info(f"Streams expirados removidos: {removed}")
        return removed
