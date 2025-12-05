import os
import math
import sqlite3
import google.generativeai as genai
from flask import Flask, render_template, abort, request, g, jsonify

# ==============================================================================
# ⚠️ CONFIGURAÇÃO OBRIGATÓRIA ⚠️
# ==============================================================================
GOOGLE_API_KEY = "AIzaSyCtZ5x54klmPxAsPo8KuS9PaDzGum0UgFA" 
# ==============================================================================

if GOOGLE_API_KEY and GOOGLE_API_KEY != "A_TUA_API_KEY_AQUI":
    genai.configure(api_key=GOOGLE_API_KEY)

from db import get_db, close_connection, get_tables, get_primary_key

app = Flask(__name__)
app.teardown_appcontext(close_connection)

ITEMS_PER_PAGE = 50
SCHEMA_CACHE = None

# --- MAPA DE COLUNAS ESPECIAIS ---
# Define qual a coluna de texto principal para tabelas onde o nome da coluna não é óbvio
DISPLAY_COLUMNS = {
    'Grapes': 'Grape',       # Alterado de 'Grapes' para 'Grape'
    'Vintages': 'Vintage',   # Alterado de 'Vintages' para 'Vintage'
    'Harmonize': 'Harmonize'
}

INVERSE_RELATIONS = {
    'Winery': {'table': 'Wine', 'fk': 'WineryID', 'display': 'WineName'},
    'Region': {'table': 'Wine', 'fk': 'RegionID', 'display': 'WineName'},
    'Countries': {'table': 'Region', 'fk': 'Code', 'display': 'RegionName'},
    'Wine': [
        {'table': 'Grapes', 'fk': 'WineID', 'display': 'Grape'},      # Atualizado
        {'table': 'Harmonize', 'fk': 'WineID', 'display': 'Harmonize'},
        {'table': 'Vintages', 'fk': 'WineID', 'display': 'Vintage'}   # Atualizado
    ]
}

# As queries estatísticas mantêm-se, pois usam tabelas principais ou agregados
QUERIES = {
    '1': {'title': 'Top 10: Vinhos Tintos Mais Fortes', 
          'sql': """SELECT 
    w.WineID, 
    w.WineName, 
    winery.WineryName,
    w.ABV 
FROM Wine w
JOIN Winery winery ON w.WineryID = winery.WineryID
WHERE w.Type = 'Red' 
ORDER BY w.ABV DESC 
LIMIT 10;"""
    },
    '2': {'title': 'Top Regiões: Maior Produção de Vinhos', 
          'sql': """SELECT 
    r.RegionID,
    r.RegionName, 
    c.Country,
    COUNT(w.WineID) as Total_Wines 
FROM Region r 
JOIN Wine w ON r.RegionID = w.RegionID 
JOIN Countries c ON r.Code = c.Code
GROUP BY r.RegionName 
ORDER BY Total_Wines DESC 
LIMIT 10;"""
    },
    '3': {'title': 'Adegas Digitais (Com Website)', 
          'sql': """SELECT 
    WineryID,
    WineryName, 
    Website 
FROM Winery 
WHERE Website IS NOT NULL 
  AND Website != "" 
ORDER BY WineryName ASC
LIMIT 15;"""
    },
    '4': {
        'title': 'Vinhos de Acidez Alta (High Acidity)', 
        'sql': """SELECT 
    w.WineID,
    w.WineName, 
    w.Acidity,
    r.RegionName
FROM Wine w
JOIN Region r ON w.RegionID = r.RegionID
WHERE w.Acidity = 'High'
ORDER BY w.WineName
LIMIT 15;"""
    },
    '5': {
        'title': 'Panorama Internacional (Regiões por País)', 
        'sql': """SELECT 
    c.Code,
    c.Country, 
    COUNT(r.RegionID) as Num_Regions
FROM Countries c
JOIN Region r ON c.Code = r.Code
GROUP BY c.Country
ORDER BY Num_Regions DESC;"""
    },
    '6': {
        'title': 'Vinhos "Encorpados" (Full-bodied) do Porto', 
        'sql': """SELECT 
    w.WineID,
    w.WineName, 
    w.Body, 
    r.RegionName
FROM Wine w
JOIN Region r ON w.RegionID = r.RegionID
WHERE w.Body = 'Very full-bodied' 
  AND (r.RegionName LIKE '%Porto%' OR r.RegionName LIKE '%Douro%')
LIMIT 15;"""
    },
    '7': {
        'title': 'Harmonização: Vinhos para Carne (Beef)', 
        'sql': """SELECT 
    w.WineID,
    w.WineName, 
    h.Harmonize 
FROM Wine w 
JOIN Harmonize h ON w.WineID = h.WineID 
WHERE h.Harmonize LIKE '%Beef%'
LIMIT 15;"""
    },
    '8': {
        'title': 'Média de Álcool (ABV) por Tipo', 
        'sql': """SELECT 
    Type as Wine_Type, 
    ROUND(AVG(ABV), 2) as Average_ABV,
    COUNT(*) as Sample_Size
FROM Wine 
GROUP BY Type
ORDER BY Average_ABV DESC;"""
    },
    '9': {
        'title': 'Exploração de Castas: Cabernet Sauvignon', 
        'sql': """SELECT 
    w.WineID,
    w.WineName, 
    g.Grape as Casta
FROM Wine w 
JOIN Grapes g ON w.WineID = g.WineID 
WHERE g.Grape LIKE '%Cabernet Sauvignon%' 
LIMIT 15;"""
    },
    '10':{
        'title': 'Vinhos Vintage Antigos (Pré-2000)', 
        'sql': """SELECT 
    w.WineID,
    w.WineName, 
    v.Vintage as Ano
FROM Wine w 
JOIN Vintages v ON w.WineID = v.WineID 
WHERE CAST(v.Vintage as INTEGER) < 2000
ORDER BY v.Vintage ASC 
LIMIT 15;"""
    }
}

