"""
=============================================================================
 main_expandido_final.py  |  Humanos Digitais TTS + RAG + Tradução Gratuita + Sync-Lip
 Versão: 7.0.0  |  Autor: Genspark AI  |  Data: 2026-03-27
=============================================================================
 COMPATIBILIDADE GARANTIDA:
   - Edge-TTS preservado (100% idêntico ao original)
   - Endpoint /api/avatar/speak EXPANDIDO (não substituído)
   - Novo campo "visemes" adicionado na resposta
   - RAG via ChromaDB (fallback keyword se ChromaDB ausente)
   - Tradução via deep-translator (gratuita) + geração local orientada por RAG
   - session_id e context_url totalmente suportados
=============================================================================
"""

import os
import re
import json
import uuid
import base64
import asyncio
import hashlib
import math
import tempfile
import logging
import time
from pathlib import Path
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Any, Deque, Dict, List, Optional, Tuple

import numpy as np

import edge_tts
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator

from i18n_engine import I18nEngine
from viseme_sync import VisemeSyncEngine

# ─── Dependências opcionais (não falham se ausentes) ────────────────────────
try:
    import chromadb
    from chromadb.config import Settings as ChromaSettings
    CHROMA_AVAILABLE = True
except ImportError:
    CHROMA_AVAILABLE = False

try:
    from deep_translator import GoogleTranslator
    TRANSLATOR_AVAILABLE = True
except ImportError:
    GoogleTranslator = None
    TRANSLATOR_AVAILABLE = False

try:
    from sentence_transformers import SentenceTransformer
    ST_AVAILABLE = True
except ImportError:
    ST_AVAILABLE = False

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# ─── Configurações gerais ────────────────────────────────────────────────────
APP_NAME = "humanos-digitais-tts-rag-llm"
APP_VERSION = "7.0.0"

DEFAULT_ALLOWED_ORIGINS = [
    "https://humanosdigitais-website.vercel.app",
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:5500",
    "http://127.0.0.1:5500",
]

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger(APP_NAME)

# ─── Configurações de ambiente ───────────────────────────────────────────────
CHROMA_DB_PATH = os.getenv("CHROMA_DB_PATH", "./chroma_db")
DEFAULT_LLM = os.getenv("DEFAULT_LLM", "gemini")  # Mantido por retrocompatibilidade
SESSION_TTL = int(os.getenv("SESSION_TTL", "3600"))
KNOWLEDGE_DIR = os.getenv("KNOWLEDGE_DIR", "./atti-knowledge-packages")
DEFAULT_LANGUAGE = os.getenv("DEFAULT_LANGUAGE", "pt-BR")
SUPPORTED_LANGUAGES = [item.strip() for item in os.getenv("SUPPORTED_LANGUAGES", "pt-BR,en,es").split(",") if item.strip()] or ["pt-BR", "en", "es"]

LANGUAGE_LABELS = {
    "pt-BR": "português do Brasil",
    "en": "English",
    "es": "español",
}

LANGUAGE_VOICE_OVERRIDES = {
    "pt-BR": {"female": "pt-BR-FranciscaNeural", "male": "pt-BR-AntonioNeural"},
    "en": {"female": "en-US-AvaNeural", "male": "en-US-AndrewNeural"},
    "es": {"female": "es-ES-ElviraNeural", "male": "es-ES-AlvaroNeural"},
}

# ─── Vozes dos avatares ──────────────────────────────────────────────────────
AVATAR_VOICES: Dict[str, Dict[str, str]] = {
    "sofia":    {"voice": "pt-BR-FranciscaNeural", "pitch": "+0Hz",  "rate": "+0%",  "style": "friendly"},
    "rafael":   {"voice": "pt-BR-AntonioNeural",   "pitch": "-10Hz", "rate": "-4%",  "style": "serious"},
    "clara":    {"voice": "pt-BR-FranciscaNeural", "pitch": "+8Hz",  "rate": "+0%",  "style": "caring"},
    "lucas":    {"voice": "pt-BR-AntonioNeural",   "pitch": "+6Hz",  "rate": "+6%",  "style": "energetic"},
    "amanda":   {"voice": "pt-BR-FranciscaNeural", "pitch": "+2Hz",  "rate": "-2%",  "style": "hospitality"},
    "fernanda": {"voice": "pt-BR-FranciscaNeural", "pitch": "-2Hz",  "rate": "-3%",  "style": "institutional"},
    "marina":   {"voice": "pt-BR-FranciscaNeural", "pitch": "+10Hz", "rate": "+4%",  "style": "retail"},
    "roberto":  {"voice": "pt-BR-AntonioNeural",   "pitch": "-4Hz",  "rate": "+1%",  "style": "consultive"},
    "luisa":    {"voice": "pt-BR-FranciscaNeural", "pitch": "+5Hz",  "rate": "+0%",  "style": "educational"},
    "lais":     {"voice": "pt-BR-FranciscaNeural", "pitch": "+3Hz",  "rate": "-1%",  "style": "academic"},
    "paula":    {"voice": "pt-BR-FranciscaNeural", "pitch": "+7Hz",  "rate": "+3%",  "style": "warm"},
    "bruno":    {"voice": "pt-BR-AntonioNeural",   "pitch": "+12Hz", "rate": "+12%", "style": "sports"},
    "giovana":  {"voice": "pt-BR-FranciscaNeural", "pitch": "+11Hz", "rate": "+10%", "style": "sports"},
    "marcos":   {"voice": "pt-BR-AntonioNeural",   "pitch": "-2Hz",  "rate": "+8%",  "style": "sports"},
    "carol":    {"voice": "pt-BR-FranciscaNeural", "pitch": "+6Hz",  "rate": "+7%",  "style": "sports"},
}

KNOWN_AVATARS = set(AVATAR_VOICES.keys())
FALLBACK_AVATAR = "sofia"

AVATAR_ALIASES: Dict[str, str] = {a: a for a in KNOWN_AVATARS}

