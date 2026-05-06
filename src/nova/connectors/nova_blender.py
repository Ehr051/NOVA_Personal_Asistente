"""
nova_blender.py
───────────────
Integración de Nova con Blender vía blender-mcp socket (addon BlenderMCP).

Arquitectura:
  Nova → nova_blender.py → socket TCP 127.0.0.1:9876 → BlenderMCP addon → Blender Python API

Requiere:
  1. Blender abierto con el addon blender_mcp_addon.py activado
  2. El addon escucha en el puerto 9876 por defecto

Uso:
    from nova.connectors.nova_blender import ejecutar_en_blender, generar_objeto_desde_descripcion
    resultado = ejecutar_en_blender("import bpy; bpy.ops.mesh.primitive_cube_add()")
    resultado = generar_objeto_desde_descripcion("una silla de cuatro patas con respaldo")
"""

from __future__ import annotations

import os
import json
import socket
import logging
import subprocess
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)

_BLENDER_HOST = "127.0.0.1"
_BLENDER_PORT = 9876
_BLENDER_APP  = "/Applications/Blender.app/Contents/MacOS/Blender"
_SCRIPTS_DIR  = Path.home() / "Desktop" / "Nova_Blender_Scripts"

_OLLAMA_BASE  = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434/v1")


# ─── Conexión al addon ────────────────────────────────────────────────────────

def _esta_blender_activo() -> bool:
    """Verifica si Blender está corriendo con el addon MCP activo."""
    try:
        with socket.create_connection((_BLENDER_HOST, _BLENDER_PORT), timeout=2):
            return True
    except (ConnectionRefusedError, OSError):
        return False


def ejecutar_en_blender(codigo_python: str) -> str:
    """
    Ejecuta código Python directamente en Blender via el addon MCP.
    Retorna el resultado o error.
    """
    if not _esta_blender_activo():
        return (
            "Blender no está conectado, Señor. "
            "Abrí Blender → Edit → Preferences → Add-ons → activá 'BlenderMCP' → "
            "hacé click en 'Start Server'."
        )
    try:
        with socket.create_connection((_BLENDER_HOST, _BLENDER_PORT), timeout=30) as s:
            payload = json.dumps({"type": "execute_code", "params": {"code": codigo_python}})
            s.sendall(payload.encode())
            response = b""
            s.settimeout(10)
            try:
                while True:
                    chunk = s.recv(4096)
                    if not chunk:
                        break
                    response += chunk
                    # Try parse — addon sends one JSON object then closes connection
                    try:
                        json.loads(response.decode())
                        break
                    except json.JSONDecodeError:
                        pass
            except socket.timeout:
                pass
            result = json.loads(response.decode())
            if result.get("status") == "success":
                inner = result.get("result", {})
                output = inner.get("result", "").strip() if isinstance(inner, dict) else str(inner).strip()
                return output if output else "Ejecutado OK en Blender."
            return f"Error en Blender: {result.get('message', result.get('error', 'desconocido'))}"
    except Exception as e:
        return f"No pude conectarme a Blender: {e}"


def guardar_script(nombre: str, codigo: str) -> str:
    """Guarda un script Python para Blender en ~/Desktop/Nova_Blender_Scripts/."""
    _SCRIPTS_DIR.mkdir(parents=True, exist_ok=True)
    nombre_safe = nombre.replace(" ", "_").replace("/", "_")
    if not nombre_safe.endswith(".py"):
        nombre_safe += ".py"
    path = _SCRIPTS_DIR / nombre_safe
    path.write_text(codigo, encoding="utf-8")
    return str(path)


# ─── Sistema de aprendizaje: ejemplos de referencia ──────────────────────────

_EXAMPLES_DIR = Path(__file__).parent / "blender_examples"


def _buscar_ejemplos(descripcion: str, max_ejemplos: int = 2) -> list[dict]:
    """Busca ejemplos relevantes por tags para usar como few-shot."""
    idx_file = _EXAMPLES_DIR / "_index.json"
    if not idx_file.exists():
        return []
    try:
        idx = json.loads(idx_file.read_text())
        desc_lower = descripcion.lower()
        scored = []
        for ej in idx.get("ejemplos", []):
            if not ej.get("aprobado"):
                continue
            score = sum(1 for tag in ej.get("tags", []) if tag in desc_lower)
            if score > 0:
                scored.append((score, ej))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [e for _, e in scored[:max_ejemplos]]
    except Exception:
        return []


