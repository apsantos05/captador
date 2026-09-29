"""Regras do fluxo (fluxo.html), independentes de HTTP — usadas pelas rotas e pela semente de demonstração.

  1-2  CEP + nº → endereço padronizado
  3    já está na base própria? → responde na hora, sem custo
  4    bureau: quem mora no endereço (nome + CPF)
  5    bureau: telefones do CPF (1x por CPF, depois cache)
  6    remove opt-out + grava log
  7    lead quente → matrícula automática confirma o dono
  8    salva na base própria → card do corretor
"""
from .providers.bureau import obter_bureau
from .providers.endereco import so_digitos
from .providers.matricula import analisar_matricula, obter_fonte_matricula

FINALIDADES = {"captacao_venda": "Captação — venda", "captacao_locacao": "Captação — locação", "avaliacao": "Avaliação"}
RESULTADOS_ABORDAGEM = {
    "sem_resposta": "Sem resposta", "nao_tem_interesse": "Não tem interesse", "agendou": "Agendou visita",
    "captou": "Captou o imóvel", "pediu_para_nao_contatar": "Pediu para não ser contatado",
}
CANAIS = {"whatsapp", "ligacao", "visita"}


class ErroFonte(Exception):
    """Falha em fonte externa (bureau, matrícula)."""


def mascarar_cpf(cpf: str) -> str:
    return f"***.{cpf[3:6]}.{cpf[6:9]}-**"


def normalizar_complemento(c: str) -> str:
    return " ".join((c or "").upper().split())


def _bloqueados(conn) -> set[str]:
    return {r["valor"] for r in conn.execute("SELECT valor FROM optout")}


async def _contatos(conn, cpf: str, bloqueados: set[str]) -> tuple[list[dict], float, bool]:
    """Passos 5-6: telefones do CPF (cache antes de pagar o bureau), sem os bloqueados.
    Retorna (contatos, custo, veio_do_bureau)."""
    if cpf in bloqueados:
        return [], 0.0, False
    sql = "SELECT * FROM contatos WHERE cpf = ? ORDER BY whatsapp DESC, id"
    linhas = conn.execute(sql, (cpf,)).fetchall()
    custo, do_bureau = 0.0, False
    if not linhas:
        bureau = obter_bureau()
        try:
            achados = await bureau.buscar_contatos(cpf)
        except Exception as e:  # noqa: BLE001
            raise ErroFonte(f"Bureau indisponível ao buscar telefones: {e}") from e
        for c in achados:
            conn.execute(
                "INSERT OR IGNORE INTO contatos (cpf, tipo, valor, whatsapp, fonte) VALUES (?,?,?,?,?)",
                (cpf, c["tipo"], c["valor"], int(c["whatsapp"]), bureau.nome),
            )
        custo, do_bureau = bureau.custo_contatos, True
        linhas = conn.execute(sql, (cpf,)).fetchall()
    contatos = [
        {"tipo": r["tipo"], "valor": r["valor"], "whatsapp": bool(r["whatsapp"])}
        for r in linhas if so_digitos(r["valor"]) not in bloqueados
    ]
    return contatos, custo, do_bureau


async def ficha(conn, imovel_id: int) -> tuple[dict, float, int]:
    """Card do corretor: dono confirmado primeiro, depois moradores. Retorna (ficha, custo, cpfs_no_bureau)."""
    imovel = dict(conn.execute("SELECT * FROM imoveis WHERE id = ?", (imovel_id,)).fetchone())
    pessoas = conn.execute(
        "SELECT * FROM pessoas WHERE imovel_id = ? ORDER BY papel = 'proprietario' DESC, id", (imovel_id,)
    ).fetchall()
    cpf_dono = next((p["cpf"] for p in pessoas if p["papel"] == "proprietario"), None)
    moradores = {p["cpf"] for p in pessoas if p["papel"] == "morador"}
    bloqueados = _bloqueados(conn)
    custo, consultados, lista = 0.0, 0, []
    for p in pessoas:
        if p["papel"] == "morador" and p["cpf"] == cpf_dono:
            continue  # o morador que é o dono aparece uma vez só, como dono
        contatos, c, do_bureau = await _contatos(conn, p["cpf"], bloqueados)
        custo += c
        consultados += do_bureau
        if p["papel"] == "proprietario":
            situacao = "dono_mora" if p["cpf"] in moradores else "dono"
        else:
            situacao = "inquilino" if cpf_dono else "provavel_dono"
        lista.append({
            "id": p["id"], "nome": p["nome"], "cpf": mascarar_cpf(p["cpf"]), "papel": p["papel"],
            "situacao": situacao, "bloqueado": p["cpf"] in bloqueados, "contatos": contatos,
        })
    abordagens = conn.execute(
        """SELECT a.canal, a.resultado, a.observacao, a.criado_em, u.nome AS corretor, p.nome AS pessoa
           FROM abordagens a JOIN usuarios u ON u.id = a.usuario_id LEFT JOIN pessoas p ON p.id = a.pessoa_id
           WHERE a.imovel_id = ? ORDER BY a.id DESC LIMIT 10""",
        (imovel_id,),
    ).fetchall()
    imovel.update(
        dono_confirmado=cpf_dono is not None,
        pessoas=lista,
        abordagens=[dict(a) | {"resultado_txt": RESULTADOS_ABORDAGEM.get(a["resultado"], a["resultado"])} for a in abordagens],
    )
    return imovel, custo, consultados


