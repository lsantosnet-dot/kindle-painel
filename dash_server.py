#!/usr/bin/env python3
"""Painel para Kindle Paperwhite 3 (1072x1448): calendario, feriados e clima do dia de Belo Horizonte.

Sem hora no corpo do painel (so o rodape informa quando a imagem foi gerada).

Uso:
  python dash_server.py              -> sobe o servidor na porta 8000 (http://IP:8000/dash.png)
  python dash_server.py --preview    -> salva preview.png com dados reais e sai
  python dash_server.py --sample     -> salva preview.png com dados de exemplo (sem internet)

Requer: pip install pillow
"""
import io
import json
import os
import sys
import threading
import time
import urllib.request
import calendar
from datetime import date, datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from PIL import Image, ImageDraw, ImageFont

# ---------------- Configuracao ----------------
W, H = 1072, 1448
LAT, LON = -19.9167, -43.9345          # Belo Horizonte
CIDADE = "Belo Horizonte"
PORT = 8000
WEATHER_TTL = 10 * 60

try:
    from zoneinfo import ZoneInfo
    TZ = ZoneInfo("America/Sao_Paulo")
except Exception:  # Windows sem tzdata: Brasil nao usa horario de verao
    TZ = timezone(timedelta(hours=-3))

DIAS = ["segunda-feira", "terça-feira", "quarta-feira", "quinta-feira",
        "sexta-feira", "sábado", "domingo"]
DIAS_CURTO = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"]
MESES = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho",
         "agosto", "setembro", "outubro", "novembro", "dezembro"]

# codigo WMO -> (texto, tipo de icone)
WMO = {
    0: ("Céu limpo", "sun"), 1: ("Quase limpo", "sun"),
    2: ("Parcialmente nublado", "partly"), 3: ("Nublado", "cloud"),
    45: ("Neblina", "fog"), 48: ("Neblina", "fog"),
    51: ("Garoa fraca", "rain"), 53: ("Garoa", "rain"), 55: ("Garoa forte", "rain"),
    61: ("Chuva fraca", "rain"), 63: ("Chuva", "rain"), 65: ("Chuva forte", "rain"),
    66: ("Chuva gelada", "rain"), 67: ("Chuva gelada", "rain"),
    71: ("Neve", "cloud"), 73: ("Neve", "cloud"), 75: ("Neve", "cloud"),
    80: ("Pancadas de chuva", "rain"), 81: ("Pancadas de chuva", "rain"),
    82: ("Pancadas fortes", "storm"),
    95: ("Tempestade", "storm"), 96: ("Tempestade", "storm"), 99: ("Tempestade", "storm"),
}


def wmo(code):
    return WMO.get(code, ("—", "cloud"))


# ---------------- Fontes ----------------
FONT_DIRS = [
    "", "C:/Windows/Fonts/", "/usr/share/fonts/truetype/dejavu/",
    "/usr/share/fonts/truetype/liberation/", "/Library/Fonts/",
    "/System/Library/Fonts/Supplemental/",
]
REGULAR = ["arial.ttf", "DejaVuSans.ttf", "LiberationSans-Regular.ttf", "Arial.ttf"]
BOLD = ["arialbd.ttf", "DejaVuSans-Bold.ttf", "LiberationSans-Bold.ttf", "Arial Bold.ttf"]
_cache = {}


def font(size, bold=False):
    key = (size, bold)
    if key in _cache:
        return _cache[key]
    for d in FONT_DIRS:
        for name in (BOLD if bold else REGULAR):
            try:
                f = ImageFont.truetype(d + name, size)
                _cache[key] = f
                return f
            except OSError:
                continue
    f = ImageFont.load_default()
    _cache[key] = f
    return f