def guardar_ejemplo(nombre: str, descripcion: str, codigo: str,
                    tags: list[str] | None = None, aprobado: bool = False) -> str:
    """Guarda un script generado/aprobado como ejemplo de referencia futuro."""
    _EXAMPLES_DIR.mkdir(parents=True, exist_ok=True)
    safe = nombre.replace(" ", "_").lower()
    if not safe.endswith(".py"):
        safe += ".py"
    path = _EXAMPLES_DIR / safe
    path.write_text(codigo, encoding="utf-8")

    idx_file = _EXAMPLES_DIR / "_index.json"
    idx = json.loads(idx_file.read_text()) if idx_file.exists() else {"ejemplos": []}
    # actualizar o agregar
    existing = next((e for e in idx["ejemplos"] if e["archivo"] == safe), None)
    entry = {
        "archivo": safe,
        "titulo": descripcion[:80],
        "tags": tags or descripcion.lower().split()[:10],
        "tecnicas": [],
        "aprobado": aprobado,
    }
    if existing:
        existing.update(entry)
    else:
        idx["ejemplos"].append(entry)
    idx_file.write_text(json.dumps(idx, ensure_ascii=False, indent=2))
    return str(path)


# ─── Generación de objetos con LLM ───────────────────────────────────────────

def _generar_script_con_llm(descripcion: str, tipo: str = "objeto") -> str:
    """Usa LLM para generar código Python de Blender desde una descripción."""
    from openai import OpenAI
    try:
        from dotenv import load_dotenv
        from pathlib import Path as _Path
        _env = _Path(__file__).parents[3] / ".env"
        if _env.exists():
            load_dotenv(_env, override=False)
    except Exception:
        pass
    key = os.getenv("GROQ_API_KEY", "").strip()
    if key and not key.startswith("gsk_..."):
        client = OpenAI(base_url="https://api.groq.com/openai/v1", api_key=key)
        model = "llama-3.3-70b-versatile"
    else:
        client = OpenAI(base_url=_OLLAMA_BASE, api_key="ollama")
        model = "qwen2.5:7b"

    # Detectar si es pieza mecánica/paramétrica para usar system prompt especializado
    _mecanico = any(w in descripcion.lower() for w in [
        "engranaje", "gear", "diente", "tooth", "ruleman", "rodamiento", "bearing",
        "tuerca", "tornillo", "perno", "bolt", "nut", "screw", "hélice", "helice",
        "piñon", "piñón", "cremallera", "rack", "leva", "cam", "resorte", "spring",
        "rosca", "thread", "hexagonal", "poligono", "polygon",
    ])

    if _mecanico:
        system = """Sos un experto en modelado 3D paramétrico con Blender Python API (bpy) 4.x y bmesh.
Generá código Python preciso y funcional para crear la pieza mecánica descrita.
REGLAS ESTRICTAS:
- Solo código Python válido, sin explicaciones ni comentarios
- Empezá con: import bpy, bmesh, math; bpy.ops.object.select_all(action='DESELECT')
- Para engranajes: calculá vértices con math.cos/sin, usá bmesh para crear dientes reales
- Para agujeros: usá modifier BOOLEAN con cilindros cutter, luego apply y remove cutter
- NUNCA uses bpy.ops.transform.rotate() ni bpy.ops.transform.resize() — deprecados en 4.x
- Para materiales: mat.use_nodes=True; bsdf = next(n for n in mat.node_tree.nodes if n.type=='BSDF_PRINCIPLED')
- Posicioná con primitive_add(location=...) o .location / .rotation_euler / .scale directo
- Nombrá cada objeto: bpy.context.active_object.name = "nombre"
- Al final: bpy.context.view_layer.update()
- Máximo 80 líneas, código denso y funcional"""
    else:
        system = """Sos un experto en Blender Python API (bpy) versión 4.x.
Generá código Python para Blender 4.x que cree el objeto/escena descrito.
REGLAS ESTRICTAS:
- Solo código Python válido, sin explicaciones ni comentarios
- Empezá con: import bpy; bpy.ops.object.select_all(action='DESELECT')
- Para posicionar usá SIEMPRE parámetros de primitive_add: location=(x,y,z), rotation=(rx,ry,rz), scale=(sx,sy,sz)
- NUNCA uses bpy.ops.transform.rotate() ni bpy.ops.transform.resize() — deprecados en 4.x
- NUNCA uses bpy.ops.object.select_all() a mitad del script para aplicar materiales
- Nombrá cada objeto: bpy.context.active_object.name = "nombre"
- Para materiales: mat = bpy.data.materials.new("nombre"); mat.use_nodes = True; bsdf = next(n for n in mat.node_tree.nodes if n.type == 'BSDF_PRINCIPLED'); bsdf.inputs["Base Color"].default_value = (r,g,b,1); objeto.data.materials.append(mat)
- Aplicá el material INMEDIATAMENTE después de crear cada objeto, antes de crear el siguiente
- Al final: bpy.context.view_layer.update()
- Máximo 70 líneas, sin markdown, sin ```python"""

    prompts = {
        "objeto": f"Creá en Blender este objeto 3D: {descripcion}",
        "escena": f"Creá en Blender esta escena 3D: {descripcion}",
        "desde_descripcion_cad": (
            f"Creá en Blender un modelo 3D basado en esta descripción técnica de un objeto real:\n{descripcion}"
        ),
    }
    prompt = prompts.get(tipo, prompts["objeto"])

    # Inyectar ejemplos de referencia como few-shot
    ejemplos = _buscar_ejemplos(descripcion)
    messages: list[dict] = [{"role": "system", "content": system}]
    for ej in ejemplos:
        ej_path = _EXAMPLES_DIR / ej["archivo"]
        if ej_path.exists():
            ej_code = ej_path.read_text(encoding="utf-8")
            # Limitar a 300 líneas para no saturar el contexto
            lines = ej_code.splitlines()[:300]
            messages.append({"role": "user",
                              "content": f"Ejemplo de referencia — {ej['titulo']}:"})
            messages.append({"role": "assistant",
                              "content": "\n".join(lines)})
    messages.append({"role": "user", "content": prompt})

    try:
        resp = client.chat.completions.create(
            model=model,
            messages=messages,
            max_tokens=4096,
            temperature=0.15,
            timeout=120,
        )
        codigo = resp.choices[0].message.content.strip()
        # Limpiar markdown si el modelo lo incluyó igual
        if "```" in codigo:
            import re
            codigo = re.sub(r"```(?:python)?\n?", "", codigo).strip()
        return codigo
    except Exception as e:
        log.warning("LLM para Blender falló: %s", e)
        return ""


