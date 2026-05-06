"""
Code Assistant Agent for Nova
Specialized agent for programming assistance, code review, debugging, and technical explanations.
"""

import os
import re
from typing import Optional, Dict, List

# Import Nova components
try:
    from nova.core.nova_router import NovaRouter
    from nova.tools.nova_skills import (
        web_search, read_text_file, write_text_file, 
        append_text_file, replace_in_text_file
    )
    _NOVA_COMPONENTS_AVAILABLE = True
    # Try to import GitHub components, but make them optional
    try:
        from nova.tools.nova_github import (
            skill_github_repos as github_repos,
            skill_github_issues as github_issues,
            skill_github_prs as github_prs
        )
    except ImportError:
        github_repos = github_issues = github_prs = None
except ImportError as e:
    print(f"[Code Assistant] Warning: Some Nova components not available: {e}")
    _NOVA_COMPONENTS_AVAILABLE = False
    github_repos = github_issues = github_prs = None

class CodeAssistantAgent:
    """
    Agente especializado en programación que proporciona:
    - Explicación de conceptos de programación
    - Asistencia en depuración
    - Sugerencias de código y mejores prácticas
    - Revisión de código
    - Búsqueda de documentación y ejemplos
    - Integración con GitHub (si está configurado)
    """
    
    def __init__(self):
        self.router = NovaRouter() if _NOVA_COMPONENTS_AVAILABLE else None
        self.language_hints = {
            'python': ['def ', 'import ', 'class ', 'if __name__'],
            'javascript': ['function ', 'const ', 'let ', '=>'],
            'java': ['public class', 'private ', 'public static void main'],
            'cpp': ['#include', 'class ', 'int main'],
            'html': ['<!DOCTYPE', '<html>', '<body>'],
            'css': ['{', '}', ':'],
            'sql': ['SELECT ', 'INSERT ', 'UPDATE ', 'CREATE TABLE']
        }
    
    def detect_language(self, code: str) -> str:
        """Intenta detectar el lenguaje de programación del código proporcionado."""
        code_lower = code.lower()
        for language, hints in self.language_hints.items():
            if any(hint in code_lower for hint in hints):
                return language
        return "texto plano"
    
    def explain_code(self, code: str) -> str:
        """Explica qué hace un fragmento de código."""
        if not _NOVA_COMPONENTS_AVAILABLE:
            return "Explicación de código: Servicio no disponible"
        
        language = self.detect_language(code)
        prompt = f"""
Explica en español qué hace el siguiente código de {language}:
{code}

Proporciona una explicación clara y concisa, línea por línea si es necesario,
mentionando el propósito general y cualquier concepto importante.
"""
        try:
            # Usar el router para obtener una explicación
            messages = [{"role": "user", "content": prompt}]
            result = self.router.route(messages=messages, max_tokens=500)
            return result.get("response", "No se pudo generar explicación")
        except Exception as e:
            return f"Error explicando código: {e}"
    
    def debug_code(self, code: str, error_message: str = "") -> str:
        """Ayuda a depurar un fragmento de código."""
        if not _NOVA_COMPONENTS_AVAILABLE:
            return "Depuración de código: Servicio no disponible"
        
        language = self.detect_language(code)
        prompt = f"""
Ayúdame a depurar el siguiente código de {language}:
{code}

{f"Error encontrado: {error_message}" if error_message else ""}

Por favor proporciona:
1. Posibles causas del problema
2. Sugerencias de cómo corregirlo
3. Código corregido si es posible
4. Explicación de qué estaba mal
"""
        try:
            # Usar el router para obtener una explicación
            messages = [{"role": "user", "content": prompt}]
            result = self.router.route(messages=messages, max_tokens=600)
            return result.get("response", "No se pudo generar ayuda para depuración")
        except Exception as e:
            return f"Error en depuración: {e}"
    
    def suggest_improvements(self, code: str) -> str:
        """Sugiere mejoras para un fragmento de código."""
        if not _NOVA_COMPONENTS_AVAILABLE:
            return "Mejoras de código: Servicio no disponible"
        
        language = self.detect_language(code)
        prompt = f"""
Analiza el siguiente código de {language} y sugiere mejoras:
{code}

Considera:
- Legibilidad y estilo
- Mejores prácticas
- Optimización de rendimiento
- Seguridad (si aplica)
- Mantenibilidad

Proporciona sugerencias específicas y, si es apropiado, muestra el código mejorado.
"""
        try:
            messages = [{"role": "user", "content": prompt}]
            result = self.router.route(messages=messages, max_tokens=500)
            return result.get("response", "No se pudieron generar sugerencias")
        except Exception as e:
            return f"Error sugiriendo mejoras: {e}"
    
    def search_documentation(self, query: str, language: str = "") -> str:
        """Busca documentación y ejemplos relacionados."""
        if not _NOVA_COMPONENTS_AVAILABLE:
            return "Búsqueda de documentación: Servicio no disponible"
        
        lang_part = f"en {language}" if language else ""
        search_query = f"{query} {lang_part} documentación ejemplos tutorial"
        
        try:
            results = web_search(search_query)
            return results
        except Exception as e:
            return f"Error buscando documentación: {e}"
    
    def generate_code(self, description: str, language: str = "python") -> str:
        """Genera código basado en una descripción."""
        if not _NOVA_COMPONENTS_AVAILABLE:
            return "Generación de código: Servicio no disponible"
        
        prompt = f"""
Genera código de {language} que cumpla con la siguiente descripción:
{description}

El código debe estar:
- Bien comentado
- Seguir mejores prácticas del lenguaje
- Ser funcional y completo
- Incluir manejo básico de errores si es apropiado

Proporciona solo el código, sin explicaciones adicionales unless specifically requested.
"""
        try:
            messages = [{"role": "user", "content": prompt}]
            result = self.router.route(messages=messages, max_tokens=400)
            return result.get("response", "No se pudo generar código")
        except Exception as e:
            return f"Error generando código: {e}"
    
    def review_github_activity(self, username: str = "", repo: str = "") -> str:
        """Revisa actividad reciente en GitHub (si está configurado)."""
        if not _NOVA_COMPONENTS_AVAILABLE or not github_repos:
            return "Revisión de GitHub: Servicio no disponible o GitHub no configurado"
        
        try:
            if username:
                activity = github_repos(username)
                if repo:
                    activity += "\n\n" + github_issues(repo)
                    activity += "\n\n" + github_prs(repo)
                return activity
            else:
                return "Por favor especifique un nombre de usuario de GitHub"
        except Exception as e:
            return f"Error accediendo a GitHub: {e}"
    
    def execute(self, task: str, task_type: str = "explain", **kwargs) -> str:
        """
        Ejecuta una tarea de asistencia de código.
        
        Args:
            task: Descripción de la tarea o código a analizar
            task_type: Tipo de tarea (explain, debug, improve, search, generate, github)
            **kwargs: Argumentos adicionales específicos del tipo de tarea
        """
        try:
            if task_type == "explain":
                return self.explain_code(task)
            elif task_type == "debug":
                error_msg = kwargs.get('error', '')
                return self.debug_code(task, error_msg)
            elif task_type == "improve":
                return self.suggest_improvements(task)
            elif task_type == "search":
                language = kwargs.get('language', '')
                return self.search_documentation(task, language)
            elif task_type == "generate":
                language = kwargs.get('language', 'python')
                return self.generate_code(task, language)
            elif task_type == "github":
                username = kwargs.get('username', '')
                repo = kwargs.get('repo', '')
                return self.review_github_activity(username, repo)
            else:
                return f"Tipo de tarea desconocido: {task_type}. Tipos válidos: explain, debug, improve, search, generate, github"
        except Exception as e:
            return f"Error ejecutando tarea de código: {e}"

