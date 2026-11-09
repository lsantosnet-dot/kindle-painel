#!/usr/bin/env python3
"""Gera 3 prototipos de painel SEM hora (so conteudo que nao envelhece em horas).
Uso: python prototipos/prototipos.py   -> salva A_calendario.png, B_clima_do_dia.png, C_zen.png
Usa dados de exemplo (sample) e a data de hoje.
"""
import calendar, math, os, sys
from datetime import date, datetime, timedelta
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from PIL import Image, ImageDraw
from dash_server import (W, H, font, txt, text_w, centered, wrap, icon, wmo, DIAS,
                         DIAS_CURTO, MESES, SAMPLE_WEATHER, SAMPLE_NEWS, CIDADE, TZ)

PAD = 56
OUT = os.path.dirname(os.path.abspath(__file__))

# ---------- dados "que nao envelhecem" ----------
def easter(y):
    a = y % 19; b, c = divmod(y, 100); d, e = divmod(b, 4)
    f = (b + 8) // 25; g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30; i, k = divmod(c, 4)
    l = (32 + 2 * e + 2 * i - h - k) % 7; m = (a + 11 * h + 22 * l) // 451
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

SYNODIC = 29.530588853
def lua(hoje):
    """fase 0..1 (0=nova, .5=cheia) e iluminacao"""
    ref = datetime(2000, 1, 6, 18, 14)
    dias = (datetime(hoje.year, hoje.month, hoje.day, 12) - ref).total_seconds() / 86400
    f = (dias / SYNODIC) % 1
    return f, (1 - math.cos(2 * math.pi * f)) / 2

def nome_fase(f):
    n = ["Lua nova", "Crescente", "Quarto crescente", "Crescente gibosa", "Lua cheia",
         "Minguante gibosa", "Quarto minguante", "Minguante"]
    return n[int((f * 8) + 0.5) % 8]

def desenha_lua(d, cx, cy, r, f):
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=225, outline=0, width=3)
    # parte escura: pixel a pixel por linha
    k = math.cos(2 * math.pi * f)   # 1 nova ... -1 cheia
    crescente = f < 0.5
    for yy in range(-r, r + 1):
        half = int(math.sqrt(max(r * r - yy * yy, 0)))
        t = int(half * k)           # posicao do terminador
        if crescente:   # iluminada a direita; escura = esquerda do terminador
            x0, x1 = -half, t if k >= 0 else -half
            if k < 0: x0, x1 = -half, t
            d.line([cx + x0, cy + yy, cx + x1, cy + yy], fill=70)
        else:           # iluminada a esquerda; escura = direita
            x0, x1 = (-t if k >= 0 else half), half
            if k < 0: x0, x1 = -t, half
            d.line([cx + x0, cy + yy, cx + x1, cy + yy], fill=70)
    d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=0, width=3)

FRASES = [
    ("O segredo de ir em frente é começar.", "Mark Twain"),
    ("Pequenos passos todos os dias levam longe.", "Provérbio"),
    ("Quem tem um porquê enfrenta qualquer como.", "Nietzsche"),
    ("A imaginação é mais importante que o conhecimento.", "Albert Einstein"),
    ("Feito é melhor que perfeito.", "Sheryl Sandberg"),
]
def frase(hoje):
    return FRASES[hoje.toordinal() % len(FRASES)]

# sample extra (viria do Open-Meteo: sunrise, sunset, uv_index_max, hourly)
EXTRA = {"nascer": "05:21", "por": "18:09", "uv": 11, "periodos": [
    ("Manhã", 21, 10), ("Tarde", 27, 60), ("Noite", 22, 30)]}

def base(hoje):
    img = Image.new("L", (W, H), 255)
    return img, ImageDraw.Draw(img)

def rodape(d, hoje, extra=""):
    y = H - 70
    d.line([PAD, y, W - PAD, y], fill=170, width=2)
    agora = datetime.now(TZ)
    txt(d, (PAD, y + 16), "Última atualização: %s%s" % (agora.strftime("%d/%m/%Y %H:%M"), extra),
        font(28), fill=90)

def clima_hoje(w):
    c, dly = w["current"], w["daily"]
    desc, kind = wmo(dly["weather_code"][0])  # indice 0 = hoje
    return desc, kind, round(dly["temperature_2m_max"][0]), round(dly["temperature_2m_min"][0]), dly["precipitation_probability_max"][0]

