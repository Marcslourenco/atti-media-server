# Instrução Técnica: Correção do Favicon 404 e State Lock no Frontend

Este documento consolida as orientações definitivas para o repositório do frontend (`humanosdigitais-website-fix`) para resolver o erro 404 do favicon e blindar o componente de áudio contra requisições duplicadas.

---

## 1. Correção do Favicon 404 na Vercel
Para eliminar definitivamente o erro 404 de `/favicon.ico` no console da Vercel, abra o arquivo `index.html` do seu frontend e adicione a tag SVG embutida no cabeçalho (`<head>`):

```html
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Humanos Digitais</title>
  
  <!-- Favicon embutido em SVG para zerar o erro 404 no Vercel -->
  <link rel="icon" href="data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 100 100%22><text y=%22.9em%22 font-size=%2290%22>👤</text></svg>">
</head>
```

---

## 2. Implementação do Greeting Bypass e State Lock no Cliente
Quando inicializar a Sofia ou trocar de avatar, envie o parâmetro `is_greeting: true` quando for a saudação de abertura, e proteja a chamada com `AbortController` e trava de estado:

```javascript
// Exemplo de chamada segura ao backend
const speakWithAvatar = async (text, avatarId, isGreeting = false) => {
  if (window.isAvatarSpeaking || window.isAvatarLoading) {
    console.warn("⚠️ Avatar ocupado. Ignorando clique duplo (Race Condition evitada).");
    return;
  }

  window.isAvatarLoading = true;

  if (window.activeAbortController) {
    window.activeAbortController.abort();
  }
  window.activeAbortController = new AbortController();

  try {
    const res = await fetch("https://atti-media-server.onrender.com/api/avatar/speak", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        text: text,
        avatar_id: avatarId,
        is_greeting: isGreeting
      }),
      signal: window.activeAbortController.signal
    });

    const data = await res.json();
    window.isAvatarLoading = false;

    if (data.success && data.audio_data) {
      window.isAvatarSpeaking = true;
      
      const audioBytes = Uint8Array.from(atob(data.audio_data), c => c.charCodeAt(0));
      const blob = new Blob([audioBytes], { type: 'audio/mp3' });
      const audio = new Audio(URL.createObjectURL(blob));

      if (typeof window.applyVisemes === 'function') {
        window.applyVisemes(data.visemes);
      }

      audio.onended = () => { window.isAvatarSpeaking = false; };
      audio.onerror = () => { window.isAvatarSpeaking = false; };

      await audio.play();
    }
  } catch (err) {
    if (err.name !== 'AbortError') {
      console.error("Erro na fala do avatar:", err);
    }
    window.isAvatarLoading = false;
    window.isAvatarSpeaking = false;
  }
};
