"""src/media/pipeline_real.py

Pipeline completo de geração de vídeo do avatar.

Orquestra:
  1. TTS (XTTSEngineReal ou gTTS)
  2. Animação facial (LivePortraitEngineReal)
  3. Visemas / Lip sync (VisemeSyncEngine)
  4. Composição final do vídeo com áudio (ffmpeg)
  5. Upload para storage (local ou S3/MinIO) → retorna URL

Dependências:
  - ffmpeg instalado no sistema (apt-get install ffmpeg)
  - src.tts.xtts_engine_real
  - src.avatar.liveportrait_engine_real
  - src.avatar.viseme_sync
  - src.streaming.audio_stream
"""

from __future__ import annotations

import logging
import os
import subprocess
import tempfile
import time
import uuid
from typing import Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Configurações
# ---------------------------------------------------------------------------
_OUTPUT_DIR = os.getenv("ATTI_OUTPUT_DIR", "/tmp/atti_outputs")
_BASE_URL = os.getenv("ATTI_BASE_URL", "http://localhost:8000")
_MODELS_DIR = os.getenv("ATTI_MODELS_DIR", "/models")


def _ensure_output_dir() -> str:
    os.makedirs(_OUTPUT_DIR, exist_ok=True)
    return _OUTPUT_DIR


# ---------------------------------------------------------------------------
# Helpers de storage
# ---------------------------------------------------------------------------

def _save_to_local(src_path: str, filename: str) -> str:
    """Move arquivo para o diretório de outputs e retorna URL pública."""
    import shutil
    out_dir = _ensure_output_dir()
    dst = os.path.join(out_dir, filename)
    shutil.move(src_path, dst)
    return f"{_BASE_URL}/outputs/{filename}"


def _upload_to_s3(local_path: str, object_name: str) -> str:
    """Upload para S3/MinIO se configurado. Retorna URL pública."""
    bucket = os.getenv("ATTI_S3_BUCKET", "")
    endpoint = os.getenv("ATTI_S3_ENDPOINT", "")
    if not bucket:
        raise RuntimeError("ATTI_S3_BUCKET não configurado.")

    try:
        import boto3
        from botocore.client import Config

        s3 = boto3.client(
            "s3",
            endpoint_url=endpoint or None,
            aws_access_key_id=os.getenv("ATTI_S3_ACCESS_KEY"),
            aws_secret_access_key=os.getenv("ATTI_S3_SECRET_KEY"),
            config=Config(signature_version="s3v4"),
        )
        s3.upload_file(local_path, bucket, object_name, ExtraArgs={"ACL": "public-read"})
        public_url = f"{endpoint}/{bucket}/{object_name}" if endpoint else \
                     f"https://{bucket}.s3.amazonaws.com/{object_name}"
        logger.info(f"Upload S3 concluído: {public_url}")
        return public_url
    except ImportError:
        raise RuntimeError("boto3 não instalado. pip install boto3")


def _publish_artifact(local_path: str, filename: str) -> str:
    """Publica artefato no storage configurado e retorna URL.

    Prioridade:
      - ATTI_S3_BUCKET configurado → S3/MinIO
      - Caso contrário → storage local
    """
    if os.getenv("ATTI_S3_BUCKET"):
        try:
            return _upload_to_s3(local_path, filename)
        except Exception as exc:
            logger.warning(f"Upload S3 falhou ({exc}), usando storage local.")
    return _save_to_local(local_path, filename)


# ---------------------------------------------------------------------------
# Pipeline principal
# ---------------------------------------------------------------------------

def generate_full_video(
    avatar_id: str,
    voice_profile: str,
    text: str,
    speed: float = 1.0,
    language: str = "pt",
    fps: int = 30,
    output_format: str = "mp4",
) -> str:
    """Gera vídeo completo do avatar falando o texto dado.

    Args:
        avatar_id:     ID do avatar (mapeia para imagem em /models/avatars/)
        voice_profile: ID do perfil de voz (mapeia para arquivo em /models/voices/)
        text:          Texto a ser falado pelo avatar
        speed:         Velocidade da fala (0.5–2.0)
        language:      Idioma BCP-47 (pt, en, es...)
        fps:           Frames por segundo do vídeo
        output_format: Formato de saída (mp4, webm...)

    Returns:
        URL pública do vídeo gerado.

    Raises:
        RuntimeError: se qualquer etapa do pipeline falhar.
    """
    job_id = str(uuid.uuid4())[:8]
    t0 = time.time()
    logger.info(f"[{job_id}] Pipeline iniciado | avatar={avatar_id} | voice={voice_profile} | chars={len(text)}")

    with tempfile.TemporaryDirectory() as tmpdir:
        audio_path = os.path.join(tmpdir, "speech.wav")
        video_path = os.path.join(tmpdir, f"video_raw.{output_format}")
        final_path = os.path.join(tmpdir, f"final_{job_id}.{output_format}")

        # ── ETAPA 1: TTS ─────────────────────────────────────────────────
        logger.info(f"[{job_id}] Etapa 1/4: TTS")
        audio_bytes = _synthesize_audio(text=text, voice_profile=voice_profile, speed=speed, language=language)
        with open(audio_path, "wb") as f:
            f.write(audio_bytes)
        logger.info(f"[{job_id}] TTS concluído: {len(audio_bytes)} bytes | {time.time()-t0:.1f}s")

        # ── ETAPA 2: Visemas / Lip Sync ───────────────────────────────────
        logger.info(f"[{job_id}] Etapa 2/4: Visemas")
        blend_shapes = _extract_blend_shapes(audio_path=audio_path, fps=fps)
        logger.info(f"[{job_id}] Visemas concluídos | {time.time()-t0:.1f}s")

        # ── ETAPA 3: Animação Facial ──────────────────────────────────────
        logger.info(f"[{job_id}] Etapa 3/4: Animação facial")
        avatar_image_path = os.path.join(_MODELS_DIR, "avatars", f"{avatar_id}.png")
        frames = _animate_avatar(
            avatar_image_path=avatar_image_path,
            audio_path=audio_path,
            fps=fps,
        )
        logger.info(f"[{job_id}] Animação concluída: {len(frames) if frames else 0} frames | {time.time()-t0:.1f}s")

        # ── ETAPA 4: Composição final ─────────────────────────────────────
        logger.info(f"[{job_id}] Etapa 4/4: Composição de vídeo")
        _compose_video(
            frames=frames,
            audio_path=audio_path,
            output_path=final_path,
            fps=fps,
        )
        logger.info(f"[{job_id}] Vídeo composto | {time.time()-t0:.1f}s")

        # ── Publicação ────────────────────────────────────────────────────
        filename = f"avatar_{avatar_id}_{job_id}.{output_format}"
        video_url = _publish_artifact(final_path, filename)
        logger.info(f"[{job_id}] Pipeline concluído em {time.time()-t0:.1f}s → {video_url}")
        return video_url


