"""
Orchestrator Agent for Nova
Implements multi-turn reasoning and task decomposition capabilities.
"""

import json
import os
from typing import Dict, List, Optional, Any

# Import Nova components
try:
    from nova.core.nova_router import NovaRouter
    from nova.tools.nova_skills import (
        web_search, notes_create, notes_append,
        skill_calendario, skill_emails, get_time, get_date
    )
    _NOVA_COMPONENTS_AVAILABLE = True
except ImportError as e:
    print(f"[Orchestrator Agent] Warning: Some Nova components not available: {e}")
    _NOVA_COMPONENTS_AVAILABLE = False

class OrchestratorAgent:
    """
    Agente orquestador que proporciona:
    - Razonamiento multi-turno complejo
    - Descomposición de objetivos en sub-tareas
    - Selección automática de herramientas según la tarea
    - Validación y refinamiento iterativo de resultados
    - Integración con el sistema de skills para capacidades expandibles
    """
    
    def __init__(self, max_turns: int = 5):
        self.router = NovaRouter() if _NOVA_COMPONENTS_AVAILABLE else None
        self.max_turns = max_turns
        self.conversation_history = []
        self.available_tools = self._load_available_tools() if _NOVA_COMPONENTS_AVAILABLE else {}
        
    def _load_available_tools(self) -> Dict[str, Any]:
        """Carga las herramientas/skills disponibles para su uso"""
        tools = {}
        if _NOVA_COMPONENTS_AVAILABLE:
            from nova.tools import nova_skills
            import inspect
            
            # Get all functions that look like skills
            for name, obj in inspect.getmembers(nova_skills):
                if inspect.isfunction(obj) and not name.startswith('_') and name not in [
                    'dispatch', 'needs_web_search', 'maybe_clarify_command', 
                    'capabilities_summary', '_dispatch_nova_enhanced', '_update_env', 
                    '_restart_nova', '_type_via_clipboard', '_resolve_user_path', 
                    '_parse_path_and_content', '_osascript', '_app_paths', 
                    '_OPEN_APP_ALIASES', '_MALE_VOICES', '_FEMALE_VOICES', 
                    '_DIAS', '_MESES', '_active_timers', '_notify_cb', '_router', 
                    '_HAS_DDG', '_HAS_N8N', '_HAS_GITHUB', '_HAS_BROWSER', 
                    '_HAS_NOVA_ENHANCED', '_INTENTS', '_REALTIME_KEYWORDS', '_drive_last_results'
                ]:
                    tools[name] = obj
        return tools
    
    def decompose_goal(self, goal: str) -> List[Dict[str, str]]:
        """
        Descompone un objetivo complejo en sub-tareas manejables.
        """
        if not _NOVA_COMPONENTS_AVAILABLE:
            return [{"task": goal, "tool": "web_search", "description": "Búsqueda básica"}]
        
        try:
            # Usar el router para analizar y descomponer el objetivo
            prompt = f"""
            Analiza el siguiente objetivo y descompónlo en sub-tareas específicas y accionables:
            
            Objetivo: {goal}
            
            Para cada sub-tarea, proporciona:
            1. Descripción clara de la tarea
            2. Tipo de herramienta/skill que sería más apropiada para completarla
            3. Resultado esperado
            
            Formatea tu respuesta como una lista JSON de objetos con las claves:
            - "task": descripción de la sub-tarea
            - "tool": habilidad/skill recomendada para usar
            - "description": explicación de qué se busca lograr
            - "expected_result": qué se espera obtener como resultado
            
            Máximo 5 sub-tareas.
            """
            
            messages = [{"role": "user", "content": prompt}]
            result = self.router.route(messages=messages, max_tokens=800)
            response_text = result.get("response", "")
            
            # Intentar extraer JSON de la respuesta
            try:
                # Buscar contenido que parezca JSON
                start_idx = response_text.find('[')
                end_idx = response_text.rfind(']') + 1
                if start_idx != -1 and end_idx != 0:
                    json_str = response_text[start_idx:end_idx]
                    tasks = json.loads(json_str)
                    if isinstance(tasks, list):
                        return tasks
            except:
                pass
            
            # Fallback: descomposición básica
            return [
                {
                    "task": f"Investigar información básica sobre: {goal}",
                    "tool": "web_search",
                    "description": "Recopilar datos iniciales y contexto general",
                    "expected_result": "Información preliminar sobre el tema"
                },
                {
                    "task": f"Analizar y organizar la información recopilada sobre: {goal}",
                    "tool": "notes_create",
                    "description": "Crear un resumen estructurado de los hallazgos",
                    "expected_result": "Nota organizada con los puntos clave"
                }
            ]
            
        except Exception as e:
            print(f"[Orchestrator] Error descomponiendo objetivo: {e}")
            return [{"task": goal, "tool": "web_search", "description": "Búsqueda básica"}]
    
    def execute_tool(self, tool_name: str, task_description: str) -> str:
        """
        Ejecuta una herramienta específica con la descripción de la tarea.
        """
        if not _NOVA_COMPONENTS_AVAILABLE or tool_name not in self.available_tools:
            return f"Herramienta '{tool_name}' no disponible"
        
        try:
            tool_func = self.available_tools[tool_name]
            
            # Mapear descripciones de tareas a parámetros de función comunes
            if tool_name in ['web_search', 'skill_emails', 'skill_calendario']:
                # Estas funciones toman una cadena de consulta
                return tool_func(task_description)
            elif tool_name in ['notes_create', 'notes_append']:
                # Estas funciones toman título y contenido
                if tool_name == 'notes_create':
                    return tool_func(f"Orchestrator Task: {task_description}", 
                                   f"Resultado de la tarea: {task_description}")
                else:
                    return tool_func(f"Orchestrator Task: {task_description}", 
                                   f"Actualización: {task_description}")
            else:
                # Para otras funciones, intentar pasar la descripción como parámetro
                try:
                    return tool_func(task_description)
                except:
                    return f"Herramienta {tool_name} ejecutada con tarea: {task_description}"
                    
        except Exception as e:
            return f"Error ejecutando herramienta {tool_name}: {e}"
    
    def validate_result(self, goal: str, result: str, turn: int) -> Dict[str, Any]:
        """
        Valida si el resultado obtenido es suficiente para alcanzar el objetivo.
        """
        if not _NOVA_COMPONENTS_AVAILABLE:
            return {"sufficient": turn >= self.max_turns, "feedback": "Límite de turnos alcanzado"}
        
        try:
            prompt = f"""
            Evalúa si el siguiente resultado es suficiente para alcanzar el objetivo planteado:
            
            Objetivo original: {goal}
            Resultado obtenido (turno {turn}): {result[:500]}...
            
            Considera:
            1. ¿El resultado responde directamente al objetivo?
            2. ¿La información es completa y relevante?
            3. ¿Se necesitan más detalles o fuentes adicionales?
            4. ¿El resultado está bien organizado y es útil?
            
            Responde con un JSON que contenga:
            - "sufficient": boolean indicando si el resultado es suficiente
            - "feedback": explicación de por qué es o no suficiente
            - "suggestions": lista de sugerencias para mejorar (si es necesario)
            """
            
            messages = [{"role": "user", "content": prompt}]
            result_obj = self.router.route(messages=messages, max_tokens=400)
            response_text = result_obj.get("response", "{}")
            
            # Intentar extraer JSON
            try:
                start_idx = response_text.find('{')
                end_idx = response_text.rfind('}') + 1
                if start_idx != -1 and end_idx != 0:
                    json_str = response_text[start_idx:end_idx]
                    return json.loads(json_str)
            except:
                pass
                
            # Fallback basado en longitud y presencia de contenido
            sufficient = len(result) > 100 and turn >= 2
            return {
                "sufficient": sufficient,
                "feedback": "Resultado parece adecuado" if sufficient else "Necesita más detalle o vueltas adicionales",
                "suggestions": ["Profundizar en aspectos específicos"] if not sufficient else []
            }
            
        except Exception as e:
            print(f"[Orchestrator] Error validando resultado: {e}")
            return {"sufficient": turn >= self.max_turns, "feedback": "Error en validación, continuando por límite de turnos"}
    
    def execute(self, goal: str) -> str:
        """
        Ejecuta el proceso de razonamiento multi-turno para alcanzar un objetivo.
        """
        if not _NOVA_COMPONENTS_AVAILABLE:
            return "Orchestrator Agent: Servicio no disponible"
        
        try:
            print(f"🎯 Iniciando orquestación para: {goal}")
            
            # Descomponer el objetivo
            sub_tasks = self.decompose_goal(goal)
            print(f"📋 Descompuesto en {len(sub_tasks)} sub-tareas")
            
            # Ejecutar cada sub-tarea
            all_results = []
            for i, task_info in enumerate(sub_tasks):
                print(f"⚙️  Ejecutando sub-tarea {i+1}/{len(sub_tasks)}: {task_info['task']}")
                
                result = self.execute_tool(
                    task_info.get('tool', 'web_search'),
                    task_info['task']
                )
                
                task_result = {
                    "task": task_info['task'],
                    "tool_used": task_info.get('tool', 'unknown'),
                    "result": result,
                    "turn": i + 1
                }
                all_results.append(task_result)
                
                # Guardar en historial de conversación
                self.conversation_history.append({
                    "role": "assistant",
                    "content": f"Tarea: {task_info['task']}\nResultado: {result[:200]}..."
                })
                
                # Validar si podemos terminar temprano
                validation = self.validate_result(goal, result, i + 1)
                if validation.get("sufficient", False):
                    print(f"✅ Objetivo alcanzado en turno {i+1}")
                    break
                    
                # Si no es suficiente y no es el último turno, considerar refinamiento
                if not validation.get("sufficient", False) and i < len(sub_tasks) - 1:
                    suggestions = validation.get("suggestions", [])
                    if suggestions:
                        print(f"💡 Sugerencias para mejora: {', '.join(suggestions[:2])}")
            
            # Sintetizar resultados finales
            final_result = self._synthesize_results(goal, all_results)
            return final_result
            
        except Exception as e:
            return f"Error en la orquestación: {e}"
    
    def _synthesize_results(self, goal: str, results: List[Dict]) -> str:
        """
        Sintetiza todos los resultados obtenidos en una respuesta coherente.
        """
        if not results:
            return f"No se pudo obtener resultados para el objetivo: {goal}"
        
        try:
            if _NOVA_COMPONENTS_AVAILABLE and self.router:
                # Usar el router para crear una síntesis inteligente
                results_summary = []
                for i, res in enumerate(results):
                    results_summary.append(
                        f"Sub-tarea {i+1} ({res['task']}):\n"
                        f"Herramienta usada: {res['tool_used']}\n"
                        f"Resultado: {res['result'][:300]}{'...' if len(res['result']) > 300 else ''}\n"
                    )
                
                prompt = f"""
                Sintetiza los siguientes resultados obtenidos en búsqueda del objetivo: {goal}
                
                {''.join(results_summary)}
                
                Proporciona una respuesta coherente, bien estructurada y directamente relevante al objetivo.
                Incluye los puntos clave, elimina redundancias y presenta la información de manera útil.
                """
                
                messages = [{"role": "user", "content": prompt}]
                result_obj = self.router.route(messages=messages, max_tokens=600)
                return result_obj.get("response", "Error generando síntesis")
            else:
                # Síntesis básica
                synthesis = [f"Resultado para el objetivo: {goal}\n"]
                synthesis.append("=" * 50)
                
                for i, res in enumerate(results):
                    synthesis.append(f"\nSub-tarea {i+1}: {res['task']}")
                    synthesis.append(f"Herramienta: {res['tool_used']}")
                    synthesis.append(f"Resultado: {res['result']}")
                    synthesis.append("-" * 30)
                
                synthesis.append("\nSíntesis completada por el Agente Orquestador.")
                return "\n".join(synthesis)
                
        except Exception as e:
            # Síntesis de emergencia
            synthesis = [f"Resultados para: {goal}\n"]
            for i, res in enumerate(results):
                synthesis.append(f"{i+1}. {res['task']}: {res['result'][:200]}...")
            return "\n".join(synthesis)

# Función de conveniencia para uso externo
def orchestrator_execute(goal: str, max_turns: int = 5) -> str:
    """Función de conveniencia para ejecutar el agente orquestador."""
    agent = OrchestratorAgent(max_turns=max_turns)
    return agent.execute(goal)

if __name__ == "__main__":
    # Ejemplo de uso directo
    print("Orchestrator Agent - Ejemplo de uso:")
    print("=" * 40)
    
    # Ejemplo simple
    result = orchestrator_execute("¿Cuál es el clima actual en Buenos Aires y qué noticias tecnológicas son relevantes hoy?")
    print("\nResultado:")
    print(result)