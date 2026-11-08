#!/usr/bin/env python3
"""Painel para Kindle Paperwhite 3 (1072x1448): hora, clima de Belo Horizonte e manchetes.

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
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from PIL import Image, ImageDraw, ImageFont

# ---------------- Configuracao ----------------
W, H = 1072, 1448
LAT, LON = -19.9167, -43.9345          # Belo Horizonte
CIDADE = "Belo Horizonte"
PORT = 8000
NEWS_FEEDS = [
    "https://g1.globo.com/rss/g1/minas-gerais/",
    "https://g1.globo.com/rss/g1/",
]
MAX_NEWS = 6
WEATHER_TTL = 10 * 60
NEWS_TTL = 15 * 60

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
        "&current=temperature_2m,apparent_temperature,relative_humidity_2m,"
        "weather_code,wind_speed_10m"
        "&daily=weather_code,temperature_2m_max,temperature_2m_min,"
        "precipitation_probability_max"
        "&timezone=America%%2FSao_Paulo&forecast_days=4" % (LAT, LON)
    )
    return json.loads(http_get(url).decode("utf-8"))


def fetch_news():
    for feed in NEWS_FEEDS:
        try:
            root = ET.fromstring(http_get(feed))
            titles = []
            for item in root.iter("item"):
                t = (item.findtext("title") or "").strip()
                if t and t not in titles:
                    titles.append(t)
                if len(titles) >= MAX_NEWS:
                    break
            if titles:
                return titles
        except Exception as e:
            print("Falha no feed", feed, e)
    return []


SAMPLE_WEATHER = {
    "current": {"temperature_2m": 24.3, "apparent_temperature": 25.1,
                "relative_humidity_2m": 62, "weather_code": 2, "wind_speed_10m": 11.4},
    "daily": {
        "time": ["2026-11-08", "2026-11-09", "2026-11-10", "2026-11-11"],
        "weather_code": [2, 63, 95, 1],
        "temperature_2m_max": [28.1, 26.0, 25.2, 29.4],
        "temperature_2m_min": [17.5, 18.1, 18.9, 17.0],
        "precipitation_probability_max": [20, 80, 90, 10],
    },
}
SAMPLE_NEWS = [
    "Prefeitura anuncia novo esquema de trânsito na Avenida do Contorno durante obras",
    "Chuva forte deve atingir a Região Metropolitana de BH na segunda-feira",
    "Atlético-MG vence no Mineirão e se aproxima da zona de classificação",
    "Governo de Minas divulga calendário de pagamento do funcionalismo",
    "Aeroporto de Confins registra recorde de passageiros no mês",
    "Feira de artesanato reúne mais de 300 expositores na Praça da Liberdade",
]

_state = {"weather": None, "w_time": 0, "news": None, "n_time": 0}
_lock = threading.Lock()


def get_data(sample=False):
    if sample:
        return SAMPLE_WEATHER, SAMPLE_NEWS
    now = time.time()
    with _lock:
        if _state["weather"] is None or now - _state["w_time"] > WEATHER_TTL:
            try:
                _state["weather"] = fetch_weather()
                _state["w_time"] = now
            except Exception as e:
                print("Falha no clima:", e)
        if _state["news"] is None or now - _state["n_time"] > NEWS_TTL:
            try:
                n = fetch_news()
                if n:
                    _state["news"] = n
                    _state["n_time"] = now
            except Exception as e:
                print("Falha nas notícias:", e)
        return _state["weather"], _state["news"]


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


def render(weather, news, battery=None, now=None):
    now = now or datetime.now(TZ)
    img = Image.new("L", (W, H), 255)
    d = ImageDraw.Draw(img)
    pad = 56

    # --- Data + hora ---
    data = "%s, %d de %s" % (DIAS[now.weekday()].capitalize(), now.day, MESES[now.month - 1])
    centered(d, 36, data, font(42))
    centered(d, 84, now.strftime("%H:%M"), font(270, True))
    d.line([pad, 400, W - pad, 400], fill=0, width=4)

    # --- Clima atual ---
    y0 = 420
    txt(d, (pad, y0), CIDADE.upper(), font(30, True), fill=90)
    if weather:
        cur = weather["current"]
        desc, kind = wmo(cur["weather_code"])
        icon(d, kind, pad + 110, y0 + 165, 180)
        temp = "%d°" % round(cur["temperature_2m"])
        txt(d, (pad + 240, y0 + 50), temp, font(170, True), fill=0)
        dl = wrap(d, desc, font(34, True), W - pad - (pad + 600))
        for k, ln in enumerate(dl[:2]):
            txt(d, (pad + 600, y0 + 55 + k * 40), ln, font(34, True), fill=0)
        yy = y0 + 55 + len(dl[:2]) * 40 + 8
        txt(d, (pad + 600, yy),
               "Sensação %d°" % round(cur["apparent_temperature"]), font(32), fill=40)
        txt(d, (pad + 600, yy + 42),
               "Umidade %d%%" % round(cur["relative_humidity_2m"]), font(34), fill=40)
        txt(d, (pad + 600, yy + 84),
               "Vento %d km/h" % round(cur["wind_speed_10m"]), font(34), fill=40)

        # previsao 3 dias
        daily = weather["daily"]
        colw = (W - 2 * pad) // 3
        ytop = y0 + 290
        d.line([pad, ytop - 12, W - pad, ytop - 12], fill=170, width=2)
        for i in range(1, 4):
            if i >= len(daily["time"]):
                break
            dt = datetime.strptime(daily["time"][i], "%Y-%m-%d")
            cx = pad + colw * (i - 1) + colw // 2
            centered(d, ytop, DIAS_CURTO[dt.weekday()], font(34, True), cx=cx)
            icon(d, wmo(daily["weather_code"][i])[1], cx, ytop + 100, 90)
            centered(d, ytop + 160, "%d° / %d°" % (round(daily["temperature_2m_max"][i]),
                                                  round(daily["temperature_2m_min"][i])),
                     font(34), cx=cx)
            centered(d, ytop + 205, "chuva %d%%" % daily["precipitation_probability_max"][i],
                     font(28), fill=70, cx=cx)
        news_top = ytop + 250
    else:
        centered(d, y0 + 150, "Sem dados de clima", font(44), fill=90)
        news_top = y0 + 300

    # --- Manchetes ---
    d.line([pad, news_top, W - pad, news_top], fill=0, width=4)
    txt(d, (pad, news_top + 18), "MANCHETES", font(30, True), fill=90)
    y = news_top + 66
    footer_y = H - 70
    f = font(34)
    if news:
        for n in news:
            lines = wrap(d, n, f, W - 2 * pad - 30)[:3]
            block = len(lines) * 41 + 20
            if y + block > footer_y - 10:
                break
            d.ellipse([pad, y + 14, pad + 12, y + 26], fill=0)
            for ln in lines:
                txt(d, (pad + 30, y), ln, font=f, fill=0)
                y += 41
            y += 20
    else:
        txt(d, (pad, y), "Sem notícias no momento.", font=f, fill=90)

    # --- Rodape ---
    rod = "Atualizado às %s" % now.strftime("%H:%M")
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
        weather, news = get_data()
        data = png_bytes(render(weather, news, battery))
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
        weather, news = get_data()
        render(weather, news).save(out)
        print("Salvo:", out)
        return
    if "--sample" in sys.argv or "--preview" in sys.argv:
        sample = "--sample" in sys.argv
        weather, news = get_data(sample)
        out = os.path.join(here, "preview.png")
        render(weather, news, battery="87").save(out)
        print("Salvo:", out)
        return
    print("Servidor no ar. Teste no navegador: http://localhost:%d/dash.png" % PORT)
    print("Deixe esta janela aberta. Para parar: Ctrl+C")
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
