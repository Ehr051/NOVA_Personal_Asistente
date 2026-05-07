#!/usr/bin/env python3
"""
test_dispatcher.py — Prueba automatizada del dispatcher de NOVA
Testea todos los patterns sin iniciar el HUD ni el micrófono.
"""
import os, sys
os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"
sys.path.insert(0, "/Users/mac/Desktop/NOVA_Personal_Asistente")
sys.path.insert(0, "/Users/mac/Desktop/NOVA_Personal_Asistente/src")

import pytest

if os.getenv("NOVA_RUN_DISPATCHER_TESTS") != "1":
    pytest.skip(
        "Dispatcher script test touches real desktop apps/system state. "
        "Set NOVA_RUN_DISPATCHER_TESTS=1 to run it manually.",
        allow_module_level=True,
    )

# Importar skills (sin iniciar el loop de voz)
from nova.tools import nova_skills as skills

PASS = "✅"
FAIL = "❌"
SKIP = "⚠️ "

results = []

def test(label: str, command: str, expect_contains: str = None, expect_not_none: bool = True):
    """Ejecuta un comando en el dispatcher y verifica el resultado."""
    try:
        result = skills.dispatch(command)
        if result is None:
            if expect_not_none:
                results.append((FAIL, label, f"→ LLM (sin skill match) | cmd: '{command}'"))
            else:
                results.append((PASS, label, f"→ Sin match (esperado)"))
        else:
            short = result[:80].replace("\n", " ")
            if expect_contains and expect_contains.lower() not in result.lower():
                results.append((FAIL, label, f"'{expect_contains}' no en respuesta: {short}"))
            else:
                results.append((PASS, label, short))
    except Exception as e:
        results.append((FAIL, label, f"EXCEPCIÓN: {e}"))

def section(title: str):
    results.append(("──", title, ""))

# ─── Sección 1: Apps ───────────────────────────────────────────
section("SISTEMA & APPS")
test("Abre Safari",            "abre Safari",          "safari")
test("Abre música (alias)",    "abre música",          "Music")
test("Abre Chrome (español)",  "abre chrome",          "Chrome")
test("Abre navegador",         "abre el navegador",    "Chrome")
test("Lista apps instaladas",  "qué apps tengo instaladas", "instaladas")
test("Apps abiertas (v1)",     "apps activas",         None)
test("Apps abiertas (v2)",     "qué apps están abiertas", None)
test("En qué app estoy",       "qué app es esta",      None)
test("Batería",                "cuánta batería tengo", "%")
test("Estado sistema",         "estado del sistema",   "voz")

# ─── Sección 2: Volumen ─────────────────────────────────────────
section("VOLUMEN")
test("Volumen actual",         "qué volumen hay",      "%")
test("Sube volumen a 70",      "sube el volumen a 70", "70")
test("Baja volumen a 40",      "pon el volumen a 40",  "40")
test("Silenciar",              "silencia el audio",    None)
test("Activar audio",          "activa el audio",      None)

# ─── Sección 3: Mouse ──────────────────────────────────────────
section("MOUSE & TECLADO")
test("Mueve mouse a coords",   "mueve el mouse a 800 600",  "800")
test("Posición mouse",         "dónde está el ratón",       None)
test("Haz click",              "haz click",                 "click")
test("Click en coords",        "haz click en 500 300",      None)
test("Presiona enter",         "presiona enter",            None)
test("Presiona escape",        "presiona escape",           None)

# ─── Sección 4: Tiempo ─────────────────────────────────────────
section("TIEMPO")
test("Qué hora (con acento)",  "qué hora es",          ":")
test("Qué hora (sin acento)",  "que hora es",          ":")
test("Dime la hora",           "dime la hora",         ":")
test("Qué día (con acento)",   "qué día es hoy",       None)
test("Qué día (sin acento)",   "que dia es hoy",       None)
test("Dime la fecha",          "dime la fecha",        None)
test("Timer 5 min",            "pon un timer de 5 minutos", "5 min")
test("Alarma 3 min",           "alarma de 3 minutos",  "3 min")

