"""DMD Klinikasi — sayt + admin panel + baza (bitta loyiha).

Ishga tushirish:
    pip install -r requirements.txt
    python app.py
Sayt:  http://127.0.0.1:5000        Admin: http://127.0.0.1:5000/admin
"""
import json
import os
import re
import secrets
import sqlite3
import threading
import time
import urllib.parse
import urllib.request
from html import escape

from flask import Flask, Response, abort, jsonify, request, send_from_directory, session

BASE = os.path.dirname(os.path.abspath(__file__))
# DATA_DIR can point to a persistent disk in production.  It defaults to the
# project directory so local development keeps the existing behavior.
DATA_DIR = os.environ.get("DATA_DIR", BASE)
os.makedirs(DATA_DIR, exist_ok=True)
DB_FILE = os.path.join(DATA_DIR, "data.db")
STATIC = os.path.join(BASE, "static")

# ---- Sozlamalar (muhit o'zgaruvchilari orqali o'zgartiring) -------------
ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "admin@dmd.uz")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "admin123")  # ALBATTA O'ZGARTIRING!
TG_TOKEN = os.environ.get("TG_TOKEN", "")  # ixtiyoriy: Telegram bot tokeni
TG_CHAT = os.environ.get("TG_CHAT", "")    # ixtiyoriy: xabar boradigan chat ID

FIELDS = {
    "posts": ["title", "tur", "kat", "slug", "matn", "holat", "seot", "seod"],
    "xizmatlar": ["nomi", "tavsif", "vaqt"],
    "shifokorlar": ["ism", "mut", "yil", "holat"],
    "narxlar": ["xizmat", "narx"],
    "savollar": ["savol", "javob"],
    "arizalar": ["ism", "tel", "xizmat", "holat"],
}
REQUIRED = {
    "posts": ["title", "slug"], "xizmatlar": ["nomi"], "shifokorlar": ["ism", "mut"],
    "narxlar": ["xizmat", "narx"], "savollar": ["savol", "javob"], "arizalar": ["ism", "tel"],
}
CHOICES = {
    "posts": {"tur": ["Maqola", "Yangilik"], "holat": ["Qoralama", "Chop etilgan"]},
    "shifokorlar": {"holat": ["Faol", "Nofaol"]},
    "arizalar": {"holat": ["Yangi", "Bog\u02bblanildi", "Bekor qilindi"]},
}
LONG = ("matn", "javob", "tavsif")
SET_KEYS = ["tel", "manzil", "vaqt"]

