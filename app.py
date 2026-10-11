import os
import threading
from collections import defaultdict, deque

import requests
from flask import Flask, request, jsonify
from google import genai
from google.genai import types

app = Flask(__name__)

# timeout en milisegundos (15 segundos por modelo)
client = genai.Client(
    api_key=os.environ.get("GEMINI_API_KEY"),
    http_options=types.HttpOptions(timeout=15000),
)

WHATSAPP_TOKEN = os.environ.get("WHATSAPP_TOKEN")
PHONE_NUMBER_ID = os.environ.get("PHONE_NUMBER_ID")
VERIFY_TOKEN = "grupo_ol_secreto"

MODELOS = ["gemini-3.5-flash", "gemini-3.8-flash", "gemini-flash-latest"]

INSTRUCCIONES = """Eres Luis Silva, técnico de soporte de TI de Grupo OL.
Atiendes por WhatsApp a empleados que no son técnicos. Problemas típicos:
PC lenta, Excel que se cuelga, PC que no enciende, impresoras, internet,
correo, contraseñas.

Reglas:
- Español, tono amable y directo. Saluda en una sola línea.
- Si el problema es ambiguo, haz UNA pregunta corta para entenderlo.
- Si es claro, da de 3 a 5 pasos numerados, simples y seguros.
- Formato WhatsApp: solo *negrita* con un asterisco. NO uses #, ### ni ---.
- Máximo 800 caracteres.
- No pidas contraseñas ni comandos peligrosos.
- Si hay riesgo (olor a quemado, pérdida de datos, pantalla azul repetida),
  indica que contacte al área de TI.
- Termina con una pregunta corta de seguimiento."""

lock = threading.Lock()
procesados = set()                              # ids ya atendidos
historiales = defaultdict(lambda: deque(maxlen=6))  # últimos 6 mensajes por número


def enviar_whatsapp(numero, texto):
    url = f"https://graph.facebook.com/v21.0/{PHONE_NUMBER_ID}/messages"
    headers = {
        "Authorization": f"Bearer {WHATSAPP_TOKEN}",
        "Content-Type": "application/json",
    }
    payload = {
        "messaging_product": "whatsapp",
        "to": numero,
        "type": "text",
        "text": {"body": texto},
    }
    r = requests.post(url, json=payload, headers=headers, timeout=15)
    print("RESPUESTA DE WHATSAPP:", r.status_code, flush=True)
    if r.status_code != 200:
        print(r.text, flush=True)


def generar_respuesta(numero, texto_usuario):
    config = types.GenerateContentConfig(
        system_instruction=INSTRUCCIONES,
        max_output_tokens=3000,   # antes 600: el razonamiento también consume tokens
        temperature=0.4,
    )

    with lock:
        contenido = list(historiales[numero])
    contenido.append({"role": "user", "parts": [{"text": texto_usuario}]})

    ultimo_error = None
    for nombre in MODELOS:
        try:
            print("PROBANDO MODELO:", nombre, flush=True)
            r = client.models.generate_content(
                model=nombre, contents=contenido, config=config
            )
            texto = r.text
            if not texto:
                raise ValueError("Respuesta vacía")
            try:
                print("FIN:", r.candidates[0].finish_reason, flush=True)
            except Exception:
                pass
            print("MODELO USADO:", nombre, flush=True)

            with lock:
                historiales[numero].append(
                    {"role": "user", "parts": [{"text": texto_usuario}]}
                )
                historiales[numero].append(
                    {"role": "model", "parts": [{"text": texto}]}
                )
            return texto
        except Exception as ex:
            print(f"FALLO MODELO {nombre}:", str(ex), flush=True)
            ultimo_error = ex
    raise ultimo_error


def atender_mensaje(numero, texto):
    try:
        enviar_whatsapp(numero, "⏳ Un momento, estoy analizando tu problema...")
        respuesta = generar_respuesta(numero, texto)[:4000]
        enviar_whatsapp(numero, respuesta)
    except Exception as ex:
        print("ERROR AL ATENDER:", str(ex), flush=True)
        try:
            enviar_whatsapp(
                numero,
                "Disculpa, tuve un problema técnico. Intenta de nuevo en un momento 🙏",
            )
        except Exception:
            pass


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

        for e in data.get("entry", []):
            for c in e.get("changes", []):
                value = c.get("value", {})
                for msg in value.get("messages", []):
                    msg_id = msg.get("id")
                    numero = msg.get("from", "")
                    texto = msg.get("text", {}).get("body", "")

                    if not (texto and numero):
                        continue
                    with lock:
                        if msg_id in procesados:
                            continue
                        procesados.add(msg_id)
                    print("MENSAJE RECIBIDO:", numero, texto, flush=True)

                    threading.Thread(
                        target=atender_mensaje, args=(numero, texto), daemon=True
                    ).start()
    except Exception as ex:
        print("ERROR:", str(ex), flush=True)

    return jsonify({"status": "received"}), 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
