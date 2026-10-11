import os
import threading
import requests
from flask import Flask, request, jsonify
from google import genai
from google.genai import types

app = Flask(__name__)

# timeout en milisegundos (20 segundos)
client = genai.Client(
    api_key=os.environ.get("GEMINI_API_KEY"),
    http_options=types.HttpOptions(timeout=20000),
)

WHATSAPP_TOKEN = os.environ.get("WHATSAPP_TOKEN")
PHONE_NUMBER_ID = os.environ.get("PHONE_NUMBER_ID")
VERIFY_TOKEN = "grupo_ol_secreto"

MODELOS = ["gemini-3.8-flash", "gemini-flash-latest", "gemini-3.5-flash"]

procesados = set()  # ids de mensajes ya atendidos


def generar_respuesta(prompt):
    ultimo_error = None
    for nombre in MODELOS:
        try:
            print("PROBANDO MODELO:", nombre, flush=True)
            r = client.models.generate_content(model=nombre, contents=prompt)
            print("MODELO USADO:", nombre, flush=True)
            return r.text
        except Exception as ex:
            print(f"FALLO MODELO {nombre}:", str(ex), flush=True)
            ultimo_error = ex
    raise ultimo_error


def atender_mensaje(numero, texto):
    try:
        prompt = f"""
        Eres Luis Silva, el asistente experto de soporte técnico de Grupo OL.
        Responde de forma amable, clara y paso a paso al siguiente problema:

        Problema: {texto}
        """
        respuesta_ia = generar_respuesta(prompt)[:4000]

        url = f"https://graph.facebook.com/v21.0/{PHONE_NUMBER_ID}/messages"
        headers = {
            "Authorization": f"Bearer {WHATSAPP_TOKEN}",
            "Content-Type": "application/json",
        }
        payload = {
            "messaging_product": "whatsapp",
            "to": numero,
            "type": "text",
            "text": {"body": respuesta_ia},
        }
        r = requests.post(url, json=payload, headers=headers, timeout=15)
        print("RESPUESTA DE WHATSAPP:", r.status_code, r.text, flush=True)
    except Exception as ex:
        print("ERROR AL ATENDER:", str(ex), flush=True)


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
        data = request.json or {}
        print("WEBHOOK RECIBIDO:", data, flush=True)

        for e in data.get("entry", []):
            for c in e.get("changes", []):
                value = c.get("value", {})
                for msg in value.get("messages", []):
                    msg_id = msg.get("id")
                    numero = msg.get("from", "")
                    texto = msg.get("text", {}).get("body", "")

                    if not (texto and numero):
                        continue
                    if msg_id in procesados:
                        print("MENSAJE REPETIDO, SE IGNORA:", msg_id, flush=True)
                        continue
                    procesados.add(msg_id)

                    # Se atiende en segundo plano para responderle a Meta ya
                    threading.Thread(
                        target=atender_mensaje, args=(numero, texto), daemon=True
                    ).start()
    except Exception as ex:
        print("ERROR:", str(ex), flush=True)

    return jsonify({"status": "received"}), 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