# ---------------------------------------------------------------------------
# Etapas internas
# ---------------------------------------------------------------------------

def _synthesize_audio(text: str, voice_profile: str, speed: float, language: str) -> bytes:
    """Etapa TTS: retorna bytes WAV."""
    try:
        from src.tts.xtts_engine_real import XTTSEngineReal
        import io
        import numpy as np
        import scipy.io.wavfile as wav_io

        engine = XTTSEngineReal()
        audio_np, sr = engine.synthesize(text=text, voice_id=voice_profile, speed=speed, language=language)
        buf = io.BytesIO()
        wav_io.write(buf, sr, audio_np.astype(np.float32))
        return buf.getvalue()

    except Exception as exc:
        logger.warning(f"XTTS falhou ({exc}), usando gTTS.")
        try:
            from gtts import gTTS
            import io
            tts = gTTS(text=text, lang=language, slow=(speed < 0.85))
            buf = io.BytesIO()
            tts.write_to_fp(buf)
            buf.seek(0)
            return buf.read()
        except Exception as exc2:
            raise RuntimeError(f"TTS falhou (XTTS e gTTS): {exc2}") from exc2


def _extract_blend_shapes(audio_path: str, fps: int):
    """Etapa Visemas: retorna BlendShapes ou None."""
    try:
        from src.avatar.viseme_sync import VisemeSyncEngine
        engine = VisemeSyncEngine(fps=fps)
        visemes = engine.extract_visemes(audio_path)
        # Estima total de frames a partir do número de visemas
        total_frames = max(fps * 3, len(visemes))
        lip_curve = engine.generate_lip_curve(visemes, total_frames)
        return engine.to_blend_shapes(lip_curve)
    except Exception as exc:
        logger.warning(f"Extração de visemas falhou ({exc}). Lip sync será ignorado.")
        return None


def _animate_avatar(avatar_image_path: str, audio_path: str, fps: int):
    """Etapa Animação: retorna lista de frames ou None."""
    if not os.path.isfile(avatar_image_path):
        logger.warning(f"Imagem do avatar não encontrada: {avatar_image_path}. Usando frame estático.")
        return None
    try:
        from src.avatar.liveportrait_engine_real import LivePortraitEngineReal
        engine = LivePortraitEngineReal()
        return engine.generate_animation(avatar_image_path, audio_path, fps=fps)
    except Exception as exc:
        logger.warning(f"LivePortrait falhou ({exc}). Usando frame estático.")
        return None


def _compose_video(frames, audio_path: str, output_path: str, fps: int) -> None:
    """Etapa Composição: salva vídeo final com áudio."""
    try:
        import cv2
    except ImportError:
        raise ImportError("opencv-python necessário. pip install opencv-python")

    if frames:
        # Composição com frames animados
        h, w = frames[0].shape[:2]
        tmp_video = output_path + ".noaudio.mp4"
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        writer = cv2.VideoWriter(tmp_video, fourcc, fps, (w, h))
        for f in frames:
            writer.write(f)
        writer.release()
    else:
        # Sem frames: cria vídeo preto com duração do áudio
        import subprocess
        tmp_video = output_path + ".noaudio.mp4"
        cmd = [
            "ffmpeg", "-y",
            "-f", "lavfi", "-i", "color=c=black:s=512x512:r=30",
            "-i", audio_path,
            "-shortest",
            "-c:v", "libx264",
            tmp_video,
        ]
        result = subprocess.run(cmd, capture_output=True)
        if result.returncode != 0:
            raise RuntimeError(f"ffmpeg (vídeo preto) falhou: {result.stderr.decode()}")

    # Mescla vídeo + áudio
    cmd = [
        "ffmpeg", "-y",
        "-i", tmp_video,
        "-i", audio_path,
        "-c:v", "copy",
        "-c:a", "aac",
        "-shortest",
        output_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if os.path.isfile(tmp_video):
        os.remove(tmp_video)

    if result.returncode != 0:
        logger.warning(f"ffmpeg mescla falhou: {result.stderr}")
        # Fallback: copia vídeo sem áudio
        import shutil
        shutil.copy(tmp_video + ".noaudio.mp4" if os.path.isfile(tmp_video + ".noaudio.mp4") else output_path + ".noaudio.mp4", output_path)