SEED = {
    "posts": [{"title": "DMD klinikasida yangi UZI apparati ishga tushdi", "tur": "Yangilik", "kat": "Yangilik",
               "slug": "yangi-uzi-apparati", "holat": "Chop etilgan",
               "matn": "Bemorlarga yanada sifatli xizmat ko\u02bbrsatish maqsadida yangi avlod UZI apparati o\u02bbrnatildi.",
               "seot": "Yangi UZI apparati \u2014 DMD Klinikasi",
               "seod": "DMD klinikasida zamonaviy UZI apparati ishga tushdi. Aniq diagnostika, tez natija."}],
    "xizmatlar": [
        {"nomi": "Laboratoriya", "tavsif": "Qon, siydik va gormon tahlillari.", "vaqt": "30\u201345 daqiqa"},
        {"nomi": "UZI diagnostika", "tavsif": "Ichki a\u02bczolar UZI tekshiruvi.", "vaqt": "20\u201330 daqiqa"},
        {"nomi": "Kardiologiya & EKG", "tavsif": "12 kanalli EKG va yurak holatini baholash.", "vaqt": "15 daqiqa"},
        {"nomi": "Endokrinologiya", "tavsif": "Qandli diabet va gormon buzilishlari bo\u02bbyicha maslahat.", "vaqt": "30 daqiqa"},
        {"nomi": "Pediatriya", "tavsif": "Bolalar salomatligi va davolash.", "vaqt": "30 daqiqa"},
        {"nomi": "Kompleks tekshiruv", "tavsif": "Bir kunda to\u02bbliq salomatlik baholash.", "vaqt": "2\u20133 soat"},
    ],
    "shifokorlar": [
        {"ism": "Dr. Ism Familiya", "mut": "Kardiolog", "yil": "10 yil", "holat": "Faol"},
        {"ism": "Dr. Ism Familiya", "mut": "Pediatr", "yil": "8 yil", "holat": "Faol"},
        {"ism": "Dr. Ism Familiya", "mut": "UZI mutaxassisi", "yil": "12 yil", "holat": "Faol"},
    ],
    "narxlar": [
        {"xizmat": "Umumiy qon tahlili", "narx": "50 000 so\u02bbm"},
        {"xizmat": "UZI (1 a\u02bczo)", "narx": "120 000 so\u02bbm"},
        {"xizmat": "EKG", "narx": "80 000 so\u02bbm"},
        {"xizmat": "Endokrinolog maslahati", "narx": "150 000 so\u02bbm"},
        {"xizmat": "Kompleks check-up", "narx": "450 000 so\u02bbm"},
    ],
    "savollar": [
        {"savol": "Oldindan yozilish shartmi?", "javob": "Yozilish tavsiya etiladi \u2014 navbatsiz qabul qilamiz. Kelib ham murojaat qilishingiz mumkin."},
        {"savol": "Bolalar qabul qilinadimi?", "javob": "Ha, pediatr shifokor bolalarni qabul qiladi."},
        {"savol": "Tahlil natijalari qachon tayyor bo\u02bbladi?", "javob": "Ko\u02bbpchilik tahlillar 2\u20134 soat ichida tayyor bo\u02bbladi."},
    ],
    "arizalar": [],
}
SEED_SET = {"tel": "+998 00 000 00 00", "manzil": "Toshkent shahri", "vaqt": "Du\u2013Shan: 08:00\u201317:00"}

app = Flask(__name__, static_folder=None)
app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax",
                  PERMANENT_SESSION_LIFETIME=7 * 24 * 3600)


def _secret():
    p = os.path.join(DATA_DIR, ".secret")
    if not os.path.exists(p):
        with open(p, "w") as f:
            f.write(secrets.token_hex(32))
    return open(p).read().strip()


app.secret_key = os.environ.get("SECRET_KEY") or _secret()


def db():
    c = sqlite3.connect(DB_FILE)
    c.row_factory = sqlite3.Row
    return c


def init():
    c = db()
    c.execute("create table if not exists items(id integer primary key autoincrement, col text not null, data text not null)")
    c.execute("create table if not exists settings(k text primary key, v text)")
    if not c.execute("select 1 from items limit 1").fetchone():
        for col, rs in SEED.items():
            for r in rs:
                c.execute("insert into items(col,data) values(?,?)", (col, json.dumps(r, ensure_ascii=False)))
        for k, v in SEED_SET.items():
            c.execute("insert or replace into settings values(?,?)", (k, v))
    c.commit()
    c.close()


def rows(col):
    c = db()
    out = []
    for r in c.execute("select id,data from items where col=? order by id", (col,)):
        d = json.loads(r["data"])
        d["id"] = r["id"]
        out.append(d)
    c.close()
    return out


def get_settings():
    c = db()
    s = {r["k"]: r["v"] for r in c.execute("select k,v from settings")}
    c.close()
    return {k: s.get(k, SEED_SET[k]) for k in SET_KEYS}


def clean(col, data, rid=None):
    if not isinstance(data, dict):
        abort(400)
    out = {f: str(data.get(f, "")).strip()[: 5000 if f in LONG else 300] for f in FIELDS[col]}
    for f, opts in CHOICES.get(col, {}).items():
        if out[f] not in opts:
            out[f] = opts[0]
    if col == "posts":
        s = re.sub(r"[^a-z0-9-]+", "-", out["slug"].lower()).strip("-") or "post"
        if any(p["slug"] == s and p["id"] != rid for p in rows("posts")):
            s += "-" + str(int(time.time()) % 10000)
        out["slug"] = s
    for f in REQUIRED[col]:
        if not out[f]:
            abort(400)
    return out


