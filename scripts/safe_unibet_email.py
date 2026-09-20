"""
SAFE Method — Combinés Triples Domicile (GitHub Actions)
Marché : "Gagne ou mène de 2 buts" (Early Payout +2b)
Règle : 1 cador (1.15-1.27) + 1 médian (1.28-1.38) + 1 solide (1.39-1.47) par ticket
Cote cible : 2.15 – 2.40 par ticket

RÈGLE ABSOLUE : tous les matchs d'un ticket = même jour calendaire.
Si pas assez de matchs dans une catégorie → on réduit le nombre de tickets.
"""

import json, os, re, smtplib, uuid, datetime, unicodedata, base64, time, sys
from email.utils import formatdate
import urllib.request


HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "fr-FR,fr;q=0.9",
    "Referer": "https://www.unibet.fr/paris-football",
}

# ─── Unibet scan (no selenium needed — JSON API) ─────────────────────────────

def fetch_json(url, retries=3):
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=20) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception as e:
            print(f"[WARN] fetch attempt {attempt+1} failed: {e}")
            time.sleep(2)
    return None


def today_date():
    """Return today's date as datetime.date (local time)."""
    return datetime.datetime.now().date()


def parse_event_date(ev):
    """Return datetime.date for a Unibet event dict, or None."""
    epoch = ev.get("startTimestamp") or ev.get("start_timestamp")
    if epoch:
        return datetime.datetime.fromtimestamp(int(epoch) / 1000).date()
    start = ev.get("start", "")
    # Try ISO format
    try:
        return datetime.datetime.fromisoformat(start[:10]).date()
    except Exception:
        pass
    return None


def scan_unibet():
    """Return today-only home-favourite matches from Unibet, sorted by c1 asc."""
    today = today_date()
    print(f"[SAFE] Scanning Unibet — today = {today}")

    url = (
        "https://www.unibet.fr/api/offerings/v2/list/events/sport/FOOTBALL"
        "/region/fr/offerings.json?alt=json&lang=fr"
    )
    data = fetch_json(url)
    if not data:
        return []

    events = data.get("liveEvents", []) + data.get("upcomingEvents", [])
    print(f"[SAFE] Total events from API: {len(events)}")

    matches = []
    for ev in events:
        ev_date = parse_event_date(ev)
        if ev_date != today:          # ← RÈGLE ABSOLUE : même jour uniquement
            continue

        epoch = ev.get("startTimestamp", 0)
        dt = datetime.datetime.fromtimestamp(int(epoch) / 1000) if epoch else None
        if dt and (dt.hour >= 22 or dt.hour <= 9):
            continue                  # Pas de matchs nocturnes / très matinaux

        time_str = dt.strftime("%Hh%M") if dt else "?h??"
        home  = (ev.get("homeTeam") or {}).get("name") or ev.get("home", "?")
        away  = (ev.get("awayTeam") or {}).get("name") or ev.get("away", "?")
        league = (ev.get("league") or {}).get("name") or ev.get("competition", "")
        ev_id  = ev.get("id", "")
        link   = f"https://www.unibet.fr/paris-football/{ev_id}" if ev_id else "https://www.unibet.fr/paris-football"

        c1 = c2 = None
        for mkt in ev.get("markets", []) or []:
            if mkt.get("name", "").lower() in ("1x2", "match result", "résultat du match"):
                for sel in mkt.get("selections", []) or []:
                    label = sel.get("name", "").lower()
                    odds  = sel.get("odds") or sel.get("price")
                    if label in ("1", "domicile", "home") and odds:
                        c1 = round(float(odds), 2)
                    elif label in ("2", "extérieur", "away") and odds:
                        c2 = round(float(odds), 2)
                break

        if not c1 or not c2:
            continue
        if not (1.15 <= c1 <= 1.47 and c1 < c2):
            continue

        matches.append({"time": time_str, "home": home.strip(), "away": away.strip(),
                         "league": league, "c1": c1, "c2": c2, "url": link,
                         "date": str(ev_date)})

    print(f"[SAFE] Home favs (1.15-1.47) today: {len(matches)}")
    return sorted(matches, key=lambda x: x["c1"])


# ─── Build tickets ────────────────────────────────────────────────────────────

