import os
import requests
from flask import Flask, request, jsonify
import google.generativeai as genai

app = Flask(__name__)

# Configuramos Gemini con la llave de entorno
genai.configure(api_key=os.environ.get("GEMINI_API_KEY"))

# Credenciales y Token de verificación
WHATSAPP_TOKEN = os.environ.get("WHATSAPP_TOKEN")
PHONE_NUMBER_ID = os.environ.get("PHONE_NUMBER_ID")
VERIFY_TOKEN = "grupo_ol_secreto"

@app.route("/", methods=["GET"])
def home():
    return "¡El Bot de Soporte de Grupo OL está activo!", 200

@app.route("/webhook", methods=["GET"])
def verify_webhook():
    mode = request.args.get("hub.mode")
    token = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")

    if mode and token:
        if mode == "subscribe" and token == VERIFY_TOKEN:
            return challenge, 200
        else:
            return "Token incorrecto", 403
    return "Parámetros inválidos", 400

@app.route("/webhook", methods=["POST"])
def webhook():
    try:
        data = request.json
        print("WEBHOOK RECIBIDO:", data)
        
        entry = data.get("entry", [])
        for e in entry:
            changes = e.get("changes", [])
            for c in changes:
                value = c.get("value", {})
                # Ojo: En la API de Meta, messages viene dentro de value
                messages = value.get("messages", [])
                if messages:
                    msg = messages[0]
                    numero_remitente = msg.get("from", "")
                    mensaje_usuario = msg.get("text", {}).get("body", "")

                    if mensaje_usuario and numero_remitente:
                        # Generar respuesta con Gemini
                        model = genai.GenerativeModel('gemini-1.5-flash')
                        prompt = f"""
                        Eres Luis Silva, el asistente experto de soporte técnico de Grupo OL.
                        Responde de forma amable, clara y paso a paso al siguiente problema:
                        
                        Problema: {mensaje_usuario}
                        """
                        response = model.generate_content(prompt)
                        respuesta_ia = response.text

                        # Enviar la respuesta de vuelta a WhatsApp
                        url = f"https://graph.facebook.com/v18.0/{PHONE_NUMBER_ID}/messages"
                        headers = {
                            "Authorization": f"Bearer {WHATSAPP_TOKEN}",
                            "Content-Type": "application/json"
                        }
                        payload = {
                            "messaging_product": "whatsapp",
                            "to": numero_remitente,
                            "text": {"body": respuesta_ia}
                        }
                        requests.post(url, json=payload, headers=headers)

        return jsonify({"status": "success"}), 200

    except Exception as e:
        print("ERROR:", str(e))
        return jsonify({"status": "error", "message": str(e)}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
