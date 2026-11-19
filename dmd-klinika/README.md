# DMD Klinikasi — sayt + admin panel (bitta loyiha)

## Ishga tushirish
    pip install -r requirements.txt
    python app.py

- Sayt:  http://127.0.0.1:5000
- Admin: http://127.0.0.1:5000/admin   (email: admin@dmd.uz, parol: admin123)

## Parolni o'zgartirish (ALBATTA)
    # Windows (PowerShell):
    $env:ADMIN_EMAIL="siz@mail.uz"; $env:ADMIN_PASSWORD="kuchli-parol"; python app.py
    # Linux / Mac:
    ADMIN_EMAIL=siz@mail.uz ADMIN_PASSWORD=kuchli-parol python app.py

## Telegramga ariza xabari (ixtiyoriy)
@BotFather dan bot token oling, botga yozing, chat ID ni aniqlang:
    TG_TOKEN=... TG_CHAT=... python app.py

## Nima qayerda
- app.py            — server, baza (SQLite: data.db), API
- static/index.html — sayt (ma'lumotlar admin paneldan olinadi)
- static/admin.html — admin panel
- Postlar saytda /yangilik/<slug> manzilida, SEO sarlavha/tavsif bilan chiqadi.

## Internetga chiqarish
    pip install gunicorn
    gunicorn -w 2 -b 0.0.0.0:8000 app:app
(HTTPS uchun Nginx yoki Caddy orqasida ishlating. data.db faylini zaxiralab turing.)
