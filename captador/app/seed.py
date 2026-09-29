"""Dados de demonstração (DEMO_MODE=1): usuários, imóveis consultados, donos confirmados e abordagens.
Tudo FICTÍCIO — gerado pelos provedores simulados."""
import secrets

from . import db, servicos
from .auth import criar_usuario
from .providers.bureau import BureauSimulado

USUARIOS = [
    ("ana@demo.captador", "Ana Souza", "corretor"),
    ("bruno@demo.captador", "Bruno Lima", "corretor"),
    ("diego@demo.captador", "Diego Rocha", "corretor"),
    ("carla@demo.captador", "Carla Mendes", "gestor"),
]

ENDERECOS = [  # (cep, logradouro, bairro, número inicial)
    ("01310100", "Avenida Paulista", "Bela Vista", 1000),
    ("01426001", "Rua Oscar Freire", "Jardim Paulista", 700),
    ("04538133", "Avenida Brigadeiro Faria Lima", "Itaim Bibi", 3000),
    ("05435000", "Rua Harmonia", "Vila Madalena", 120),
    ("01424000", "Alameda Lorena", "Jardim Paulista", 1500),
    ("05402000", "Avenida Rebouças", "Pinheiros", 2200),
    ("04534002", "Rua Joaquim Floriano", "Itaim Bibi", 400),
]


def _end(cep, logradouro, bairro, numero, complemento=""):
    return {"cep": cep, "numero": str(numero), "complemento": complemento, "logradouro": logradouro,
            "bairro": bairro, "cidade": "São Paulo", "uf": "SP"}


async def semear():
    bureau = BureauSimulado()
    with db.conectar() as conn:
        ids = [criar_usuario(conn, e, n, p, secrets.token_urlsafe(16)) for e, n, p in USUARIOS]
        corretores = ids[:3]
        consultados = []
        for i, (cep, log, bairro, n0) in enumerate(ENDERECOS):
            achou = sem = False
            for n in range(n0, n0 + 40):  # acha um nº com moradores e (no 1º endereço) um sem ninguém
                end = _end(cep, log, bairro, n, "APTO 42" if i % 2 else "")
                tem = bool(await bureau.buscar_por_endereco(end))
                if tem and not achou:
                    r = await servicos.consultar(conn, corretores[i % 3], "captacao_venda", end)
                    consultados.append((r["imovel"], corretores[i % 3]))
                    achou = True
                elif not tem and not sem and i == 0:
                    await servicos.consultar(conn, corretores[1], "captacao_venda", end)
                    sem = True
                if achou and (sem or i != 0):
                    break

        # Algumas consultas repetidas → respondidas pela base própria
        for imovel, uid in consultados[:3]:
            await servicos.consultar(conn, uid, "avaliacao", _end(
                imovel["cep"], imovel["logradouro"], imovel["bairro"], imovel["numero"], imovel["complemento"]))

        # Leads quentes: dono confirmado pela matrícula
        for k, (imovel, uid) in enumerate(consultados[:4]):
            await servicos.confirmar_dono(conn, uid, imovel["id"], "4º Registro de Imóveis de São Paulo", str(81230 + k * 17))

        # Abordagens → funil
        roteiro = ["captou", "agendou", "sem_resposta", "nao_tem_interesse", "agendou", "sem_resposta"]
        for (imovel, uid), resultado in zip(consultados, roteiro):
            pessoa = conn.execute(
                "SELECT id FROM pessoas WHERE imovel_id = ? ORDER BY papel = 'proprietario' DESC, id LIMIT 1",
                (imovel["id"],),
            ).fetchone()
            servicos.registrar_abordagem(conn, uid, imovel["id"], pessoa["id"], "whatsapp", resultado,
                                         "Proprietário quer avaliação" if resultado == "agendou" else "")
