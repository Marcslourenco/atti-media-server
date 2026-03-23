/**
 * index_patch.js — Integração TTS para Humanos Digitais
 * Versão: 2.0.0
 * Site: humanosdigitais.com.br
 * 
 * COMO USAR:
 * 1. Cole este script no seu index.html antes do </body>
 * 2. Ou importe: <script src="index_patch.js"></script>
 * 3. Configure BACKEND_URL com a URL do seu deploy
 * 
 * DEPENDÊNCIAS: Nenhuma (Vanilla JS puro)
 */

// ─────────────────────────────────────────────────────────────
// CONFIGURAÇÃO — edite apenas esta seção
// ─────────────────────────────────────────────────────────────
const HD_CONFIG = {
  // URL do backend (mude para sua URL de deploy)
  BACKEND_URL: window.HD_BACKEND_URL || 
               'https://atti-media-server.onrender.com' ||
               'http://localhost:8000',
  
  // Tocar áudio automaticamente ao selecionar avatar?
  AUTO_PLAY_ON_SELECT: true,
  
  // Volume padrão (0.0 a 1.0)
  DEFAULT_VOLUME: 0.85,
  
  // Timeout para requisições (ms)
  REQUEST_TIMEOUT: 10000,
  
  // Cache de áudios já gerados (evita requisições repetidas)
  ENABLE_CACHE: true,
  
  // Debug no console
  DEBUG: false,
};

// ─────────────────────────────────────────────────────────────
// ESTADO GLOBAL
// ─────────────────────────────────────────────────────────────
const HD_STATE = {
  currentAvatar: null,
  currentAudio: null,
  audioCache: new Map(),
  isLoading: false,
};

// ─────────────────────────────────────────────────────────────
// CORE — Funções principais
// ─────────────────────────────────────────────────────────────

/**
 * Sintetiza texto em voz para um avatar e reproduz.
 * 
 * @param {string} avatarId - ID do avatar (ex: "sofia", "bruno")
 * @param {string} texto    - Texto para falar
 * @param {Object} opts     - Opções opcionais { autoplay, volume, onEnd }
 * @returns {Promise<HTMLAudioElement>}
 */
async function falarAvatar(avatarId, texto, opts = {}) {
  const {
    autoplay = true,
    volume = HD_CONFIG.DEFAULT_VOLUME,
    onEnd = null,
    onStart = null,
  } = opts;

  const cacheKey = `${avatarId}::${texto}`;
  
  try {
    // Parar áudio anterior
    HD_pausar();
    
    // Verificar cache
    let audioBase64 = null;
    if (HD_CONFIG.ENABLE_CACHE && HD_STATE.audioCache.has(cacheKey)) {
      audioBase64 = HD_STATE.audioCache.get(cacheKey);
      HD_log(`Cache hit: ${cacheKey}`);
    } else {
      // Requisição ao backend
      HD_STATE.isLoading = true;
      HD_setLoadingState(avatarId, true);
      
      const controller = new AbortController();
      const timeout = setTimeout(
        () => controller.abort(), 
        HD_CONFIG.REQUEST_TIMEOUT
      );
      
      const response = await fetch(
        `${HD_CONFIG.BACKEND_URL}/api/avatar/speak`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            avatar_id: avatarId,
            text: texto,
          }),
          signal: controller.signal,
        }
      );
      
      clearTimeout(timeout);
      
      if (!response.ok) {
        throw new Error(`TTS API error: ${response.status}`);
      }
      
      const data = await response.json();
      audioBase64 = data.audio_base64;
      
      // Armazenar em cache
      if (HD_CONFIG.ENABLE_CACHE) {
        // Limitar cache a 50 itens
        if (HD_STATE.audioCache.size >= 50) {
          const firstKey = HD_STATE.audioCache.keys().next().value;
          HD_STATE.audioCache.delete(firstKey);
        }
        HD_STATE.audioCache.set(cacheKey, audioBase64);
      }
    }
    
    // Criar e configurar elemento de áudio
    const audio = new Audio(`data:audio/mp3;base64,${audioBase64}`);
    audio.volume = volume;
    
    HD_STATE.currentAudio = audio;
    
    // Callbacks
    if (onStart) audio.addEventListener('play', onStart, { once: true });
    if (onEnd)   audio.addEventListener('ended', onEnd, { once: true });
    
    // Evento global para o site
    audio.addEventListener('ended', () => {
      HD_STATE.isLoading = false;
      HD_setLoadingState(avatarId, false);
      document.dispatchEvent(new CustomEvent('hd:audioEnded', { 
        detail: { avatarId, texto }
      }));
    });
    
    // Reproduzir
    if (autoplay) {
      await audio.play();
      HD_log(`🔊 ${avatarId}: "${texto.substring(0, 50)}..."`);
    }
    
    return audio;
    
  } catch (err) {
    HD_STATE.isLoading = false;
    HD_setLoadingState(avatarId, false);
    
    if (err.name === 'AbortError') {
      HD_log(`⏱️ Timeout ao gerar voz para ${avatarId}`, 'warn');
    } else if (err.name === 'NotAllowedError') {
      // Autoplay bloqueado pelo browser — armazenar para tocar no próximo clique
      HD_log('🔇 Autoplay bloqueado. Aguardando interação do usuário.', 'warn');
      HD_STATE.pendingAudio = HD_STATE.currentAudio;
    } else {
      HD_log(`❌ Erro TTS: ${err.message}`, 'error');
    }
    
    return null;
  } finally {
    HD_STATE.isLoading = false;
  }
}

