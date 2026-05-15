import os
import json
import logging
from typing import Optional, List, Dict

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Tenta usar Redis se configurado, senão usa dict em memória
try:
    import redis.asyncio as aioredis
    REDIS_URL = os.getenv("REDIS_URL", "")
    _use_redis = bool(REDIS_URL)
    logger.info(f"[SessionMemory] Redis configurado: {_use_redis}")
except ImportError:
    _use_redis = False
    logger.warning("[SessionMemory] redis.asyncio não disponível, usando fallback in-memory")

_memory_store = {}  # fallback in-memory

class SessionMemory:
    """Gerenciador de memória de sessão com fallback in-memory"""
    
    def __init__(self, session_id: str, max_turns: int = 6):
        self.session_id = session_id
        self.max_turns = max_turns
        self._redis = None
        logger.info(f"[SessionMemory] Sessão criada: {session_id}")
    
    async def _get_redis(self):
        """Conecta ao Redis se configurado"""
        if _use_redis and self._redis is None:
            try:
                self._redis = await aioredis.from_url(os.getenv("REDIS_URL"))
                logger.info(f"[SessionMemory] Conectado ao Redis")
            except Exception as e:
                logger.warning(f"[SessionMemory] Erro ao conectar ao Redis: {e}")
                self._redis = None
        return self._redis
    
    def get_history(self) -> List[Dict]:
        """Retorna histórico da sessão (síncrono para compatibilidade)"""
        if _use_redis:
            try:
                # Nota: Para uso síncrono, seria necessário usar redis.Redis em vez de asyncio
                # Por enquanto, retorna fallback in-memory
                pass
            except Exception as e:
                logger.warning(f"[SessionMemory] Redis falhou, usando in-memory: {e}")
        
        return _memory_store.get(self.session_id, [])
    
    async def get_history_async(self) -> List[Dict]:
        """Retorna histórico da sessão (assíncrono)"""
        if _use_redis:
            try:
                r = await self._get_redis()
                if r:
                    data = await r.get(f"session:{self.session_id}")
                    return json.loads(data) if data else []
            except Exception as e:
                logger.warning(f"[SessionMemory] Redis falhou, usando in-memory: {e}")
        
        return _memory_store.get(self.session_id, [])
    
    def add_turn(self, user_msg: str, assistant_msg: str):
        """Adiciona um turno à conversa (síncrono)"""
        history = self.get_history()
        history.append({"role": "user", "content": user_msg})
        history.append({"role": "assistant", "content": assistant_msg})
        history = history[-(self.max_turns * 2):]  # mantém últimos N turnos
        
        _memory_store[self.session_id] = history
        logger.info(f"[SessionMemory] Turno adicionado: {self.session_id} ({len(history)} mensagens)")
    
    async def add_turn_async(self, user_msg: str, assistant_msg: str):
        """Adiciona um turno à conversa (assíncrono)"""
        history = await self.get_history_async()
        history.append({"role": "user", "content": user_msg})
        history.append({"role": "assistant", "content": assistant_msg})
        history = history[-(self.max_turns * 2):]  # mantém últimos N turnos
        
        if _use_redis:
            try:
                r = await self._get_redis()
                if r:
                    await r.setex(f"session:{self.session_id}", 3600, json.dumps(history))
                    logger.info(f"[SessionMemory] Turno salvo no Redis: {self.session_id}")
                    return
            except Exception as e:
                logger.warning(f"[SessionMemory] Redis falhou ao salvar: {e}")
        
        _memory_store[self.session_id] = history
        logger.info(f"[SessionMemory] Turno salvo em memória: {self.session_id}")
    
    def clear(self):
        """Limpa a sessão (síncrono)"""
        _memory_store.pop(self.session_id, None)
        logger.info(f"[SessionMemory] Sessão limpa: {self.session_id}")
    
    async def clear_async(self):
        """Limpa a sessão (assíncrono)"""
        if _use_redis:
            try:
                r = await self._get_redis()
                if r:
                    await r.delete(f"session:{self.session_id}")
                    logger.info(f"[SessionMemory] Sessão deletada do Redis: {self.session_id}")
            except:
                pass
        
        _memory_store.pop(self.session_id, None)
        logger.info(f"[SessionMemory] Sessão limpa: {self.session_id}")
