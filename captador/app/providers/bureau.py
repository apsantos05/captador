"""Bureau de dados licenciado: (1) endereço → pessoas vinculadas, (2) CPF → telefones.

Produção: BUREAU_MODO=http + BUREAU_URL / BUREAU_TOKEN do bureau contratado
(BigDataCorp, Assertiva, Procob, Directd, Serasa, Boa Vista...). Cada bureau tem seu formato:
ajuste os métodos `_converter_*` de `BureauHttp` conforme a documentação do contrato.
Nunca plugue aqui bases compradas avulsas / vazadas.
"""
import os
import re

import httpx

from .fake import pessoa_ficticia, semente


class BureauSimulado:
    """Dados FICTÍCIOS e determinísticos, só para demonstração."""

    nome = "simulado"
    custo_endereco = 1.20  # custos simulados, na faixa de mercado
    custo_contatos = 0.80

    async def buscar_por_endereco(self, end: dict) -> list[dict]:
        s = semente(end["cep"], end["numero"], end.get("complemento", ""))
        if s % 6 == 0:  # ~1 em 6 endereços sem resultado → cai na fila de matrícula
            return []
        pessoas = [pessoa_ficticia(s)]
        if s % 3 == 0:
            pessoas.append(pessoa_ficticia(s // 97))
        return pessoas

    async def buscar_contatos(self, cpf: str) -> list[dict]:
        s = semente(cpf)
        return [
            {"tipo": "celular", "valor": f"(11) 9{s % 10000:04d}-{(s // 10000) % 10000:04d}", "whatsapp": True},
            {"tipo": "fixo", "valor": f"(11) 3{(s // 10**8) % 1000:03d}-{(s // 10**11) % 10000:04d}", "whatsapp": False},
        ]


class BureauHttp:
    nome = "bureau"

    def __init__(self):
        self.url = os.environ["BUREAU_URL"].rstrip("/")
        self.token = os.environ["BUREAU_TOKEN"]
        self.custo_endereco = float(os.environ.get("BUREAU_CUSTO_ENDERECO", "1.00"))
        self.custo_contatos = float(os.environ.get("BUREAU_CUSTO_CONTATOS", "1.00"))

    async def _post(self, rota: str, payload: dict) -> dict:
        async with httpx.AsyncClient(timeout=20) as client:
            r = await client.post(f"{self.url}/{rota}", headers={"Authorization": f"Bearer {self.token}"}, json=payload)
            r.raise_for_status()
            return r.json()

    async def buscar_por_endereco(self, end: dict) -> list[dict]:
        # TODO: ajustar rota e campos ao bureau contratado.
        resp = await self._post("pessoas/endereco", {
            "cep": end["cep"], "numero": end["numero"], "complemento": end.get("complemento", ""),
        })
        return [{"nome": p["nome"], "cpf": re.sub(r"\D", "", p["cpf"])} for p in resp.get("pessoas", [])]

    async def buscar_contatos(self, cpf: str) -> list[dict]:
        # TODO: ajustar rota e campos ao bureau contratado.
        resp = await self._post("pessoas/telefones", {"cpf": cpf})
        return [
            {"tipo": t.get("tipo", "celular"), "valor": t["numero"], "whatsapp": bool(t.get("whatsapp"))}
            for t in resp.get("telefones", [])
        ]


def obter_bureau():
    return BureauHttp() if os.environ.get("BUREAU_MODO") == "http" else BureauSimulado()
