"""
conftest.py — configuración global de pytest.

Fix: QdrantClient.__del__ lanza "ImportError: sys.meta_path is None" durante el
shutdown de Python porque el GC corre en un hilo diferente al de creación del client.
Solución: monkey-patch __del__ para que sea no-op — el recurso se cierra igual en close().
"""
import sys
from pathlib import Path

# Asegurar que src/ está en el path para todos los tests
ROOT = Path(__file__).resolve().parents[1]
SRC  = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def pytest_configure(config):
    """Silencia el ruido de QdrantClient.__del__ durante el shutdown."""
    try:
        from qdrant_client import QdrantClient
        QdrantClient.__del__ = lambda self: None
    except ImportError:
        pass
