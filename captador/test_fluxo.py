"""Teste de ponta a ponta (modo demonstração). Rodar: python test_fluxo.py"""
import os
import pathlib
import tempfile
import warnings

warnings.filterwarnings("ignore")
os.environ.update(DEMO_MODE="1", CAPTADOR_DB=str(pathlib.Path(tempfile.mkdtemp()) / "teste.db"), LIMITE_CONSULTAS_DIA="40")
os.environ.pop("BUREAU_MODO", None)
os.environ.pop("MATRICULA_MODO", None)

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app.providers.matricula import analisar_matricula  # noqa: E402


def ok(cond, msg):
    assert cond, msg
    print("  ✓", msg)


with TestClient(app) as anon, TestClient(app) as corretor, TestClient(app) as gestor:
    print("Segurança")
    ok(anon.post("/api/consulta", json={}).status_code in (401, 422), "sem login não consulta")
    ok(anon.get("/api/me").status_code == 401, "sem login /api/me = 401")
    ok(anon.post("/api/login", json={"email": "ana@demo.captador", "senha": "errada"}).status_code == 401, "senha errada = 401")
    corretor.post("/api/login-demo", json={"papel": "corretor"})
    gestor.post("/api/login-demo", json={"papel": "gestor"})
    ok(corretor.get("/api/me").json()["papel"] == "corretor", "login demo corretor")
    ok(corretor.get("/api/relatorio").status_code == 403, "corretor não vê relatório")
    ok(corretor.get("/api/pendencias").status_code == 403, "corretor não vê fila")

    print("Dados de demonstração")
    rel = gestor.get("/api/relatorio").json()
    ok(rel["consultas"] > 5 and rel["donos_confirmados"] >= 3 and rel["funil"]["captados"] >= 1, f"semente: {rel['funil']}")
    ok(rel["pendentes"] >= 1, "semente tem pendência na fila")

    def consulta(numero, cep="04538-133", compl=""):
        r = corretor.post("/api/consulta", json={"finalidade": "captacao_venda", "cep": cep, "numero": numero, "complemento": compl})
        assert r.status_code == 200, r.text
        return r.json()

    print("Fluxo")
    ok(corretor.post("/api/consulta", json={"finalidade": "x", "cep": "1", "numero": "1"}).status_code == 422, "finalidade inválida = 422")
    com = sem = None
    for n in range(1, 40):
        r = consulta(str(n))
        com = com or (r if r["status"] == "encontrado" and r["origem"] == "bureau" else None)
        sem = sem or (r if r["status"] == "pendente_matricula" else None)
        if com and sem:
            break
    p = com["imovel"]["pessoas"][0]
    ok(p["situacao"] == "provavel_dono" and "*" in p["cpf"] and p["contatos"], "bureau: morador + telefones, CPF mascarado")
    ok([x["etapa"] for x in com["passos"]][-1] == "Salvo na base própria" and com["custo"] > 0, f"passos registrados, custo R$ {com['custo']:.2f}")
    r2 = consulta(com["imovel"]["numero"])
    ok(r2["origem"] == "base_propria" and r2["custo"] == 0, "2ª consulta: base própria, custo zero")

    casos = set()
    for n in range(1, 40):
        r = consulta(str(n))
        if r["status"] != "encontrado" or r["imovel"]["dono_confirmado"]:
            continue
        c = corretor.post(f"/api/imoveis/{r['imovel']['id']}/confirmar-dono", json={"cartorio": "4º RI", "matricula": str(900 + n)}).json()
        assert c["imovel"]["pessoas"][0]["papel"] == "proprietario"
        casos.add(c["dono_e_morador"])
        if len(casos) == 2:
            break
    ok(casos == {True, False}, "matrícula: casos dono = morador e dono ≠ morador (inquilino)")
    ok(corretor.post("/api/imoveis/999999/confirmar-dono", json={"cartorio": "x x", "matricula": "1"}).status_code == 404, "imóvel inexistente = 404")

    print("Fila manual (gestor)")
    imv = sem["imovel"]["id"]
    ok(gestor.post(f"/api/imoveis/{imv}/proprietario", json={"nome": "X Y Z", "cpf": "111.111.111-11"}).status_code == 422, "CPF inválido = 422")
    gestor.post(f"/api/imoveis/{imv}/proprietario", json={"nome": "Maria da Silva", "cpf": "529.982.247-25", "matricula": "123", "cartorio": "4º RI"})
    r3 = consulta(sem["imovel"]["numero"])
    ok(r3["origem"] == "base_propria" and r3["imovel"]["pessoas"][0]["situacao"] == "dono", "após fila: dono confirmado na base")

    print("Abordagem e opt-out")
    pid = r3["imovel"]["pessoas"][0]["id"]
    ok(corretor.post("/api/abordagens", json={"imovel_id": imv, "pessoa_id": 999999, "canal": "whatsapp", "resultado": "agendou"}).status_code == 404, "pessoa de outro imóvel = 404")
    ok(corretor.post("/api/abordagens", json={"imovel_id": imv, "pessoa_id": pid, "canal": "fax", "resultado": "agendou"}).status_code == 422, "canal inválido = 422")
    corretor.post("/api/abordagens", json={"imovel_id": imv, "pessoa_id": pid, "canal": "whatsapp", "resultado": "pediu_para_nao_contatar"})
    r4 = consulta(sem["imovel"]["numero"])
    ok(r4["imovel"]["pessoas"][0]["bloqueado"] and not r4["imovel"]["pessoas"][0]["contatos"], "opt-out esconde os telefones")
    ok(len(r4["imovel"]["abordagens"]) == 1, "histórico de abordagens no card")
    ok(len(corretor.get("/api/recentes").json()) > 0, "recentes do corretor")

    print("Limite diário")
    while (st := corretor.post("/api/consulta", json={"finalidade": "avaliacao", "cep": "04538-133", "numero": "1"}).status_code) == 200:
        pass
    ok(st == 429, "limite diário = 429")

    txt = "MATRÍCULA Nº 123.456\nR-1: JOSE PEREIRA DOS SANTOS, brasileiro, CPF nº 111.444.777-35\nR-2: MARIA DA SILVA, brasileira, CPF/MF 529.982.247-25"
    ok(analisar_matricula(txt)["sugestao"]["nome"] == "MARIA DA SILVA", "leitura de matrícula pega o último dono")
    ok(corretor.post("/api/logout").status_code == 200 and corretor.get("/api/me").status_code == 401, "logout")

print("\nOK — todos os testes passaram")
