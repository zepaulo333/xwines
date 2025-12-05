from app import app as APP

# Este ficheiro serve apenas para iniciar o servidor
# Aponte o seu comando python para aqui: python app/server.py

if __name__ == "__main__":
    print("A iniciar servidor XWines...")
    APP.run(debug=True, host='0.0.0.0', port=5000)