# Funciones de conveniencia
def explain_code(code: str) -> str:
    """Función de conveniencia para explicar código."""
    agent = CodeAssistantAgent()
    return agent.execute(code, "explain")

def debug_code(code: str, error: str = "") -> str:
    """Función de conveniencia para depurar código."""
    agent = CodeAssistantAgent()
    return agent.execute(code, "debug", error=error)

def improve_code(code: str) -> str:
    """Función de conveniencia para sugerir mejoras."""
    agent = CodeAssistantAgent()
    return agent.execute(code, "improve")

def search_code_docs(query: str, language: str = "") -> str:
    """Función de conveniencia para buscar documentación."""
    agent = CodeAssistantAgent()
    return agent.execute(query, "search", language=language)

def generate_code_from_desc(description: str, language: str = "python") -> str:
    """Función de conveniencia para generar código."""
    agent = CodeAssistantAgent()
    return agent.execute(description, "generate", language=language)

def github_activity(username: str = "", repo: str = "") -> str:
    """Función de conveniencia para revisar actividad de GitHub."""
    agent = CodeAssistantAgent()
    return agent.execute("", "github", username=username, repo=repo)

if __name__ == "__main__":
    # Ejemplo de uso
    print("Code Assistant Agent - Ejemplo de uso:")
    print("=" * 50)
    
    sample_code = """
def fibonacci(n):
    if n <= 1:
        return n
    return fibonacci(n-1) + fibonacci(n-2)
"""
    
    print("\n1. Explicación de código:")
    print(explain_code(sample_code))
    
    print("\n2. Sugerencias de mejora:")
    print(improve_code(sample_code))