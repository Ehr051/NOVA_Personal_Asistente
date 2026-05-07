import sys
import os
os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"
import pytest

if os.getenv("NOVA_RUN_LEGACY_TEXT_TESTS") != "1":
    pytest.skip(
        "Legacy text engine script is not part of the current Nova smoke suite. "
        "Set NOVA_RUN_LEGACY_TEXT_TESTS=1 to run manually.",
        allow_module_level=True,
    )

import threading
from main import NovaSupremeEngine

def run_test():
    print("Iniciando pruebas simuladas de NOVA 3.0...")
    engine = NovaSupremeEngine()
    
    # Textos simulados en lugar del micrófono
    test_queries = [
        "lista de proyectos",
        "abre google chrome"
    ]
    
    for user_text in test_queries:
        print(f"\n======================================")
        print(f"🗣 USUARIO_SIMULADO: {user_text}")
        print("======================================")
        
        # 1. Parsear 
        intent_data = engine.semantic.parse_command(user_text)
        intent = intent_data.get("intent", "chat")
        
        # 2. Ejecutar
        if intent == "chat" or intent == "dictation":
            reply = engine.process_chat(user_text)
            print(f"🤖 NOVA: {reply}")
            
        elif intent == "open_app":
            target = intent_data.get("target")
            print(f"🤖 NOVA: (Ejecutar Tool Nativa) Procedo a abrir {target}.")
            engine.semantic.execute_intent(intent_data, lambda: None)
            
        elif intent == "mcp_tool":
            target = intent_data.get("target")
            args = intent_data.get("args")
            print(f"🤖 NOVA: Delegando al enlazador MCP: {target} (Args: {args})")
            engine.mcp.call_tool(target, {"args": args})
            
if __name__ == "__main__":
    run_test()