# ---------------- Dados ----------------
def http_get(url, timeout=12):
    req = urllib.request.Request(url, headers={"User-Agent": "kindle-dash/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def fetch_weather():
    url = (
        "https://api.open-meteo.com/v1/forecast?latitude=%s&longitude=%s"
        "&current=temperature_2m"
        "&daily=weather_code,temperature_2m_max,temperature_2m_min,"
        "precipitation_probability_max,sunrise,sunset"
        "&timezone=America%%2FSao_Paulo&forecast_days=1" % (LAT, LON)
    )
    return json.loads(http_get(url).decode("utf-8"))


SAMPLE_WEATHER = {
    "current": {"temperature_2m": 24.3},
    "daily": {
        "time": ["2026-11-08"],
        "weather_code": [2],
        "temperature_2m_max": [28.1],
        "temperature_2m_min": [17.5],
        "precipitation_probability_max": [20],
        "sunrise": ["2026-11-08T05:21"],
        "sunset": ["2026-11-08T18:09"],
    },
}

_state = {"weather": None, "w_time": 0}
_lock = threading.Lock()


def get_data(sample=False):
    if sample:
        return SAMPLE_WEATHER
    now = time.time()
    with _lock:
        if _state["weather"] is None or now - _state["w_time"] > WEATHER_TTL:
            try:
                _state["weather"] = fetch_weather()
                _state["w_time"] = now
            except Exception as e:
                print("Falha no clima:", e)
        return _state["weather"]


# ---------------- Feriados nacionais ----------------
def easter(y):
    a = y % 19
    b, c = divmod(y, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    mo, da = divmod(h + l - 7 * m + 114, 31)
    return date(y, mo, da + 1)


def feriados(y):
    p = easter(y)
    return {
        date(y, 1, 1): "Confraternização Universal", date(y, 4, 21): "Tiradentes",
        date(y, 5, 1): "Dia do Trabalho", date(y, 9, 7): "Independência",
        date(y, 10, 12): "N. Sra. Aparecida", date(y, 11, 2): "Finados",
        date(y, 11, 15): "Proclamação da República", date(y, 11, 20): "Consciência Negra",
        date(y, 12, 25): "Natal", p - timedelta(48): "Carnaval", p - timedelta(47): "Carnaval",
        p - timedelta(2): "Sexta-feira Santa", p + timedelta(60): "Corpus Christi",
    }


def proximo_feriado(hoje):
    cand = {**feriados(hoje.year), **feriados(hoje.year + 1)}
    for dt in sorted(cand):
        if dt >= hoje:
            return dt, cand[dt]


# ---------------- Desenho ----------------
def txt(d, xy, s, f=None, fill=0, font=None):
    d.text(xy, s, font=f or font, fill=fill)


def text_w(d, s, f):
    return d.textlength(s, font=f)


def centered(d, y, s, f, fill=0, cx=W // 2):
    d.text((cx - text_w(d, s, f) / 2, y), s, font=f, fill=fill)


def wrap(d, s, f, max_w):
    words, lines, cur = s.split(), [], ""
    for w in words:
        t = (cur + " " + w).strip()
        if text_w(d, t, f) <= max_w:
            cur = t
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def icon(d, kind, cx, cy, s):
    """Icone simples em tons de cinza; s = tamanho aproximado."""
    r = s // 2

    def cloud(x, y, k=1.0):
        rr = int(r * k)
        d.ellipse([x - rr, y - rr // 2, x, y + rr // 2 + rr // 3], fill=60)
        d.ellipse([x - rr // 2 - rr // 3, y - rr, x + rr // 2, y + rr // 3], fill=60)
        d.ellipse([x, y - rr // 2, x + rr, y + rr // 2 + rr // 3], fill=60)
        d.rectangle([x - rr // 2, y, x + rr // 2, y + rr // 2 + rr // 3], fill=60)

    if kind == "sun":
        d.ellipse([cx - r // 2, cy - r // 2, cx + r // 2, cy + r // 2], fill=0)
        import math
        for i in range(8):
            a = i * math.pi / 4
            d.line([cx + math.cos(a) * r * 0.7, cy + math.sin(a) * r * 0.7,
                    cx + math.cos(a) * r * 1.0, cy + math.sin(a) * r * 1.0],
                   fill=0, width=max(3, s // 14))
    elif kind == "partly":
        d.ellipse([cx - r, cy - r, cx - r // 8, cy - r // 8 * 1 + r // 2], fill=150)
        cloud(cx, cy + r // 4, 0.8)
    elif kind == "fog":
        for i in range(4):
            y = cy - r // 2 + i * (r // 2)
            d.line([cx - r, y, cx + r, y], fill=90, width=max(4, s // 12))
    else:
        cloud(cx, cy - r // 4, 0.85)
        if kind == "rain":
            for i in range(4):
                x = cx - r // 2 + i * (r // 3)
                d.line([x, cy + r // 2, x - r // 5, cy + r], fill=0, width=max(3, s // 16))
        elif kind == "storm":
            pts = [(cx, cy + r // 5), (cx - r // 4, cy + r // 1.8),
                   (cx, cy + r // 1.8), (cx - r // 4, cy + r * 1.05)]
            d.line(pts, fill=0, width=max(4, s // 12), joint="curve")


def render(weather, battery=None, now=None):
    now = now or datetime.now(TZ)
    hoje = now.date()
    img = Image.new("L", (W, H), 255)
    d = ImageDraw.Draw(img)
    pad = 56

    # --- Mes, dia e dia da semana ---
    centered(d, 40, MESES[hoje.month - 1].upper() + " " + str(hoje.year), font(40, True), fill=90)
    centered(d, 70, str(hoje.day), font(330, True))
    centered(d, 450, DIAS[hoje.weekday()].capitalize(), font(70, True))
    d.line([pad, 550, W - pad, 550], fill=0, width=4)

    # --- Mini calendario (domingo primeiro) ---
    top = 570
    cw = (W - 2 * pad) // 7
    ch = 58
    for i, s in enumerate(["D", "S", "T", "Q", "Q", "S", "S"]):
        centered(d, top, s, font(30, True), fill=90, cx=pad + cw * i + cw // 2)
    fer = feriados(hoje.year)
    for r, sem in enumerate(calendar.Calendar(firstweekday=6).monthdayscalendar(hoje.year, hoje.month)):
        for i, n in enumerate(sem):
            if not n:
                continue
            cx = pad + cw * i + cw // 2
            cy = top + 52 + r * ch
            eh_fer = date(hoje.year, hoje.month, n) in fer
            if n == hoje.day:
                d.rounded_rectangle([cx - 32, cy - 4, cx + 32, cy + 50], 10, fill=0)
                centered(d, cy, str(n), font(36, True), fill=255, cx=cx)
            else:
                centered(d, cy, str(n), font(36, eh_fer), fill=150 if i in (0, 6) else 0, cx=cx)
                if eh_fer:
                    d.ellipse([cx - 4, cy + 44, cx + 4, cy + 52], fill=0)
    yb = top + 52 + 6 * ch + 5
    d.line([pad, yb, W - pad, yb], fill=170, width=2)

    # --- Semana, dia do ano, proximo feriado ---
    txt(d, (pad, yb + 20), "Semana %d  ·  Dia %d do ano" % (hoje.isocalendar()[1],
        hoje.timetuple().tm_yday), font(34), fill=40)
    dt, nome = proximo_feriado(hoje)
    falta = (dt - hoje).days
    txt(d, (pad, yb + 66), "Próximo feriado: %s" % nome, font(34, True))
    quando = "hoje!" if falta == 0 else ("amanhã" if falta == 1 else "em %d dias" % falta)
    txt(d, (pad, yb + 110), "%s, %d/%d — %s" % (DIAS_CURTO[dt.weekday()], dt.day, dt.month, quando),
        font(34), fill=40)

    # --- Clima do dia ---
    yc = yb + 165
    d.line([pad, yc, W - pad, yc], fill=0, width=4)
    if weather:
        dly = weather["daily"]
        desc, kind = wmo(dly["weather_code"][0])
        icon(d, kind, pad + 80, yc + 100, 120)
        txt(d, (pad + 190, yc + 38), CIDADE, font(28, True), fill=90)
        txt(d, (pad + 190, yc + 76), desc, font(40, True))
        txt(d, (pad + 190, yc + 128), "máx %d°  ·  mín %d°  ·  chuva %d%%" % (
            round(dly["temperature_2m_max"][0]), round(dly["temperature_2m_min"][0]),
            dly["precipitation_probability_max"][0]), font(34), fill=40)
        cur = (weather.get("current") or {}).get("temperature_2m")
        if cur is not None:
            right = W - pad
            d.text((right, yc + 36), "AGORA", font=font(26, True), fill=90, anchor="ra")
            d.text((right, yc + 62), "%d°" % round(cur), font=font(84, True), anchor="ra")
        txt(d, (pad + 190, yc + 176), "Nascer do sol %s   ·   Pôr do sol %s" % (
            dly["sunrise"][0][-5:], dly["sunset"][0][-5:]), font(34), fill=40)
    else:
        txt(d, (pad, yc + 60), "Sem dados de clima", font(44), fill=90)

    # --- Rodape ---
    footer_y = H - 70
    rod = "Última atualização: %s" % now.strftime("%d/%m/%Y %H:%M")
    if battery:
        rod += "   ·   Bateria %s%%" % battery
    d.line([pad, footer_y, W - pad, footer_y], fill=170, width=2)
    txt(d, (pad, footer_y + 16), rod, font(28), fill=90)
    return img


def png_bytes(img):
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path.split("?")[0] not in ("/dash.png", "/"):
            self.send_error(404)
            return
        battery = self.headers.get("X-Kindle-Battery")
        data = png_bytes(render(get_data(), battery))
        self.send_response(200)
        self.send_header("Content-Type", "image/png")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)
        print("%s servido para %s (bateria=%s)" %
              (datetime.now(TZ).strftime("%H:%M:%S"), self.client_address[0], battery))

    def log_message(self, *a):
        pass


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    if "--out" in sys.argv:  # modo GitHub Actions: gera o arquivo e sai
        out = sys.argv[sys.argv.index("--out") + 1]
        os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
        render(get_data()).save(out)
        print("Salvo:", out)
        return
    if "--sample" in sys.argv or "--preview" in sys.argv:
        sample = "--sample" in sys.argv
        out = os.path.join(here, "preview.png")
        render(get_data(sample), battery="87").save(out)
        print("Salvo:", out)
        return
    print("Servidor no ar. Teste no navegador: http://localhost:%d/dash.png" % PORT)
    print("Deixe esta janela aberta. Para parar: Ctrl+C")
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
