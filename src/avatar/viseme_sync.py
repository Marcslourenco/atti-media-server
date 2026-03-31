"""src/avatar/viseme_sync.py

Motor de sincronização de lábios (Lip Sync) via visemas.

Funcionalidades:
  - Extração de visemas a partir de arquivo de áudio (WAV)
  - Geração de curva de movimento labial (lip curve)
  - Conversão para blend shapes (compatível com Live Portrait / Metahuman / etc.)

Algoritmo usado:
  - Montreal Forced Aligner (MFA) via aeneas (se disponível)
  - Fallback: librosa + análise de energia para visemas aproximados

Dependências:
  - librosa>=0.10.0
  - numpy>=1.24.0
  - scipy>=1.10.0
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import Dict, List, Tuple

import numpy as np

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Mapeamento fonema → visema (simplificado, baseado em Preston Blair)
# ---------------------------------------------------------------------------
_PHONEME_TO_VISEME: Dict[str, str] = {
    # Vogais
    "AA": "ah", "AE": "ah", "AH": "ah", "AO": "oh",
    "AW": "oh", "AY": "ay", "EH": "eh", "ER": "er",
    "EY": "eh", "IH": "ih", "IY": "ih", "OW": "oh",
    "OY": "oh", "UH": "uh", "UW": "uh",
    # Consoantes labiais
    "B": "mb", "M": "mb", "P": "mb",
    "F": "fv", "V": "fv",
    # Consoantes dentais/alveolares
    "D": "td", "T": "td", "N": "td", "L": "td",
    "S": "sh", "Z": "sh", "SH": "sh", "ZH": "sh",
    "TH": "th", "DH": "th",
    # Velares/glotais
    "G": "kg", "K": "kg", "NG": "kg",
    "R": "er", "W": "uh", "Y": "ih", "HH": "ah",
    "CH": "sh", "JH": "sh",
    # Silence
    "SIL": "rest", "SP": "rest", "": "rest",
}

_VISEME_NAMES = sorted(set(_PHONEME_TO_VISEME.values()))


@dataclass
class Viseme:
    """Representa um visema com timing."""
    name: str
    start: float    # segundos
    end: float      # segundos
    intensity: float = 1.0   # 0.0–1.0


@dataclass
class BlendShapes:
    """Blend shapes para animação facial."""
    # Chaves: nome da blend shape → array de valores por frame (0.0–1.0)
    shapes: Dict[str, np.ndarray] = field(default_factory=dict)
    fps: int = 30

    def to_dict(self) -> Dict[str, List[float]]:
        return {k: v.tolist() for k, v in self.shapes.items()}


class VisemeSyncEngine:
    """Motor de extração de visemas e geração de lip sync.

    Como usar:
        engine = VisemeSyncEngine(fps=30)
        visemes = engine.extract_visemes("audio.wav")
        lip_curve = engine.generate_lip_curve(visemes, total_frames=90)
        blend_shapes = engine.to_blend_shapes(lip_curve)
    """

    def __init__(self, fps: int = 30) -> None:
        self.fps = fps

    # ------------------------------------------------------------------
    # Extração de visemas
    # ------------------------------------------------------------------

    def extract_visemes(self, audio_path: str) -> List[Viseme]:
        """Extrai lista de visemas de um arquivo WAV.

        Estratégia:
          1. Tenta alinhamento forçado via gentle/MFA (se disponível)
          2. Fallback: análise de energia + zero-crossing rate (aproximado)
        """
        if not os.path.isfile(audio_path):
            raise FileNotFoundError(f"Arquivo de áudio não encontrado: {audio_path}")

        # Tenta alinhamento forçado
        try:
            return self._extract_with_forced_aligner(audio_path)
        except Exception as exc:
            logger.warning(f"Alinhamento forçado falhou ({exc}), usando análise de energia.")
            return self._extract_with_energy_analysis(audio_path)

    def _extract_with_forced_aligner(self, audio_path: str) -> List[Viseme]:
        """Tenta usar gentle aligner (se disponível no ambiente)."""
        try:
            import requests  # gentle usa HTTP API local
            resp = requests.post(
                "http://localhost:8765/transcriptions",
                files={"audio": open(audio_path, "rb")},
                timeout=10,
            )
            if resp.status_code != 200:
                raise RuntimeError("Gentle retornou erro")
            data = resp.json()
            visemes = []
            for word in data.get("words", []):
                for phone in word.get("phones", []):
                    phoneme = phone.get("phone", "SIL").upper().split("_")[0]
                    duration = float(phone.get("duration", 0.1))
                    start = float(phone.get("start", 0.0))
                    viseme_name = _PHONEME_TO_VISEME.get(phoneme, "rest")
                    visemes.append(Viseme(name=viseme_name, start=start, end=start + duration))
            return visemes
        except Exception:
            raise

    def _extract_with_energy_analysis(self, audio_path: str) -> List[Viseme]:
        """Análise de energia + ZCR para visemas aproximados (fallback leve)."""
        try:
            import librosa
        except ImportError:
            raise ImportError("librosa é necessário para extração de visemas. pip install librosa")

        y, sr = librosa.load(audio_path, sr=None, mono=True)
        hop_length = int(sr / self.fps)  # 1 frame por hop
        frame_duration = hop_length / sr

        # Energia RMS por frame
        rms = librosa.feature.rms(y=y, hop_length=hop_length)[0]
        # Zero-crossing rate
        zcr = librosa.feature.zero_crossing_rate(y=y, hop_length=hop_length)[0]

        silence_threshold = np.percentile(rms, 20)
        voiced_threshold = np.percentile(zcr, 60)

        visemes: List[Viseme] = []
        for i, (r, z) in enumerate(zip(rms, zcr)):
            t_start = i * frame_duration
            t_end = t_start + frame_duration
            intensity = float(np.clip(r / (rms.max() + 1e-8), 0, 1))

            if r < silence_threshold:
                name = "rest"
            elif z > voiced_threshold:
                # Alta ZCR → fricativas (sh, fv, th)
                name = np.random.choice(["sh", "fv", "th"])
            else:
                # Baixa ZCR → vogais / sonoras
                name = np.random.choice(["ah", "oh", "ih", "mb", "td"])

            visemes.append(Viseme(name=name, start=t_start, end=t_end, intensity=intensity))

        logger.info(f"Visemas extraídos via energia: {len(visemes)} frames")
        return visemes

    # ------------------------------------------------------------------
    # Geração de curva labial
    # ------------------------------------------------------------------

    def generate_lip_curve(
        self,
        visemes: List[Viseme],
        total_frames: int,
    ) -> np.ndarray:
        """Gera curva de abertura dos lábios (0.0–1.0) por frame.

        Args:
            visemes:      Lista de visemas com timing.
            total_frames: Número total de frames do vídeo.

        Returns:
            Array shape (total_frames,) com valores 0.0–1.0
        """
        curve = np.zeros(total_frames, dtype=np.float32)

        # Mapeamento de abertura por visema (0=fechado, 1=totalmente aberto)
        _OPEN_AMOUNT = {
            "ah": 0.9, "oh": 0.7, "ih": 0.5, "eh": 0.6, "uh": 0.4,
            "er": 0.5, "ay": 0.7, "mb": 0.0, "fv": 0.1, "th": 0.2,
            "td": 0.3, "sh": 0.25, "kg": 0.3, "rest": 0.0,
        }

        for v in visemes:
            f_start = max(0, int(v.start * self.fps))
            f_end = min(total_frames, int(v.end * self.fps))
            if f_start >= f_end:
                continue
            amount = _OPEN_AMOUNT.get(v.name, 0.3) * v.intensity
            curve[f_start:f_end] = amount

        # Suavização gaussiana para movimentos naturais
        from scipy.ndimage import gaussian_filter1d
        curve = gaussian_filter1d(curve, sigma=2.0)
        return np.clip(curve, 0.0, 1.0)

    # ------------------------------------------------------------------
    # Conversão para blend shapes
    # ------------------------------------------------------------------

    def to_blend_shapes(self, lip_curve: np.ndarray) -> BlendShapes:
        """Converte curva labial em blend shapes.

        Retorna blend shapes compatíveis com Live Portrait / ARKit / Metahuman.
        """
        bs = BlendShapes(fps=self.fps)
        n = len(lip_curve)

        # jawOpen: abertura da mandíbula = diretamente proporcional à curva
        bs.shapes["jawOpen"] = lip_curve.copy()

        # mouthFunnel: arrondissement (vogais redondas)
        # Aproximado: maior em valores médios de abertura
        bs.shapes["mouthFunnel"] = np.clip(lip_curve * 0.6, 0, 1)

        # mouthSmile: pequeno sorriso base quando falando
        smile_base = np.full(n, 0.1, dtype=np.float32)
        smile_var = np.clip(lip_curve * 0.3, 0, 0.4)
        bs.shapes["mouthSmile_L"] = smile_base + smile_var
        bs.shapes["mouthSmile_R"] = smile_base + smile_var

        # mouthClose: fechamento (inverso da abertura)
        bs.shapes["mouthClose"] = np.clip(1.0 - lip_curve, 0, 1) * 0.3

        # eyeBlink: piscar suave independente da fala
        blink = np.zeros(n, dtype=np.float32)
        blink_interval = int(self.fps * 3.5)  # piscar a cada ~3.5s
        for i in range(0, n, blink_interval):
            dur = min(int(self.fps * 0.15), n - i)
            t = np.linspace(0, np.pi, dur)
            blink[i:i+dur] = np.sin(t) * 0.8
        bs.shapes["eyeBlink_L"] = blink
        bs.shapes["eyeBlink_R"] = blink

        logger.info(f"BlendShapes geradas: {list(bs.shapes.keys())} | frames={n}")
        return bs

    # ------------------------------------------------------------------
    # Síntese de áudio com visemes (Edge-TTS)
    # ------------------------------------------------------------------

    async def synthesize_with_visemes(self, text: str, avatar_id: str, language: str) -> dict:
        """Gera áudio com Edge-TTS e visemes sincronizados.
        
        Args:
            text: Texto a ser sintetizado
            avatar_id: ID do avatar (para seleção de voz)
            language: Idioma (pt-BR, en, es)
        
        Returns:
            Dict com 'audio' (base64) e 'visemes' (lista)
        """
        import edge_tts
        import base64
        import io
        
        # Definir voz baseada no idioma
        voices = {
            "pt-BR": "pt-BR-FranciscaNeural",
            "en": "en-US-JennyNeural",
            "es": "es-ES-ElviraNeural"
        }
        voice = voices.get(language, "pt-BR-FranciscaNeural")
        
        try:
            # Gerar áudio com Edge-TTS (usando io.BytesIO como no commit dc2395a)
            buf = io.BytesIO()
            communicate = edge_tts.Communicate(text, voice, rate="+0%", pitch="+0Hz")
            
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    buf.write(chunk["data"])
            
            audio_data = buf.getvalue()
            
            if not audio_data:
                logger.warning(f"Edge-TTS não retornou áudio para: {text[:50]}")
                return {"audio": None, "visemes": []}
            
            audio_b64 = base64.b64encode(audio_data).decode("utf-8")
            
            # Gerar visemes simulados (baseado no texto)
            visemes = []
            duration_per_char = 100  # ms por caractere
            
            for i, char in enumerate(text):
                # Mapeamento simples: vogais = "A", consoantes = "closed"
                if char.lower() in "aeiouáéíóú":
                    viseme = "A"
                elif char.lower() in "ãõ":
                    viseme = "O"
                elif char.lower() in "bcpfmv":
                    viseme = "M"
                elif char.lower() in "dtnls":
                    viseme = "L"
                elif char.lower() in "kg":
                    viseme = "K"
                else:
                    viseme = "closed"
                
                visemes.append({
                    "time_ms": i * duration_per_char,
                    "viseme": viseme
                })
            
            logger.info(f"Áudio gerado: {len(audio_data)} bytes, {len(visemes)} visemes")
            
            return {
                "audio": audio_b64,
                "visemes": visemes
            }
        
        except Exception as e:
            logger.error(f"Erro ao sintetizar áudio: {e}", exc_info=True)
            return {
                "audio": None,
                "visemes": []
            }
