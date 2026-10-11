import os
import time
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

CORREO_CONTACTO = "TU_CORREO@empresa.com"   # <-- cámbialo por tu correo real

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

PAUSA_SEGUNDOS = 2 * 60 * 60   # 2 horas sin IA cuando tú intervienes

lock = threading.Lock()
procesados = set()                                   # ids ya atendidos
historiales = defaultdict(lambda: deque(maxlen=6))   # últimos 6 mensajes por número
pausados = {}                                        # numero -> hora hasta la que está pausada la IA
ultimo_envio_bot = {}                                # numero -> hora del último envío del bot


def esta_pausado(numero):
    with lock:
        hasta = pausados.get(numero)
    return bool(hasta and time.time() < hasta)


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
    with lock:
        ultimo_envio_bot[numero] = time.time()
    r = requests.post(url, json=payload, headers=headers, timeout=15)
    print("RESPUESTA DE WHATSAPP:", r.status_code, flush=True)
    if r.status_code != 200:
        print(r.text, flush=True)


def generar_respuesta(numero, texto_usuario):
    config = types.GenerateContentConfig(
        system_instruction=INSTRUCCIONES,
        max_output_tokens=3000,   # el razonamiento del modelo también consume tokens
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

        # Si tú intervienes mientras la IA pensaba, no se envía
        if esta_pausado(numero):
            print("PAUSADO, NO SE ENVÍA:", numero, flush=True)
            return

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


# ---------- Páginas requeridas por Meta ----------

PAGINA_BASE = """<!DOCTYPE html>
<html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{titulo}</title>
<style>body{{font-family:Arial,sans-serif;max-width:720px;margin:40px auto;
padding:0 16px;line-height:1.6;color:#222}}h1{{font-size:24px}}</style>
</head><body>{cuerpo}</body></html>"""


@app.route("/privacy", methods=["GET"])
def privacy():
    cuerpo = f"""
    <h1>Política de privacidad - Soporte TI Grupo OL</h1>
    <p><b>Qué datos recibimos:</b> los mensajes que envías por WhatsApp al
    número de soporte y tu número de teléfono.</p>
    <p><b>Para qué los usamos:</b> únicamente para brindarte soporte técnico.
    Los mensajes se procesan con un servicio de inteligencia artificial para
    generar respuestas.</p>
    <p><b>Con quién se comparten:</b> con los proveedores necesarios para que
    el servicio funcione: Meta (WhatsApp) y Google (procesamiento con IA).
    No vendemos tus datos.</p>
    <p><b>Conservación:</b> guardamos las conversaciones solo el tiempo
    necesario para dar soporte.</p>
    <p><b>Tus derechos:</b> puedes pedir que eliminemos tus datos. Mira
    <a href="/delete-data">cómo hacerlo</a>.</p>
    <p><b>Contacto:</b> Área de TI de Grupo OL - {CORREO_CONTACTO}</p>
    <p>Última actualización: octubre de 2026</p>"""
    return PAGINA_BASE.format(titulo="Política de privacidad", cuerpo=cuerpo), 200


@app.route("/delete-data", methods=["GET"])
def delete_data():
    cuerpo = f"""
    <h1>Eliminación de datos</h1>
    <p>Para solicitar que eliminemos tus datos (mensajes y número de
    teléfono), escribe a <b>{CORREO_CONTACTO}</b> indicando el número de
    WhatsApp desde el que nos escribiste.</p>
    <p>Atenderemos tu solicitud y la confirmaremos por el mismo medio.</p>"""
    return PAGINA_BASE.format(titulo="Eliminación de datos", cuerpo=cuerpo), 200


# ---------- Webhook de WhatsApp ----------

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
                campo = c.get("field")
                value = c.get("value", {})

                # Mensajes que TÚ escribes desde la app (coexistencia)
                if campo == "smb_message_echoes":
                    print("ECHO RECIBIDO:", value, flush=True)
                    for m in value.get("message_echoes", []):
                        cliente = m.get("to", "")
                        texto_echo = (m.get("text", {}).get("body", "") or "").strip().lower()
                        with lock:
                            reciente = time.time() - ultimo_envio_bot.get(cliente, 0) < 20
                            if texto_echo == "/ia":
                                pausados.pop(cliente, None)
                                print("IA REACTIVADA:", cliente, flush=True)
                            elif reciente:
                                print("ECHO DEL PROPIO BOT, SE IGNORA:", cliente, flush=True)
                            else:
                                pausados[cliente] = time.time() + PAUSA_SEGUNDOS
                                print("HUMANO INTERVIENE, IA PAUSADA:", cliente, flush=True)
                    continue

                # Mensajes de clientes
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

                    if esta_pausado(numero):
                        print("IA PAUSADA, NO RESPONDE:", numero, flush=True)
                        continue

                    print("MENSAJE RECIBIDO:", numero, texto, flush=True)
                    threading.Thread(
                        target=atender_mensaje, args=(numero, texto), daemon=True
                    ).start()
    except Exception as ex:
        print("ERROR:", str(ex), flush=True)

    return jsonify({"status": "received"}), 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
