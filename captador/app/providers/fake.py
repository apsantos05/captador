"""Gerador de pessoas FICTÍCIAS e determinísticas para os modos simulados (demonstração)."""
import hashlib

NOMES = ["ANA", "BRUNO", "CARLA", "DIEGO", "ELISA", "FABIO", "GABRIELA", "HENRIQUE", "ISABELA", "JOAO",
         "LUCIANA", "MARCOS", "NATALIA", "OTAVIO", "PAULA", "RAFAEL", "SILVIA", "TIAGO", "VANESSA", "WAGNER"]
SOBRENOMES = ["ALMEIDA", "BARBOSA", "CARDOSO", "DIAS", "FERREIRA", "GOMES", "LIMA", "MARTINS",
              "NUNES", "OLIVEIRA", "PEREIRA", "RIBEIRO", "SANTOS", "SOUZA", "TEIXEIRA"]


def semente(*partes: str) -> int:
    return int(hashlib.sha256("|".join(partes).encode()).hexdigest(), 16)


def cpf_ficticio(s: int) -> str:
    base = [int(c) for c in f"{s % 10**9:09d}"]
    if len(set(base)) == 1:
        base[0] = (base[0] + 1) % 10
    for tam in (9, 10):
        soma = sum(d * (tam + 1 - i) for i, d in enumerate(base))
        base.append((soma * 10 % 11) % 10)
    return "".join(map(str, base))


def pessoa_ficticia(s: int) -> dict:
    s1 = (s // 7) % len(SOBRENOMES)
    s2 = (s1 + 1 + (s // 131) % (len(SOBRENOMES) - 1)) % len(SOBRENOMES)  # nunca repete o sobrenome
    nome = f"{NOMES[s % len(NOMES)]} {SOBRENOMES[s1]} {SOBRENOMES[s2]}"
    return {"nome": nome, "cpf": cpf_ficticio(s // 1000)}