def admin_only():
    if not session.get("admin"):
        abort(401)


def body():
    d = request.get_json(silent=True)  # faqat application/json
    if d is None:
        abort(400)
    return d


def notify(a):
    if not (TG_TOKEN and TG_CHAT):
        return
    text = "\U0001F514 YANGI QABUL\n\U0001F464 %s\n\U0001F4DE %s\n\U0001FA7A %s" % (a["ism"], a["tel"], a["xizmat"] or "-")

    def run():
        try:
            data = urllib.parse.urlencode({"chat_id": TG_CHAT, "text": text}).encode()
            urllib.request.urlopen("https://api.telegram.org/bot%s/sendMessage" % TG_TOKEN, data, timeout=10)
        except Exception:
            pass

    threading.Thread(target=run, daemon=True).start()


_hits = {}


def too_many(ip):
    now = time.time()
    h = [t for t in _hits.get(ip, []) if now - t < 600]
    _hits[ip] = h
    if len(h) >= 5:
        return True
    h.append(now)
    return False


# ------------------------------ sahifalar ---------------------------------
@app.get("/")
def index():
    return send_from_directory(STATIC, "index.html")


@app.get("/admin")
def admin():
    return send_from_directory(STATIC, "admin.html")


@app.get("/robots.txt")
def robots():
    return Response("User-agent: *\nDisallow: /admin\nDisallow: /api/\nSitemap: %ssitemap.xml\n" % request.url_root,
                    mimetype="text/plain")


@app.get("/sitemap.xml")
def sitemap():
    u = ["<url><loc>%s</loc></url>" % request.url_root]
    for p in rows("posts"):
        if p["holat"] == "Chop etilgan":
            u.append("<url><loc>%syangilik/%s</loc></url>" % (request.url_root, escape(p["slug"])))
    return Response('<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">%s</urlset>' % "".join(u),
                    mimetype="application/xml")


@app.get("/yangilik/<slug>")
def post_page(slug):
    p = next((x for x in rows("posts") if x["slug"] == slug and x["holat"] == "Chop etilgan"), None)
    if not p:
        abort(404)
    title = escape(p["seot"] or p["title"])
    desc = escape(p["seod"] or p["matn"][:160])
    paras = "".join("<p>%s</p>" % escape(x) for x in p["matn"].split("\n") if x.strip())
    s = get_settings()
    return Response("""<!DOCTYPE html><html lang="uz"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>%s</title><meta name="description" content="%s">
<meta property="og:title" content="%s"><meta property="og:description" content="%s"><meta property="og:type" content="article">
<style>:root{--bg:#f4f8fb;--card:#fff;--ink:#0f2740;--mut:#5d7186;--teal:#14b8c8;--navy:#0f2a47}
@media(prefers-color-scheme:dark){:root{--bg:#0a1623;--card:#122437;--ink:#e8f1f8;--mut:#96abbe}}
body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.7 system-ui,sans-serif}
header{background:var(--navy);padding:14px 20px}header a{color:#fff;text-decoration:none;font-weight:800}header b{color:var(--teal)}
main{max-width:720px;margin:auto;padding:24px 20px 60px}h1{line-height:1.25;font-size:28px}
.t{color:var(--teal);font-weight:700;font-size:13px}p{color:var(--ink)}.cta{display:inline-block;margin-top:20px;background:var(--teal);color:#06222a;padding:12px 20px;border-radius:12px;font-weight:700;text-decoration:none}
footer{text-align:center;color:var(--mut);font-size:13px;padding:20px}</style></head><body>
<header><a href="/">DMD<b>KLINIKA</b></a></header>
<main><div class="t">%s</div><h1>%s</h1>%s<a class="cta" href="/#qabul">Qabulga yozilish</a></main>
<footer>%s &middot; %s</footer></body></html>""" % (
        title, desc, title, desc, escape(p["tur"].upper()), escape(p["title"]), paras,
        escape(s["tel"]), escape(s["vaqt"])), mimetype="text/html")