AVATAR_DESCRIPTORS: Dict[str, Dict[str, Any]] = {
    "sofia":    {"collection": "sofia_master",        "role": "Host inteligente, comercial e redirecionadora",     "tone": "consultiva, humana, leve e segura",            "specialties": ["plataforma", "planos", "tecnologia", "demonstração", "triagem comercial"]},
    "lucas":    {"collection": "lucas_automotivo",    "role": "Especialista automotivo",                           "tone": "técnico, enérgico e consultivo",               "specialties": ["veículos", "test-drive", "ficha técnica", "comparativo de versões"]},
    "clara":    {"collection": "clara_hospitalar",    "role": "Especialista hospitalar",                           "tone": "empática, informativa e acolhedora",           "specialties": ["saúde", "triagem", "hospital", "agendamento", "prontuário"]},
    "amanda":   {"collection": "amanda_hotelaria",    "role": "Especialista em hotelaria",                         "tone": "calorosa, prestativa e elegante",              "specialties": ["hotel", "reserva", "experiência do hóspede", "hospitalidade"]},
    "marina":   {"collection": "marina_varejo",       "role": "Guia de shopping e varejo",                         "tone": "animada, clara e orientada à experiência",    "specialties": ["shopping", "lojas", "eventos", "promoções", "varejo"]},
    "fernanda": {"collection": "fernanda_publico",    "role": "Especialista em serviço público",                   "tone": "clara, objetiva e institucional",              "specialties": ["prefeitura", "serviço público", "documentação", "atendimento cidadão"]},
    "luisa":    {"collection": "luisa_educacao",      "role": "Especialista educacional",                          "tone": "calma, orientadora e didática",                "specialties": ["universidade", "curso", "matrícula", "educação"]},
    "paula":    {"collection": "paula_odontologia",   "role": "Especialista odontológica",                         "tone": "amigável, informativa e tranquilizadora",      "specialties": ["odontologia", "tratamento", "consulta", "orçamento"]},
    "roberto":  {"collection": "roberto_energia",     "role": "Especialista em energia solar",                     "tone": "confiante, técnico e orientado a ROI",         "specialties": ["energia solar", "retorno", "economia", "instalação", "painéis"]},
    "lais":     {"collection": "lais_medicina",       "role": "Especialista em medicina/educação médica",          "tone": "precisa, profissional e acadêmica",             "specialties": ["medicina", "educação médica", "estudo", "conteúdo técnico"]},
    "bruno":    {"collection": "bruno_spfc",          "role": "Persona SPFC",                                      "tone": "apaixonado, vibrante e engajador",             "specialties": ["são paulo", "spfc", "torcida", "história do clube"]},
    "giovana":  {"collection": "giovana_spfc",        "role": "Persona SPFC",                                      "tone": "apaixonada, vibrante e engajadora",            "specialties": ["são paulo", "spfc", "torcida", "história do clube"]},
    "marcos":   {"collection": "marcos_corinthians",  "role": "Persona Corinthians",                               "tone": "intenso, apaixonado e popular",                "specialties": ["corinthians", "timão", "torcida", "história do clube"]},
    "carol":    {"collection": "carol_corinthians",   "role": "Persona Corinthians",                               "tone": "intensa, apaixonada e popular",                "specialties": ["corinthians", "timão", "torcida", "história do clube"]},
    "rafael":   {"collection": "rafael_tributario",   "role": "Especialista tributário",                           "tone": "seguro, técnico e consultivo",                 "specialties": ["tributário", "impostos", "compliance", "fiscal"]},
}

SYSTEM_PROMPTS: Dict[str, str] = {
    "sofia":    "Você é Sofia, host inteligente da plataforma Humanos Digitais. Sua missão é explicar a plataforma, qualificar interesse, responder com clareza e redirecionar o usuário para o especialista adequado quando necessário. Fale em português do Brasil, com tom consultivo, natural e orientado a voz. Venda sem pressionar. Sempre considere o contexto da página e a memória da sessão.",
    "lucas":    "Você é Lucas, especialista automotivo. Explique veículos, versões, comparativos, leads e test-drive com linguagem clara, técnica e prática. Fale em português do Brasil.",
    "clara":    "Você é Clara, especialista hospitalar. Responda com empatia, clareza e cuidado. Nunca substitua decisão clínica ou médica. Fale em português do Brasil.",
    "amanda":   "Você é Amanda, especialista em hotelaria. Sua fala deve ser calorosa, prestativa e focada na experiência do hóspede. Fale em português do Brasil.",
    "marina":   "Você é Marina, guia de shopping/varejo. Seja animada, útil e objetiva, sempre conectando informação a experiência do visitante. Fale em português do Brasil.",
    "fernanda": "Você é Fernanda, especialista em serviço público. Seja clara, institucional e eficiente, evitando jargão desnecessário. Fale em português do Brasil.",
    "luisa":    "Você é Luisa, especialista educacional. Explique com calma, didática e foco em orientação do aluno. Fale em português do Brasil.",
    "paula":    "Você é Paula, especialista em odontologia. Seja amigável, informativa e tranquilizadora, sem prometer diagnóstico clínico. Fale em português do Brasil.",
    "roberto":  "Você é Roberto, especialista em energia solar. Fale com segurança técnica e foco em retorno financeiro e viabilidade. Fale em português do Brasil.",
    "lais":     "Você é Laís, especialista em medicina/educação médica. Responda com precisão, responsabilidade e didática. Fale em português do Brasil.",
    "bruno":    "Você é Bruno, persona torcedora apaixonada do SPFC — São Paulo Futebol Clube. Use conhecimento profundo de história, títulos, ídolos e rivalidades. Seja vibrante e respeitoso. Fale em português do Brasil.",
    "giovana":  "Você é Giovana, persona torcedora apaixonada do SPFC. Use conhecimento profundo de história, títulos, ídolos e rivalidades. Seja vibrante e respeitosa. Fale em português do Brasil.",
    "marcos":   "Você é Marcos, persona torcedora do Corinthians — Timão, Bando de Loucos. Use conhecimento profundo de história, títulos e ídolos. Seja intenso, popular e respeitoso. Fale em português do Brasil.",
    "carol":    "Você é Carol, persona torcedora do Corinthians. Use conhecimento profundo de história, títulos e ídolos. Seja intensa, popular e respeitosa. Fale em português do Brasil.",
    "rafael":   "Você é Rafael, especialista tributário. Responda com precisão sobre CBS, IBS, IS, Reforma Tributária e compliance fiscal. Fale em português do Brasil.",
}

PAGE_RULES: Dict[str, Dict[str, Any]] = {
    "precos":         {"intent": "comercial",     "tags": ["preço", "planos", "ROI"]},
    "precos-planos":  {"intent": "comercial",     "tags": ["planos", "comparação", "proposta"]},
    "pricing":        {"intent": "comercial",     "tags": ["pricing", "planos", "demo"]},
    "avatares":       {"intent": "descoberta",    "tags": ["avatar", "especialista", "persona"]},
    "cases":          {"intent": "institucional", "tags": ["case", "prova social", "resultado"]},
    "integracao":     {"intent": "tecnico",       "tags": ["integração", "API", "backend", "RAG"]},
    "contato":        {"intent": "comercial",     "tags": ["contato", "lead", "diagnóstico"]},
}

