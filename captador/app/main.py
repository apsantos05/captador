"""Captador — API + front-end.

Rodar:  python -m uvicorn app.main:app --reload   (dentro da pasta captador)
"""
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field
from starlette.middleware.sessions import SessionMiddleware

from . import db, servicos
from .auth import conferir_senha, exigir_gestor, usuario_atual
from .config import COOKIE_SEGURO, DEMO, LIMITE_CONSULTAS_DIA, MAX_PDF_BYTES, RAIZ, SESSION_SECRET
from .providers.endereco import buscar_cep, so_digitos
from .providers.matricula import analisar_matricula, cpf_valido, extrair_texto
from .servicos import ErroFonte

STATIC = RAIZ / "static"


@asynccontextmanager
async def ciclo_de_vida(app: FastAPI):
    if db.iniciar() and DEMO:
        from .seed import semear
        await semear()
    yield


app = FastAPI(title="Captador", lifespan=ciclo_de_vida, docs_url="/api/docs" if DEMO else None, redoc_url=None)
app.add_middleware(
    SessionMiddleware, secret_key=SESSION_SECRET, session_cookie="captador", max_age=12 * 3600,
    same_site="lax", https_only=COOKIE_SEGURO,
)


@app.exception_handler(ErroFonte)
async def _erro_fonte(_, exc):
    return JSONResponse({"detail": str(exc)}, status_code=502)


@app.exception_handler(LookupError)
async def _nao_encontrado(_, exc):
    return JSONResponse({"detail": str(exc)}, status_code=404)


@app.exception_handler(ValueError)
async def _invalido(_, exc):
    return JSONResponse({"detail": str(exc)}, status_code=422)


# ---------- modelos ----------

class LoginIn(BaseModel):
    email: str
    senha: str


class LoginDemoIn(BaseModel):
    papel: str


class ConsultaIn(BaseModel):
    finalidade: str
    cep: str
    numero: str = Field(min_length=1, max_length=10)
    complemento: str = Field("", max_length=40)


class ConfirmarDonoIn(BaseModel):
    cartorio: str = Field(min_length=2, max_length=80)
    matricula: str = Field(min_length=1, max_length=20)


class ProprietarioIn(BaseModel):
    nome: str = Field(min_length=3, max_length=120)
    cpf: str
    matricula: str = Field("", max_length=20)
    cartorio: str = Field("", max_length=80)


class AbordagemIn(BaseModel):
    imovel_id: int
    pessoa_id: int | None = None
    canal: str
    resultado: str
    observacao: str = Field("", max_length=500)


class OptoutIn(BaseModel):
    valor: str
    motivo: str = Field("", max_length=200)


# ---------- páginas e sessão ----------

@app.get("/", include_in_schema=False)
def index():
    return FileResponse(STATIC / "index.html")


@app.get("/healthz", include_in_schema=False)
def healthz():
    return {"ok": True}


@app.get("/api/config")
def config():
    return {"demo": DEMO, "finalidades": servicos.FINALIDADES, "resultados": servicos.RESULTADOS_ABORDAGEM}


def _me(usuario: dict) -> dict:
    with db.conectar() as conn:
        hoje = servicos.consultas_hoje(conn, usuario["id"])
    return usuario | {"consultas_hoje": hoje, "limite_dia": LIMITE_CONSULTAS_DIA}


@app.post("/api/login")
def login(dados: LoginIn, request: Request):
    with db.conectar() as conn:
        u = conn.execute(
            "SELECT id, senha_hash FROM usuarios WHERE email = ? AND ativo = 1", (dados.email.strip().lower(),)
        ).fetchone()
    if not u or not conferir_senha(dados.senha, u["senha_hash"]):
        raise HTTPException(401, "E-mail ou senha incorretos")
    request.session["uid"] = u["id"]
    return {"ok": True}


@app.post("/api/login-demo")
def login_demo(dados: LoginDemoIn, request: Request):
    """Só no modo demonstração: entra com um clique como corretor ou gestor."""
    if not DEMO:
        raise HTTPException(404)
    with db.conectar() as conn:
        u = conn.execute(
            "SELECT id FROM usuarios WHERE papel = ? AND ativo = 1 ORDER BY id LIMIT 1", (dados.papel,)
        ).fetchone()
    if not u:
        raise HTTPException(404, "Usuário de demonstração não encontrado")
    request.session["uid"] = u["id"]
    return {"ok": True}