def generar_objeto_desde_descripcion(descripcion: str, ejecutar: bool = True) -> str:
    """
    Genera código Blender Python desde una descripción en lenguaje natural
    y opcionalmente lo ejecuta en Blender si está conectado.
    """
    codigo = _generar_script_con_llm(descripcion, tipo="objeto")
    if not codigo:
        return "No pude generar el script de Blender, Señor."

    path = guardar_script(descripcion[:40], codigo)
    _ultimo_script.update({"descripcion": descripcion, "codigo": codigo, "path": path})

    if ejecutar and _esta_blender_activo():
        resultado = ejecutar_en_blender(codigo)
        return f"Objeto creado en Blender, Señor.\nScript guardado en: {path}\nResultado: {resultado}"
    elif ejecutar:
        return (
            f"Script generado y guardado, Señor: {path}\n"
            "Blender no está conectado. Abrí Blender con el addon MCP activo para ejecutarlo."
        )
    return f"Script generado: {path}\n\n{codigo[:300]}..."


def generar_desde_vision_cad(descripcion_cad: str) -> str:
    """
    Toma la descripción técnica de vision_para_cad() y la convierte en modelo 3D en Blender.
    Pipeline completo: objeto real → descripción técnica → script Blender → modelo 3D.
    """
    codigo = _generar_script_con_llm(descripcion_cad, tipo="desde_descripcion_cad")
    if not codigo:
        return "No pude generar el modelo 3D, Señor."

    path = guardar_script("objeto_desde_camara", codigo)

    if _esta_blender_activo():
        resultado = ejecutar_en_blender(codigo)
        return f"Modelo 3D creado en Blender desde la cámara, Señor.\nScript: {path}"
    return (
        f"Script 3D generado desde la cámara, Señor: {path}\n"
        "Abrí Blender con el addon MCP para ejecutarlo automáticamente."
    )


