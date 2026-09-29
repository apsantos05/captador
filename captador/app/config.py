"""Configuração via variáveis de ambiente (ver .env.example)."""
import os
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent

# DEMO_MODE=1: dados fictícios, banco recriado com exemplos, login com um clique.
DEMO = os.environ.get("DEMO_MODE", "1") == "1"
DB_PATH = Path(os.environ.get("CAPTADOR_DB", RAIZ / "captador.db"))
SESSION_SECRET = os.environ.get("SESSION_SECRET", "")
LIMITE_CONSULTAS_DIA = int(os.environ.get("LIMITE_CONSULTAS_DIA", "60"))
MAX_PDF_BYTES = 10 * 1024 * 1024
# Cookie só por HTTPS. Padrão: ligado em produção; no Render (sempre HTTPS) ligue também na demonstração.
COOKIE_SEGURO = os.environ.get("COOKIE_SEGURO", "0" if DEMO else "1") == "1"

if not SESSION_SECRET:
    if not DEMO:
        raise RuntimeError("Defina SESSION_SECRET em produção")
    SESSION_SECRET = "somente-para-demonstracao"
