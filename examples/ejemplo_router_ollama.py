#!/usr/bin/env python3
"""
ejemplo_router_ollama.py
────────────────────────
Ejemplo de uso del NOVA Router con Ollama y estadísticas.
"""

from nova_router import NovaRouter

def main():
    # Inicializar el router
    # Requiere:
    #   - Ollama corriendo: ollama serve
    #   - OLLAMA_BASE_URL=http://127.0.0.1:11434/v1 (opcional, es el default)
    #   - Al menos un modelo instalado: ollama pull llama3.2:1b

    print("🚀 Inicializando NOVA Router...")
    print()

    try:
        router = NovaRouter()

        # Ver el orden de proveedores
        print(f"\n📋 Orden de proveedores: {', '.join(router.provider_order)}")

        # Ver modelos de Ollama disponibles
        if router._ollama_ready:
            print(f"\n🦙 Modelos Ollama disponibles:")
            for tier, models in router._ollama_models.items():
                if models:
                    print(f"   Tier {tier}: {', '.join(models)}")

        # Probar diferentes tipos de prompts
        tests = [
            {"messages": [{"role": "user", "content": "hola"}], "desc": "Saludo simple (Tier 1)"},
            {"messages": [{"role": "user", "content": "Explica qué es un modelo de lenguaje"}], "desc": "Consulta media (Tier 2)"},
            {"messages": [{"role": "user", "content": "Implementa una función quicksort en Python con comentarios detallados"}], "desc": "Código complejo (Tier 3)"},
        ]

        for test in tests:
            print(f"\n{'='*60}")
            print(f"📝 {test['desc']}")
            print(f"   Prompt: {test['messages'][0]['content'][:50]}...")
            print(f"{'='*60}")

            try:
                result = router.route(test["messages"])
                print(f"\n✅ PROVEEDOR: {result['provider']}")
                print(f"🤖 MODELO: {result['model']}")
                print(f"📊 TIER: {result['tier']}")
                print(f"🪙 TOKENS: {result['tokens_used']}")
                print(f"💬 RESPUESTA:\n   {result['response'][:200]}...")
            except Exception as e:
                print(f"\n❌ Error: {e}")

        # Mostrar estadísticas acumuladas
        print(f"\n{'='*60}")
        print("📈 ESTADÍSTICAS DE MODELOS:")
        print(f"{'='*60}")
        stats = router.get_model_stats()
        for model, data in sorted(stats.items(), key=lambda x: x[1]['success'], reverse=True):
            success_rate = data['success'] / (data['success'] + data['fail']) * 100
            print(f"   {model}:")
            print(f"      Éxitos: {data['success']}, Fallos: {data['fail']}")
            print(f"      Tasa éxito: {success_rate:.1f}%, Latencia: {data['avg_latency']:.2f}s")
            print(f"      Score: {router.stats_tracker.score(model):.2f}")

    except EnvironmentError as e:
        print(f"\n❌ Error de configuración: {e}")
        print("\n💡 Sugerencias:")
        print("   1. Instala Ollama: https://ollama.ai")
        print("   2. Inicia el servidor: ollama serve")
        print("   3. Descarga un modelo: ollama pull llama3.2:1b")
        print("   O configura GROQ_API_KEY u OPENROUTER_API_KEY")

if __name__ == "__main__":
    main()