_ultimo_script: dict = {}   # {"descripcion": ..., "codigo": ..., "path": ...}


def aprobar_ultimo_script(tags: list[str] | None = None) -> str:
    """Marca el último script generado como ejemplo aprobado para aprendizaje futuro."""
    if not _ultimo_script:
        return "No hay ningún script reciente para aprobar, Señor."
    nombre = Path(_ultimo_script["path"]).stem
    path = guardar_ejemplo(
        nombre=nombre,
        descripcion=_ultimo_script["descripcion"],
        codigo=_ultimo_script["codigo"],
        tags=tags,
        aprobado=True,
    )
    return f"Script aprobado y guardado como ejemplo de referencia, Señor: {path}"


def abrir_blender() -> str:
    """Abre Blender en background."""
    try:
        subprocess.Popen([_BLENDER_APP], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return "Abriendo Blender, Señor. Una vez abierto activá el addon MCP."
    except Exception as e:
        return f"No pude abrir Blender: {e}"


def estado_blender() -> str:
    """Verifica si Blender está conectado."""
    if _esta_blender_activo():
        return "Blender conectado y listo, Señor."
    import subprocess
    result = subprocess.run(["pgrep", "-x", "Blender"], capture_output=True, text=True)
    if result.stdout.strip():
        return "Blender está abierto pero el addon MCP no está activo, Señor. Activá el addon en Edit → Preferences → Add-ons."
    return "Blender no está abierto, Señor."


# Alias para compatibilidad con nova_specialist
ejecutar_script = ejecutar_en_blender


# ─── Auto-evaluación con vision ───────────────────────────────────────────────

def _capturar_pantalla_bytes() -> bytes:
    """Captura la pantalla actual y devuelve bytes JPEG."""
    import io, pyautogui
    from PIL import Image
    img = pyautogui.screenshot()
    buf = io.BytesIO()
    img.convert("RGB").resize((1280, 720)).save(buf, format="JPEG", quality=85)
    return buf.getvalue()


def _comparar_con_openrouter(ref_bytes: bytes, modelo_bytes: bytes, descripcion: str) -> str:
    """
    Envía imagen de referencia (cámara) + screenshot de Blender a un modelo de visión
    de OpenRouter y pide que compare ambas. Retorna las diferencias o 'correcto'.
    """
    import base64, json, os, urllib.request
    or_key = os.getenv("OPENROUTER_API_KEY", "").strip()
    if not or_key or or_key.startswith("sk-or-v1-..."):
        return "[sin OpenRouter para comparar]"
    b64_ref = base64.b64encode(ref_bytes).decode()
    b64_mod = base64.b64encode(modelo_bytes).decode()
    prompt = (
        f"IMAGEN 1: objeto real de referencia — '{descripcion}'.\n"
        "IMAGEN 2: modelo 3D generado en Blender.\n"
        "Comparalas y listá en 2-3 puntos qué diferencias hay: forma, proporciones, detalles faltantes o incorrectos. "
        "Si coinciden fielmente → respondé solo 'correcto'."
    )
    for model in ["google/gemma-4-31b-it:free", "nvidia/nemotron-nano-12b-v2-vl:free", "google/gemma-3-27b-it:free"]:
        payload = {"model": model, "messages": [{"role": "user", "content": [
            {"type": "text", "text": prompt},
            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64_ref}"}},
            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64_mod}"}},
        ]}], "max_tokens": 300, "temperature": 0.2}
        try:
            req = urllib.request.Request(
                "https://openrouter.ai/api/v1/chat/completions",
                data=json.dumps(payload).encode(),
                headers={"Content-Type": "application/json", "Authorization": f"Bearer {or_key}",
                         "HTTP-Referer": "https://github.com/nova-assistant", "X-Title": "NOVA"},
            )
            with urllib.request.urlopen(req, timeout=60) as r:
                resp = json.loads(r.read())
                text = (resp.get("choices", [{}])[0].get("message", {}).get("content") or "").strip()
                if text:
                    log.info("[crear_con_vision] Comparación OK via %s", model)
                    return text
        except Exception as e:
            log.warning("[crear_con_vision] Comparación %s falló: %s", model, e)
    return "[comparación no disponible]"


