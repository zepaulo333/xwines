import os
import math
import sqlite3
import google.generativeai as genai
from flask import Flask, render_template, abort, request, g, jsonify


GOOGLE_API_KEY = "A" 


from db import get_db, close_connection, get_tables, get_primary_key

app = Flask(__name__)
app.teardown_appcontext(close_connection)

ITEMS_PER_PAGE = 50
SCHEMA_CACHE = None

# Definição de colunas de visualização para tabelas de ligação
DISPLAY_COLUMNS = {
    'Grapes': 'Grape',
    'Vintages': 'Vintage',
    'Harmonize': 'Harmonize'
}

# Relações Inversas (Mostrar Filhos na Página do Pai)
INVERSE_RELATIONS = {
    'Winery': {'table': 'Wine', 'fk': 'WineryID', 'display': 'WineName'},
    'Region': {
        'table': 'Wine', 
        'fk': 'RegionID', 
        'display': 'WineName'
    },
    'Countries': {'table': 'Region', 'fk': 'Code', 'display': 'RegionName'},
    'Wine': [
        {'table': 'Grapes', 'fk': 'WineID', 'display': 'Grape'},
        {'table': 'Harmonize', 'fk': 'WineID', 'display': 'Harmonize'},
        {'table': 'Vintages', 'fk': 'WineID', 'display': 'Vintage'}
    ]
}

# --- QUERIES ESTATÍSTICAS ---
QUERIES = {
    '1': {
        'title': 'P1: Tipos de Vinho Distintos', 
        'sql': """SELECT DISTINCT Type
FROM Wine
ORDER BY Type;"""
    },
    '2': {
        'title': 'P2: Vinho com Maior Teor Alcoólico', 
        'sql': """SELECT
      WineID,
      WineName,
      ABV
FROM Wine
ORDER BY
      ABV DESC
LIMIT 1;"""
    },
    '3': {
        'title': 'P3: Média de ABV (Espumantes)', 
        'sql': """SELECT ROUND(AVG(ABV), 2) AS AverageSparklingABV
FROM Wine
WHERE Type = 'Sparkling';"""
    },
    '4': {
        'title': 'P4: Adegas do Douro', 
        'sql': """SELECT 
      T2.WineryID, 
      T2.WineryName, 
      T2.Website
FROM Wine AS T1
      JOIN
      Winery AS T2 ON T1.WineryID = T2.WineryID
      JOIN
      Region AS T3 ON T1.RegionID = T3.RegionID
WHERE T3.RegionName = 'Douro'
GROUP BY T2.WineryID, T2.WineryName, T2.Website
ORDER BY T2.WineryName;"""
    },
    '5': {
        'title': 'P5: Harmonização Beef & Poultry', 
        'sql': """SELECT T1.Type
FROM Wine AS T1
      JOIN Harmonize AS T2 ON T1.WineID = T2.WineID
WHERE T2.Harmonize = 'Beef'

INTERSECT

SELECT T1.Type
FROM Wine AS T1
       JOIN Harmonize AS T2 ON T1.WineID = T2.WineID
WHERE T2.Harmonize = 'Poultry'

ORDER BY T1.Type;"""
    },
    '6': {
        'title': 'P6: Top 10 Regiões (Mais Vinhos)', 
        'sql': """SELECT
      T2.RegionID,
      T2.RegionName,
      COUNT(T1.WineID) AS TotalWines
FROM Wine AS T1
      JOIN Region AS T2
      ON T1.RegionID = T2.RegionID
GROUP BY
      T2.RegionID
ORDER BY
      TotalWines DESC
LIMIT 10;"""
    },
    '7': {
        'title': 'P7: Média de Álcool por País', 
        'sql': """SELECT
      T3.Code,
      T3.Country,
      AVG(T1.ABV) as Media_ABV
FROM Wine AS T1
    JOIN Region AS T2
      ON T1.RegionID = T2.RegionID
    JOIN Countries AS T3
      ON T2.Code = T3.Code
WHERE
      T1.ABV IS NOT NULL
GROUP BY
      T3.Code, T3.Country
ORDER BY
      Media_ABV DESC;"""
    },
    '8': {
        'title': 'P8: Adegas Exclusivas (Acidez Alta)', 
        'sql': """SELECT
    T1.WineryID,
    T1.WineryName
FROM
    Winery AS T1
    JOIN
    Wine AS T2 ON T1.WineryID = T2.WineryID
GROUP BY
    T1.WineryID, T1.WineryName
HAVING
      COUNT(T2.WineID) = COUNT(CASE WHEN T2.Acidity = 'High' THEN T2.WineID END)
      AND COUNT(T2.WineID) > 0;"""
    },
    '9': {
        'title': 'P9: Adegas Internacionais (Multi-País)', 
        'sql': """SELECT
      T1.WineryID,
      T1.WineryName
FROM Winery AS T1
    JOIN Wine AS T2
       ON T1.WineryID = T2.WineryID
    JOIN Region AS T3
       ON T2.RegionID = T3.RegionID
    JOIN Countries AS T4
       ON T3.Code = T4.Code
GROUP BY
       T1.WineryID
HAVING
       COUNT(DISTINCT T4.Code) > 1;"""
    },
    '10':{
        'title': 'P10: Vinhos Multi-Casta (>1 Uva)', 
        'sql': """SELECT
      T1.WineID,
      T1.WineName,
      COUNT(T2.Grape) AS numero_castas
FROM Wine AS T1
JOIN Grapes AS T2
      ON T1.WineID = T2.WineID
GROUP BY
      T1.WineID,
      T1.WineName
HAVING
      COUNT(T2.Grape) > 1;"""
    },
    '11':{
        'title': 'P11: Regiões Acima da Média Nacional',
        'sql': """WITH AvgABVPerCountry AS (
SELECT C.Code, AVG(W.ABV) AS CountryAvg
FROM Wine W
JOIN Region R ON W.RegionID = R.RegionID
JOIN Countries C ON C.Code = R.Code
GROUP BY C.Code
)
SELECT
      R.RegionID,
      R.RegionName,
      C.Country,
      ROUND(AVG(W.ABV), 2) AS RegionAvgABV,
      ROUND(A.CountryAvg, 2) AS CountryAvgABV
FROM Wine W
JOIN Region R ON W.RegionID = R.RegionID
JOIN Countries C ON C.Code = R.Code
JOIN AvgABVPerCountry A ON A.Code = C.Code
GROUP BY R.RegionID
HAVING AVG(W.ABV) > A.CountryAvg
ORDER BY C.Country, RegionAvgABV DESC;"""
    }
}

