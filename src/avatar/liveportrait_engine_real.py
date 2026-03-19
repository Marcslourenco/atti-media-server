"""src/avatar/liveportrait_engine_real.py

Motor de animação facial usando LivePortrait.

LivePortrait gera animação de retrato estático a partir de:
  - imagem de referência do avatar (PNG/JPG)
  - áudio de driving (WAV)

Dependências:
  - torch>=2.0.0
  - torchvision>=0.15.0
  - opencv-python>=4.8.0
  - LivePortrait (https://github.com/KwaiVGI/LivePortrait)

Instalação do LivePortrait:
  git clone https://github.com/KwaiVGI/LivePortrait /opt/liveportrait
  pip install -r /opt/liveportrait/requirements.txt
  export LIVEPORTRAIT_PATH=/opt/liveportrait
"""

from __future__ import annotations

import logging
import os
import sys
import tempfile
from typing import List, Optional

import numpy as np

logger = logging.getLogger(__name__)

_LIVEPORTRAIT_PATH = os.getenv("LIVEPORTRAIT_PATH", "/opt/liveportrait")


def _add_liveportrait_to_path() -> bool:
    """Adiciona LivePortrait ao sys.path se disponível."""
    if os.path.isdir(_LIVEPORTRAIT_PATH):
        if _LIVEPORTRAIT_PATH not in sys.path:
            sys.path.insert(0, _LIVEPORTRAIT_PATH)
        return True
    return False


class LivePortraitEngineReal:
    """Motor de animação facial via LivePortrait.

    Uso:
        engine = LivePortraitEngineReal()
        frames = engine.generate_animation("avatar.png", "audio.wav")
        # frames: lista de np.ndarray (BGR, shape H×W×3)
    """

    def __init__(self) -> None:
        self._pipeline = None
        self._device = self._detect_device()
        self._load_pipeline()

    def _detect_device(self) -> str:
        try:
            import torch
            if torch.cuda.is_available():
                logger.info("LivePortrait: usando GPU (CUDA)")
                return "cuda"
            if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
                logger.info("LivePortrait: usando GPU (MPS)")
                return "mps"
        except ImportError:
            pass
        logger.info("LivePortrait: usando CPU (pode ser lento)")
        return "cpu"

    def _load_pipeline(self) -> None:
        """Carrega pipeline LivePortrait."""
        lp_available = _add_liveportrait_to_path()
        if not lp_available:
            raise RuntimeError(
                f"LivePortrait não encontrado em LIVEPORTRAIT_PATH={_LIVEPORTRAIT_PATH}. "
                "Clone em https://github.com/KwaiVGI/LivePortrait e configure a variável."
            )

        try:
            # Importação do módulo LivePortrait (estrutura do repositório oficial)
            from src.pipelines.gradio_pipeline import GradioPipeline
            from omegaconf import OmegaConf

            cfg_path = os.path.join(_LIVEPORTRAIT_PATH, "configs", "inference.yaml")
            if not os.path.isfile(cfg_path):
                raise FileNotFoundError(f"Config LivePortrait não encontrado: {cfg_path}")

            cfg = OmegaConf.load(cfg_path)
            self._pipeline = GradioPipeline(cfg, device=self._device)
            logger.info("LivePortrait pipeline carregado com sucesso.")

        except ImportError as exc:
            logger.error(f"Dependência do LivePortrait ausente: {exc}")
            raise RuntimeError(f"LivePortraitEngineReal: dependência faltando → {exc}") from exc
        except Exception as exc:
            logger.error(f"Falha ao carregar LivePortrait: {exc}", exc_info=True)
            raise RuntimeError(f"LivePortraitEngineReal: falha ao inicializar → {exc}") from exc

    def generate_animation(
        self,
        avatar_image_path: str,
        audio_path: str,
        fps: int = 30,
        output_resolution: Optional[tuple] = None,
    ) -> List[np.ndarray]:
        """Gera frames animados do avatar sincronizados com o áudio.

        Args:
            avatar_image_path: Caminho para imagem PNG/JPG do avatar.
            audio_path:        Caminho para áudio WAV de driving.
            fps:               Frames por segundo (default 30).
            output_resolution: Tuple (W, H) para resize. None = resolução original.

        Returns:
            Lista de frames como np.ndarray (BGR, dtype=uint8, shape H×W×3)
        """
        if not os.path.isfile(avatar_image_path):
            raise FileNotFoundError(f"Imagem do avatar não encontrada: {avatar_image_path}")
        if not os.path.isfile(audio_path):
            raise FileNotFoundError(f"Áudio não encontrado: {audio_path}")

        if self._pipeline is None:
            raise RuntimeError("Pipeline LivePortrait não inicializado.")

        logger.info(
            f"Gerando animação | avatar={avatar_image_path} | áudio={audio_path} | fps={fps}"
        )

        try:
            import cv2
        except ImportError:
            raise ImportError("opencv-python é necessário. pip install opencv-python")

        # Carrega imagem do avatar
        source_img = cv2.imread(avatar_image_path)
        if source_img is None:
            raise ValueError(f"Não foi possível ler imagem: {avatar_image_path}")

        # Chama pipeline LivePortrait
        # A API exata depende da versão do LivePortrait instalada.
        # Adaptamos para a interface mais comum (audio-driven).
        with tempfile.TemporaryDirectory() as tmpdir:
            output_video = os.path.join(tmpdir, "output.mp4")

            # Interface: pipeline.execute(source, audio, output, fps)
            self._pipeline.execute(
                source_image=avatar_image_path,
                driving_audio=audio_path,
                output_path=output_video,
                fps=fps,
            )

            if not os.path.isfile(output_video):
                raise RuntimeError("LivePortrait não gerou arquivo de saída.")

            # Extrai frames do vídeo gerado
            frames: List[np.ndarray] = []
            cap = cv2.VideoCapture(output_video)
            while True:
                ret, frame = cap.read()
                if not ret:
                    break
                if output_resolution is not None:
                    frame = cv2.resize(frame, output_resolution)
                frames.append(frame)
            cap.release()

        logger.info(f"Animação gerada: {len(frames)} frames")
        return frames

    def save_video(
        self,
        frames: List[np.ndarray],
        output_path: str,
        fps: int = 30,
        audio_path: Optional[str] = None,
    ) -> str:
        """Salva frames como vídeo MP4, opcionalmente com áudio.

        Args:
            frames:      Lista de frames BGR (np.ndarray).
            output_path: Caminho de saída (.mp4).
            fps:         Frames por segundo.
            audio_path:  Se fornecido, mistura o áudio no vídeo final via ffmpeg.

        Returns:
            Caminho do arquivo de saída.
        """
        try:
            import cv2
        except ImportError:
            raise ImportError("opencv-python necessário. pip install opencv-python")

        if not frames:
            raise ValueError("Nenhum frame para salvar.")

        h, w = frames[0].shape[:2]
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        tmp_video = output_path + ".tmp.mp4"
        out = cv2.VideoWriter(tmp_video, fourcc, fps, (w, h))
        for f in frames:
            out.write(f)
        out.release()

        if audio_path and os.path.isfile(audio_path):
            # Mescla vídeo + áudio via ffmpeg
            import subprocess
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
            if result.returncode != 0:
                logger.warning(f"ffmpeg falhou ao mesclar áudio: {result.stderr}")
                os.rename(tmp_video, output_path)
            else:
                os.remove(tmp_video)
                logger.info(f"Vídeo com áudio salvo: {output_path}")
        else:
            os.rename(tmp_video, output_path)
            logger.info(f"Vídeo salvo (sem áudio): {output_path}")

        return output_path