# ─── Sección 5: Música ─────────────────────────────────────────
section("MÚSICA")
test("Pausa música",           "pausa la música",      None)
test("Siguiente canción (acento)", "siguiente canción", None)
test("Siguiente canción (sin)", "siguiente cancion",   None)
test("Canción anterior",       "canción anterior",     None)
test("Qué canción suena",      "qué está sonando",     None)
test("Shuffle on",             "shuffle activado",     None)

# ─── Sección 6: Archivos ───────────────────────────────────────
section("ARCHIVOS")
test("Qué hay en escritorio",  "que hay en mi escritorio",  "Desktop")
test("Qué hay en descargas",   "que hay en descargas",      "Downloads")
test("Busca archivo",          "busca el archivo requirements.txt", None)
test("Lista carpeta ~",        "lista la carpeta ~/Desktop", None)
test("Lee archivo",            "lee el archivo requirements.txt", None)

# ─── Sección 7: Notas ──────────────────────────────────────────
section("NOTAS (Apple Notes)")
test("Crea nota simple",       "crea una nota llamada test123", "test123")
test("Crea nota con body",     "crea una nota llamada ideas con texto: probar nova", "ideas")
test("Lista notas",            "mis notas",            None)

# ─── Sección 8: Obsidian ───────────────────────────────────────
section("OBSIDIAN / DIARIO")
test("Anota en diario",        "anota en el diario: prueba ok", None)
test("Anota (NO debe ir a Apple Notes)", "anota en obsidian: test", None)

# ─── Sección 9: Memoria ────────────────────────────────────────
section("MEMORIA")
test("Recuerda con 'que'",     "recuerda que mi color favorito es azul", None)
test("Recuerda sin 'que'",     "recuerda mi cumpleaños es el 2 de octubre", None)
test("Qué recuerdas sobre",    "qué recuerdas sobre mi color favorito", None)
test("Recuerdas algo de",      "recuerdas algo sobre el cumpleaños", None)

# ─── Sección 10: Web & Browser ─────────────────────────────────
section("WEB")
test("Busca en internet",      "busca en internet el precio del dólar", None)
test("Abre google.com (URL)",  "abre google.com",      None)  # puede fallar si no hay browser
test("Busca en navegador",     "busca en el navegador noticias argentinas", None)

# ─── Sección 11: Terminal ──────────────────────────────────────
section("TERMINAL")
test("Ejecuta con 'el'",       "ejecuta el comando pwd",   "/")
test("Ejecuta sin 'el'",       "ejecuta comando pwd",      "/")
test("Terminal directo",       "terminal: echo hola",      "hola")

# ─── Sección 12: Piloto automático ─────────────────────────────
section("PILOTO AUTOMÁTICO")
test("Piloto (NO debe ir a open_app)", "piloto automático abre chrome", None, expect_not_none=True)

# ─── Imprimir resultados ────────────────────────────────────────
print("\n" + "═"*70)
print("  NOVA — REPORTE DE PRUEBA AUTOMATIZADA DEL DISPATCHER")
print("═"*70)

passed = 0
failed = 0
for icon, label, detail in results:
    if icon == "──":
        print(f"\n  ── {label} ──")
        continue
    print(f"  {icon} {label:<42} {detail[:50]}")
    if icon == PASS:
        passed += 1
    elif icon == FAIL:
        failed += 1

total = passed + failed
print("\n" + "─"*70)
print(f"  Resultado: {passed}/{total} pasaron  |  {failed} fallaron")
print("─"*70 + "\n")

# Guardar reporte
import datetime
ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
report_path = f"/Users/mac/Desktop/NOVA_Personal_Asistente/test_report_{ts}.txt"
with open(report_path, "w") as f:
    for icon, label, detail in results:
        if icon == "──":
            f.write(f"\n── {label} ──\n")
        else:
            f.write(f"{icon} {label:<42} {detail}\n")
    f.write(f"\nResultado: {passed}/{total} pasaron | {failed} fallaron\n")
print(f"  Reporte guardado en: {report_path}\n")
