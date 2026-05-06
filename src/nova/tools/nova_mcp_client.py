import os
import json
import urllib.request
import urllib.error

class NovaMCPClient:
    """
    Cliente para el Model Context Protocol (MCP) de OpenClaw/Hermes.
    Actúa como Gateway para delegar acciones que Nova no puede hacer localmente
    mediante el uso de herramientas dinámicas (tools) expuestas por el servidor.
    """
    def __init__(self):
        # Apuntamos localmente a OpenClaw/Hermes que expone MCP en el puerto 18789
        self.base_url = os.getenv("OPENCLAW_BASE_URL", "http://127.0.0.1:18789/v1").rstrip("/")
        self.api_key = os.getenv("OPENCLAW_API_KEY", "openclaw-local")

    def call_tool(self, tool_name: str, parameters: dict) -> dict:
        """
        Llama a una herramienta específica provista por el ecosistema Hermes/OpenClaw.
        Ej: tool_name="create_calendar_event", parameters={"time": "tomorrow..."}
        """
        print(f"[NovaMCP] Ejecutando tool '{tool_name}' con MCP...")
        try:
            payload = json.dumps({
                "tool": tool_name,
                "parameters": parameters
            }).encode('utf-8')

            req = urllib.request.Request(
                f"{self.base_url}/mcp/execute",
                data=payload,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {self.api_key}"
                },
                method="POST"
            )

            with urllib.request.urlopen(req, timeout=15) as response:
                data = json.loads(response.read().decode('utf-8'))
                print(f"[NovaMCP] ✓ Tool '{tool_name}' ejecutada con éxito.")
                return {"status": "success", "result": data}
                
        except urllib.error.URLError as e:
            print(f"[NovaMCP] ⚠️ Error de red MCP: {e}")
            return {"status": "error", "message": str(e)}
        except Exception as e:
            print(f"[NovaMCP] ⚠️ Error ejecutando MCP: {e}")
            return {"status": "error", "message": f"Fallo en la tool: {str(e)}"}

    def get_available_tools(self) -> list:
        """
        Carga las skills/herramientas descubiertas por el servidor MCP.
        Permite a Nova 'aprender' qué sabe hacer Hermes/OpenClaw.
        """
        try:
            req = urllib.request.Request(
                f"{self.base_url}/mcp/tools",
                headers={"Authorization": f"Bearer {self.api_key}"},
                method="GET"
            )
            with urllib.request.urlopen(req, timeout=5) as response:
                data = json.loads(response.read().decode('utf-8'))
                return data.get("tools", [])
        except Exception:
            return []

if __name__ == "__main__":
    mcp = NovaMCPClient()
    print("Herramientas disponibles en MCP Gateway:", mcp.get_available_tools())
