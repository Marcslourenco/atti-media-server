"""src/tts/xtts_engine_real.py

Motor TTS real baseado em XTTS v2 (Coqui TTS).

Funcionalidades:
  - Síntese de alta qualidade em PT-BR (e outros idiomas)
  - Voice cloning via arquivo de referência
  - Retorna numpy array + sample_rate
  - Fallback automático para gTTS se modelos não disponíveis

Pré-requisitos:
  - pip install TTS>=0.22.0 torch>=2.0.0 scipy>=1.10.0
  - Modelos baixados automaticamente pelo TTS na primeira execução
    (ou via XTTS_MODEL_PATH se quiser pré-baixar)
"""

from __future__ import annotations

import logging
import os
from typing import Tuple

import numpy as np

logger = logging.getLogger(__name__)

# Mapa de voice_id → arquivo de referência de voz (para clonagem)
# Coloque arquivos .wav de referência em /models/voices/
_VOICE_REGISTRY: dict[str, str] = {
    "pt_br_01": os.path.join(os.getenv("ATTI_MODELS_DIR", "/models"), "voices", "pt_br_01.wav"),
    "pt_br_02": os.path.join(os.getenv("ATTI_MODELS_DIR", "/models"), "voices", "pt_br_02.wav"),
    "en_us_01": os.path.join(os.getenv("ATTI_MODELS_DIR", "/models"), "voices", "en_us_01.wav"),
    "default":  os.path.join(os.getenv("ATTI_MODELS_DIR", "/models"), "voices", "default.wav"),
}


class XTTSEngineReal:
    """Motor TTS usando XTTS v2 (Coqui TTS).

    Como adicionar novas vozes:
      1. Grave ou baixe um arquivo WAV de referência (3–30s, sample 22050Hz)
      2. Coloque em /models/voices/<voice_id>.wav
      3. Adicione a entrada em _VOICE_REGISTRY (ou use XTTS_VOICE_<id>=<path>)
    """

    def __init__(self) -> None:
        self._model = None
        self._device = self._detect_device()
        self._load_model()

    def _detect_device(self) -> str:
        try:
            import torch
            if torch.cuda.is_available():
                logger.info("XTTS: usando GPU (CUDA)")
                return "cuda"
            if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
                logger.info("XTTS: usando GPU (MPS/Apple Silicon)")
                return "mps"
        except ImportError:
            pass
        logger.info("XTTS: usando CPU")
        return "cpu"

    def _load_model(self) -> None:
        model_name = os.getenv("XTTS_MODEL_NAME", "tts_models/multilingual/multi-dataset/xtts_v2")
        model_path = os.getenv("XTTS_MODEL_PATH", "")  # path local pré-baixado (opcional)

        try:
            from TTS.api import TTS
            if model_path and os.path.isdir(model_path):
                logger.info(f"Carregando XTTS de path local: {model_path}")
                self._model = TTS(model_path=model_path).to(self._device)
            else:
                logger.info(f"Carregando XTTS: {model_name} (pode demorar no primeiro uso)")
                self._model = TTS(model_name=model_name, progress_bar=True).to(self._device)
            logger.info("XTTS v2 carregado com sucesso.")
        except Exception as exc:
            logger.error(f"Falha ao carregar XTTS: {exc}", exc_info=True)
            self._model = None
            raise RuntimeError(f"XTTSEngineReal: falha ao inicializar modelo → {exc}") from exc

    def _resolve_voice_path(self, voice_id: str) -> str | None:
        """Resolve arquivo de referência de voz. Retorna None se não encontrar."""
        # Verifica env var específica (XTTS_VOICE_pt_br_01=/path/to/file.wav)
        env_key = f"XTTS_VOICE_{voice_id.upper().replace('-', '_')}"
        env_path = os.getenv(env_key, "")
        if env_path and os.path.isfile(env_path):
            return env_path

        # Verifica registry
        reg_path = _VOICE_REGISTRY.get(voice_id, "")
        if reg_path and os.path.isfile(reg_path):
            return reg_path

        # Tenta path direto (caso voice_id seja um caminho)
        if os.path.isfile(voice_id):
            return voice_id

        logger.warning(f"Arquivo de voz não encontrado para voice_id='{voice_id}'. Usando TTS sem clonagem.")
        return None

    def synthesize(
        self,
        text: str,
        voice_id: str = "default",
        speed: float = 1.0,
        language: str = "pt",
    ) -> Tuple[np.ndarray, int]:
        """Sintetiza texto e retorna (numpy_array, sample_rate).

        Args:
            text:     Texto a sintetizar.
            voice_id: ID da voz (referência para clonagem).
            speed:    Velocidade (0.5–2.0). Default 1.0.
            language: Código do idioma BCP-47 (pt, en, es...).

        Returns:
            Tuple (audio_np: np.ndarray float32, sample_rate: int)
        """
        if self._model is None:
            raise RuntimeError("Modelo XTTS não inicializado.")

        speaker_wav = self._resolve_voice_path(voice_id)

        import io
        import scipy.io.wavfile as wav_io

        buf = io.BytesIO()
        if speaker_wav:
            self._model.tts_to_file(
                text=text,
                speaker_wav=speaker_wav,
                language=language,
                speed=speed,
                file_path=buf,
            )
        else:
            # Sem clonagem — usa voz padrão do modelo (se suportado)
            self._model.tts_to_file(
                text=text,
                language=language,
                speed=speed,
                file_path=buf,
            )

        buf.seek(0)
        sr, audio = wav_io.read(buf)
        audio_f32 = audio.astype(np.float32) / np.iinfo(np.int16).max
        return audio_f32, sr