def crear_con_vision(descripcion: str, max_iter: int = 3, camara_idx: int = 0) -> str:
    """
    Ciclo completo: captura objeto real de cámara → genera en Blender → compara
    visualmente cámara vs Blender → corrige hasta max_iter veces.

    Flujo por iteración:
      0. Captura imagen de referencia de la cámara (una vez al inicio, y cada iteración fallida)
      1. Genera modelo 3D en Blender
      2. Activa ventana Blender + espera 2s
      3. Captura screenshot del viewport de Blender
      4. Compara AMBAS imágenes (referencia cámara + Blender) via OpenRouter
      5. Si hay diferencias → actualiza descripción con el feedback y reintenta
    """
    import time, subprocess

    try:
        from nova.connectors.nova_vision import _capturar_camara, _llamar_vision
        _vision_ok = True
    except ImportError:
        _capturar_camara = None
        _vision_ok = False

    # Paso 0: capturar referencia inicial de la cámara
    ref_bytes: bytes | None = None
    if _vision_ok and _capturar_camara:
        ref_bytes = _capturar_camara(camara_idx)
        if ref_bytes:
            log.info("[crear_con_vision] Referencia de cámara capturada (%d bytes)", len(ref_bytes))
        else:
            log.warning("[crear_con_vision] No se pudo capturar imagen de cámara")

    descripcion_actual = descripcion
    historial: list[str] = []

    for intento in range(1, max_iter + 1):
        log.info("[crear_con_vision] Intento %d/%d", intento, max_iter)

        # Paso 1: generar y ejecutar en Blender
        generar_objeto_desde_descripcion(descripcion_actual, ejecutar=True)

        # Paso 2: traer Blender al frente y esperar que renderice
        time.sleep(2)
        try:
            subprocess.run(["osascript", "-e", 'tell application "Blender" to activate'],
                           capture_output=True, timeout=3)
            time.sleep(0.8)
        except Exception:
            pass

        if not _vision_ok:
            return f"Modelo creado en intento {intento}. Sin visión para evaluar."

        # Paso 3: capturar screenshot del viewport de Blender
        try:
            blender_bytes = _capturar_pantalla_bytes()
        except Exception as e:
            return f"Modelo creado. Error capturando pantalla: {e}"

        # Paso 4: comparar referencia de cámara vs modelo en Blender
        if ref_bytes:
            analisis = _comparar_con_openrouter(ref_bytes, blender_bytes, descripcion)
        else:
            # Sin referencia de cámara: solo evaluar el modelo contra la descripción
            analisis = _llamar_vision(
                blender_bytes,
                f"¿Este modelo 3D en Blender representa correctamente: '{descripcion}'? "
                "Lista 2-3 diferencias o di 'correcto'."
            )

        historial.append(f"Intento {intento}: {analisis}")
        log.info("[crear_con_vision] Análisis: %s", analisis[:160])

        # Paso 5: ¿aprobado?
        if any(p in analisis.lower() for p in ["correcto", "coincide", "bien representado", "looks good"]):
            return (
                f"Modelo aprobado en intento {intento}/{max_iter}, Señor.\n"
                f"Análisis final: {analisis}"
            )

        # Paso 6: no aprobado → volver a mirar la cámara para detalles frescos
        if intento < max_iter and _capturar_camara:
            nuevo_ref = _capturar_camara(camara_idx)
            if nuevo_ref:
                ref_bytes = nuevo_ref
                log.info("[crear_con_vision] Referencia de cámara actualizada para intento %d", intento + 1)

        descripcion_actual = f"{descripcion}. Correcciones: {analisis.strip()}"

    return (
        f"Límite de {max_iter} intentos alcanzado, Señor. El modelo puede tener imprecisiones.\n"
        f"Último análisis: {historial[-1] if historial else 'sin evaluación'}"
    )
