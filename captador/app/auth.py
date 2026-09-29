"""Login com sessão (cookie assinado) e papéis: corretor e gestor."""
import hashlib
import hmac
import os

from fastapi import Depends, HTTPException, Request

from . import db

ITERACOES = 200_000


def hash_senha(senha: str) -> str:
    sal = os.urandom(16)
    h = hashlib.pbkdf2_hmac("sha256", senha.encode(), sal, ITERACOES)
    return f"{sal.hex()}${h.hex()}"


def conferir_senha(senha: str, armazenado: str) -> bool:
    sal, h = armazenado.split("$")
    calc = hashlib.pbkdf2_hmac("sha256", senha.encode(), bytes.fromhex(sal), ITERACOES)
    return hmac.compare_digest(calc.hex(), h)


def criar_usuario(conn, email: str, nome: str, papel: str, senha: str) -> int:
    cur = conn.execute(
        "INSERT INTO usuarios (email, nome, papel, senha_hash) VALUES (?,?,?,?)",
        (email.strip().lower(), nome.strip(), papel, hash_senha(senha)),
    )
    return cur.lastrowid


def usuario_atual(request: Request) -> dict:
    uid = request.session.get("uid")
    if uid:
        with db.conectar() as conn:
            u = conn.execute("SELECT id, email, nome, papel FROM usuarios WHERE id = ? AND ativo = 1", (uid,)).fetchone()
        if u:
            return dict(u)
    raise HTTPException(401, "Faça login")


def exigir_gestor(usuario: dict = Depends(usuario_atual)) -> dict:
    if usuario["papel"] != "gestor":
        raise HTTPException(403, "Apenas gestores")
    return usuario