def _log(conn, usuario_id, finalidade, imovel_id, resultado, custo=0.0):
    conn.execute(
        "INSERT INTO consultas (usuario_id, finalidade, imovel_id, resultado, custo) VALUES (?,?,?,?,?)",
        (usuario_id, finalidade, imovel_id, resultado, round(custo, 2)),
    )


def consultas_hoje(conn, usuario_id: int) -> int:
    return conn.execute(
        """SELECT COUNT(*) FROM consultas WHERE usuario_id = ? AND resultado != 'confirmacao_dono'
           AND date(criado_em) = date('now')""",
        (usuario_id,),
    ).fetchone()[0]


async def consultar(conn, usuario_id: int, finalidade: str, end: dict) -> dict:
    """Passos 3 a 8. `end` já vem padronizado (cep, numero, complemento, logradouro, bairro, cidade, uf)."""
    passos = [{"etapa": "Endereço padronizado", "fonte": "ViaCEP", "detalhe": end.get("logradouro") or end["cep"], "custo": 0}]
    conn.execute(
        """INSERT INTO imoveis (cep, numero, complemento, logradouro, bairro, cidade, uf)
           VALUES (:cep, :numero, :complemento, :logradouro, :bairro, :cidade, :uf)
           ON CONFLICT (cep, numero, complemento) DO NOTHING""",
        end,
    )
    imovel_id = conn.execute(
        "SELECT id FROM imoveis WHERE cep = ? AND numero = ? AND complemento = ?",
        (end["cep"], end["numero"], end["complemento"]),
    ).fetchone()["id"]

    # Passo 3: base própria
    if conn.execute("SELECT 1 FROM pessoas WHERE imovel_id = ?", (imovel_id,)).fetchone():
        passos.append({"etapa": "Encontrado na base própria", "fonte": "Captador", "detalhe": "resposta imediata", "custo": 0})
        f, custo, _ = await ficha(conn, imovel_id)
        _log(conn, usuario_id, finalidade, imovel_id, "base_propria", custo)
        return {"status": "encontrado", "origem": "base_propria", "custo": custo, "passos": passos, "imovel": f}
    passos.append({"etapa": "Não está na base própria", "fonte": "Captador", "detalhe": "segue para o bureau", "custo": 0})

    # Passo 4: bureau → quem mora no endereço
    bureau = obter_bureau()
    try:
        pessoas = await bureau.buscar_por_endereco(end)
    except Exception as e:  # noqa: BLE001
        raise ErroFonte(f"Bureau indisponível ao buscar o endereço: {e}") from e
    custo = bureau.custo_endereco
    n = len(pessoas)
    passos.append({"etapa": "Pessoas no endereço", "fonte": "Bureau", "custo": bureau.custo_endereco,
                   "detalhe": f"{n} pessoa{'s' if n != 1 else ''} vinculada{'s' if n != 1 else ''}" if n else "ninguém vinculado"})
    if not pessoas:
        conn.execute("INSERT OR IGNORE INTO pendencias (imovel_id, solicitado_por) VALUES (?,?)", (imovel_id, usuario_id))
        passos.append({"etapa": "Enviado à fila de matrículas", "fonte": "Captador", "detalhe": "resolução manual", "custo": 0})
        _log(conn, usuario_id, finalidade, imovel_id, "pendente_matricula", custo)
        f, _, _ = await ficha(conn, imovel_id)
        return {"status": "pendente_matricula", "origem": "bureau", "custo": custo, "passos": passos, "imovel": f}

    for p in pessoas:
        conn.execute(
            "INSERT OR IGNORE INTO pessoas (imovel_id, nome, cpf, papel, fonte) VALUES (?,?,?, 'morador', ?)",
            (imovel_id, " ".join(p["nome"].upper().split()), so_digitos(p["cpf"]), bureau.nome),
        )
    # Passos 5, 6 e 8
    f, custo_contatos, consultados = await ficha(conn, imovel_id)
    custo += custo_contatos
    passos.append({"etapa": "Telefones e WhatsApp", "fonte": "Bureau", "custo": custo_contatos,
                   "detalhe": f"{consultados} CPF{'s' if consultados != 1 else ''} consultado{'s' if consultados != 1 else ''}"})
    passos.append({"etapa": "Filtro LGPD", "fonte": "Captador", "detalhe": "opt-out aplicado · consulta registrada", "custo": 0})
    passos.append({"etapa": "Salvo na base própria", "fonte": "Captador", "detalhe": "próxima consulta sai grátis", "custo": 0})
    _log(conn, usuario_id, finalidade, imovel_id, "bureau", custo)
    return {"status": "encontrado", "origem": "bureau", "custo": custo, "passos": passos, "imovel": f}


