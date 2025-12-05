import pandas as pd
import sqlite3
import ast
import os
import sys

# Caminhos dos ficheiros
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CSV_FILE = os.path.join(BASE_DIR, 'X-Wines.csv')
DB_FILE = os.path.join(BASE_DIR, 'XWines_Relational1.db')

def create_db():

    # -------------------------------
    # 1) Remover BD antiga (se existir)
    # -------------------------------
    if os.path.exists(DB_FILE):
        try:
            os.remove(DB_FILE)
            print("Base de dados antiga removida.")
        except PermissionError:
            print("ERRO: A base de dados está a ser usada por outro programa.")
            print("Feche o servidor Flask (CTRL+C) e volte a tentar.")
            sys.exit(1)

    # -------------------------------
    # 2) Ler ficheiro CSV
    # -------------------------------
    print("A carregar ficheiro CSV...")
    try:
        df = pd.read_csv(CSV_FILE)
    except Exception as e:
        print(f"Erro ao ler CSV: {e}")
        return

    # -------------------------------
    # 3) Função para converter listas representadas como strings
    # -------------------------------
    def parse_list(x):
        if isinstance(x, str) and x.strip().startswith('['):
            try:
                return ast.literal_eval(x)
            except:
                return []
        return []

    print("A processar tabelas...")

    # -------------------------------
    # 4) Criar DataFrames individuais
    # -------------------------------

    # Países
    df_countries = df[['Code', 'Country']].drop_duplicates('Code').dropna()

    # Regiões
    df_region = df[['RegionID', 'RegionName', 'Code']].drop_duplicates('RegionID').dropna()

    # Produtores / Wineries
    df_winery = df[['WineryID', 'WineryName', 'Website']].drop_duplicates('WineryID')

    # Vinhos
    df_wine = df[['WineID', 'WineName', 'Type', 'Elaborate', 'Body',
                  'Acidity', 'ABV', 'WineryID', 'RegionID']].drop_duplicates('WineID')

    # Uvas (listas)
    df_grapes = df[['WineID', 'Grapes']].copy()
    df_grapes['Grapes'] = df_grapes['Grapes'].apply(parse_list)
    df_grapes = df_grapes.explode('Grapes').dropna()

    # Harmonizações (listas)
    df_harm = df[['WineID', 'Harmonize']].copy()
    df_harm['Harmonize'] = df_harm['Harmonize'].apply(parse_list)
    df_harm = df_harm.explode('Harmonize').dropna()

    # Colheitas / Vintages
    df_vint = df[['WineID', 'Vintages']].copy()
    df_vint['Vintages'] = df_vint['Vintages'].apply(parse_list)
    df_vint = df_vint.explode('Vintages').dropna()

    # -------------------------------
    # 5) Criar BD e ativar foreign keys
    # -------------------------------
    print("A gravar base de dados SQLite...")
    conn = sqlite3.connect(DB_FILE)
    conn.execute("PRAGMA foreign_keys = ON;")
    cursor = conn.cursor()

    # -------------------------------
    # 6) Criar tabelas com PK e FK
    # -------------------------------
    schema_sql = """
    -- Tabela de Países
    CREATE TABLE Countries (
        Code TEXT PRIMARY KEY,
        Country TEXT NOT NULL
    );

    -- Tabela de Regiões
    CREATE TABLE Region (
        RegionID INTEGER PRIMARY KEY,
        RegionName TEXT,
        Code TEXT,
        FOREIGN KEY (Code) REFERENCES Countries(Code)
    );

    -- Tabela de Produtores
    CREATE TABLE Winery (
        WineryID INTEGER PRIMARY KEY,
        WineryName TEXT,
        Website TEXT
    );

    -- Tabela principal de Vinhos
    CREATE TABLE Wine (
        WineID INTEGER PRIMARY KEY,
        WineName TEXT,
        Type TEXT,
        Elaborate TEXT,
        Body TEXT,
        Acidity TEXT,
        ABV REAL,
        WineryID INTEGER,
        RegionID INTEGER,
        FOREIGN KEY (WineryID) REFERENCES Winery(WineryID),
        FOREIGN KEY (RegionID) REFERENCES Region(RegionID)
    );

    -- Tabela de Uvas associadas a um vinho
    CREATE TABLE Grapes (
        WineID INTEGER,
        Grape TEXT,
        PRIMARY KEY (WineID, Grape),
        FOREIGN KEY (WineID) REFERENCES Wine(WineID)
    );

    -- Tabela de Harmonizações
    CREATE TABLE Harmonize (
        WineID INTEGER,
        Harmonize TEXT,
        PRIMARY KEY (WineID, Harmonize),
        FOREIGN KEY (WineID) REFERENCES Wine(WineID)
    );

    -- Tabela de Colheitas (anos)
    CREATE TABLE Vintages (
        WineID INTEGER,
        Vintage INTEGER,
        PRIMARY KEY (WineID, Vintage),
        FOREIGN KEY (WineID) REFERENCES Wine(WineID)
    );
    """

    cursor.executescript(schema_sql)
    conn.commit()

    # -------------------------------
    # 7) Inserir dados nas tabelas criadas
    # -------------------------------
    df_countries.to_sql("Countries", conn, if_exists="append", index=False)
    df_region.to_sql("Region", conn, if_exists="append", index=False)
    df_winery.to_sql("Winery", conn, if_exists="append", index=False)
    df_wine.to_sql("Wine", conn, if_exists="append", index=False)

    df_grapes.rename(columns={"Grapes": "Grape"}).to_sql("Grapes", conn, if_exists="append", index=False)
    df_harm.rename(columns={"Harmonize": "Harmonize"}).to_sql("Harmonize", conn, if_exists="append", index=False)
    df_vint.rename(columns={"Vintages": "Vintage"}).to_sql("Vintages", conn, if_exists="append", index=False)

    conn.close()

    print("Base de dados criada com sucesso com PK e FK!")


# -------------------------------
# Execução principal
# -------------------------------
if __name__ == '__main__':
    create_db()