def get_unique_values(db, table, column, limit=20):
    try:
        cur = db.execute(f"SELECT DISTINCT {column} FROM {table} WHERE {column} IS NOT NULL LIMIT {limit}")
        values = [str(row[0]) for row in cur.fetchall()]
        return f"-- Ex. values for {table}.{column}: {', '.join(values)}"
    except: return ""

def get_enriched_schema():
    global SCHEMA_CACHE
    if SCHEMA_CACHE: return SCHEMA_CACHE
    db = get_db()
    context_parts = []
    target_tables = ['Wine', 'Winery', 'Region', 'Countries', 'Grapes', 'Harmonize', 'Vintages']
    for table in target_tables:
        ddl = db.execute(f"SELECT sql FROM sqlite_master WHERE type='table' AND name='{table}'").fetchone()
        if ddl and ddl['sql']:
            clean_sql = " ".join(ddl['sql'].split())
            context_parts.append(clean_sql + ";")
    context_parts.append("\n/* DATABASE DATA CONTEXT */")
    context_parts.append(get_unique_values(db, 'Wine', 'Type'))
    context_parts.append(get_unique_values(db, 'Countries', 'Country', 50))
    context_parts.append(get_unique_values(db, 'Harmonize', 'Harmonize', 30))
    context_parts.append(get_unique_values(db, 'Grapes', 'Grape', 30))
    SCHEMA_CACHE = "\n".join(context_parts)
    return SCHEMA_CACHE

def ask_gemini_sql(user_question):
    if not GOOGLE_API_KEY or GOOGLE_API_KEY == "A_TUA_API_KEY_AQUI":
        return None, "⚠️ Falta a API Key no ficheiro app.py."

    try:
        genai.configure(api_key=GOOGLE_API_KEY)
        schema_context = get_enriched_schema()
        
        prompt = f"""
        Role: Expert SQL Data Analyst. Dialect: SQLite.
        
        Database Schema & Data Samples:
        {schema_context}
        
        Goal: Generate a SQL query to answer: "{user_question}"
        
        Strict Rules:
        1. Output ONLY raw SQL. No markdown.
        2. MANDATORY: Select the Primary Key FIRST (e.g. WineID), THEN select meaningful columns.
        3. Use LIKE for text searches (case-insensitive).
        4. If searching for food pairings, join 'Wine' with 'Harmonize'.
        5. If searching for grapes/castas, join 'Wine' with 'Grapes' (column is 'Grape').
        6. If searching for years, join 'Wine' with 'Vintages' (column is 'Vintage').
        7. LIMIT results to 50 unless specified otherwise.
        8. FORMAT THE SQL: Use newlines and indentation for readability (e.g. SELECT on one line, FROM on next, WHERE on next). Do not write single-line SQL.
        """
        
        model = genai.GenerativeModel('gemini-2.5-flash-preview-09-2025')
        response = model.generate_content(prompt)
        sql = response.text.strip().replace('```sql', '').replace('```', '').strip()
        return sql, None
        
    except Exception as e:
        return None, f"Erro IA: {str(e)}"