/**
 * Saudação padrão de um avatar (usa endpoint /greet — mais rápido).
 */
async function saudarAvatar(avatarId, opts = {}) {
  try {
    const response = await fetch(
      `${HD_CONFIG.BACKEND_URL}/api/avatar/${avatarId}/greet`
    );
    
    if (!response.ok) throw new Error(`Greet API error: ${response.status}`);
    
    const data = await response.json();
    
    const audio = new Audio(`data:audio/mp3;base64,${data.audio_base64}`);
    audio.volume = opts.volume || HD_CONFIG.DEFAULT_VOLUME;
    HD_STATE.currentAudio = audio;
    
    if (opts.autoplay !== false) {
      await audio.play().catch(() => {
        // Autoplay bloqueado — aguardar clique
        HD_STATE.pendingAudio = audio;
      });
    }
    
    return audio;
  } catch (err) {
    HD_log(`Fallback: ${err.message}`, 'warn');
    return null;
  }
}

/**
 * Para o áudio atual imediatamente.
 */
function HD_pausar() {
  if (HD_STATE.currentAudio) {
    HD_STATE.currentAudio.pause();
    HD_STATE.currentAudio.currentTime = 0;
    HD_STATE.currentAudio = null;
  }
}

/**
 * Muda volume do áudio em reprodução.
 */
function HD_setVolume(vol) {
  if (HD_STATE.currentAudio) {
    HD_STATE.currentAudio.volume = Math.max(0, Math.min(1, vol));
  }
}

/**
 * Limpa o cache de áudios.
 */
function HD_limparCache() {
  HD_STATE.audioCache.clear();
  HD_log('Cache de áudio limpo');
}

// ─────────────────────────────────────────────────────────────
// INTEGRAÇÃO COM O SITE — Listeners automáticos
// ─────────────────────────────────────────────────────────────

/**
 * Configura listeners automáticos para os elementos do site.
 * Chame após o DOM estar pronto.
 */
function HD_initIntegracao() {
  HD_log('🚀 Humanos Digitais TTS iniciado');
  
  // ── 1. Saudar avatar ao clicar no card do grid ──────────────
  document.querySelectorAll('[data-avatar-id]').forEach(card => {
    card.addEventListener('click', async function() {
      const avatarId = this.dataset.avatarId;
      HD_STATE.currentAvatar = avatarId;
      
      // Remover seleção anterior
      document.querySelectorAll('[data-avatar-id]').forEach(c => {
        c.classList.remove('hd-avatar-selected');
      });
      this.classList.add('hd-avatar-selected');
      
      if (HD_CONFIG.AUTO_PLAY_ON_SELECT) {
        await saudarAvatar(avatarId);
      }
    });
  });

  // ── 2. Tocar resposta quando avatar responde ─────────────────
  // Observa mutações no elemento de resposta do avatar
  const respostaEl = document.querySelector(
    '[data-avatar-response], .avatar-response, #avatarResponse, .chat-response'
  );
  
  if (respostaEl) {
    const observer = new MutationObserver(mutations => {
      mutations.forEach(m => {
        if (m.type === 'childList' && m.addedNodes.length > 0) {
          const texto = respostaEl.textContent?.trim();
          if (texto && HD_STATE.currentAvatar && texto.length > 5) {
            falarAvatar(HD_STATE.currentAvatar, texto);
          }
        }
      });
    });
    
    observer.observe(respostaEl, { childList: true, subtree: true });
    HD_log('Observer de respostas configurado');
  }

  // ── 3. Perguntas sugeridas ────────────────────────────────────
  document.querySelectorAll('[data-suggested-question], .suggested-question').forEach(btn => {
    btn.addEventListener('click', async function() {
      const pergunta = this.dataset.question || this.textContent?.trim();
      if (pergunta && HD_STATE.currentAvatar) {
        // Aguardar resposta do chat antes de falar
        // (resposta chega via evento ou mutação do DOM)
        HD_log(`Pergunta sugerida: "${pergunta}"`);
      }
    });
  });

  // ── 4. Desbloquear autoplay na primeira interação ─────────────
  const desbloquearAutoplay = () => {
    if (HD_STATE.pendingAudio) {
      HD_STATE.pendingAudio.play().catch(() => {});
      HD_STATE.pendingAudio = null;
    }
    document.removeEventListener('click', desbloquearAutoplay);
    document.removeEventListener('touchstart', desbloquearAutoplay);
  };
  
  document.addEventListener('click', desbloquearAutoplay, { once: true });
  document.addEventListener('touchstart', desbloquearAutoplay, { once: true });
  
  // ── 5. Verificar backend ──────────────────────────────────────
  HD_checkBackend();
}