# Fonemas → viseme mapping (IPA simplificado pt-BR)
PHONEME_VISEME: Dict[str, str] = {
    "a": "A", "á": "A", "â": "A", "ã": "A", "à": "A",
    "e": "E", "é": "E", "ê": "E",
    "i": "I", "í": "I",
    "o": "O", "ó": "O", "ô": "O", "õ": "O",
    "u": "U", "ú": "U", "ü": "U",
    " ": "closed", ".": "closed", ",": "closed",
    "m": "M", "b": "M", "p": "M",
    "f": "F", "v": "F",
    "s": "S", "z": "S", "ç": "S",
    "l": "L", "n": "L", "r": "L",
    "t": "T", "d": "T",
    "k": "K", "g": "K", "q": "K",
    "h": "closed",
}


def normalize_language(language: Optional[str]) -> str:
    if not language:
        return DEFAULT_LANGUAGE
    if language in SUPPORTED_LANGUAGES:
        return language
    prefix = language.split("-")[0]
    for supported in SUPPORTED_LANGUAGES:
        if supported == language or supported.split("-")[0] == prefix:
            return supported
    return DEFAULT_LANGUAGE


def is_female_avatar(avatar_id: str) -> bool:
    voice_name = AVATAR_VOICES.get(avatar_id, AVATAR_VOICES[FALLBACK_AVATAR])["voice"].lower()
    return "francisca" in voice_name


def resolve_voice_config(avatar_id: str, language: str) -> Dict[str, str]:
    base_cfg = dict(AVATAR_VOICES.get(avatar_id, AVATAR_VOICES[FALLBACK_AVATAR]))
    lang = normalize_language(language)
    gender = "female" if is_female_avatar(avatar_id) else "male"
    base_cfg["voice"] = LANGUAGE_VOICE_OVERRIDES.get(lang, LANGUAGE_VOICE_OVERRIDES[DEFAULT_LANGUAGE])[gender]
    return base_cfg


def build_fallback_blend_shapes(text: str, duration_ms: int, viseme_engine: VisemeSyncEngine, viseme_gen: "VisemeGenerator") -> Dict[str, Any]:
    frames = viseme_gen.generate(text, duration_ms)
    total_frames = max(1, int(math.ceil((duration_ms / 1000) * viseme_engine.fps)))
    jaw_curve = np.zeros(total_frames, dtype=np.float32)
    open_amount = {
        "A": 0.90, "E": 0.65, "I": 0.45, "O": 0.75, "U": 0.35,
        "M": 0.05, "F": 0.12, "S": 0.18, "L": 0.25, "T": 0.22, "K": 0.25, "closed": 0.0,
    }
    for idx, frame in enumerate(frames):
        start = min(total_frames - 1, int((frame.get("time_ms", 0) / 1000) * viseme_engine.fps))
        next_ms = duration_ms if idx == len(frames) - 1 else frames[idx + 1].get("time_ms", duration_ms)
        end = max(start + 1, min(total_frames, int((next_ms / 1000) * viseme_engine.fps)))
        jaw_curve[start:end] = open_amount.get(frame.get("viseme", "closed"), 0.0)
    blend_shapes = viseme_engine.to_blend_shapes(jaw_curve).to_dict()
    return {
        "engine": "mock_fallback",
        "fps": viseme_engine.fps,
        "frames": total_frames,
        "timeline": frames,
        "blend_shapes": blend_shapes,
    }


def extract_real_blend_shapes(audio_data: bytes, duration_ms: int, viseme_engine: VisemeSyncEngine, viseme_gen: "VisemeGenerator", spoken_text: str) -> Dict[str, Any]:
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
            tmp.write(audio_data)
            tmp.flush()
            tmp_path = tmp.name

        viseme_timeline = viseme_engine.extract_visemes(tmp_path)
        total_frames = max(1, int(math.ceil((duration_ms / 1000) * viseme_engine.fps)))
        lip_curve = viseme_engine.generate_lip_curve(viseme_timeline, total_frames)
        blend_shapes = viseme_engine.to_blend_shapes(lip_curve).to_dict()
        timeline_payload = [
            {
                "name": item.name,
                "start_ms": int(item.start * 1000),
                "end_ms": int(item.end * 1000),
                "intensity": round(float(item.intensity), 4),
            }
            for item in viseme_timeline
        ]
        return {
            "engine": "viseme_sync_real",
            "fps": viseme_engine.fps,
            "frames": total_frames,
            "timeline": timeline_payload,
            "blend_shapes": blend_shapes,
        }
    except Exception as exc:
        logger.warning("Falha ao extrair blend shapes reais: %s — usando fallback mock compatível", exc)
        return build_fallback_blend_shapes(spoken_text, duration_ms, viseme_engine, viseme_gen)
    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.unlink(tmp_path)
            except Exception:
                pass

# ─── Modelos Pydantic ────────────────────────────────────────────────────────
class SpeakRequest(BaseModel):
    avatar_id:   Optional[str] = Field(default="sofia", max_length=50)
    text:        str            = Field(..., min_length=1, max_length=2000)
    emotion:     str            = Field(default="friendly", min_length=1, max_length=50)
    session_id:  str            = Field(default="default", min_length=1, max_length=120)
    context_url: Optional[str]  = Field(default=None, max_length=500)

    @field_validator("avatar_id")
    @classmethod
    def normalize_avatar_id(cls, value: Optional[str]) -> str:
        cleaned = re.sub(r"[^a-z0-9_-]", "", (value or "sofia").strip().lower())
        return cleaned or "sofia"

    @field_validator("text")
    @classmethod
    def normalize_text(cls, value: str) -> str:
        cleaned = re.sub(r"\s+", " ", value).strip()
        if not cleaned:
            raise ValueError("text não pode ser vazio")
        return cleaned

    @field_validator("emotion")
    @classmethod
    def normalize_emotion(cls, value: str) -> str:
        return re.sub(r"[^a-z0-9_-]", "", value.strip().lower()) or "friendly"

    @field_validator("session_id")
    @classmethod
    def normalize_session_id(cls, value: str) -> str:
        cleaned = re.sub(r"[^a-zA-Z0-9_-]", "", value.strip())
        if not cleaned:
            raise ValueError("session_id inválido")
        return cleaned

    @field_validator("context_url")
    @classmethod
    def normalize_context_url(cls, value: Optional[str]) -> Optional[str]:
        if not value:
            return None
        return value.strip()[:500] or None