# ---------- A: Calendario ----------
def proto_a(hoje, w):
    img, d = base(hoje)
    centered(d, 40, MESES[hoje.month - 1].upper() + " " + str(hoje.year), font(40, True), fill=90)
    centered(d, 70, str(hoje.day), font(330, True))
    centered(d, 450, DIAS[hoje.weekday()].capitalize(), font(70, True))
    d.line([PAD, 550, W - PAD, 550], fill=0, width=4)
    # mini calendario
    calendar.setfirstweekday(6)
    top = 570; cw = (W - 2 * PAD) // 7; ch = 58
    for i, s in enumerate(["D", "S", "T", "Q", "Q", "S", "S"]):
        centered(d, top, s, font(30, True), fill=90, cx=PAD + cw * i + cw // 2)
    fer = feriados(hoje.year)
    for r, sem in enumerate(calendar.monthcalendar(hoje.year, hoje.month)):
        for i, n in enumerate(sem):
            if not n: continue
            cx = PAD + cw * i + cw // 2; cy = top + 52 + r * ch
            if n == hoje.day:
                d.rounded_rectangle([cx - 32, cy - 4, cx + 32, cy + 50], 10, fill=0)
                centered(d, cy, str(n), font(36, True), fill=255, cx=cx)
            else:
                f_ = 150 if i in (0, 6) else 0
                centered(d, cy, str(n), font(36, date(hoje.year, hoje.month, n) in fer and True), fill=f_, cx=cx)
                if date(hoje.year, hoje.month, n) in fer:
                    d.ellipse([cx - 4, cy + 44, cx + 4, cy + 52], fill=0)
    yb = top + 52 + 6 * ch + 5
    d.line([PAD, yb, W - PAD, yb], fill=170, width=2)
    # linha de info
    sem = hoje.isocalendar()[1]; doa = hoje.timetuple().tm_yday
    dt, nome = proximo_feriado(hoje)
    falta = (dt - hoje).days
    txt(d, (PAD, yb + 20), "Semana %d  ·  Dia %d do ano" % (sem, doa), font(34), fill=40)
    txt(d, (PAD, yb + 66), "Próximo feriado: %s" % nome, font(34, True))
    txt(d, (PAD, yb + 110), "%s, %d/%d — %s" % (DIAS_CURTO[dt.weekday()], dt.day, dt.month,
        "hoje!" if falta == 0 else ("amanhã" if falta == 1 else "em %d dias" % falta)), font(34), fill=40)
    # clima do dia
    yc = yb + 165
    d.line([PAD, yc, W - PAD, yc], fill=0, width=4)
    desc, kind, mx, mn, ch_ = clima_hoje(w)
    icon(d, kind, PAD + 80, yc + 100, 120)
    txt(d, (PAD + 190, yc + 38), "%s" % CIDADE, font(28, True), fill=90)
    txt(d, (PAD + 190, yc + 76), desc, font(40, True))
    txt(d, (PAD + 190, yc + 128), "máx %d°  ·  mín %d°  ·  chuva %d%%" % (mx, mn, ch_), font(34), fill=40)
    txt(d, (PAD + 190, yc + 176), "Nascer do sol %s   ·   Pôr do sol %s" % (EXTRA["nascer"], EXTRA["por"]), font(34), fill=40)
    rodape(d, hoje)
    return img

# ---------- B: Clima do dia ----------
def proto_b(hoje, w):
    img, d = base(hoje)
    txt(d, (PAD, 40), DIAS[hoje.weekday()].upper(), font(54, True))
    txt(d, (PAD, 105), "%d de %s de %d" % (hoje.day, MESES[hoje.month - 1], hoje.year), font(40), fill=60)
    centered(d, 20, str(hoje.day), font(220, True), cx=W - PAD - 150)
    d.line([PAD, 290, W - PAD, 290], fill=0, width=4)
    desc, kind, mx, mn, chv = clima_hoje(w)
    txt(d, (PAD, 310), CIDADE.upper() + " · HOJE", font(30, True), fill=90)
    icon(d, kind, PAD + 130, 520, 230)
    txt(d, (PAD + 290, 390), "%d°" % mx, font(200, True))
    txt(d, (PAD + 690, 410), "mín %d°" % mn, font(46), fill=60)
    txt(d, (PAD + 690, 480), "chuva %d%%" % chv, font(46), fill=60)
    centered(d, 640, desc, font(52, True))
    # periodos do dia
    y = 740; cw = (W - 2 * PAD) // 3
    d.line([PAD, y - 12, W - PAD, y - 12], fill=170, width=2)
    for i, (nome, t, p) in enumerate(EXTRA["periodos"]):
        cx = PAD + cw * i + cw // 2
        centered(d, y, nome.upper(), font(30, True), fill=90, cx=cx)
        centered(d, y + 44, "%d°" % t, font(86, True), cx=cx)
        # barrinha de chuva
        d.rectangle([cx - 70, y + 160, cx + 70, y + 176], outline=0, width=2)
        d.rectangle([cx - 70, y + 160, cx - 70 + 140 * p // 100, y + 176], fill=0)
        centered(d, y + 184, "chuva %d%%" % p, font(28), fill=70, cx=cx)
    # sol, UV
    y = 990
    d.line([PAD, y, W - PAD, y], fill=0, width=4)
    for i, (rot, val) in enumerate([("NASCER DO SOL", EXTRA["nascer"]), ("PÔR DO SOL", EXTRA["por"]),
                                    ("ÍNDICE UV", "%d  extremo" % EXTRA["uv"])]):
        x = PAD + (W - 2 * PAD) // 3 * i
        txt(d, (x, y + 22), rot, font(26, True), fill=90)
        txt(d, (x, y + 60), val, font(44, True) if i < 2 else font(40, True))
    # proximos dias
    y = 1130
    d.line([PAD, y, W - PAD, y], fill=170, width=2)
    daily = w["daily"]
    for i in range(1, 3):
        cx = PAD + (W - 2 * PAD) // 2 * (i - 1) + (W - 2 * PAD) // 4
        dt = datetime.strptime(daily["time"][i], "%Y-%m-%d")
        centered(d, y + 24, DIAS[dt.weekday()].capitalize(), font(34, True), cx=cx)
        icon(d, wmo(daily["weather_code"][i])[1], cx - 130, y + 140, 90)
        centered(d, y + 100, "%d° / %d°" % (round(daily["temperature_2m_max"][i]), round(daily["temperature_2m_min"][i])), font(40), cx=cx + 60)
        centered(d, y + 152, "chuva %d%%" % daily["precipitation_probability_max"][i], font(28), fill=70, cx=cx + 60)
    rodape(d, hoje)
    return img

# ---------- C: Zen ----------
def proto_c(hoje, w):
    img, d = base(hoje)
    centered(d, 60, DIAS[hoje.weekday()].upper(), font(60, True), fill=70)
    centered(d, 130, str(hoje.day), font(380, True))
    centered(d, 560, "de %s de %d" % (MESES[hoje.month - 1], hoje.year), font(52))
    d.line([W // 2 - 60, 650, W // 2 + 60, 650], fill=0, width=4)
    desc, kind, mx, mn, chv = clima_hoje(w)
    icon(d, kind, W // 2 - 250, 760, 130)
    txt(d, (W // 2 - 150, 715), "%d°" % mx, font(100, True))
    txt(d, (W // 2 + 60, 722), desc, font(36, True))
    txt(d, (W // 2 + 60, 770), "mín %d° · chuva %d%%" % (mn, chv), font(32), fill=60)
    # lua + sol
    f, ilum = lua(hoje)
    desenha_lua(d, W // 2 - 280, 1010, 70, f)
    txt(d, (W // 2 - 180, 960), nome_fase(f), font(40, True))
    txt(d, (W // 2 - 180, 1010), "%d%% iluminada" % round(ilum * 100), font(32), fill=60)
    txt(d, (W // 2 - 180, 1055), "☀ %s – %s" % (EXTRA["nascer"], EXTRA["por"]), font(32), fill=60)
    # frase
    d.line([PAD, 1150, W - PAD, 1150], fill=170, width=2)
    q, a = frase(hoje)
    ys = 1185
    for ln in wrap(d, "“%s”" % q, font(44), W - 2 * PAD - 60):
        centered(d, ys, ln, font(44)); ys += 56
    centered(d, ys + 6, "— " + a, font(30), fill=90)
    rodape(d, hoje)
    return img

if __name__ == "__main__":
    hoje = datetime.now(TZ).date()
    for nome, fn in [("A_calendario", proto_a), ("B_clima_do_dia", proto_b), ("C_zen", proto_c)]:
        p = os.path.join(OUT, nome + ".png")
        fn(hoje, SAMPLE_WEATHER).save(p); print("Salvo:", p)
