"""Banco SQLite: base própria endereço ↔ matrícula ↔ pessoas (morador/dono) ↔ contatos + trilha de auditoria (LGPD)."""
import sqlite3
from contextlib import contextmanager

from .config import DB_PATH, DEMO

SCHEMA_VERSION = 3

SCHEMA = """
CREATE TABLE IF NOT EXISTS usuarios (
    id INTEGER PRIMARY KEY,
    email TEXT NOT NULL UNIQUE,
    nome TEXT NOT NULL,
    papel TEXT NOT NULL CHECK (papel IN ('corretor', 'gestor')),
    senha_hash TEXT NOT NULL,
    ativo INTEGER NOT NULL DEFAULT 1,
    criado_em TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS imoveis (
    id INTEGER PRIMARY KEY,
    cep TEXT NOT NULL,
    numero TEXT NOT NULL,
    complemento TEXT NOT NULL DEFAULT '',
    logradouro TEXT, bairro TEXT, cidade TEXT, uf TEXT,
    cartorio TEXT, matricula TEXT,
    criado_em TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (cep, numero, complemento)
);
CREATE TABLE IF NOT EXISTS pessoas (
    id INTEGER PRIMARY KEY,
    imovel_id INTEGER NOT NULL REFERENCES imoveis(id) ON DELETE CASCADE,
    nome TEXT NOT NULL,
    cpf TEXT NOT NULL CHECK (length(cpf) = 11),
    papel TEXT NOT NULL CHECK (papel IN ('morador', 'proprietario')),
    fonte TEXT NOT NULL,
    criado_em TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (imovel_id, cpf, papel)
);
CREATE INDEX IF NOT EXISTS ix_pessoas_imovel ON pessoas(imovel_id);
CREATE INDEX IF NOT EXISTS ix_pessoas_cpf ON pessoas(cpf);
CREATE TABLE IF NOT EXISTS contatos (
    id INTEGER PRIMARY KEY,
    cpf TEXT NOT NULL,
    tipo TEXT NOT NULL,
    valor TEXT NOT NULL,
    whatsapp INTEGER NOT NULL DEFAULT 0,
    fonte TEXT NOT NULL,
    atualizado_em TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (cpf, valor)
);
CREATE TABLE IF NOT EXISTS pendencias (
    id INTEGER PRIMARY KEY,
    imovel_id INTEGER NOT NULL UNIQUE REFERENCES imoveis(id) ON DELETE CASCADE,
    solicitado_por INTEGER NOT NULL REFERENCES usuarios(id),
    status TEXT NOT NULL DEFAULT 'aguardando_matricula' CHECK (status IN ('aguardando_matricula', 'resolvida')),
    criado_em TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
-- Trilha de auditoria LGPD: toda consulta fica registrada com quem, quando, finalidade e custo.
CREATE TABLE IF NOT EXISTS consultas (
    id INTEGER PRIMARY KEY,
    usuario_id INTEGER NOT NULL REFERENCES usuarios(id),
    finalidade TEXT NOT NULL,
    imovel_id INTEGER REFERENCES imoveis(id),
    resultado TEXT NOT NULL CHECK (resultado IN ('base_propria', 'bureau', 'pendente_matricula', 'confirmacao_dono')),
    custo REAL NOT NULL DEFAULT 0,
    criado_em TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS ix_consultas_usuario_data ON consultas(usuario_id, criado_em);
CREATE TABLE IF NOT EXISTS abordagens (
    id INTEGER PRIMARY KEY,
    usuario_id INTEGER NOT NULL REFERENCES usuarios(id),
    imovel_id INTEGER NOT NULL REFERENCES imoveis(id),
    pessoa_id INTEGER REFERENCES pessoas(id),
    canal TEXT NOT NULL,
    resultado TEXT NOT NULL,
    observacao TEXT,
    criado_em TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS ix_abordagens_imovel ON abordagens(imovel_id);
CREATE TABLE IF NOT EXISTS optout (
    valor TEXT PRIMARY KEY,
    motivo TEXT,
    criado_em TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""


def _abrir() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 5000")
    return conn


@contextmanager
def conectar():
    conn = _abrir()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def iniciar() -> bool:
    """Cria o schema. Retorna True se o banco estava vazio (para semear a demonstração)."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    if DB_PATH.exists():
        conn = _abrir()
        versao = conn.execute("PRAGMA user_version").fetchone()[0]
        conn.close()
        if versao != SCHEMA_VERSION:
            if not DEMO:
                raise RuntimeError(f"Banco na versão {versao}, esperado {SCHEMA_VERSION}: migração necessária")
            DB_PATH.unlink()  # demonstração: recria do zero
    conn = _abrir()
    try:
        conn.execute("PRAGMA journal_mode = WAL")
        conn.executescript(SCHEMA)
        conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
        vazio = conn.execute("SELECT COUNT(*) FROM usuarios").fetchone()[0] == 0
        conn.commit()
        return vazio
    finally:
        conn.close()