# -------------------------------- API -------------------------------------
@app.get("/api/public")
def public():
    posts = [p for p in rows("posts") if p["holat"] == "Chop etilgan"][::-1]
    return jsonify(
        xizmatlar=rows("xizmatlar"),
        shifokorlar=[d for d in rows("shifokorlar") if d["holat"] != "Nofaol"],
        narxlar=rows("narxlar"), savollar=rows("savollar"),
        posts=[{k: p[k] for k in ("id", "title", "tur", "kat", "slug", "matn")} for p in posts],
        set=get_settings())


@app.post("/api/login")
def login():
    d = body()
    ok_e = secrets.compare_digest(str(d.get("email", "")), ADMIN_EMAIL)
    ok_p = secrets.compare_digest(str(d.get("password", "")), ADMIN_PASSWORD)
    if not (ok_e and ok_p):
        time.sleep(0.8)
        abort(401)
    session.permanent = True
    session["admin"] = True
    return jsonify(ok=True)


@app.post("/api/logout")
def logout():
    session.clear()
    return jsonify(ok=True)


@app.get("/api/admin/all")
def admin_all():
    admin_only()
    out = {c: rows(c) for c in FIELDS}
    out["set"] = get_settings()
    return jsonify(out)


@app.put("/api/settings")
def put_settings():
    admin_only()
    d = body()
    c = db()
    for k in SET_KEYS:
        c.execute("insert or replace into settings values(?,?)", (k, str(d.get(k, "")).strip()[:300]))
    c.commit()
    c.close()
    return jsonify(get_settings())


@app.post("/api/<col>")
def create(col):
    if col not in FIELDS:
        abort(404)
    if col == "arizalar" and not session.get("admin"):  # ochiq: saytdan ariza
        if too_many(request.remote_addr):
            abort(429)
        d = body()
        a = clean(col, {**d, "holat": "Yangi"})
        if not 9 <= len(re.sub(r"\D", "", a["tel"])) <= 15:
            abort(400)
        public_ok = True
    else:
        admin_only()
        a = clean(col, body())
        public_ok = False
    c = db()
    cur = c.execute("insert into items(col,data) values(?,?)", (col, json.dumps(a, ensure_ascii=False)))
    c.commit()
    a["id"] = cur.lastrowid
    c.close()
    if public_ok:
        notify(a)
    return jsonify(a), 201


@app.put("/api/<col>/<int:rid>")
def update(col, rid):
    admin_only()
    if col not in FIELDS:
        abort(404)
    a = clean(col, body(), rid)
    c = db()
    cur = c.execute("update items set data=? where id=? and col=?", (json.dumps(a, ensure_ascii=False), rid, col))
    c.commit()
    c.close()
    if not cur.rowcount:
        abort(404)
    a["id"] = rid
    return jsonify(a)


@app.delete("/api/<col>/<int:rid>")
def delete(col, rid):
    admin_only()
    if col not in FIELDS:
        abort(404)
    c = db()
    c.execute("delete from items where id=? and col=?", (rid, col))
    c.commit()
    c.close()
    return jsonify(ok=True)


@app.errorhandler(400)
@app.errorhandler(401)
@app.errorhandler(404)
@app.errorhandler(429)
def err(e):
    if request.path.startswith("/api/"):
        return jsonify(error=e.name), e.code
    return Response("<h1>%s</h1><p><a href='/'>Bosh sahifa</a></p>" % e.code, status=e.code, mimetype="text/html")


init()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5000"))
    if ADMIN_PASSWORD == "admin123":
        print("\n!!! Diqqat: standart parol (admin123). Internetga chiqarishdan oldin ADMIN_PASSWORD ni o'zgartiring.\n")
    app.run(host=os.environ.get("HOST", "127.0.0.1"), port=port, debug=False)
