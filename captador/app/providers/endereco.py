"""Normalização de endereço via ViaCEP (gratuito, público)."""
import re

import httpx


def so_digitos(valor: str) -> str:
    return re.sub(r"\D", "", valor or "")


async def buscar_cep(cep: str) -> dict:
    cep = so_digitos(cep)
    if len(cep) != 8:
        raise ValueError("CEP deve ter 8 dígitos")
    try:
        async with httpx.AsyncClient(timeout=8) as client:
            r = await client.get(f"https://viacep.com.br/ws/{cep}/json/")
            dados = r.json()
    except (httpx.HTTPError, ValueError):
        # Sem internet / ViaCEP fora: segue só com o CEP.
        return {"cep": cep, "logradouro": "", "bairro": "", "cidade": "", "uf": ""}
    if dados.get("erro"):
        raise ValueError("CEP não encontrado")
    return {
        "cep": cep,
        "logradouro": dados.get("logradouro", ""),
        "bairro": dados.get("bairro", ""),
        "cidade": dados.get("localidade", ""),
        "uf": dados.get("uf", ""),
    }
