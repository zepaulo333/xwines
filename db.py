import sqlite3
from flask import g
import os

DATABASE = 'XWines.db'

def get_db():
    """Conecta à base de dados e garante que retorna linhas como dicionários."""
    db = getattr(g, '_database', None)
    if db is None:
        if not os.path.exists(DATABASE):
            # Fallback para procurar na pasta app/
            alt_path = os.path.join('app', DATABASE)
            if os.path.exists(alt_path):
                db_path = alt_path
            else:
                db_path = DATABASE
        else:
            db_path = DATABASE

        db = g._database = sqlite3.connect(db_path)
        db.row_factory = sqlite3.Row
    return db

def close_connection(exception):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()

def get_tables():
    db = get_db()
    cur = db.execute("SELECT name FROM sqlite_master WHERE type='table';")
    return [row['name'] for row in cur.fetchall()]

def get_primary_key(table):
    """
    Define a chave primária para cada tabela.
    Tabelas de associação (Grapes, Harmonize, Vintages) usam o 'rowid' interno do SQLite.
    """
    if table == 'Countries': return 'Code'
    if table in ['Grapes', 'Harmonize', 'Vintages']: return 'rowid'
    return f"{table}ID"