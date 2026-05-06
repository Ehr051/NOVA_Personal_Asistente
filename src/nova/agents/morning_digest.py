"""
Morning Digest Agent for Nova
Provides a personalized morning briefing with weather, calendar, news, dollar quote, and reminders.
"""

import datetime
import html as _html
import json
import os
import re
import urllib.parse
import urllib.request
import urllib.error
import xml.etree.ElementTree as ET
from typing import Dict, List, Optional

# Import Nova components
try:
    from nova.core.nova_router import NovaRouter
    from nova.tools.nova_skills import (
        get_time, get_date, get_weather, skill_calendario,
        skill_emails, web_search, notes_create
    )
    from nova.tools.nova_neuro_memory import neuro_memory
    _NOVA_COMPONENTS_AVAILABLE = True
except ImportError as e:
    print(f"[Morning Digest] Warning: Some Nova components not available: {e}")
    _NOVA_COMPONENTS_AVAILABLE = False

class MorningDigestAgent:
    """
    Agente de resumen matutino que proporciona:
    - Hora y fecha
    - Clima local
    - Revisión de calendario del día
    - Resumen de correos importantes
    - Noticias relevantes
    - Recordatorios personales
    """
    
    # Fuentes preferidas para diversificar puntos de vista
    DEFAULT_NEWS_SOURCES = [
        "tn.com.ar",            # TN - Todo Noticias (AR)
        "dw.com",               # Deutsche Welle (DE/internacional)
        "actualidad.rt.com",    # RT en español (RU)
        "lanacion.com.ar",      # La Nación (AR)
    ]

    def __init__(self):
        self.router = NovaRouter() if _NOVA_COMPONENTS_AVAILABLE else None
        self.neuro_memory = neuro_memory if _NOVA_COMPONENTS_AVAILABLE else None
        self.location = os.getenv("MORNING_DIGEST_LOCATION", "Buenos Aires")
        self.news_topics = [
            t.strip() for t in os.getenv(
                "MORNING_DIGEST_NEWS_TOPS",
                "tecnología,política,economía"
            ).split(",") if t.strip()
        ]
        sources_env = os.getenv("MORNING_DIGEST_NEWS_SOURCES", "").strip()
        self.news_sources = (
            [s.strip() for s in sources_env.split(",") if s.strip()]
            if sources_env
            else list(self.DEFAULT_NEWS_SOURCES)
        )
        
    def get_weather(self) -> str:
        """Obtiene el clima actual usando la skill get_weather (wttr.in, datos reales)."""
        if not _NOVA_COMPONENTS_AVAILABLE:
            return "Clima: Servicio no disponible"
        try:
            return get_weather(self.location)
        except Exception as e:
            return f"Error obteniendo clima: {e}"
    
    def get_calendar(self) -> str:
        """Obtiene los eventos del calendario para hoy."""
        if not _NOVA_COMPONENTS_AVAILABLE:
            return "Calendario: Servicio no disponible"
        try:
            # Usar skill de calendario
            calendar_info = skill_calendario("hoy")
            return calendar_info
        except Exception as e:
            return f"Error obteniendo calendario: {e}"
    
    def get_emails_summary(self) -> str:
        """Obtiene un resumen de correos importantes."""
        if not _NOVA_COMPONENTS_AVAILABLE:
            return "Correos: Servicio no disponible"
        try:
            # Buscar correos urgentes o importantes
            emails_info = skill_emails("urgentes importantes")
            return emails_info
        except Exception as e:
            return f"Error obteniendo correos: {e}"
    
    def _fetch_google_news_rss(
        self,
        query: str,
        limit: int = 3,
        restrict_sites: Optional[List[str]] = None,
    ) -> List[Dict[str, str]]:
        """Descarga el RSS de Google News para una query y devuelve los top N titulares.

        Si restrict_sites se provee, filtra los resultados a esos dominios via operador `site:`.
        """
        if restrict_sites:
            sites_filter = "(" + " OR ".join(f"site:{s}" for s in restrict_sites) + ")"
            full_query = f"{sites_filter} {query}"
        else:
            full_query = query
        url = (
            "https://news.google.com/rss/search?"
            + urllib.parse.urlencode({
                "q": full_query,
                "hl": "es-419",
                "gl": "AR",
                "ceid": "AR:es-419",
            })
        )
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 Nova/1.0"})
        with urllib.request.urlopen(req, timeout=8) as resp:
            xml_bytes = resp.read()
        root = ET.fromstring(xml_bytes)
        channel = root.find("channel")
        if channel is None:
            return []
        items: List[Dict[str, str]] = []
        for item in channel.findall("item")[:limit]:
            title_el = item.find("title")
            source_el = item.find("source")
            desc_el = item.find("description")
            pub_el = item.find("pubDate")
            title = (title_el.text or "").strip() if title_el is not None else ""
            source = (source_el.text or "").strip() if source_el is not None else ""
            # title comes as "Titular - Fuente"; strip the suffix if source matches
            if source and title.endswith(f" - {source}"):
                title = title[: -(len(source) + 3)]
            desc_raw = (desc_el.text or "") if desc_el is not None else ""
            # Strip HTML tags from description, decode entities, collapse whitespace
            desc_clean = re.sub(r"<[^>]+>", " ", desc_raw)
            desc_clean = _html.unescape(desc_clean)
            desc_clean = re.sub(r"\s+", " ", desc_clean).strip()
            # Description in Google News RSS often repeats the same headlines list — keep first 180 chars
            summary = desc_clean[:200].rstrip()
            pub = (pub_el.text or "").strip() if pub_el is not None else ""
            items.append({"title": title, "source": source, "summary": summary, "pub": pub})
        return items

    def get_news(self) -> str:
        """Obtiene titulares reales por tópico, restringidos a las fuentes preferidas."""
        sections: List[str] = []
        for topic in self.news_topics[:3]:
            topic_clean = topic.strip()
            try:
                items = self._fetch_google_news_rss(
                    f"{topic_clean} Argentina",
                    limit=3,
                    restrict_sites=self.news_sources,
                )
                # Fallback: si las fuentes preferidas no devolvieron nada, abrir el filtro
                if not items:
                    items = self._fetch_google_news_rss(
                        f"{topic_clean} Argentina",
                        limit=3,
                    )
            except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ET.ParseError) as e:
                sections.append(f"• {topic_clean.capitalize()}: error obteniendo noticias ({e})")
                continue
            except Exception as e:
                sections.append(f"• {topic_clean.capitalize()}: error inesperado ({e})")
                continue

            if not items:
                sections.append(f"• {topic_clean.capitalize()}: sin titulares.")
                continue

            lines = [f"• {topic_clean.upper()}:"]
            for it in items:
                src = f" ({it['source']})" if it["source"] else ""
                lines.append(f"  – {it['title']}{src}")
            sections.append("\n".join(lines))
        return "\n".join(sections) if sections else "Sin noticias disponibles."

    DOLARHOY_PAGES = [
        ("Oficial", "https://dolarhoy.com/cotizacion-dolar-oficial"),
        ("Blue", "https://dolarhoy.com/cotizacion-dolar-blue"),
        ("MEP", "https://dolarhoy.com/cotizacion-dolar-mep"),
        ("CCL", "https://dolarhoy.com/cotizacion-dolar-ccl"),
    ]

    def _scrape_dolarhoy_page(self, url: str) -> Optional[Dict[str, str]]:
        """Devuelve {compra, venta} desde una subpágina de DolarHoy, o None si falla."""
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 Nova/1.0"})
        try:
            with urllib.request.urlopen(req, timeout=6) as resp:
                html = resp.read().decode("utf-8", errors="ignore")
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError):
            return None
        # En DolarHoy la primera página de cada cotización tiene un panel principal
        # con el primer "$1380,00" como compra y el segundo como venta.
        prices = re.findall(r"\$\s*([0-9]+(?:[.,][0-9]+)?)", html)
        if len(prices) < 2:
            return None
        return {"compra": prices[0], "venta": prices[1]}

    def get_dolar_ar(self) -> str:
        """Obtiene cotizaciones del dólar AR desde DolarHoy (con fallback a dolarapi.com)."""
        lines: List[str] = []
        for label, url in self.DOLARHOY_PAGES:
            row = self._scrape_dolarhoy_page(url)
            if row:
                lines.append(
                    f"• {label}: $ {row['venta']} (venta) / $ {row['compra']} (compra)"
                )
        if lines:
            return "\n".join(lines) + "\n  _Fuente: DolarHoy_"

        # Fallback: dolarapi.com si DolarHoy falla totalmente
        try:
            req = urllib.request.Request(
                "https://dolarapi.com/v1/dolares",
                headers={"User-Agent": "Nova/1.0"},
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            return f"Dólar: error obteniendo cotización ({e})"

        if not isinstance(data, list) or not data:
            return "Dólar: sin datos disponibles."

        wanted = {"oficial": "Oficial", "blue": "Blue", "bolsa": "MEP", "contadoconliqui": "CCL"}
        for item in data:
            casa = (item.get("casa") or "").lower()
            if casa not in wanted:
                continue
            if item.get("venta") is None:
                continue
            lines.append(
                f"• {wanted[casa]}: $ {item['venta']} (venta) / $ {item['compra']} (compra)"
            )
        return "\n".join(lines) + "\n  _Fuente: dolarapi.com (fallback)_" if lines else "Dólar: sin datos."
    
    def get_personal_reminders(self) -> str:
        """Obtiene recordatorios personales de la memoria."""
        if not self.neuro_memory:
            return "Recordatorios: Memoria no disponible"
        try:
            # Buscar recordatorios para hoy o próximos días
            today = datetime.date.today().strftime("%Y-%m-%d")
            reminders = self.neuro_memory.search_context(f"recordatorio {today} tarea cita")
            if reminders:
                return f"Recordatorios:\n{reminders}"
            else:
                return "No hay recordatorios para hoy."
        except Exception as e:
            return f"Error obteniendo recordatorios: {e}"
    
    def generate_digest(self) -> Dict[str, str]:
        """Genera el resumen matutino completo."""
        digest = {
            "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "location": self.location,
            "header": f"🌅 Buenos días, Señor. Aquí tiene su resumen matutino para {get_date() if _NOVA_COMPONENTS_AVAILABLE else 'fecha desconocida'}.",
            "weather": self.get_weather(),
            "dolar": self.get_dolar_ar(),
            "calendar": self.get_calendar(),
            "emails": self.get_emails_summary(),
            "news": self.get_news(),
            "reminders": self.get_personal_reminders(),
            "footer": "Que tenga un excelente día, Señor."
        }
        return digest

    def format_digest(self, digest: Dict[str, str]) -> str:
        """Formatea el resumen para presentación."""
        sections = [
            digest["header"],
            "",
            "📍 UBICACIÓN:",
            f"  {digest['location']}",
            "",
            "🕐 HORA:",
            f"  {digest['timestamp'].split(' ')[1]}",
            "",
            "🌡️ CLIMA:",
            f"  {digest['weather']}",
            "",
            "💵 DÓLAR (ARG):",
            f"  {digest['dolar']}",
            "",
            "📅 CALENDARIO:",
            f"  {digest['calendar']}",
            "",
            "📧 CORREOS:",
            f"  {digest['emails']}",
            "",
            "📰 NOTICIAS:",
            f"  {digest['news']}",
            "",
            "⏰ RECORDATORIOS:",
            f"  {digest['reminders']}",
            "",
            digest["footer"]
        ]
        return "\n".join(sections)
    
    def execute(self) -> str:
        """Ejecuta el agente y devuelve el resumen formateado."""
        try:
            digest = self.generate_digest()
            return self.format_digest(digest)
        except Exception as e:
            return f"Error generando resumen matutino: {e}"

# Función de conveniencia para uso externo
def morning_digest() -> str:
    """Función de conveniencia para obtener el resumen matutino."""
    agent = MorningDigestAgent()
    return agent.execute()

if __name__ == "__main__":
    # Para pruebas directas
    print(morning_digest())