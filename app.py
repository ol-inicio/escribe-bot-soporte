import os
from flask import Flask, request, jsonify
from google import genai

app = Flask(__name__)

# Configuramos la IA de Gemini con tu llave
# (Render leerá la llave de una variable de entorno segura)
client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))

@app.route("/", methods=["GET"])
def home():
    return "¡El Bot de Soporte de Grupo OL está activo y funcionando!", 200

@app.route("/webhook", methods=["POST"])
def webhook():
    try:
        data = request.json
        # Supongamos que recibimos el mensaje del usuario en el campo 'message'
        mensaje_usuario = data.get("message", "")

        if not mensaje_usuario:
            return jsonify({"error": "No se encontró ningún mensaje"}), 400

        # Le damos instrucciones a Gemini de cómo debe comportarse
        prompt = f"""
        Eres Luis Silva, el asistente experto de soporte técnico de Grupo OL.
        Responde de forma amable, clara, profesional y paso a paso al siguiente problema del usuario:
        
        Problema: {mensaje_usuario}
        """

        # Consultamos a Gemini 2.5 Flash
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
        )

        respuesta_ia = response.text

        # Devolvemos la respuesta lista para enviarla
        return jsonify({"status": "success", "response": respuesta_ia}), 200

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)