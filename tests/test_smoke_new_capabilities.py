import pytest
from unittest.mock import patch, MagicMock

try:
    from nova.tools import nova_skills
except ImportError:
    pass

@pytest.fixture
def mock_router():
    router = MagicMock()
    router.route.return_value = {"response": "Mocked response", "tier": 1, "model": "test", "tokens_used": 10, "budget_remaining_pct": 100}
    return router

def test_smoke_lsp():
    """Verifica que la skill de LSP existe y no crashea al ser llamada."""
    if not hasattr(nova_skills, "skill_lsp_workspace"):
        pytest.skip("LSP no implementado aún en nova_skills")
    assert callable(nova_skills.skill_lsp_workspace)
    with patch("subprocess.run") as mock_run:
        mock_run.return_value.stdout = b"mocked lsp response"
        mock_run.return_value.returncode = 0
        resp = nova_skills.skill_lsp_workspace("status")
        assert isinstance(resp, str)

def test_smoke_ocr():
    """Verifica que la skill OCR existe."""
    if not hasattr(nova_skills, "skill_extraer_texto_pantalla"):
        pytest.skip("OCR no implementado en nova_skills")
    assert callable(nova_skills.skill_extraer_texto_pantalla)

def test_polyglot_mode():
    """Testea que novaesp respeta el cambio de idioma."""
    try:
        from nova.lang import novaesp
    except ImportError:
        pytest.skip("novaesp no disponible")
    
    original_lang = novaesp._SESSION_LANG
    try:
        novaesp._SESSION_LANG = "en"
        msgs, lang = novaesp._build_messages([{"role": "user", "content": "hello"}], "System prompt")
        assert lang == "en"
        assert "Responde SIEMPRE en" in msgs[0]["content"]
    finally:
        novaesp._SESSION_LANG = original_lang
