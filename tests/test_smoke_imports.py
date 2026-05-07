import importlib
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def test_core_modules_import():
    modules = [
        "nova.tools.nova_skills",
        "nova.connectors.nova_n8n",
        "nova.core.nova_router",
        "nova.perception.mcp_server",
    ]

    for module in modules:
        importlib.import_module(module)