def salvar_dono(conn, imovel_id: int, nome: str, cpf: str, fonte: str):
    conn.execute(
        "INSERT OR IGNORE INTO pessoas (imovel_id, nome, cpf, papel, fonte) VALUES (?,?,?, 'proprietario', ?)",
        (imovel_id, " ".join(nome.upper().split()), cpf, fonte),
    )
    conn.execute("UPDATE pendencias SET status = 'resolvida' WHERE imovel_id = ?", (imovel_id,))


async def confirmar_dono(conn, usuario_id: int, imovel_id: int, cartorio: str, matricula: str) -> dict:
    """Passo 7: puxa a matrícula automaticamente e confirma quem é o dono."""
    imovel = conn.execute("SELECT * FROM imoveis WHERE id = ?", (imovel_id,)).fetchone()
    if not imovel:
        raise LookupError("Imóvel não encontrado")
    morador = conn.execute(
        "SELECT nome, cpf FROM pessoas WHERE imovel_id = ? AND papel = 'morador' ORDER BY id LIMIT 1", (imovel_id,)
    ).fetchone()
    fonte = obter_fonte_matricula()
    try:
        texto = await fonte.obter_texto(
            imovel["uf"], imovel["cidade"], cartorio, matricula,
            morador_cpf=morador["cpf"] if morador else None, morador_nome=morador["nome"] if morador else None,
        )
    except Exception as e:  # noqa: BLE001
        raise ErroFonte(f"Falha ao obter a matrícula: {e}") from e

    analise = analisar_matricula(texto)
    dono = analise["sugestao"]
    if not dono:
        raise ValueError("Não achei o proprietário na matrícula. Use a fila para preencher à mão.")
    cpf_dono = so_digitos(dono["cpf"])
    conn.execute(
        "UPDATE imoveis SET cartorio = ?, matricula = ? WHERE id = ?",
        (cartorio, analise["matricula"] or matricula, imovel_id),
    )
    salvar_dono(conn, imovel_id, dono["nome"] or "PROPRIETÁRIO (NOME NÃO LIDO)", cpf_dono, "matricula")
    f, custo_contatos, _ = await ficha(conn, imovel_id)
    custo = fonte.custo + custo_contatos
    _log(conn, usuario_id, "confirmacao_dono", imovel_id, "confirmacao_dono", custo)
    return {"dono_e_morador": bool(morador) and morador["cpf"] == cpf_dono, "custo": custo, "imovel": f}


def registrar_abordagem(conn, usuario_id, imovel_id, pessoa_id, canal, resultado, observacao):
    if resultado not in RESULTADOS_ABORDAGEM or canal not in CANAIS:
        raise ValueError("Canal ou resultado inválido")
    pessoa = None
    if pessoa_id is not None:
        pessoa = conn.execute("SELECT cpf FROM pessoas WHERE id = ? AND imovel_id = ?", (pessoa_id, imovel_id)).fetchone()
        if not pessoa:
            raise LookupError("Pessoa não pertence a este imóvel")
    elif not conn.execute("SELECT 1 FROM imoveis WHERE id = ?", (imovel_id,)).fetchone():
        raise LookupError("Imóvel não encontrado")
    conn.execute(
        "INSERT INTO abordagens (usuario_id, imovel_id, pessoa_id, canal, resultado, observacao) VALUES (?,?,?,?,?,?)",
        (usuario_id, imovel_id, pessoa_id, canal, resultado, (observacao or "").strip()[:500]),
    )
    if resultado == "pediu_para_nao_contatar" and pessoa:
        conn.execute("INSERT OR IGNORE INTO optout (valor, motivo) VALUES (?, 'pedido na abordagem')", (pessoa["cpf"],))
