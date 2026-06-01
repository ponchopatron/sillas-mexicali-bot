import os
import json
import re
from datetime import datetime
from flask import Flask, request
import requests

TOKEN = os.environ.get("BOT_TOKEN", "")
CHAT_ID = os.environ.get("CHAT_ID", "")
DATA_FILE = "data.json"

app = Flask(__name__)

def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r") as f:
            return json.load(f)
    return {
        "inventario": [
            {"nombre": "Silla Blanca Tulip", "qty": 6, "precio": 750},
            {"nombre": "Silla Negra Tulip", "qty": 6, "precio": 750},
            {"nombre": "Silla Beige Tulip", "qty": 8, "precio": 750},
            {"nombre": "Silla Blanca Eames", "qty": 10, "precio": 500},
            {"nombre": "Silla Negra Eames", "qty": 3, "precio": 500},
            {"nombre": "Mesa Blanca Redonda 80cm", "qty": 2, "precio": 1500},
            {"nombre": "Mesa Negra Redonda 80cm", "qty": 2, "precio": 1500}
        ],
        "movimientos": [],
        "meta_mensual": 30000
    }

def save_data(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def send_message(chat_id, text):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    requests.post(url, json={"chat_id": chat_id, "text": text, "parse_mode": "Markdown"})

def fmt(n):
    return f"${n:,.0f}"

def hoy():
    return datetime.now().strftime("%Y-%m-%d")

def mes_actual():
    return datetime.now().strftime("%Y-%m")

def resumen(data):
    movs = data["movimientos"]
    mes = mes_actual()
    ventas_mes = sum(m["monto"] for m in movs if m["tipo"] == "venta" and m["fecha"].startswith(mes))
    gastos_mes = sum(m["monto"] for m in movs if m["tipo"] in ["compra", "gasto"] and m["fecha"].startswith(mes))
    ventas_hoy = sum(m["monto"] for m in movs if m["tipo"] == "venta" and m["fecha"] == hoy())
    meta = data["meta_mensual"]
    pct = int(ventas_mes / meta * 100) if meta > 0 else 0
    inv_total = sum(i["qty"] * i["precio"] for i in data["inventario"])
    inv_pzas = sum(i["qty"] for i in data["inventario"])
    bajos = [i for i in data["inventario"] if i["qty"] <= 2]
    txt = f"📊 *Resumen del negocio*\n\n"
    txt += f"🗓 *Hoy:* {fmt(ventas_hoy)}\n"
    txt += f"📅 *Ventas del mes:* {fmt(ventas_mes)}\n"
    txt += f"💸 *Gastos del mes:* {fmt(gastos_mes)}\n"
    txt += f"🎯 *Meta mensual:* {fmt(meta)} ({pct}% alcanzado)\n"
    txt += f"📦 *Inventario:* {fmt(inv_total)} ({inv_pzas} piezas)\n"
    if bajos:
        txt += f"\n⚠️ *Stock bajo:*\n"
        for b in bajos:
            txt += f"  · {b['nombre']}: {b['qty']} pzas\n"
    return txt

def inventario_txt(data):
    txt = "📦 *Inventario actual*\n\n"
    for i in data["inventario"]:
        alerta = " ⚠️" if i["qty"] <= 2 else ""
        txt += f"· {i['nombre']}: *{i['qty']} pzas* @ {fmt(i['precio'])}{alerta}\n"
    total = sum(i["qty"] * i["precio"] for i in data["inventario"])
    txt += f"\n*Total inventario: {fmt(total)}*"
    return txt

def ultimos_movimientos(data, n=5):
    movs = data["movimientos"]
    if not movs:
        return "No hay movimientos registrados aún."
    ultimos = movs[-n:][::-1]
    txt = f"🕐 *Últimos {len(ultimos)} movimientos*\n\n"
    for m in ultimos:
        emoji = "💰" if m["tipo"] == "venta" else "🛒" if m["tipo"] == "compra" else "💸" if m["tipo"] == "gasto" else "⏳"
        txt += f"{emoji} {m['desc']} — *{fmt(m['monto'])}*\n   {m['fecha']}\n"
    return txt

def ayuda():
    return """🤖 *Comandos disponibles*

*Registrar movimientos:*
`vendí 4 sillas negras $3000 transferencia`
`compré 6 sillas blancas $1785`
`gasto publicidad $300`
`anticipo cliente $1500`

*Consultar:*
`/resumen` — ventas del día y mes
`/inventario` — stock actual
`/historial` — últimos movimientos
`/meta 35000` — cambiar meta mensual

*Ajustar inventario:*
`/agregar Silla Rosa Tulip 4 700`
`/ajustar Silla Negra Tulip 8`"""

def parse_movimiento(texto, data):
    texto = texto.lower().strip()
    if any(texto.startswith(p) for p in ["vend", "vendí", "vendi", "venta"]):
        monto_match = re.search(r'\$?([\d,]+)', texto)
        if not monto_match:
            return None, "No entendí el monto. Ejemplo: `vendí 4 sillas negras $3000 transferencia`"
        monto = float(monto_match.group(1).replace(",", ""))
        pago = "efectivo"
        for p in ["transferencia", "transfer", "spei"]:
            if p in texto:
                pago = "transferencia"
                break
        for p in ["mercado pago", "mp", "link"]:
            if p in texto:
                pago = "mercado pago"
                break
        desc_raw = re.sub(r'\$[\d,]+', '', texto)
        desc_raw = re.sub(r'(vendí|vendi|venta|vend[ií])', '', desc_raw).strip()
        for item in data["inventario"]:
            nombre_lower = item["nombre"].lower()
            palabras = nombre_lower.split()
            if any(p in desc_raw for p in palabras if len(p) > 3):
                qty_match = re.search(r'(\d+)', desc_raw)
                qty = int(qty_match.group(1)) if qty_match else 1
                item["qty"] = max(0, item["qty"] - qty)
                break
        mov = {"tipo": "venta", "desc": texto.capitalize(), "monto": monto, "pago": pago, "fecha": hoy()}
        data["movimientos"].append(mov)
        save_data(data)
        return True, f"✅ *Venta registrada*\n💰 {fmt(monto)} — {pago}\n📅 {hoy()}"
    if any(texto.startswith(p) for p in ["compr", "compré", "compre"]):
        monto_match = re.search(r'\$?([\d,]+)', texto)
        if not monto_match:
            return None, "No entendí el monto. Ejemplo: `compré 6 sillas blancas $1785`"
        monto = float(monto_match.group(1).replace(",", ""))
        desc_raw = re.sub(r'\$[\d,]+', '', texto)
        desc_raw = re.sub(r'(compré|compre|compr[eé])', '', desc_raw).strip()
        for item in data["inventario"]:
            nombre_lower = item["nombre"].lower()
            palabras = nombre_lower.split()
            if any(p in desc_raw for p in palabras if len(p) > 3):
                qty_match = re.search(r'(\d+)', desc_raw)
                qty = int(qty_match.group(1)) if qty_match else 1
                item["qty"] += qty
                break
        mov = {"tipo": "compra", "desc": texto.capitalize(), "monto": monto, "pago": "", "fecha": hoy()}
        data["movimientos"].append(mov)
        save_data(data)
        return True, f"✅ *Compra registrada*\n🛒 {fmt(monto)}\n📅 {hoy()}"
    if any(texto.startswith(p) for p in ["gasto", "gasté", "gaste", "pagué", "pague"]):
        monto_match = re.search(r'\$?([\d,]+)', texto)
        if not monto_match:
            return None, "No entendí el monto. Ejemplo: `gasto publicidad $300`"
        monto = float(monto_match.group(1).replace(",", ""))
        mov = {"tipo": "gasto", "desc": texto.capitalize(), "monto": monto, "pago": "", "fecha": hoy()}
        data["movimientos"].append(mov)
        save_data(data)
        return True, f"✅ *Gasto registrado*\n💸 {fmt(monto)}\n📅 {hoy()}"
    if any(p in texto for p in ["anticipo", "seña", "sena", "adelanto"]):
        monto_match = re.search(r'\$?([\d,]+)', texto)
        if not monto_match:
            return None, "No entendí el monto. Ejemplo: `anticipo cliente $1500`"
        monto = float(monto_match.group(1).replace(",", ""))
        mov = {"tipo": "anticipo", "desc": texto.capitalize(), "monto": monto, "pago": "", "fecha": hoy()}
        data["movimientos"].append(mov)
        save_data(data)
        return True, f"✅ *Anticipo registrado*\n⏳ {fmt(monto)}\n📅 {hoy()}"
    return None, None

def handle_message(chat_id, texto):
    data = load_data()
    texto = texto.strip()
    if texto in ["/start", "/inicio", "hola", "start"]:
        send_message(chat_id, f"👋 Hola! Soy tu bot de *Sillas Mexicali*.\n\n{ayuda()}")
        return
    if texto in ["/resumen", "resumen"]:
        send_message(chat_id, resumen(data))
        return
    if texto in ["/inventario", "inventario"]:
        send_message(chat_id, inventario_txt(data))
        return
    if texto in ["/historial", "historial", "/movimientos"]:
        send_message(chat_id, ultimos_movimientos(data))
        return
    if texto in ["/ayuda", "/help", "ayuda"]:
        send_message(chat_id, ayuda())
        return
    if texto.startswith("/meta"):
        parts = texto.split()
        if len(parts) == 2 and parts[1].isdigit():
            data["meta_mensual"] = int(parts[1])
            save_data(data)
            send_message(chat_id, f"🎯 Meta mensual actualizada a *{fmt(int(parts[1]))}*")
        else:
            send_message(chat_id, "Formato: `/meta 35000`")
        return
    if texto.startswith("/agregar"):
        parts = texto.split()
        if len(parts) >= 4:
            qty = int(parts[-2]) if parts[-2].isdigit() else 1
            precio = int(parts[-1]) if parts[-1].isdigit() else 0
            nombre = " ".join(parts[1:-2])
            data["inventario"].append({"nombre": nombre, "qty": qty, "precio": precio})
            save_data(data)
            send_message(chat_id, f"✅ Producto agregado: *{nombre}* — {qty} pzas @ {fmt(precio)}")
        else:
            send_message(chat_id, "Formato: `/agregar Silla Rosa Tulip 4 700`")
        return
    if texto.startswith("/ajustar"):
        parts = texto.split()
        if len(parts) >= 3 and parts[-1].isdigit():
            qty = int(parts[-1])
            nombre_bus = " ".join(parts[1:-1]).lower()
            encontrado = False
            for item in data["inventario"]:
                if nombre_bus in item["nombre"].lower():
                    item["qty"] = qty
                    encontrado = True
                    send_message(chat_id, f"✅ Inventario ajustado: *{item['nombre']}* → {qty} pzas")
                    break
            if not encontrado:
                send_message(chat_id, f"No encontré '{nombre_bus}' en el inventario.")
            save_data(data)
        else:
            send_message(chat_id, "Formato: `/ajustar Silla Negra Tulip 8`")
        return
    ok, msg = parse_movimiento(texto, data)
    if msg:
        send_message(chat_id, msg)
        return
    send_message(chat_id, f"No entendí ese mensaje 🤔\n\nEscribe `/ayuda` para ver los comandos disponibles.")

@app.route(f"/{TOKEN}", methods=["POST"])
def webhook():
    data = request.json
    if "message" in data:
        chat_id = data["message"]["chat"]["id"]
        texto = data["message"].get("text", "")
        if texto:
            handle_message(str(chat_id), texto)
    return "ok"

@app.route("/")
def index():
    return "Bot Sillas Mexicali activo ✓"

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
