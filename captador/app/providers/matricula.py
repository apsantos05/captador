"""Matrícula: obtenção automática (RI Digital via Infosimples) + leitura do PDF.

A matrícula lista o histórico do imóvel em atos (R-1, R-2, AV-3...). O proprietário atual
normalmente aparece no ÚLTIMO registro de transmissão (compra e venda, doação, partilha...).
Aqui extraímos os candidatos (nome + CPF) e o operador confirma — parsing 100% automático
de matrícula é frágil porque cada cartório redige de um jeito.
"""
import base64
import io
import os
import re

import httpx
from pypdf import PdfReader

from .fake import pessoa_ficticia, semente

CPF_RE = re.compile(r"\b(\d{3}\.\d{3}\.\d{3}-\d{2})\b")
MATRICULA_RE = re.compile(r"MATR[IÍ]CULA\s*(?:N[º°o.]*)?\s*[:\-]?\s*([\d.]+)", re.I)
# Nome em maiúsculas logo antes do CPF: "JOÃO DA SILVA, brasileiro, ..., CPF nº 123.456.789-00"
NOME_ANTES_CPF_RE = re.compile(
    r"([A-ZÀ-Ý][A-ZÀ-Ý]+(?:\s+(?:D[AEO]S?|E|[A-ZÀ-Ý][A-ZÀ-Ý]+))+)[^A-ZÀ-Ý]{0,400}?CPF[^0-9]{0,20}(\d{3}\.\d{3}\.\d{3}-\d{2})"
)


def cpf_valido(cpf: str) -> bool:
    d = re.sub(r"\D", "", cpf)
    if len(d) != 11 or d == d[0] * 11:
        return False
    for i in (9, 10):
        soma = sum(int(d[j]) * ((i + 1) - j) for j in range(i))
        if (soma * 10 % 11) % 10 != int(d[i]):
            return False
    return True


def extrair_texto(pdf_bytes: bytes) -> str:
    leitor = PdfReader(io.BytesIO(pdf_bytes))
    return "\n".join(p.extract_text() or "" for p in leitor.pages)


def analisar_matricula(texto: str) -> dict:
    """Retorna número da matrícula e candidatos a proprietário (o último tende a ser o atual)."""
    m = MATRICULA_RE.search(texto)
    candidatos, vistos = [], set()
    for nome, cpf in NOME_ANTES_CPF_RE.findall(texto):
        if cpf in vistos or not cpf_valido(cpf):
            continue
        vistos.add(cpf)
        candidatos.append({"nome": " ".join(nome.split()), "cpf": cpf})
    # CPFs soltos que o regex de nome não pegou
    for cpf in CPF_RE.findall(texto):
        if cpf not in vistos and cpf_valido(cpf):
            vistos.add(cpf)
            candidatos.append({"nome": "", "cpf": cpf})
    return {
        "matricula": m.group(1).strip(".") if m else "",
        "candidatos": candidatos,
        "sugestao": candidatos[-1] if candidatos else None,
    }


def formatar_cpf(cpf: str) -> str:
    d = re.sub(r"\D", "", cpf)
    return f"{d[:3]}.{d[3:6]}.{d[6:9]}-{d[9:]}"


class MatriculaSimulada:
    """Gera uma matrícula FICTÍCIA. Em ~1/3 dos casos o dono é outra pessoa (imóvel alugado)."""

    nome = "simulado"
    custo = 45.00  # simulado: visualização de matrícula + tarifa da API

    async def obter_texto(self, uf, municipio, cartorio, matricula, morador_cpf=None, morador_nome=None) -> str:
        s = semente(cartorio, matricula)
        vendedor = pessoa_ficticia(s // 13)
        if morador_cpf and s % 3:
            dono = {"nome": morador_nome, "cpf": morador_cpf}
        else:
            dono = pessoa_ficticia(s // 7)
        return (
            f"{cartorio} - {municipio}/{uf}\nMATRÍCULA Nº {matricula}\n"
            f"R-1: Proprietário {vendedor['nome']}, brasileiro, CPF nº {formatar_cpf(vendedor['cpf'])}.\n"
            f"R-2: COMPRA E VENDA. Adquirente: {dono['nome']}, brasileiro(a), CPF nº {formatar_cpf(dono['cpf'])}.\n"
        )


class MatriculaInfosimples:
    """RI Digital (ONR) via APIs da Infosimples, usando a conta RI Digital da própria empresa.

    Consultas: "Registradores / Matrícula / Novo Pedido" e "... / Download de Matrícula já gerada".
    TODO: conferir na documentação da conta Infosimples os nomes exatos das rotas, parâmetros
    e o campo em que o PDF é devolvido, e ajustar INFOSIMPLES_ROTA_* / _extrair_pdf.
    """

    nome = "infosimples"

    def __init__(self):
        self.token = os.environ["INFOSIMPLES_TOKEN"]
        self.base = os.environ.get("INFOSIMPLES_URL", "https://api.infosimples.com/api/v2/consultas").rstrip("/")
        self.rota_pedido = os.environ.get("INFOSIMPLES_ROTA_PEDIDO", "registradores/matric-pedido")
        self.rota_download = os.environ.get("INFOSIMPLES_ROTA_DOWNLOAD", "registradores/matric-download")
        self.login = {"email": os.environ["RIDIGITAL_EMAIL"], "senha": os.environ["RIDIGITAL_SENHA"], "tipo_login": "email"}
        self.custo = float(os.environ.get("MATRICULA_CUSTO", "45.00"))

    async def _consulta(self, client, rota, params) -> dict:
        r = await client.post(f"{self.base}/{rota}", data={"token": self.token, "timeout": 300, **params})
        r.raise_for_status()
        resp = r.json()
        if resp.get("code") != 200:
            raise RuntimeError(f"Infosimples {rota}: {resp.get('code_message', resp.get('code'))}")
        return resp

    async def obter_texto(self, uf, municipio, cartorio, matricula, morador_cpf=None, morador_nome=None) -> str:
        params = {**self.login, "uf": uf, "municipio": municipio, "cartorio": cartorio,
                  "matricula": matricula, "finalidade": "Consulta"}
        async with httpx.AsyncClient(timeout=320) as client:
            pedido = await self._consulta(client, self.rota_pedido, params)
            numero = pedido["data"][0]["numero_pedido"]
            download = await self._consulta(client, self.rota_download, {**self.login, "numero_pedido": numero})
            return extrair_texto(await self._extrair_pdf(client, download))

    async def _extrair_pdf(self, client, resp: dict) -> bytes:
        dado = resp["data"][0]
        if dado.get("pdf_base64"):
            return base64.b64decode(dado["pdf_base64"])
        url = dado.get("url_pdf") or (resp.get("site_receipts") or [None])[0]
        if not url:
            raise RuntimeError("Resposta da Infosimples sem PDF — ajustar _extrair_pdf")
        r = await client.get(url)
        r.raise_for_status()
        return r.content


def obter_fonte_matricula():
    return MatriculaInfosimples() if os.environ.get("MATRICULA_MODO") == "infosimples" else MatriculaSimulada()
