"""
ATTI Internationalization Engine v2.0
Sistema de suporte multilíngue com detecção automática e fallback.
Suporta EN, PT-BR, ES e extensível para outros idiomas.
"""

import os
import json
from typing import Dict, Optional, List
from enum import Enum
from pathlib import Path


class Language(Enum):
    """Idiomas suportados"""
    ENGLISH = "en"
    PORTUGUESE_BR = "pt-BR"
    SPANISH = "es"


class I18nEngine:
    """
    Motor de Internacionalização para Avatar ATTI v2.0
    
    Características:
    - Suporte multilíngue (EN, PT-BR, ES)
    - Detecção automática por header Accept-Language
    - Sistema de fallback
    - Carregamento dinâmico de traduções
    - Suporte a interpolação de variáveis
    - Pluralização
    """
    
    def __init__(self, config: Optional[Dict] = None):
        """
        Inicializa o motor de i18n
        
        Args:
            config: Dicionário com configurações:
                - default_language: Idioma padrão (padrão: "en")
                - translations_dir: Diretório de traduções (padrão: "./translations")
                - supported_languages: Lista de idiomas suportados
        """
        self.config = config or {}
        self.default_language = self.config.get("default_language", "en")
        self.translations_dir = self.config.get("translations_dir", "./translations")
        self.supported_languages = self.config.get(
            "supported_languages",
            ["en", "pt-BR", "es"]
        )
        
        self.current_language = self.default_language
        self.translations: Dict[str, Dict] = {}
        
        self._load_translations()
    
    def _load_translations(self) -> None:
        """Carrega arquivos de tradução"""
        for lang in self.supported_languages:
            self.translations[lang] = self._load_language_file(lang)
    
    def _load_language_file(self, language: str) -> Dict:
        """
        Carrega arquivo de tradução para um idioma
        
        Args:
            language: Código do idioma (ex: "en", "pt-BR")
            
        Returns:
            Dicionário com traduções
        """
        # Tentar carregar de arquivo
        file_path = os.path.join(self.translations_dir, f"{language}.json")
        
        if os.path.exists(file_path):
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                print(f"Error loading translations for {language}: {e}")
        
        # Retornar traduções padrão se arquivo não existir
        return self._get_default_translations(language)
    
    def _get_default_translations(self, language: str) -> Dict:
        """Retorna traduções padrão para um idioma"""
        defaults = {
            "en": {
                "greeting": "Hello! How can I help you?",
                "thinking": "Let me think about that...",
                "error": "I encountered an error. Please try again.",
                "goodbye": "Goodbye! Have a great day!",
                "loading": "Loading...",
                "cancel": "Cancel",
                "confirm": "Confirm",
                "yes": "Yes",
                "no": "No",
                "ok": "OK",
                "close": "Close",
                "back": "Back",
                "next": "Next",
                "previous": "Previous",
                "search": "Search",
                "no_results": "No results found.",
                "try_again": "Try again",
                "session_timeout": "Your session has expired.",
                "connection_error": "Connection error. Please check your internet.",
                "invalid_input": "Invalid input. Please try again.",
                "success": "Success!",
                "warning": "Warning",
                "info": "Information",
                "help": "Help"
            },
            "pt-BR": {
                "greeting": "Olá! Como posso ajudá-lo?",
                "thinking": "Deixe-me pensar sobre isso...",
                "error": "Encontrei um erro. Por favor, tente novamente.",
                "goodbye": "Adeus! Tenha um ótimo dia!",
                "loading": "Carregando...",
                "cancel": "Cancelar",
                "confirm": "Confirmar",
                "yes": "Sim",
                "no": "Não",
                "ok": "OK",
                "close": "Fechar",
                "back": "Voltar",
                "next": "Próximo",
                "previous": "Anterior",
                "search": "Pesquisar",
                "no_results": "Nenhum resultado encontrado.",
                "try_again": "Tentar novamente",
                "session_timeout": "Sua sessão expirou.",
                "connection_error": "Erro de conexão. Verifique sua internet.",
                "invalid_input": "Entrada inválida. Por favor, tente novamente.",
                "success": "Sucesso!",
                "warning": "Aviso",
                "info": "Informação",
                "help": "Ajuda"
            },
            "es": {
                "greeting": "¡Hola! ¿Cómo puedo ayudarte?",
                "thinking": "Déjame pensar en eso...",
                "error": "Encontré un error. Por favor, inténtalo de nuevo.",
                "goodbye": "¡Adiós! ¡Que tengas un gran día!",
                "loading": "Cargando...",
                "cancel": "Cancelar",
                "confirm": "Confirmar",
                "yes": "Sí",
                "no": "No",
                "ok": "OK",
                "close": "Cerrar",
                "back": "Atrás",
                "next": "Siguiente",
                "previous": "Anterior",
                "search": "Buscar",
                "no_results": "No se encontraron resultados.",
                "try_again": "Intentar de nuevo",
                "session_timeout": "Tu sesión ha expirado.",
                "connection_error": "Error de conexión. Verifica tu internet.",
                "invalid_input": "Entrada inválida. Por favor, inténtalo de nuevo.",
                "success": "¡Éxito!",
                "warning": "Advertencia",
                "info": "Información",
                "help": "Ayuda"
            }
        }
        
        return defaults.get(language, defaults["en"])
    
    def set_language(self, language: str) -> bool:
        """
        Define o idioma atual
        
        Args:
            language: Código do idioma
            
        Returns:
            True se idioma foi definido, False se não suportado
        """
        if language not in self.supported_languages:
            return False
        
        self.current_language = language
        return True
    
    def get_language(self) -> str:
        """Retorna o idioma atual"""
        return self.current_language
    
    def detect_language_from_header(self, accept_language: str) -> str:
        """
        Detecta idioma a partir do header Accept-Language
        
        Args:
            accept_language: Header Accept-Language do navegador
            
        Returns:
            Código do idioma detectado ou padrão
        """
        if not accept_language:
            return self.default_language
        
        # Parsear header Accept-Language
        # Formato: "en-US,en;q=0.9,pt-BR;q=0.8"
        languages = []
        for part in accept_language.split(","):
            lang_part = part.split(";")[0].strip()
            languages.append(lang_part)
        
        # Tentar encontrar idioma suportado
        for lang in languages:
            # Correspondência exata
            if lang in self.supported_languages:
                return lang
            
            # Correspondência por prefixo (ex: "en" para "en-US")
            lang_prefix = lang.split("-")[0]
            for supported in self.supported_languages:
                if supported.startswith(lang_prefix):
                    return supported
        
        return self.default_language
    
    def translate(self, key: str, language: Optional[str] = None, 
                 variables: Optional[Dict] = None) -> str:
        """
        Traduz uma chave
        
        Args:
            key: Chave de tradução (ex: "greeting")
            language: Idioma (usa atual se não especificado)
            variables: Variáveis para interpolação
            
        Returns:
            String traduzida
        """
        lang = language or self.current_language
        
        # Fallback para idioma padrão se não encontrado
        if lang not in self.translations:
            lang = self.default_language
        
        # Obter tradução
        translation = self.translations[lang].get(key, key)
        
        # Interpolação de variáveis
        if variables:
            for var_key, var_value in variables.items():
                translation = translation.replace(f"{{{var_key}}}", str(var_value))
        
        return translation
    
    def t(self, key: str, **kwargs) -> str:
        """
        Atalho para translate()
        
        Args:
            key: Chave de tradução
            **kwargs: Variáveis para interpolação
            
        Returns:
            String traduzida
        """
        return self.translate(key, variables=kwargs if kwargs else None)
    
    def get_all_translations(self, language: Optional[str] = None) -> Dict:
        """
        Retorna todas as traduções para um idioma
        
        Args:
            language: Idioma (usa atual se não especificado)
            
        Returns:
            Dicionário com todas as traduções
        """
        lang = language or self.current_language
        return self.translations.get(lang, {})
    
    def add_translation(self, key: str, value: str, language: Optional[str] = None) -> None:
        """
        Adiciona uma tradução em tempo de execução
        
        Args:
            key: Chave de tradução
            value: Valor traduzido
            language: Idioma (usa atual se não especificado)
        """
        lang = language or self.current_language
        
        if lang not in self.translations:
            self.translations[lang] = {}
        
        self.translations[lang][key] = value
    
    def pluralize(self, key: str, count: int, language: Optional[str] = None) -> str:
        """
        Retorna tradução com pluralização
        
        Args:
            key: Chave de tradução (ex: "item" para "item_singular" e "item_plural")
            count: Quantidade para determinar singular/plural
            language: Idioma
            
        Returns:
            String traduzida com pluralização
        """
        if count == 1:
            return self.translate(f"{key}_singular", language)
        else:
            return self.translate(f"{key}_plural", language)
    
    def get_supported_languages(self) -> List[str]:
        """Retorna lista de idiomas suportados"""
        return self.supported_languages
    
    def export_config(self) -> Dict:
        """Exporta configuração em JSON"""
        return {
            "default_language": self.default_language,
            "current_language": self.current_language,
            "supported_languages": self.supported_languages,
            "translations_loaded": list(self.translations.keys())
        }
    
    def export_translations(self, language: Optional[str] = None) -> Dict:
        """Exporta todas as traduções para um idioma"""
        lang = language or self.current_language
        return self.translations.get(lang, {})


# Exemplo de uso
if __name__ == "__main__":
    i18n = I18nEngine({
        "default_language": "en",
        "supported_languages": ["en", "pt-BR", "es"]
    })
    
    print("I18n Engine initialized")
    print(f"Current language: {i18n.get_language()}")
    print(f"Supported languages: {i18n.get_supported_languages()}")
    
    # Traduzir
    print(f"\nEnglish: {i18n.translate('greeting')}")
    
    # Mudar idioma
    i18n.set_language("pt-BR")
    print(f"Portuguese: {i18n.translate('greeting')}")
    
    # Detectar de header
    detected = i18n.detect_language_from_header("pt-BR,pt;q=0.9,en;q=0.8")
    print(f"\nDetected language: {detected}")
    
    # Usar atalho
    i18n.set_language("es")
    print(f"Spanish: {i18n.t('error')}")
