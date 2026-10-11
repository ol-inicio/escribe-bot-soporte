import os
from flask import Flask, request, jsonify
import google.generativeai as genai

app = Flask(__name__)

# Configuramos Gemini con la llave de entorno
genai.configure(api_key=os.environ.get("GEMINI_API_KEY"))

@app.route("/", methods=["GET"])
def home():
    return "¡El Bot de Soporte de Grupo OL está activo!", 200

@app.route("/webhook", methods=["POST"])
def webhook():
    try:
        data = request.json
        mensaje_usuario = data.get("message", "")

        if not mensaje_usuario:
            return jsonify({"error": "No se encontró ningún mensaje"}), 400

        # Usamos el modelo estándar y estable
        model = genai.GenerativeModel('gemini-1.5-flash')
        
        prompt = f"""
        Eres Luis Silva, el asistente experto de soporte técnico de Grupo OL.
        Responde de forma amable, clara y paso a paso al siguiente problema:
        
        Problema: {mensaje_usuario}
        """

        response = model.generate_content(prompt)
        return jsonify({"status": "success", "response": response.text}), 200

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
