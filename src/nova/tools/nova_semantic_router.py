import json
from nova.core.nova_router import NovaRouter

class NovaSemanticRouter:
    """
    Semantic Router para NOVA 3.0.
    Reemplaza expresiones regulares rígidas por un análisis LLM extremadamente
    optimizado ("cavernícola") para gastar mínimos tokens y clasificar la intención.
    Usa el NovaRouter existente para aprovechar los modelos Tier 1 gratis/rápidos.
    """
    def __init__(self, router: NovaRouter):
        self.router = router
        # Prompt cavernícola: instrucciones mínimas, sin formalaturas, JSON estricto
        # Ahorro extremo de tokens.
        self.system_prompt = (
            "Eres un parser MÁQUINA. Cero charla. "
            "Input: frase de usuario. "
            "Output: ÚNICAMENTE JSON VÁLIDO. "
            'Esquema: {"intent": "X", "target": "Y", "args": "Z"} '
            "Intents permitidos: 'open_app', 'web_search', 'system_command', 'dictation', 'mcp_tool', 'chat'. "
            "Si es una charla normal, intent='chat'. "
            "Ejemplo input: 'abre word y crea documento'. "
            'Ejemplo output: {"intent": "open_app", "target": "Word", "args": "new_document"}'
        )

    def parse_command(self, user_text: str) -> dict:
        """
        Pasa el texto por el LLM Tier 1 (el más rápido y barato/gratuito)
        para obtener el JSON estructurado.
        """
        # Forzar Tier 1 y max_tokens muy bajo para asegurar velocidad y menos costo
        # Bypass al límite de historial enviando un array limpio
        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": user_text}
        ]
        
        try:
            print(f"[SemanticRouter] Analizando intención: '{user_text}'...")
            resultado = self.router.route(
                messages=messages,
                force_tier=1,       # Usar los modelos más ligeros (Llama3.2 3B, Haiku)
                max_tokens=60,      # Un JSON no ocupará más de 60 tokens
                temperature=0.0     # Precisión absoluta, cero creatividad
            )
            
            raw_response = resultado.get("response", "").strip()
            
            # Limpiar posible markdown (```json ... ```) adherido por algunos modelos
            if raw_response.startswith("```json"):
                raw_response = raw_response[7:]
            if raw_response.startswith("```"):
                raw_response = raw_response[3:]
            raw_response = raw_response.rstrip("`").strip()
            
            parsed_intent = json.loads(raw_response)
            print(f"[SemanticRouter] Intento detectado: {parsed_intent}")
            return parsed_intent
            
        except json.JSONDecodeError:
            print(f"[SemanticRouter] ⚠️ Falló parseo JSON. Fallback a 'chat'. Output bruto: {raw_response}")
            return {"intent": "chat", "target": "", "args": ""}
        except Exception as e:
            print(f"[SemanticRouter] ⚠️ Error crítico: {e}")
            return {"intent": "chat", "target": "", "args": ""}

    def execute_intent(self, intent_data: dict, chat_callback):
        """
        Ejecuta la intención detectada contactando los controladores (macOS, MCP, etc.)
        o delega la charla de vuelta a Nova.
        """
        intent = intent_data.get("intent")
        target = intent_data.get("target")
        args = intent_data.get("args")

        if intent == "open_app":
            # Aquí llamamos directamente a Applescript nativo (inquebrantable)
            print(f"🔧 Ejecutando nativo: abriendo app {target}...")
            import subprocess
            subprocess.run(["osascript", "-e", f'tell application "{target}" to activate'])
            # Futura sub-integración: si args == "new_document", usar keystrokes Cmd+N
            return f"He abierto {target}."
            
        elif intent == "mcp_tool":
            print(f"🔧 Delegando al MCP Client para la tool: {target}")
            # Lógica para llamar a Hermes / OpenClaw
            return f"Ejecutando herramienta {target} vía MCP."

        elif intent == "web_search":
            return f"Iniciando búsqueda web sobre {target}."
            
        elif intent == "chat":
            # Si el modelo determinó que es charla, delegar la generación normal
            return chat_callback()

        return "Comando procesado, Señor."

# Uso (ejemplo)
if __name__ == "__main__":
    from nova.core.nova_router import NovaRouter
    router_inst = NovaRouter() # Mantiene la rotación intacta
    semantic = NovaSemanticRouter(router_inst)
    
    intent = semantic.parse_command("por favor abrí un nuevo documento en word")
    print("\nResultado:", intent)