@app.post("/api/logout")
def logout(request: Request):
    request.session.clear()
    return {"ok": True}


@app.get("/api/me")
def me(usuario: dict = Depends(usuario_atual)):
    return _me(usuario)


# ---------- fluxo do corretor ----------

@app.post("/api/consulta")
async def consultar(dados: ConsultaIn, usuario: dict = Depends(usuario_atual)):
    if dados.finalidade not in servicos.FINALIDADES:
        raise HTTPException(422, "Finalidade inválida")
    with db.conectar() as conn:
        if servicos.consultas_hoje(conn, usuario["id"]) >= LIMITE_CONSULTAS_DIA:
            raise HTTPException(429, f"Limite diário de {LIMITE_CONSULTAS_DIA} consultas atingido")
    end = await buscar_cep(dados.cep)  # ValueError → 422
    end["numero"] = dados.numero.strip()
    end["complemento"] = servicos.normalizar_complemento(dados.complemento)
    with db.conectar() as conn:
        return await servicos.consultar(conn, usuario["id"], dados.finalidade, end)


@app.post("/api/imoveis/{imovel_id}/confirmar-dono")
async def confirmar_dono(imovel_id: int, dados: ConfirmarDonoIn, usuario: dict = Depends(usuario_atual)):
    with db.conectar() as conn:
        return await servicos.confirmar_dono(conn, usuario["id"], imovel_id, dados.cartorio.strip(), dados.matricula.strip())


@app.post("/api/abordagens")
def registrar_abordagem(dados: AbordagemIn, usuario: dict = Depends(usuario_atual)):
    with db.conectar() as conn:
        servicos.registrar_abordagem(
            conn, usuario["id"], dados.imovel_id, dados.pessoa_id, dados.canal, dados.resultado, dados.observacao
        )
    return {"ok": True}


@app.get("/api/recentes")
def recentes(usuario: dict = Depends(usuario_atual)):
    """Últimos imóveis consultados pelo corretor (para reabrir com um clique)."""
    with db.conectar() as conn:
        rows = conn.execute(
            """SELECT i.id, i.cep, i.numero, i.complemento, i.logradouro, i.bairro, MAX(c.criado_em) AS quando,
                      EXISTS (SELECT 1 FROM pessoas p WHERE p.imovel_id = i.id AND p.papel = 'proprietario') AS dono_confirmado,
                      EXISTS (SELECT 1 FROM pessoas p WHERE p.imovel_id = i.id) AS tem_pessoas
               FROM consultas c JOIN imoveis i ON i.id = c.imovel_id
               WHERE c.usuario_id = ? GROUP BY i.id ORDER BY quando DESC LIMIT 8""",
            (usuario["id"],),
        ).fetchall()
        return [dict(r) for r in rows]


# ---------- gestor ----------

@app.get("/api/pendencias")
def listar_pendencias(_: dict = Depends(exigir_gestor)):
    with db.conectar() as conn:
        rows = conn.execute(
            """SELECT p.id AS pendencia_id, u.nome AS solicitado_por, p.criado_em AS solicitado_em, i.*
               FROM pendencias p JOIN imoveis i ON i.id = p.imovel_id JOIN usuarios u ON u.id = p.solicitado_por
               WHERE p.status = 'aguardando_matricula' ORDER BY p.id"""
        ).fetchall()
        return [dict(r) for r in rows]


@app.post("/api/matricula/analisar")
async def analisar_pdf(arquivo: UploadFile = File(...), _: dict = Depends(exigir_gestor)):
    conteudo = await arquivo.read(MAX_PDF_BYTES + 1)
    if len(conteudo) > MAX_PDF_BYTES:
        raise HTTPException(413, "PDF maior que 10 MB")
    try:
        texto = extrair_texto(conteudo)
    except Exception:  # noqa: BLE001
        raise HTTPException(422, "Não consegui ler o PDF")
    if not texto.strip():
        raise HTTPException(422, "PDF sem texto (provavelmente imagem escaneada — digite os dados)")
    return analisar_matricula(texto)