def get_unique_values(db, table, column, limit=20):
    try:
        cur = db.execute(f"SELECT DISTINCT {column} FROM {table} WHERE {column} IS NOT NULL LIMIT {limit}")
        values = [str(row[0]) for row in cur.fetchall()]
        return f"-- Valid values for {table}.{column}: {', '.join(values)}"
    except:
        return ""

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
    context_parts.append(get_unique_values(db, 'Wine', 'Body'))
    context_parts.append(get_unique_values(db, 'Countries', 'Country', 50))
    # Atualizado para usar as novas colunas
    context_parts.append(get_unique_values(db, 'Grapes', 'Grape', 30))
    context_parts.append(get_unique_values(db, 'Vintages', 'Vintage', 30))

    SCHEMA_CACHE = "\n".join(context_parts)
    return SCHEMA_CACHE

def ask_gemini_sql(user_question):
    if not GOOGLE_API_KEY or GOOGLE_API_KEY == "A_TUA_API_KEY_AQUI":
        return None, "⚠️ Falta a API Key! Configure no ficheiro app/app.py."

    try:
        genai.configure(api_key=GOOGLE_API_KEY)
        schema_context = get_enriched_schema()
        
        # Prompt Avançado Bilingue
        prompt = f"""
        Role: Expert SQL Sommelier & Data Analyst.
        Dialect: SQLite.
        
        Context:
        You are assisting a user in a Wine Database application.
        The user may ask in Portuguese (PT-PT) or English. You must interpret both.
        
        Database Schema & Samples:
        {schema_context}
        
        Mapping Rules (PT -> EN Database Values):
        - "Tinto" -> Type='Red'
        - "Branco" -> Type='White'
        - "Espumante" -> Type='Sparkling'
        - "Rosé" / "Rosado" -> Type='Rosé'
        - "Verde" -> Name LIKE '%Vinho Verde%' OR Region LIKE '%Vinho Verde%'
        - "Casta" / "Uva" -> Table 'Grapes', column 'Grape'
        - "Ano" -> Table 'Vintages', column 'Vintage'
        - "Harmonizar" / "Comer" / "Acompanhar" -> Table 'Harmonize'
        
        Query Generation Rules:
        1. Output ONLY valid, raw SQL. No markdown, no explanations.
        2. CRITICAL: The FIRST column in SELECT MUST be the Primary Key (WineID, WineryID, RegionID, or Code) to enable clickable links in the UI.
        3. Select descriptive columns after the ID (e.g., SELECT WineID, WineName, Type, ABV...).
        4. Use LIKE for flexible text search (e.g. "Peixe" -> Harmonize LIKE '%Fish%' OR Harmonize LIKE '%Seafood%').
        5. Do NOT use LIMIT unless the user explicitly asks (e.g. "top 10"). Show all matches.
        
        User Question: "{user_question}"
        SQL Query:
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
            if err:
                error = err
            else:
                sql_query = generated_sql
                try:
                    db = get_db()
                    cur = db.execute(sql_query)
                    results = cur.fetchall()
                    if results is None: results = []
                    if len(results) > 1000:
                        error = f"Atenção: A consulta retornou {len(results)} resultados. A página pode ficar lenta."
                except Exception as e:
                    error = f"Erro SQL: {e}"

    return render_template('ai_search.html', 
                           user_question=user_question, 
                           sql_query=sql_query, 
                           results=results, 
                           error=error)

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
    search_query = request.args.get('q', '').strip()
    offset = (page - 1) * ITEMS_PER_PAGE
    
    where_clause = ""
    params = []
    
    if search_query:
        columns_info = db.execute(f"PRAGMA table_info({table_name})").fetchall()
        search_conditions = []
        for col in columns_info:
            col_name = col['name']
            if 'Name' in col_name or 'Country' in col_name or 'Type' in col_name or 'Code' in col_name or 'Title' in col_name or col_name == pk:
                search_conditions.append(f"{col_name} LIKE ?")
                params.append(f"%{search_query}%")
        
        # Atualização para as novas colunas
        if table_name in DISPLAY_COLUMNS:
             col = DISPLAY_COLUMNS[table_name]
             search_conditions.append(f"{col} LIKE ?")
             params.append(f"%{search_query}%")

        if search_conditions:
            where_clause = "WHERE " + " OR ".join(search_conditions)

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
        if table_name in DISPLAY_COLUMNS:
             display_col = DISPLAY_COLUMNS[table_name]
        else:
            keys = rows[0].keys()
            for k in keys:
                if 'Name' in k or 'Country' in k:
                    display_col = k
                    break
    
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.args.get('format') == 'json':
        return jsonify({
            'rows': [dict(row) for row in rows],
            'display_col': display_col,
            'pk': pk,
            'total_pages': total_pages,
            'current_page': page,
            'total_rows': total_rows
        })

    return render_template('list.html', 
                           table_name=table_name, 
                           rows=rows, 
                           pk=pk, 
                           display_col=display_col,
                           page=page,
                           total_pages=total_pages,
                           total_rows=total_rows,
                           search_query=search_query)

@app.route('/<table_name>/<pk_val>/')
def detail_view(table_name, pk_val):
    valid_tables = get_tables()
    if table_name not in valid_tables: abort(404)
    pk = get_primary_key(table_name)
    db = get_db()
    
    where_clause = "rowid = ?" if pk == 'rowid' else f"{pk} = ?"
    sel_cols = "rowid, *" if pk == 'rowid' else "*"
    
    query = f"SELECT {sel_cols} FROM {table_name} WHERE {where_clause}"
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
                if data:
                    relations[rel['table']] = {'data': data, 'pk': rel_pk, 'display': rel['display']}
            except: pass

    return render_template('detail.html', table_name=table_name, item=item, pk=pk, relations=relations)

if __name__ == '__main__':
    app.run(debug=True, port=5000)