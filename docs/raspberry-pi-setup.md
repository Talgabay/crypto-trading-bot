# 🍓 מדריך התקנה — הבוט על Raspberry Pi

מדריך עצמאי מא׳ עד ת׳. בסוף התהליך הבוט ירוץ על ה-Pi 24/7, יקום לבד אחרי
הפסקת חשמל או קריסה, וישלח התראות לטלגרם מכל מקום.

> ⚠️ **כלל ברזל: בוט אחד בלבד!** לפני שמדליקים את הבוט על ה-Pi, לוודא
> שהבוט על המק בבית **כבוי**. שניהם עובדים מול אותו חשבון testnet ויפריעו
> זה לזה.

---

## שלב 0 — האם ה-Pi מתאים? (בדיקת 64-ביט)

פתח טרמינל על ה-Pi והרץ:

```bash
uname -m
```

| פלט | משמעות |
|------|---------|
| `aarch64` | ✅ מערכת 64-ביט — אפשר להמשיך |
| `armv7l` או `armv6l` | ❌ מערכת 32-ביט — צריך לצרוב מחדש (ראה למטה) |

בדיקה נוספת (לא חובה): `getconf LONG_BIT` — אמור להדפיס `64`.

**אם יצא 32-ביט:** צריך לצרוב את כרטיס ה-SD מחדש עם
[Raspberry Pi Imager](https://www.raspberrypi.com/software/) ולבחור
**Raspberry Pi OS (64-bit)**. שים לב: Pi 2 ומטה לא תומכים ב-64-ביט;
Pi 3 ומעלה — כן.

---

## שלב 1 — התקנת כלים

```bash
sudo apt update
sudo apt install -y git python3-venv python3-pip nodejs npm gh
```

## שלב 2 — התחברות ל-GitHub ושכפול הריפו

הריפו פרטי, אז צריך להתחבר פעם אחת:

```bash
gh auth login
```

בוחרים: `GitHub.com` → `HTTPS` → `Login with a web browser`, ועוקבים אחרי
הקוד שמופיע (פותחים את הלינק בדפדפן ומקלידים את הקוד).

ואז:

```bash
cd ~
gh repo clone Talgabay/crypto-trading-bot
cd crypto-trading-bot
```

## שלב 3 — סביבת פייתון + תלויות

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

(לוקח כמה דקות על Pi — סבלנות.)

## שלב 4 — קובץ הסודות `.env`

הסודות **בכוונה לא נמצאים ב-GitHub**. יוצרים את הקובץ ידנית:

```bash
cp .env.example .env
nano .env
```

וממלאים את 4 השדות האלה (השאר נשאר כמו שהוא):

```
BINANCE_TESTNET_API_KEY=   ← מ-https://testnet.binance.vision (אפשר לג'נרט חדש)
BINANCE_TESTNET_SECRET=    ← יחד עם המפתח
TELEGRAM_BOT_TOKEN=        ← מ-@BotFather (ההודעה שמורה בצ'אט שלך איתו)
TELEGRAM_CHAT_ID=          ← מ-@userinfobot
USE_LIVE=true              ← מוסיפים שורה זו אם אינה קיימת
```

שמירה ב-nano: `Ctrl+O` → Enter → `Ctrl+X`.

> 💡 אם אין לך את מפתחות ה-testnet בהישג יד — פשוט תיצור חדשים באתר
> (זה חינם ולוקח דקה). הישנים יפסיקו לעניין אותנו.
> ⚠️ אל תשלח את הסודות במייל/וואטסאפ לעצמך.

## שלב 5 — בדיקה שהכל עובד

```bash
source .venv/bin/activate
pytest -q                      # אמור: 17 passed
python -m backtest.run         # אמור להדפיס שורת תוצאות
```

## שלב 6 — שירות קבוע (העיקר!)

זה מה שגורם לבוט לרוץ תמיד — גם אחרי ריסטרט, גם אחרי קריסה:

```bash
sudo tee /etc/systemd/system/trading-bot.service > /dev/null <<'EOF'
[Unit]
Description=Crypto Trading Co-Pilot
After=network-online.target
Wants=network-online.target

[Service]
User=pi
WorkingDirectory=/home/pi/crypto-trading-bot
ExecStart=/home/pi/crypto-trading-bot/.venv/bin/uvicorn api.app:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl enable --now trading-bot
```

> אם שם המשתמש על ה-Pi אינו `pi`, החלף את `User=pi` ואת הנתיבים
> (`/home/pi/...`) בהתאם. בודקים עם `whoami`.

**פקודות שימושיות:**

```bash
systemctl status trading-bot          # מצב השירות
journalctl -u trading-bot -f          # לוג חי (יציאה: Ctrl+C)
sudo systemctl restart trading-bot    # הפעלה מחדש
sudo systemctl stop trading-bot       # עצירה
```

## שלב 7 — אימות

1. `curl localhost:8000/health` → אמור להחזיר `{"status":"ok",...}`
2. `curl localhost:8000/api/status` → לוודא `"live":true` ומחירים אמיתיים
3. 📲 תוך דקות אמורות להתחיל לזרום הודעות לטלגרם כשיש מה לדווח

## שלב 8 — דשבורד (אופציונלי)

הדשבורד נגיש רק מהרשת שבה נמצא ה-Pi (בעבודה). טלגרם — מכל מקום.

```bash
cd ~/crypto-trading-bot/ui
npm install
npm run dev -- --host
```

ואז מכל מחשב באותה רשת: `http://<כתובת-ה-IP-של-ה-Pi>:3002`
(את ה-IP מוצאים עם `hostname -I`.)

---

## פתרון תקלות נפוצות

| תופעה | פתרון |
|-------|--------|
| `pip install` נכשל על pandas/numpy | כנראה מערכת 32-ביט — חזור לשלב 0 |
| `gh: command not found` | `sudo apt install gh`, ואם אין — ראה הוראות באתר cli.github.com |
| הבוט רץ אבל אין הודעות טלגרם | בדוק `journalctl -u trading-bot -f`; ודא ששלחת לבוט הודעה אחת בטלגרם |
| `/api/status` מראה `"live":false` | חסר `USE_LIVE=true` ב-.env או מפתחות ריקים; אחרי תיקון: `sudo systemctl restart trading-bot` |
| שעה לא נכונה (שגיאות חתימה מול Binance) | `timedatectl` לוודא סנכרון שעון |
