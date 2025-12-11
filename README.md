# XWines - Gestor de Vinhos Inteligente

Uma aplicação web desenvolvida em **Flask** para explorar uma base de dados de vinhos, potenciada por **Inteligência Artificial** para pesquisas em linguagem natural.

---

## 🚀 Funcionalidades Principais

### **Sommelier IA**
Faz perguntas em linguagem natural (ex: *"Vinhos tintos do Douro para carne"*) e a IA gera automaticamente a consulta SQL correspondente.

### **Exploração de Dados**
Navega facilmente entre **Vinhos**, **Adegas**, **Regiões** e **Países**, com ligações automáticas entre entidades.

### **Estatísticas Avançadas**
Painel com **11 análises complexas** sobre produção, características e distribuição dos vinhos.

### **Pesquisa em Tempo Real**
Filtragem instantânea em todas as tabelas da aplicação.

---

## 🛠️ Tecnologias Usadas
- **Backend:** Python (Flask)
- **Base de Dados:** SQLite (*XWines_Relational1.db*)
- **Frontend:** HTML5 + Tailwind CSS
- **IA:** Google Gemini API

---

## ⚙️ Como Executar

### 1. Instalar dependências
```bash
pip install flask google-generativeai
```

### 2. Configurar a API Key
Abre o ficheiro `app/app.py` e coloca a tua chave do Google AI Studio:
```python
GOOGLE_API_KEY = "COLA_AQUI_A_TUA_CHAVE"
```

### 3. Iniciar a aplicação
```bash
python app/app.py
```