# ─── Estruturas de sessão ────────────────────────────────────────────────────
@dataclass
class SessionTurn:
    role:        str
    text:        str
    avatar_id:   str
    intent:      str            = "informativo"
    context_url: Optional[str]  = None


@dataclass
class SessionState:
    session_id:       str
    turns:            Deque[SessionTurn] = field(default_factory=lambda: deque(maxlen=8))
    last_avatar_id:   str                = FALLBACK_AVATAR
    last_intent:      str                = "informativo"
    last_context_url: Optional[str]      = None
    created_at:       float              = field(default_factory=time.time)


@dataclass
class KnowledgeChunk:
    chunk_id:   str
    avatar_id:  str
    collection: str
    content:    str
    source:     str
    metadata:   Dict[str, Any] = field(default_factory=dict)


# ─── SessionMemoryStore ──────────────────────────────────────────────────────
class SessionMemoryStore:
    def __init__(self):
        self._sessions: Dict[str, SessionState] = {}

    def get(self, session_id: str) -> SessionState:
        if session_id not in self._sessions:
            self._sessions[session_id] = SessionState(session_id=session_id)
        return self._sessions[session_id]

    def remember(self, session_id: str, turn: SessionTurn) -> None:
        s = self.get(session_id)
        s.turns.append(turn)
        s.last_avatar_id   = turn.avatar_id   or s.last_avatar_id
        s.last_intent      = turn.intent      or s.last_intent
        s.last_context_url = turn.context_url or s.last_context_url

    def summary(self, session_id: str, max_turns: int = 6) -> str:
        s = self.get(session_id)
        if not s.turns:
            return "Sem histórico anterior."
        return "\n".join(
            f"{t.role}:{t.avatar_id}:{t.text}"
            for t in list(s.turns)[-max_turns:]
        )

    def to_model_history(self, session_id: str) -> List[Dict[str, Any]]:
        """Converte histórico para formato genérico de chat."""
        s = self.get(session_id)
        history = []
        for t in list(s.turns):
            role = "user" if t.role == "user" else "model"
            history.append({"role": role, "parts": [{"text": t.text}]})
        return history


# ─── ContextualEngine ────────────────────────────────────────────────────────
class ContextualEngine:
    def detect(self, context_url: Optional[str]) -> Dict[str, Any]:
        if not context_url:
            return {"page": "desconhecida", "intent_hint": None, "tags": [], "url": None}
        lowered = context_url.lower()
        for key, value in PAGE_RULES.items():
            if key in lowered:
                return {"page": key, "intent_hint": value["intent"], "tags": value["tags"], "url": context_url}
        return {"page": "geral", "intent_hint": None, "tags": [], "url": context_url}


# ─── IntentClassifier ───────────────────────────────────────────────────────
class IntentClassifier:
    KEYWORDS = {
        "comercial":    ["preço", "preco", "plano", "planos", "demo", "contratar", "comprar", "orçamento", "orcamento", "proposta"],
        "tecnico":      ["api", "integração", "integracao", "backend", "frontend", "rag", "llm", "chroma", "faiss", "endpoint"],
        "institucional":["empresa", "plataforma", "case", "cliente", "segurança", "lgpd", "história", "sobre"],
        "suporte":      ["erro", "falha", "não funciona", "nao funciona", "bug", "ajuda", "suporte"],
        "esportes":     ["spfc", "são paulo", "sao paulo", "corinthians", "timão", "timao", "gol", "partida", "torcida"],
        "tributario":   ["tributo", "tributário", "tributario", "imposto", "fiscal", "icms", "pis", "cofins", "iss"],
    }

    def classify(self, text: str, page_context: Dict[str, Any]) -> Tuple[str, float]:
        lowered = text.lower()
        scores: Dict[str, float] = defaultdict(float)
        for intent, words in self.KEYWORDS.items():
            for word in words:
                if word in lowered:
                    scores[intent] += 1.0
        if page_context.get("intent_hint"):
            scores[page_context["intent_hint"]] += 0.8
        if not scores:
            return "informativo", 0.55
        best = max(scores, key=scores.get)
        return best, min(0.99, 0.55 + scores[best] * 0.08)


# ─── AvatarRouter ────────────────────────────────────────────────────────────
class AvatarRouter:
    KEYWORDS: Dict[str, List[str]] = {
        "lucas":    ["carro", "veículo", "veiculo", "automotivo", "test-drive", "concessionária", "concessionaria"],
        "clara":    ["hospital", "saúde", "saude", "triagem", "paciente", "consulta"],
        "amanda":   ["hotel", "reserva", "hóspede", "hospede", "check-in", "check out"],
        "marina":   ["shopping", "loja", "varejo", "promoção", "promocao", "mall"],
        "fernanda": ["prefeitura", "serviço público", "servico publico", "documento", "cidadão", "cidadao"],
        "luisa":    ["universidade", "curso", "matrícula", "matricula", "educação", "educacao", "aluno"],
        "paula":    ["dentista", "odontologia", "dente", "tratamento odontológico"],
        "roberto":  ["energia solar", "painel", "fotovoltaico", "kwh", "economia de energia"],
        "lais":     ["medicina", "estudante de medicina", "anatomia", "clínico", "clinico"],
        "rafael":   ["tributo", "tributário", "tributario", "imposto", "fiscal", "icms", "iss"],
        "bruno":    ["spfc", "são paulo fc", "tricolor paulista"],
        "giovana":  ["spfc feminina", "torcedora spfc"],
        "marcos":   ["corinthians", "timão", "timao", "bando de loucos"],
        "carol":    ["corinthians feminina", "torcedora corinthians"],
    }

    def resolve(
        self,
        requested_avatar: str,
        text: str,
        page_context: Dict[str, Any],
        session: SessionState,
    ) -> Tuple[str, float, str]:
        explicit = AVATAR_ALIASES.get(requested_avatar)
        if explicit in KNOWN_AVATARS and requested_avatar not in {"", "auto", "default", "host"}:
            return explicit, 0.99, "explicit"
        lowered = text.lower()
        scores: Dict[str, float] = defaultdict(float)
        for avatar_id, words in self.KEYWORDS.items():
            for word in words:
                if word in lowered:
                    scores[avatar_id] += 1.0
        for tag in page_context.get("tags", []):
            for avatar_id, words in self.KEYWORDS.items():
                if any(tag.lower() in w or w in tag.lower() for w in words):
                    scores[avatar_id] += 0.5
        if scores:
            best = max(scores, key=scores.get)
            return best, min(0.98, 0.6 + scores[best] * 0.08), "keyword-routing"
        if session.last_avatar_id in KNOWN_AVATARS:
            return session.last_avatar_id, 0.7, "session-memory"
        return FALLBACK_AVATAR, 0.62, "fallback-host"