@app.post("/api/imoveis/{imovel_id}/proprietario")
def definir_proprietario(imovel_id: int, dados: ProprietarioIn, _: dict = Depends(exigir_gestor)):
    if not cpf_valido(dados.cpf):
        raise HTTPException(422, "CPF inválido")
    with db.conectar() as conn:
        if not conn.execute("SELECT 1 FROM imoveis WHERE id = ?", (imovel_id,)).fetchone():
            raise HTTPException(404, "Imóvel não encontrado")
        conn.execute(
            "UPDATE imoveis SET matricula = ?, cartorio = ? WHERE id = ?",
            (dados.matricula.strip(), dados.cartorio.strip(), imovel_id),
        )
        servicos.salvar_dono(conn, imovel_id, dados.nome, so_digitos(dados.cpf), "matricula_manual")
    return {"ok": True}


@app.post("/api/optout")
def optout(dados: OptoutIn, _: dict = Depends(exigir_gestor)):
    valor = so_digitos(dados.valor)
    if len(valor) < 10:
        raise HTTPException(422, "Informe um CPF ou telefone com DDD")
    with db.conectar() as conn:
        conn.execute("INSERT OR IGNORE INTO optout (valor, motivo) VALUES (?,?)", (valor, dados.motivo))
    return {"ok": True}


@app.get("/api/relatorio")
def relatorio(_: dict = Depends(exigir_gestor)):
    with db.conectar() as conn:
        def q(sql):
            return conn.execute(sql).fetchone()[0]

        consultas = q("SELECT COUNT(*) FROM consultas WHERE resultado != 'confirmacao_dono'")
        da_base = q("SELECT COUNT(*) FROM consultas WHERE resultado = 'base_propria'")
        custo_medio_bureau = q("SELECT COALESCE(AVG(custo), 0) FROM consultas WHERE resultado = 'bureau'")
        return {
            "consultas": consultas,
            "respostas_base_propria": da_base,
            "economia_base_propria": round(da_base * custo_medio_bureau, 2),
            "imoveis_na_base": q("SELECT COUNT(DISTINCT imovel_id) FROM pessoas"),
            "donos_confirmados": q("SELECT COUNT(DISTINCT imovel_id) FROM pessoas WHERE papel = 'proprietario'"),
            "pendentes": q("SELECT COUNT(*) FROM pendencias WHERE status = 'aguardando_matricula'"),
            "custo_total": q("SELECT COALESCE(SUM(custo), 0) FROM consultas"),
            "optouts": q("SELECT COUNT(*) FROM optout"),
            "funil": {
                "consultas": consultas,
                "abordados": q("SELECT COUNT(DISTINCT imovel_id) FROM abordagens"),
                "agendados": q("SELECT COUNT(DISTINCT imovel_id) FROM abordagens WHERE resultado IN ('agendou', 'captou')"),
                "captados": q("SELECT COUNT(DISTINCT imovel_id) FROM abordagens WHERE resultado = 'captou'"),
            },
            "por_corretor": [
                dict(r) for r in conn.execute(
                    """SELECT u.nome,
                              (SELECT COUNT(*) FROM consultas c WHERE c.usuario_id = u.id AND c.resultado != 'confirmacao_dono') AS consultas,
                              (SELECT COUNT(*) FROM abordagens a WHERE a.usuario_id = u.id) AS abordagens,
                              (SELECT COUNT(*) FROM abordagens a WHERE a.usuario_id = u.id AND a.resultado = 'captou') AS captacoes,
                              (SELECT COALESCE(SUM(custo), 0) FROM consultas c WHERE c.usuario_id = u.id) AS custo
                       FROM usuarios u WHERE u.papel = 'corretor' ORDER BY captacoes DESC, consultas DESC"""
                )
            ],
            "ultimas_consultas": [
                dict(r) for r in conn.execute(
                    """SELECT c.criado_em, u.nome AS corretor, c.finalidade, c.resultado, c.custo,
                              i.logradouro, i.numero, i.complemento, i.bairro
                       FROM consultas c JOIN usuarios u ON u.id = c.usuario_id LEFT JOIN imoveis i ON i.id = c.imovel_id
                       ORDER BY c.id DESC LIMIT 12"""
                )
            ],
        }