def build_tickets(matches):
    """
    Cross-blend into N tickets (N = min available per category, max 5).
    Categories:
      heavy  : 1.15 – 1.27
      median : 1.28 – 1.38
      solid  : 1.39 – 1.47
    If a category is short, we cap N accordingly — NEVER mix dates.
    """
    heavy  = [m for m in matches if 1.15 <= m["c1"] <= 1.27]
    median = [m for m in matches if 1.28 <= m["c1"] <= 1.38]
    solid  = [m for m in matches if 1.39 <= m["c1"] <= 1.47]

    n = min(len(heavy), len(median), len(solid), 5)
    print(f"[SAFE] heavy={len(heavy)} median={len(median)} solid={len(solid)} → {n} ticket(s)")

    tickets = []
    for i in range(n):
        tickets.append({"matches": [heavy[i], median[i], solid[i]]})
    return tickets


# ─── HTML email ───────────────────────────────────────────────────────────────

def build_html(tickets, mise=7.0):
    today_str = datetime.datetime.now().strftime("%A %d %B %Y").capitalize()
    total = len(tickets) * mise

    rows = ""
    for i, t in enumerate(tickets, 1):
        cote = round(t["matches"][0]["c1"] * t["matches"][1]["c1"] * t["matches"][2]["c1"], 2)
        gain = round(mise * cote, 2)
        mrows = "".join(f"""
          <tr>
            <td style="padding:6px 10px;color:#94a3b8;">⏰ {m['time']}</td>
            <td style="padding:6px 10px;font-weight:600;color:#f1f5f9;">{m['home']}
              <span style="color:#64748b;font-weight:400;"> vs {m['away']}</span></td>
            <td style="padding:6px 10px;color:#94a3b8;font-size:12px;">{m['league']}</td>
            <td style="padding:6px 10px;text-align:center;font-weight:700;color:#f59e0b;">{m['c1']}</td>
          </tr>""" for m in t["matches"])
        rows += f"""
        <div style="background:#0f172a;border:1px solid #1e3a5f;border-radius:12px;margin-bottom:16px;overflow:hidden;">
          <div style="background:linear-gradient(135deg,#1e3a5f,#0f2744);padding:12px 18px;display:flex;justify-content:space-between;align-items:center;">
            <span style="font-size:16px;font-weight:700;color:#60a5fa;">🎫 TICKET {i}</span>
            <span style="font-size:13px;color:#94a3b8;">
              Cote <b style="color:#f59e0b;">{cote}</b> &nbsp;·&nbsp;
              Mise <b style="color:#f1f5f9;">{int(mise)}€</b> &nbsp;·&nbsp;
              Gain <b style="color:#4ade80;">{gain}€</b>
            </span>
          </div>
          <table style="width:100%;border-collapse:collapse;">{mrows}</table>
        </div>"""

    gains = sorted([round(mise * round(
        t["matches"][0]["c1"]*t["matches"][1]["c1"]*t["matches"][2]["c1"],2
    ),2) for t in tickets], reverse=True)
    seuil_3 = sum(gains[:3]) if len(gains) >= 3 else sum(gains)

    return f"""<!DOCTYPE html>
<html lang="fr">
<head><meta charset="UTF-8"><title>SAFE Method</title></head>
<body style="margin:0;padding:0;background:#020617;font-family:'Segoe UI',Arial,sans-serif;color:#f1f5f9;">
<div style="max-width:700px;margin:0 auto;padding:24px 16px;">

  <div style="background:linear-gradient(135deg,#1e3a5f,#0f2744);border-radius:14px;padding:22px 26px;margin-bottom:22px;border:1px solid #1e40af;">
    <div style="font-size:26px;font-weight:800;color:#60a5fa;">🔒 SAFE METHOD</div>
    <div style="font-size:13px;color:#94a3b8;margin-top:4px;">{today_str} &nbsp;·&nbsp; Combinés Triples Domicile</div>
    <div style="margin-top:14px;display:flex;gap:10px;flex-wrap:wrap;">
      <span style="background:#1e293b;border:1px solid #334155;border-radius:8px;padding:7px 12px;font-size:12px;">🎯 Marché : <b style="color:#f59e0b;">Gagne ou mène de 2 buts</b></span>
      <span style="background:#1e293b;border:1px solid #334155;border-radius:8px;padding:7px 12px;font-size:12px;">💰 Mise totale : <b>{int(total)}€</b></span>
      <span style="background:#1e293b;border:1px solid #334155;border-radius:8px;padding:7px 12px;font-size:12px;">✅ Rentable dès <b style="color:#4ade80;">3/{len(tickets)}</b></span>
    </div>
  </div>

  {rows}

  <div style="background:#0f172a;border:1px solid #1e293b;border-radius:10px;padding:16px 20px;font-size:13px;">
    <b style="color:#60a5fa;">📊 Tableau de marche</b><br><br>
    3/{len(tickets)} gagnants → <b style="color:#4ade80;">~{seuil_3:.2f}€ encaissés ✅</b><br>
    {len(tickets)}/{len(tickets)} gagnants → <b style="color:#4ade80;">~{sum(gains):.2f}€ encaissés 🏆</b>
  </div>

  <div style="text-align:center;margin-top:18px;font-size:11px;color:#334155;">
    SAFE Method v1 — Unibet France — Uniquement des matchs du {today_str}<br>
    Joueurs problématiques : <a href="https://www.joueurs-info-service.fr" style="color:#475569;">joueurs-info-service.fr</a>
  </div>
</div>
</body>
</html>"""