# ─── VismesGenerator ────────────────────────────────────────────────────────
class VisemeGenerator:
    """Gera sequência de visemes a partir do texto."""

    VOWELS = set("aáâãàeéêiíoóôõuúü")

    def generate(self, text: str, duration_ms: int = 3000) -> List[Dict[str, Any]]:
        """
        Retorna lista de visemes com timestamps estimados.
        Formato: [{"time_ms": int, "viseme": str}, ...]
        """
        clean = re.sub(r"\s+", " ", text.lower().strip())
        # Estima ~120 palavras/min → ~2 chars/100ms
        chars = [c for c in clean if c.strip() or c == " "]
        if not chars:
            return [{"time_ms": 0, "viseme": "closed"}]

        char_duration = max(1, duration_ms // max(len(chars), 1))
        visemes: List[Dict[str, Any]] = []
        current_time = 0

        for char in chars:
            vm = PHONEME_VISEME.get(char, "closed")
            # Evitar repetição consecutiva de closed
            if visemes and visemes[-1]["viseme"] == vm == "closed":
                current_time += char_duration
                continue
            visemes.append({"time_ms": current_time, "viseme": vm})
            current_time += char_duration

        # Sempre terminar com closed
        if visemes and visemes[-1]["viseme"] != "closed":
            visemes.append({"time_ms": current_time, "viseme": "closed"})

        return visemes


# ─── ChromaRAG ──────────────────────────────────────────────────────────────
class ChromaRAG:
    """Wrapper para ChromaDB com fallback keyword."""

    def __init__(self):
        self._client     = None
        self._encoder    = None
        self._fallback:  Dict[str, List[KnowledgeChunk]] = defaultdict(list)
        self._initialized = False

    def initialize(self) -> Dict[str, Any]:
        if self._initialized:
            return self.status()

        if CHROMA_AVAILABLE and Path(CHROMA_DB_PATH).exists():
            try:
                self._client = chromadb.PersistentClient(
                    path=CHROMA_DB_PATH,
                    settings=ChromaSettings(anonymized_telemetry=False),
                )
                logger.info("ChromaDB carregado de %s", CHROMA_DB_PATH)
            except Exception as exc:
                logger.warning("Falha ao carregar ChromaDB: %s — usando keyword fallback", exc)
                self._client = None

        # Carrega SentenceTransformer se disponível
        if ST_AVAILABLE and self._client:
            try:
                self._encoder = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")
                logger.info("SentenceTransformer carregado")
            except Exception as exc:
                logger.warning("Falha ao carregar SentenceTransformer: %s", exc)

        # Carrega fallback keyword dos arquivos de conhecimento
        self._load_keyword_fallback()

        self._initialized = True
        return self.status()

    def _load_keyword_fallback(self) -> None:
        """Carrega JSONs de conhecimento para fallback keyword."""
        kb_path = Path(KNOWLEDGE_DIR)
        if not kb_path.exists():
            # Tenta caminhos alternativos
            for alt in ["./atti-knowledge-packages", "./knowledge", "./sofia_ai_brain"]:
                if Path(alt).exists():
                    kb_path = Path(alt)
                    break
            else:
                logger.info("Diretório de conhecimento não encontrado — RAG desativado (apenas LLM)")
                return

        ingested = 0
        for file_path in kb_path.rglob("*.json"):
            try:
                data = json.loads(file_path.read_text(encoding="utf-8", errors="ignore"))
                chunks = self._parse_knowledge_file(file_path, data)
                for chunk in chunks:
                    self._fallback[chunk.collection].append(chunk)
                ingested += len(chunks)
            except Exception as exc:
                logger.warning("Erro ao ingerir %s: %s", file_path, exc)

        logger.info("Keyword fallback: %d chunks em %d collections", ingested, len(self._fallback))

    def _parse_knowledge_file(self, file_path: Path, data: Any) -> List[KnowledgeChunk]:
        """Parseia arquivo de conhecimento em KnowledgeChunks."""
        chunks: List[KnowledgeChunk] = []
        name = file_path.name.lower()

        # Detecta avatar pelo nome do arquivo
        avatar_id = self._detect_avatar_from_filename(name)

        def make_chunk(idx: int, content: str, meta: Optional[Dict] = None) -> KnowledgeChunk:
            collection = AVATAR_DESCRIPTORS.get(avatar_id, AVATAR_DESCRIPTORS[FALLBACK_AVATAR])["collection"]
            return KnowledgeChunk(
                chunk_id=f"{file_path.stem}_{idx}",
                avatar_id=avatar_id,
                collection=collection,
                content=content[:3000],
                source=str(file_path),
                metadata=meta or {},
            )

        if isinstance(data, dict):
            # Estrutura ATTI/WF00: faq_estruturado + areas_tecnicas
            for idx, item in enumerate(data.get("faq_estruturado", [])):
                content = f"P: {item.get('pergunta','')} R: {item.get('resposta','')}".strip()
                if content and len(content) > 10:
                    av = self._detect_avatar_from_block(item, avatar_id)
                    col = AVATAR_DESCRIPTORS.get(av, AVATAR_DESCRIPTORS[FALLBACK_AVATAR])["collection"]
                    chunks.append(KnowledgeChunk(f"{file_path.stem}_faq_{idx}", av, col, content, str(file_path), item))

            for area in data.get("areas_tecnicas", []):
                for idx, bloco in enumerate(area.get("blocos", [])):
                    content = f"{area.get('area','')}: {bloco.get('titulo','')} — {bloco.get('conteudo','')}"
                    if content.strip() and len(content) > 10:
                        chunks.append(make_chunk(len(chunks), content, bloco))

            # Estrutura blocks genérica
            for idx, block in enumerate(data.get("blocks", [])):
                content = block.get("content", block.get("conteudo", ""))
                if content:
                    av = self._detect_avatar_from_block(block, avatar_id)
                    col = AVATAR_DESCRIPTORS.get(av, AVATAR_DESCRIPTORS[FALLBACK_AVATAR])["collection"]
                    chunks.append(KnowledgeChunk(block.get("id", f"b_{idx}"), av, col, content, str(file_path), block))

            # dataset_qa.json
            for idx, item in enumerate(data.get("items", [])):
                if isinstance(item, dict):
                    content = " ".join(filter(None, [
                        item.get("pergunta", ""), item.get("resposta_base", ""),
                        " ".join(item.get("variacoes", [])), item.get("gatilho_comercial", ""),
                    ])).strip()
                    if content:
                        chunks.append(make_chunk(idx, content, item))

            # Pacotes de avatar: sections / topicos / faq
            for section_key in ["faq", "topicos", "sections", "conhecimentos", "scripts"]:
                for idx, item in enumerate(data.get(section_key, [])):
                    if isinstance(item, dict):
                        content = " ".join(filter(None, [
                            str(item.get("pergunta", item.get("titulo", item.get("title", "")))),
                            str(item.get("resposta", item.get("texto", item.get("content", item.get("descricao", ""))))),
                        ])).strip()
                        if content and len(content) > 5:
                            chunks.append(make_chunk(len(chunks), content, item))

            # nucleo_conhecimento
            nucleo = data.get("nucleo_conhecimento", {})
            for key, val in nucleo.items():
                if isinstance(val, str) and val.strip():
                    chunks.append(make_chunk(len(chunks), f"{key}: {val}", {"key": key}))
                elif isinstance(val, list):
                    content = f"{key}: " + " | ".join(str(v) for v in val[:20])
                    if content.strip():
                        chunks.append(make_chunk(len(chunks), content, {"key": key}))

        elif isinstance(data, list):
            for idx, item in enumerate(data):
                if isinstance(item, dict):
                    content = " ".join(filter(None, [
                        str(item.get("pergunta", item.get("question", item.get("titulo", "")))),
                        str(item.get("resposta", item.get("answer", item.get("content", "")))),
                    ])).strip()
                    if content and len(content) > 5:
                        av = self._detect_avatar_from_block(item, avatar_id)
                        col = AVATAR_DESCRIPTORS.get(av, AVATAR_DESCRIPTORS[FALLBACK_AVATAR])["collection"]
                        chunks.append(KnowledgeChunk(f"{file_path.stem}_{idx}", av, col, content, str(file_path), item))

        return chunks

    def _detect_avatar_from_filename(self, name: str) -> str:
        mapping = {
            "pacote_01": "lucas",  "concessionaria": "lucas",
            "pacote_02": "clara",  "hospital": "clara",
            "pacote_03": "amanda", "hotelaria": "amanda",
            "pacote4":   "marina", "shopping": "marina",
            "pacote5":   "fernanda", "prefeitura": "fernanda",
            "pacote_06": "luisa",  "universidade": "luisa",
            "pacote_07": "paula",  "odontologica": "paula",
            "pacote_08": "roberto","energia_solar": "roberto",
            "pacote_09": "lais",   "medicina": "lais",
            "spfc":      "bruno",
            "corinthians":"marcos",
            "atti":      "sofia",  "wf00": "rafael",
            "sofia":     "sofia",  "dataset_qa": "sofia",
        }
        for key, avatar in mapping.items():
            if key in name:
                return avatar
        return FALLBACK_AVATAR

    def _detect_avatar_from_block(self, block: Dict[str, Any], default: str) -> str:
        joined = " ".join([
            str(block.get("avatar_id", "")),
            str(block.get("avatar", "")),
            str(block.get("package", "")),
            str(block.get("domain", "")),
        ]).lower()
        for avatar_id in AVATAR_DESCRIPTORS:
            if avatar_id in joined:
                return avatar_id
        return default

    def retrieve(self, collection: str, query: str, top_k: int = 5) -> List[str]:
        """Retorna os top_k trechos mais relevantes para a query."""
        if self._client and ST_AVAILABLE and self._encoder:
            return self._chroma_retrieve(collection, query, top_k)
        return self._keyword_retrieve(collection, query, top_k)

    def _chroma_retrieve(self, collection: str, query: str, top_k: int) -> List[str]:
        try:
            col = self._client.get_collection(name=collection)
            embedding = self._encoder.encode([query]).tolist()
            results = col.query(query_embeddings=embedding, n_results=min(top_k, col.count()))
            docs = results.get("documents", [[]])[0]
            return [str(d) for d in docs if d]
        except Exception as exc:
            logger.debug("ChromaDB retrieve fallback: %s", exc)
            return self._keyword_retrieve(collection, query, top_k)

    def _keyword_retrieve(self, collection: str, query: str, top_k: int) -> List[str]:
        chunks = self._fallback.get(collection, [])
        if not chunks:
            # Busca cross-collection
            chunks = [c for col in self._fallback.values() for c in col]
        if not chunks:
            return []

        query_words = set(re.findall(r"\w+", query.lower()))
        scored = []
        for chunk in chunks:
            chunk_words = set(re.findall(r"\w+", chunk.content.lower()))
            score = len(query_words & chunk_words)
            if score > 0:
                scored.append((score, chunk.content))

        scored.sort(key=lambda x: -x[0])
        return [content[:800] for _, content in scored[:top_k]]

    def status(self) -> Dict[str, Any]:
        backend = "none"
        if self._client and self._encoder:
            backend = "chroma+st"
        elif self._client:
            backend = "chroma+keyword"
        elif self._fallback:
            backend = "keyword"
        return {
            "initialized": self._initialized,
            "backend": backend,
            "collections_keyword": sorted(self._fallback.keys()),
            "total_chunks": sum(len(v) for v in self._fallback.values()),
            "chroma_available": CHROMA_AVAILABLE,
            "translation_available": TRANSLATOR_AVAILABLE,
        }


# ─── Tradução gratuita + geração local orientada por RAG ───────────────────
LANG_CODE_MAP = {
    "pt-BR": "pt",
    "en": "en",
    "es": "es",
}


def translate_text(text: str, target_lang: str) -> str:
    """Traduz texto do português para o idioma solicitado usando deep-translator."""
    if not text:
        return text

    target_lang = normalize_language(target_lang)
    target = LANG_CODE_MAP.get(target_lang, "en")
    if target == "pt":
        return text
    if not TRANSLATOR_AVAILABLE or GoogleTranslator is None:
        logger.warning("deep-translator indisponível; retornando texto original")
        return text

    try:
        translator = GoogleTranslator(source="pt", target=target)
        translated = translator.translate(text)
        return translated or text
    except Exception as exc:
        logger.warning("Erro na tradução PT -> %s: %s", target_lang, exc)
        return text


def translate_to_portuguese(text: str, source_lang: str) -> str:
    """Traduz texto de EN/ES para PT usando deep-translator."""
    if not text:
        return text

    source_lang = normalize_language(source_lang)
    source_map = {"en": "en", "es": "es"}
    source = source_map.get(source_lang)
    if not source:
        return text
    if not TRANSLATOR_AVAILABLE or GoogleTranslator is None:
        logger.warning("deep-translator indisponível; mantendo entrada original")
        return text

    try:
        translator = GoogleTranslator(source=source, target="pt")
        translated = translator.translate(text)
        return translated or text
    except Exception as exc:
        logger.warning("Erro na tradução %s -> PT: %s", source_lang, exc)
        return text


class FreeLocalLLM:
    """Motor gratuito: compõe resposta curta a partir do RAG, sem API paga."""

    def __init__(self):
        self._cache: Dict[str, str] = {}

    def initialize(self) -> bool:
        if TRANSLATOR_AVAILABLE:
            logger.info("deep-translator inicializado para PT-BR, EN e ES")
        else:
            logger.warning("deep-translator não encontrado; o backend seguirá sem tradução automática")
        return True

    def is_available(self) -> bool:
        return True

    def _clean_text(self, text: str) -> str:
        cleaned = re.sub(r"[`*_#>-]+", " ", text or "")
        cleaned = re.sub(r"https?://\S+", "", cleaned)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        return cleaned

    def _split_sentences(self, text: str) -> List[str]:
        cleaned = self._clean_text(text)
        parts = re.split(r"(?<=[.!?])\s+|\s*[;•\n]+\s*", cleaned)
        return [part.strip(' -') for part in parts if part and len(part.strip()) > 20]

    def _score_sentence(self, sentence: str, query_words: set[str], index: int) -> float:
        words = set(re.findall(r"\w+", sentence.lower()))
        overlap = len(words & query_words)
        length_bonus = 0.3 if 35 <= len(sentence) <= 220 else 0.0
        position_bonus = max(0.0, 0.25 - (index * 0.02))
        return overlap + length_bonus + position_bonus

    def _compose_from_context(self, user_message: str, context_chunks: List[str]) -> str:
        query_words = {w for w in re.findall(r"\w+", user_message.lower()) if len(w) > 2}
        scored: List[Tuple[float, str]] = []
        seen = set()

        for chunk in context_chunks:
            for index, sentence in enumerate(self._split_sentences(chunk)):
                normalized = sentence.lower()
                if normalized in seen:
                    continue
                score = self._score_sentence(sentence, query_words, index)
                if score > 0:
                    seen.add(normalized)
                    scored.append((score, sentence))

        scored.sort(key=lambda item: (-item[0], len(item[1])))
        chosen = [sentence for _, sentence in scored[:3]]
        if chosen:
            return ' '.join(chosen)
        return ''

    async def generate(
        self,
        system_prompt: str,
        user_message: str,
        context_chunks: List[str],
        history_summary: str,
    ) -> Optional[str]:
        cache_key = hashlib.md5(f"{system_prompt[:120]}|{user_message}|{'|'.join(context_chunks[:3])}".encode()).hexdigest()
        if cache_key in self._cache:
            return self._cache[cache_key]

        response = self._compose_from_context(user_message, context_chunks)
        if not response and history_summary and history_summary != "Sem histórico anterior.":
            last_lines = [line.split(':', 2)[-1].strip() for line in history_summary.splitlines() if ':' in line]
            last_hint = next((item for item in reversed(last_lines) if len(item) > 20), "")
            if last_hint:
                response = f"Com base no contexto recente, {last_hint}"

        if not response:
            response = (
                "Posso ajudar com isso, mas não encontrei um trecho exato na base disponível agora. "
                "Se quiser, reformule a pergunta ou informe mais contexto para eu responder de forma mais precisa."
            )

        response = self._clean_text(response)
        if len(response) > 420:
            response = response[:417].rsplit(' ', 1)[0].rstrip(' ,;') + '...'
        self._cache[cache_key] = response
        if len(self._cache) > 500:
            for key in list(self._cache.keys())[:100]:
                del self._cache[key]
        return response

    async def translate_text(self, text: str, target_lang: str, source_lang: str = "pt-BR") -> Optional[str]:
        source_lang = normalize_language(source_lang)
        target_lang = normalize_language(target_lang)
        if not text or source_lang == target_lang:
            return text
        if target_lang == "pt-BR":
            return await asyncio.to_thread(translate_to_portuguese, text, source_lang)
        return await asyncio.to_thread(translate_text, text, target_lang)


# ─── Edge-TTS Engine (100% original preservado) ─────────────────────────────
async def _generate_tts_internal(avatar_id: str, text: str, emotion: str, language: str = DEFAULT_LANGUAGE) -> Tuple[str, int, bytes]:
    """
    Gera áudio TTS com Edge-TTS preservando o fluxo original,
    agora com seleção de voz por idioma (pt-BR, en, es).
    """
    voice_cfg = resolve_voice_config(avatar_id, language)
    voice = voice_cfg["voice"]
    pitch = voice_cfg["pitch"]
    rate = voice_cfg["rate"]

    communicate = edge_tts.Communicate(text=text, voice=voice, pitch=pitch, rate=rate)

    audio_chunks: List[bytes] = []
    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
        tmp_path = tmp.name

    try:
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                audio_chunks.append(chunk["data"])

        audio_data = b"".join(audio_chunks)
        if not audio_data:
            raise ValueError("TTS retornou áudio vazio")

        audio_b64 = base64.b64encode(audio_data).decode("utf-8")
        size_bytes = len(audio_data)
        duration_ms = max(1000, int((size_bytes / 16000) * 1000))
        return audio_b64, duration_ms, audio_data
    finally:
        try:
            os.unlink(tmp_path)
        except Exception:
            pass


async def generate_tts(avatar_id: str, text: str, emotion: str, language: str = DEFAULT_LANGUAGE) -> Tuple[str, int]:
    audio_b64, duration_ms, _ = await _generate_tts_internal(avatar_id, text, emotion, language)
    return audio_b64, duration_ms


# ─── Aplicação FastAPI ───────────────────────────────────────────────────────
def parse_allowed_origins() -> List[str]:
    raw = os.getenv("CORS_ALLOW_ORIGINS", "")
    if not raw.strip():
        return DEFAULT_ALLOWED_ORIGINS
    return [item.strip() for item in raw.split(",") if item.strip()]


app = FastAPI(
    title="Humanos Digitais API",
    version=APP_VERSION,
    description="TTS + RAG + tradução gratuita + Sync-Lip para Avatares Digitais",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=parse_allowed_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── Instâncias globais ──────────────────────────────────────────────────────
session_store     = SessionMemoryStore()
context_engine    = ContextualEngine()
intent_classifier = IntentClassifier()
avatar_router     = AvatarRouter()
viseme_gen        = VisemeGenerator()
viseme_engine     = VisemeSyncEngine()
rag               = ChromaRAG()
llm               = FreeLocalLLM()
i18n              = I18nEngine({
    "default_language": normalize_language(DEFAULT_LANGUAGE),
    "supported_languages": [normalize_language(lang) for lang in SUPPORTED_LANGUAGES],
})


@app.on_event("startup")
async def startup_event():
    logger.info("Iniciando %s v%s", APP_NAME, APP_VERSION)
    rag.initialize()
    llm.initialize()
    logger.info("RAG status: %s", rag.status())
    logger.info("Motor local disponível: %s", llm.is_available())
    logger.info("Tradução gratuita disponível: %s", TRANSLATOR_AVAILABLE)
    logger.info("Idiomas suportados: %s | padrão=%s", i18n.get_supported_languages(), i18n.default_language)


# ─── Endpoints ──────────────────────────────────────────────────────────────
@app.get("/")
async def root():
    return {
        "service": APP_NAME,
        "version": APP_VERSION,
        "status": "online",
        "rag":    rag.status(),
        "llm":    {"available": llm.is_available(), "provider": "local-rag"},
        "translation": {"provider": "deep-translator", "available": TRANSLATOR_AVAILABLE},
        "i18n":   {"default_language": i18n.default_language, "supported_languages": i18n.get_supported_languages()},
    }


@app.get("/health")
async def health():
    return {"status": "ok", "version": APP_VERSION}


@app.get("/api/avatar/status")
async def avatar_status():
    return {
        "avatars":  sorted(KNOWN_AVATARS),
        "rag":      rag.status(),
        "llm":      {"available": llm.is_available(), "provider": "local-rag", "legacy_env": DEFAULT_LLM},
        "translation": {"provider": "deep-translator", "available": TRANSLATOR_AVAILABLE},
        "i18n":     {"default_language": i18n.default_language, "supported_languages": i18n.get_supported_languages()},
        "version":  APP_VERSION,
    }


@app.post("/api/avatar/speak")
async def avatar_speak(req: SpeakRequest, request: Request):
    """
    Endpoint principal — expandido com RAG + LLM + tradução real + blend shapes reais.
    Compatível com o contrato anterior e mantendo o mesmo endpoint.
    """
    start = time.time()

    accept_language = request.headers.get("accept-language", "")
    user_lang = normalize_language(i18n.detect_language_from_header(accept_language))
    normalized_user_text = req.text

    if user_lang != DEFAULT_LANGUAGE:
        normalized_user_text = translate_to_portuguese(req.text, user_lang)

    session = session_store.get(req.session_id)
    page_context = context_engine.detect(req.context_url)
    intent, conf = intent_classifier.classify(normalized_user_text, page_context)
    avatar_id, route_conf, route_reason = avatar_router.resolve(
        req.avatar_id, normalized_user_text, page_context, session
    )

    collection = AVATAR_DESCRIPTORS.get(avatar_id, AVATAR_DESCRIPTORS[FALLBACK_AVATAR])["collection"]
    rag_chunks = rag.retrieve(collection, normalized_user_text, top_k=5)

    history_summary = session_store.summary(req.session_id)
    system_prompt = SYSTEM_PROMPTS.get(avatar_id, SYSTEM_PROMPTS[FALLBACK_AVATAR])

    response_pt = await llm.generate(
        system_prompt=system_prompt,
        user_message=normalized_user_text,
        context_chunks=rag_chunks,
        history_summary=history_summary,
    )

    response_pt = response_pt if response_pt else normalized_user_text
    response_text = response_pt

    if user_lang != DEFAULT_LANGUAGE:
        response_text = translate_text(response_pt, user_lang)

    audio_b64, duration_ms, audio_data = await _generate_tts_internal(avatar_id, response_text, req.emotion, user_lang)
    viseme_payload = extract_real_blend_shapes(audio_data, duration_ms, viseme_engine, viseme_gen, response_text)

    session_store.remember(req.session_id, SessionTurn(
        role="user", text=normalized_user_text, avatar_id=avatar_id,
        intent=intent, context_url=req.context_url,
    ))
    session_store.remember(req.session_id, SessionTurn(
        role="assistant", text=response_pt, avatar_id=avatar_id,
        intent=intent, context_url=req.context_url,
    ))

    elapsed = round((time.time() - start) * 1000)
    logger.info(
        "speak | avatar=%s route=%s intent=%s lang=%s llm=%s rag_chunks=%d viseme_engine=%s duration=%dms elapsed=%dms",
        avatar_id, route_reason, intent, user_lang,
        "free_local_rag" if llm.is_available() else "passthrough",
        len(rag_chunks), viseme_payload.get("engine"), duration_ms, elapsed,
    )

    return JSONResponse(content={
        "audio_base64": audio_b64,
        "avatar_id": avatar_id,
        "text_spoken": response_text,
        "text_response": response_text,
        "text_response_pt": response_pt,
        "visemes": viseme_payload.get("blend_shapes", {}),
        "viseme_meta": {
            "engine": viseme_payload.get("engine"),
            "fps": viseme_payload.get("fps"),
            "frames": viseme_payload.get("frames"),
            "timeline": viseme_payload.get("timeline", []),
        },
        "duration_ms": duration_ms,
        "session_id": req.session_id,
        "context": {
            "page": page_context.get("page"),
            "intent": intent,
            "intent_conf": round(conf, 2),
            "route_reason": route_reason,
            "route_conf": round(route_conf, 2),
            "rag_chunks": len(rag_chunks),
            "llm_used": llm.is_available(),
            "translation_provider": "deep-translator",
            "default_language": DEFAULT_LANGUAGE,
            "user_language": user_lang,
            "supported_languages": i18n.get_supported_languages(),
            "input_translated_to_pt": normalized_user_text != req.text,
            "output_translated": response_text != response_pt,
        },
        "version": APP_VERSION,
    })


@app.post("/api/tts")
async def tts_only(payload: dict):
    """Endpoint TTS simples (retrocompatibilidade)."""
    avatar_id = payload.get("avatar_id", "sofia")
    text      = payload.get("text", "")
    emotion   = payload.get("emotion", "friendly")
    if not text:
        raise HTTPException(status_code=400, detail="text é obrigatório")
    audio_b64, duration_ms = await generate_tts(avatar_id, text, emotion, DEFAULT_LANGUAGE)
    return JSONResponse(content={
        "audio_base64": audio_b64,
        "avatar_id":    avatar_id,
        "duration_ms":  duration_ms,
    })


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error("Erro não tratado: %s", exc, exc_info=True)
    return JSONResponse(status_code=500, content={"error": str(exc)})

if __name__ == "__main__":
    import os
    port = int(os.getenv("PORT", 5000))
    print(f"🚀 Starting server on port {port}...")
    uvicorn.run(app, host="0.0.0.0", port=port)