# --- ROTAS ---
@app.route('/')
def index():
    tables = get_tables()
    get_enriched_schema()
    return render_template('index.html', tables=tables)

@app.route('/ai-sommelier', methods=['GET', 'POST'])
def ai_sommelier():
    sql_query = None
    results = None
    error = None
    user_question = ""
    if request.method == 'POST':
        user_question = request.form.get('question')
        if user_question:
            generated_sql, err = ask_gemini_sql(user_question)
            if err: error = err
            else:
                sql_query = generated_sql
                try:
                    db = get_db()
                    cur = db.execute(sql_query)
                    results = cur.fetchall()
                    if results is None: results = []
                except Exception as e: error = f"Erro SQL: {e}"
    return render_template('ai_search.html', user_question=user_question, sql_query=sql_query, results=results, error=error)

@app.route('/queries/')
@app.route('/queries/<query_id>')
def queries(query_id=None):
    results = None
    active_query = None
    if query_id and query_id in QUERIES:
        db = get_db()
        cur = db.execute(QUERIES[query_id]['sql'])
        results = cur.fetchall()
        active_query = QUERIES[query_id]
    return render_template('queries.html', queries=QUERIES, active_id=query_id, active_query=active_query, results=results)

@app.route('/<table_name>/')
def list_table(table_name):
    valid_tables = get_tables()
    if table_name not in valid_tables: abort(404)
    db = get_db()
    pk = get_primary_key(table_name)
    page = request.args.get('page', 1, type=int)
    offset = (page - 1) * ITEMS_PER_PAGE
    search_query = request.args.get('q', '').strip()
    
    where_clause = ""
    params = []
    if search_query:
        columns_info = db.execute(f"PRAGMA table_info({table_name})").fetchall()
        search_conditions = []
        for col in columns_info:
            if 'Name' in col['name'] or 'Country' in col['name'] or 'Type' in col['name'] or col['name'] == pk:
                search_conditions.append(f"{col['name']} LIKE ?")
                params.append(f"%{search_query}%")
        if table_name in DISPLAY_COLUMNS:
             col = DISPLAY_COLUMNS[table_name]
             search_conditions.append(f"{col} LIKE ?")
             params.append(f"%{search_query}%")
        if search_conditions: where_clause = "WHERE " + " OR ".join(search_conditions)

    count_sql = f"SELECT COUNT(*) as total FROM {table_name} {where_clause}"
    total_rows = db.execute(count_sql, params).fetchone()['total']
    total_pages = math.ceil(total_rows / ITEMS_PER_PAGE)
    
    sel_cols = f"rowid, *" if pk == 'rowid' else "*"
    data_sql = f"SELECT {sel_cols} FROM {table_name} {where_clause} LIMIT ? OFFSET ?"
    query_params = params + [ITEMS_PER_PAGE, offset]
    cur = db.execute(data_sql, query_params)
    rows = cur.fetchall()
    
    display_col = pk
    if len(rows) > 0:
        if table_name in DISPLAY_COLUMNS: display_col = DISPLAY_COLUMNS[table_name]
        else:
            for k in rows[0].keys():
                if 'Name' in k or 'Country' in k: display_col = k; break
    
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.args.get('format') == 'json':
        return jsonify({'rows': [dict(row) for row in rows], 'display_col': display_col, 'pk': pk, 'total_pages': total_pages, 'current_page': page, 'total_rows': total_rows})

    return render_template('list.html', table_name=table_name, rows=rows, pk=pk, display_col=display_col, page=page, total_pages=total_pages, total_rows=total_rows, search_query=search_query)

@app.route('/<table_name>/<pk_val>/')
def detail_view(table_name, pk_val):
    valid_tables = get_tables()
    if table_name not in valid_tables: abort(404)
    pk = get_primary_key(table_name)
    db = get_db()
    if pk == 'rowid': query = f"SELECT rowid, * FROM {table_name} WHERE rowid = ?"
    else: query = f"SELECT * FROM {table_name} WHERE {pk} = ?"
    cur = db.execute(query, (pk_val,))
    item = cur.fetchone()
    if item is None: abort(404)
    
    relations = {}
    if table_name in INVERSE_RELATIONS:
        config = INVERSE_RELATIONS[table_name]
        configs = config if isinstance(config, list) else [config]
        for rel in configs:
            try:
                rel_pk = get_primary_key(rel['table'])
                r_sel = f"rowid, *" if rel_pk == 'rowid' else "*"
                r_cur = db.execute(f"SELECT {r_sel} FROM {rel['table']} WHERE {rel['fk']} = ? LIMIT 50", (pk_val,))
                data = r_cur.fetchall()
                if data: relations[rel['table']] = {'data': data, 'pk': rel_pk, 'display': rel['display']}
            except: pass

    return render_template('detail.html', table_name=table_name, item=item, pk=pk, relations=relations)

if __name__ == '__main__':
    app.run(debug=True, port=5000)