# ─── Send email ───────────────────────────────────────────────────────────────

def send_email(html_body, subject):
    gmail   = os.environ.get("GMAIL_EMAIL", "langlet.gregory@gmail.com").strip()
    passwd  = os.environ.get("GMAIL_APP_PASSWORD", "").strip().replace('\ufeff', '')
    if not passwd:
        print("[SMTP] GMAIL_APP_PASSWORD manquant")
        return False
    raw_to  = os.environ.get("RECIPIENT_EMAILS", gmail)
    recipients = [r.strip() for r in raw_to.split(",") if r.strip()]

    subj = unicodedata.normalize('NFKD', subject).encode('ASCII','ignore').decode('ASCII')
    html_body = html_body.replace('\ufeff','').replace('\ufffe','')
    bnd  = uuid.uuid4().hex
    fname = f"safe_{datetime.datetime.now().strftime('%Y_%m_%d')}.html"
    h64  = base64.b64encode(html_body.encode('utf-8')).decode('ascii')
    t64  = base64.b64encode("Combinés SAFE en pièce jointe.".encode('utf-8')).decode('ascii')

    raw = (
        f'From: Gregory LANGLET <{gmail}>\r\n'
        f'To: {", ".join(recipients)}\r\n'
        f'Subject: {subj}\r\n'
        f'Date: {formatdate(localtime=True)}\r\n'
        f'MIME-Version: 1.0\r\n'
        f'Content-Type: multipart/mixed; boundary="{bnd}"\r\n\r\n'
        f'--{bnd}\r\nContent-Type: text/plain; charset=utf-8\r\n'
        f'Content-Transfer-Encoding: base64\r\n\r\n{t64}\r\n\r\n'
        f'--{bnd}\r\nContent-Type: text/html; charset=utf-8; name="{fname}"\r\n'
        f'Content-Disposition: attachment; filename="{fname}"\r\n'
        f'Content-Transfer-Encoding: base64\r\n\r\n{h64}\r\n\r\n'
        f'--{bnd}--\r\n'
    )
    with smtplib.SMTP("smtp.gmail.com", 587, timeout=30) as s:
        s.ehlo(); s.starttls(); s.ehlo()
        s.login(gmail, passwd)
        s.sendmail(gmail, recipients, raw.encode('ascii'))
    print(f"[SMTP] Email envoyé → {recipients}")
    return True


# ─── Main ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    matches = scan_unibet()

    tickets = build_tickets(matches)

    if not tickets:
        print("[SAFE] 0 ticket buildable aujourd'hui — pas d'email envoyé.")
        sys.exit(0)

    mise = 7.0
    for i, t in enumerate(tickets, 1):
        cote = round(t["matches"][0]["c1"]*t["matches"][1]["c1"]*t["matches"][2]["c1"],2)
        noms = " + ".join(m["home"] for m in t["matches"])
        print(f"  T{i}: {noms} → cote {cote} → gain {round(mise*cote,2)}€")

    today_fmt = datetime.datetime.now().strftime("%d/%m/%Y")
    html = build_html(tickets, mise)
    send_email(html, f"SAFE Method - {len(tickets)} Combines Triples du {today_fmt}")
