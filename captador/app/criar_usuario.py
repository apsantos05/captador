"""Cria um usuário em produção.

Uso:  python -m app.criar_usuario email@beam.com.br "Nome Sobrenome" corretor|gestor
A senha é pedida no terminal (não fica no histórico).
"""
import getpass
import sys

from . import db
from .auth import criar_usuario

if __name__ == "__main__":
    if len(sys.argv) != 4 or sys.argv[3] not in ("corretor", "gestor"):
        sys.exit(__doc__)
    senha = getpass.getpass("Senha: ")
    if len(senha) < 10 or senha != getpass.getpass("Repita a senha: "):
        sys.exit("Senha precisa ter 10+ caracteres e as duas precisam ser iguais")
    db.iniciar()
    with db.conectar() as conn:
        criar_usuario(conn, sys.argv[1], sys.argv[2], sys.argv[3], senha)
    print("Usuário criado.")