/**
 * Verifica se o backend está respondendo.
 */
async function HD_checkBackend() {
  try {
    const r = await fetch(`${HD_CONFIG.BACKEND_URL}/health`, {
      signal: AbortSignal.timeout(5000)
    });
    const data = await r.json();
    HD_log(`✅ Backend OK: ${data.voices_available} vozes disponíveis`);
    return true;
  } catch {
    HD_log(`⚠️ Backend offline: ${HD_CONFIG.BACKEND_URL}`, 'warn');
    return false;
  }
}

// ─────────────────────────────────────────────────────────────
// HELPERS
// ─────────────────────────────────────────────────────────────

function HD_log(msg, level = 'log') {
  if (HD_CONFIG.DEBUG || level !== 'log') {
    console[level](`[HD-TTS] ${msg}`);
  }
}

function HD_setLoadingState(avatarId, loading) {
  const card = document.querySelector(`[data-avatar-id="${avatarId}"]`);
  if (card) {
    card.classList.toggle('hd-avatar-loading', loading);
  }
}

// ─────────────────────────────────────────────────────────────
// CSS dinâmico — indicadores visuais
// ─────────────────────────────────────────────────────────────
(function() {
  const style = document.createElement('style');
  style.textContent = `
    [data-avatar-id] {
      transition: transform 0.2s ease, box-shadow 0.2s ease;
      cursor: pointer;
    }
    .hd-avatar-selected {
      transform: scale(1.03);
      box-shadow: 0 0 0 3px #4f46e5, 0 8px 32px rgba(79,70,229,0.25) !important;
    }
    .hd-avatar-loading::after {
      content: '🔊';
      position: absolute;
      top: 8px;
      right: 8px;
      font-size: 1.1rem;
      animation: hd-pulse 0.8s ease-in-out infinite;
    }
    @keyframes hd-pulse {
      0%, 100% { opacity: 1; transform: scale(1); }
      50%       { opacity: 0.4; transform: scale(0.85); }
    }
  `;
  document.head.appendChild(style);
})();

// ─────────────────────────────────────────────────────────────
// AUTO-INIT quando DOM estiver pronto
// ─────────────────────────────────────────────────────────────
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', HD_initIntegracao);
} else {
  HD_initIntegracao();
}

// ─────────────────────────────────────────────────────────────
// Exportar API pública (para uso externo)
// ─────────────────────────────────────────────────────────────
window.HumanosDigitaisTTS = {
  falar:        falarAvatar,
  saudar:       saudarAvatar,
  pausar:       HD_pausar,
  setVolume:    HD_setVolume,
  limparCache:  HD_limparCache,
  checkBackend: HD_checkBackend,
  config:       HD_CONFIG,
  state:        HD_STATE,
};

// Alias de conveniência
window.falarAvatar = falarAvatar;
window.saudarAvatar = saudarAvatar;

/*
─────────────────────────────────────────────────────────────
USO MANUAL (no console ou em qualquer script):
─────────────────────────────────────────────────────────────

// Fazer um avatar falar:
await falarAvatar('sofia', 'Olá! Como posso te ajudar?');

// Saudação padrão:
await saudarAvatar('bruno');

// Avatar de futebol animado:
await falarAvatar('bruno', 'Gol do Tricolor! Que golaço!!!', { volume: 1.0 });

// Parar:
HD_pausar();

─────────────────────────────────────────────────────────────
ADICIONAR data-avatar-id nos cards do site:
─────────────────────────────────────────────────────────────

<div class="avatar-card" data-avatar-id="sofia">
  <img src="sofia.jpg" alt="Sofia">
  <h3>Sofia</h3>
</div>

─────────────────────────────────────────────────────────────
*/
