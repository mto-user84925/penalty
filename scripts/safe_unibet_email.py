"""
SAFE Method — Combinés Triples Domicile (48 Heures)
Réutilise get_unibet_active_games() + scan_unibet_match_details() depuis auto_premium_unibet.py
"""

import sys, os, json, datetime, smtplib, uuid, unicodedata, base64
from email.utils import formatdate, make_msgid
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from auto_premium_unibet import get_unibet_active_games, scan_unibet_match_details

EXCLUDED_KEYWORDS = ["villarreal", "modène", "modena", "empoli", "sarajevo", "sloga"]

def get_paris_now():
    return datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=2)

def today_date():
    return get_paris_now().date()

def tomorrow_date():
    return (get_paris_now() + datetime.timedelta(days=1)).date()

def parse_match_date(m):
    import re
    start_iso = m.get("start_iso", "")
    if start_iso:
        try:
            dt = datetime.datetime.fromisoformat(start_iso.replace("Z", "+00:00")) + datetime.timedelta(hours=2)
            return dt.date()
        except Exception:
            pass

    date_str = m.get("date_str", "")
    match = re.search(r"(\d{2}/\d{2})", date_str)
    if match:
        day, month = match.group(1).split("/")
        year = datetime.datetime.now().year
        try:
            return datetime.date(year, int(month), int(day))
        except ValueError:
            pass
    return None

def parse_match_hour(m):
    import re
    match = re.search(r"(\d{1,2})h\d{2}", m.get("date_str", ""))
    return int(match.group(1)) if match else 12

def is_trap(m):
    dom = (m.get("dom") or "").lower()
    ext = (m.get("ext") or "").lower()
    for kw in EXCLUDED_KEYWORDS:
        if kw in dom or kw in ext:
            return True
    return False

def extract_candidates_for_day(all_scanned, target_date):
    candidates = []
    for m in all_scanned:
        if not m:
            continue

        ev_date = parse_match_date(m)
        if ev_date != target_date:
            continue

        hour = parse_match_hour(m)
        if hour >= 22 or hour <= 9:
            continue

        if is_trap(m):
            continue

        c1 = m.get("c1")
        c2 = m.get("c2")
        if not c1 or not c2:
            continue

        if not (1.18 <= c1 <= 1.50 and c1 < c2):
            continue

        p2_c1 = m.get("p2_c1")
        cote_jouee = round(float(p2_c1), 2) if p2_c1 else round(float(c1), 2)

        candidates.append({
            "time": m.get("date_str", "").split("à ")[-1].strip() if "à " in m.get("date_str","") else "?h??",
            "home": m.get("dom", "?").strip(),
            "away": m.get("ext", "?").strip(),
            "league": m.get("league", ""),
            "c1": round(float(c1), 2),
            "c2": round(float(c2), 2),
            "p2_c1": round(float(p2_c1), 2) if p2_c1 else None,
            "cote_jouee": cote_jouee,
            "url": m.get("url", "https://www.unibet.fr/paris-football"),
            "date": str(target_date),
        })
    return sorted(candidates, key=lambda x: x["c1"])

def build_tickets(matches):
    heavy  = sorted([m for m in matches if 1.18 <= m["c1"] <= 1.29], key=lambda x: x["c1"])
    median = sorted([m for m in matches if 1.30 <= m["c1"] <= 1.38], key=lambda x: x["c1"])
    solid  = sorted([m for m in matches if 1.39 <= m["c1"] <= 1.50], key=lambda x: x["c1"])

    n = min(len(heavy), len(median), len(solid), 5)
    print(f"[SAFE] Rangs qualifiés : Cador={len(heavy)} | Médian={len(median)} | Solide={len(solid)} → {n} ticket(s)")

    if n == 0:
        return []

    tickets = []
    for i in range(n):
        cad = heavy[i]
        sol = solid[len(solid) - 1 - i]
        med = median[i]
        tickets.append({"matches": [cad, med, sol]})

    return tickets

def render_day_tickets_html(tickets, day_label, mise=7.0, start_idx=1):
    if not tickets:
        return f"""
        <div style="background:#0f172a;border:1px dashed #334155;border-radius:12px;padding:24px;margin-bottom:24px;text-align:center;color:#94a3b8;font-size:14px;">
          ⚠️ <b>Aucun combiné triple qualifié pour {day_label}</b><br>
          <span style="font-size:12px;color:#64748b;">(Programme plus calme en journée, aucun favori à domicile sous 1.50 — rythme normal des lundis post-weekend)</span>
        </div>"""

    out = ""
    for i, t in enumerate(tickets, start_idx):
        cote = round(t["matches"][0]["cote_jouee"] * t["matches"][1]["cote_jouee"] * t["matches"][2]["cote_jouee"], 2)
        gain = round(mise * cote, 2)
        mrows = "".join(f"""
          <tr style="border-bottom:1px solid #1e293b;">
            <td style="padding:10px 12px;color:#94a3b8;font-size:13px;white-space:nowrap;">⏰ {m['time']}</td>
            <td style="padding:10px 12px;font-weight:600;color:#f1f5f9;font-size:14px;">
              <a href="{m['url']}" style="color:#f1f5f9;text-decoration:none;" target="_blank">👑 <b>{m['home']}</b></a>
              <span style="color:#64748b;font-weight:400;font-size:13px;"> vs {m['away']}</span>
            </td>
            <td style="padding:10px 12px;color:#94a3b8;font-size:12px;">{m['league']}</td>
            <td style="padding:10px 12px;text-align:center;font-weight:700;color:#f59e0b;font-size:15px;white-space:nowrap;">
              @{m['cote_jouee']}
              <div style="font-size:10px;color:#64748b;font-weight:400;">1N2: {m['c1']}</div>
            </td>
          </tr>""" for m in t["matches"])
        out += f"""
        <div style="background:#0f172a;border:1px solid #1e3a5f;border-radius:12px;margin-bottom:16px;overflow:hidden;box-shadow:0 4px 6px -1px rgba(0,0,0,0.3);">
          <div style="background:linear-gradient(135deg,#1e3a5f,#0f2744);padding:12px 18px;display:flex;justify-content:space-between;align-items:center;">
            <span style="font-size:15px;font-weight:800;color:#60a5fa;">🎫 TICKET {i} · COMBINÉ TRIPLE</span>
            <span style="font-size:13px;color:#94a3b8;">
              Cote <b style="color:#f59e0b;font-size:15px;">@{cote}</b> &nbsp;·&nbsp;
              Mise <b style="color:#f1f5f9;">{int(mise)}€</b> &nbsp;·&nbsp;
              Gain <b style="color:#4ade80;font-size:15px;">{gain}€</b>
            </span>
          </div>
          <table style="width:100%;border-collapse:collapse;">{mrows}</table>
        </div>"""
    return out

def build_full_html(tickets_today, tickets_tomorrow, mise=7.0):
    today = today_date()
    tomorrow = tomorrow_date()
    today_fmt = today.strftime("%A %d %B %Y").capitalize()
    tomorrow_fmt = tomorrow.strftime("%A %d %B %Y").capitalize()

    total_tickets = len(tickets_today) + len(tickets_tomorrow)
    total_mise = total_tickets * mise

    sec_today = render_day_tickets_html(tickets_today, today_fmt, mise=mise, start_idx=1)
    sec_tomorrow = render_day_tickets_html(tickets_tomorrow, tomorrow_fmt, mise=mise, start_idx=len(tickets_today)+1)

    return f"""<!DOCTYPE html>
<html lang="fr"><head><meta charset="UTF-8"><title>STRATÉGIE OFFICIELLE UNIBET · SAFE 48H</title></head>
<body style="margin:0;padding:0;background:#020617;font-family:'Segoe UI',Arial,sans-serif;color:#f1f5f9;">
<div style="max-width:720px;margin:0 auto;padding:24px 16px;">
  <!-- Header -->
  <div style="background:linear-gradient(135deg,#1e3a5f,#0f2744);border-radius:14px;padding:22px 26px;margin-bottom:24px;border:1px solid #1e40af;">
    <div style="font-size:24px;font-weight:800;color:#60a5fa;letter-spacing:-0.5px;">⚽ STRATÉGIE OFFICIELLE UNIBET · +2 GAGNANT</div>
    <div style="font-size:13px;color:#94a3b8;margin-top:4px;">{today_fmt} &nbsp;·&nbsp; Combinés Triples 100% Domicile &nbsp;·&nbsp; Scan 48h</div>
    <div style="margin-top:14px;display:flex;gap:10px;flex-wrap:wrap;">
      <span style="background:#1e293b;border:1px solid #334155;border-radius:8px;padding:7px 12px;font-size:12px;">🎯 Marché : <b style="color:#f59e0b;">Gagne ou mène de 2 buts (+2b)</b></span>
      <span style="background:#1e293b;border:1px solid #334155;border-radius:8px;padding:7px 12px;font-size:12px;">💰 Mise : <b style="color:#f1f5f9;">{int(total_mise)}€</b> ({int(mise)}€/ticket)</span>
      <span style="background:#1e293b;border:1px solid #334155;border-radius:8px;padding:7px 12px;font-size:12px;">🎫 <b style="color:#60a5fa;">{total_tickets} tickets ({len(tickets_today)} j. / {len(tickets_tomorrow)} j+1)</b></span>
    </div>
  </div>

  <!-- SECTION AUJOURD'HUI -->
  <div style="margin-bottom:28px;">
    <div style="display:flex;align-items:center;gap:10px;margin-bottom:14px;padding-left:4px;">
      <span style="background:#2563eb;color:#ffffff;font-size:12px;font-weight:700;padding:4px 10px;border-radius:6px;">AUJOURD'HUI</span>
      <span style="font-size:18px;font-weight:800;color:#f1f5f9;">📅 {today_fmt} ({len(tickets_today)} tickets)</span>
    </div>
    {sec_today}
  </div>

  <!-- SECTION DEMAIN -->
  <div style="margin-bottom:28px;">
    <div style="display:flex;align-items:center;gap:10px;margin-bottom:14px;padding-left:4px;">
      <span style="background:#475569;color:#ffffff;font-size:12px;font-weight:700;padding:4px 10px;border-radius:6px;">DEMAIN</span>
      <span style="font-size:18px;font-weight:800;color:#f1f5f9;">📅 {tomorrow_fmt} ({len(tickets_tomorrow)} tickets)</span>
    </div>
    {sec_tomorrow}
  </div>

  <div style="background:#0f172a;border:1px solid #1e293b;border-radius:10px;padding:16px 20px;font-size:13px;">
    <b style="color:#60a5fa;font-size:14px;">📊 Règle mathématique du Standard SAFE</b><br><br>
    • <b>Bénéfice net garanti dès 3 tickets gagnants</b> sur les 5.<br>
    • <b>Option Early Payout</b> : Dès que votre équipe mène par 2 buts (2-0, 3-1), la sélection est payée immédiatement gagnante.
  </div>

  <div style="text-align:center;margin-top:24px;font-size:11px;color:#475569;">
    Méthode SAFE Standard Permanent — Unibet France — Scan automatique 48h toutes les 2h<br>
    Lien live : <a href="https://mto-user84925.github.io/penalty/email.html" style="color:#60a5fa;">mto-user84925.github.io/penalty/email.html</a><br>
    Joueurs problématiques : <a href="https://www.joueurs-info-service.fr" style="color:#64748b;">joueurs-info-service.fr</a>
  </div>
</div></body></html>"""

def send_email(html_body, subject):
    gmail_email = os.environ.get("GMAIL_EMAIL", "langlet.gregory@gmail.com").strip()
    gmail_pass  = os.environ.get("GMAIL_APP_PASSWORD", "").strip().replace('\ufeff', '')
    smtp_host   = os.environ.get("SMTP_HOST", "smtp.sfr.fr").strip()
    smtp_port   = int(os.environ.get("SMTP_PORT", "465"))
    smtp_user   = os.environ.get("SMTP_USER", "gregory.langlet@sfr.fr").strip()
    smtp_pass   = os.environ.get("SMTP_PASS", "").strip()

    raw_recipients = os.environ.get("EMAIL_TO") or os.environ.get("RECIPIENT_EMAILS") or "gregory.langlet@sfr.fr, langlet.gregory@gmail.com"
    recipients = [r.strip() for r in raw_recipients.split(",") if r.strip()]

    clean_subject = unicodedata.normalize('NFKD', subject).encode('ASCII', 'ignore').decode('ASCII')
    html_body = html_body.replace('\ufeff', '').replace('\ufffe', '')

    msg = MIMEMultipart('mixed')
    msg["Subject"] = clean_subject
    msg["From"] = f"Gregory LANGLET <{gmail_email}>"
    msg["To"] = ", ".join(recipients)
    msg["Date"] = formatdate(localtime=True)
    msg["Message-ID"] = make_msgid()
    msg["X-Mailer"] = "Python/smtplib"

    plain = f"Combinés SAFE Method Unibet du jour. Consultez la version HTML en ligne : https://mto-user84925.github.io/penalty/email.html"
    alt_part = MIMEMultipart('alternative')
    alt_part.attach(MIMEText(plain, 'plain', 'utf-8'))
    alt_part.attach(MIMEText(html_body, 'html', 'utf-8'))
    msg.attach(alt_part)

    # 1. Tentative Gmail SMTP prioritaire
    if gmail_pass:
        try:
            print(f"[SMTP] Envoi vers {recipients} via Gmail SMTP...")
            with smtplib.SMTP("smtp.gmail.com", 587, timeout=30) as server:
                server.ehlo(); server.starttls(); server.ehlo()
                server.login(gmail_email, gmail_pass)
                server.sendmail(gmail_email, recipients, msg.as_bytes())
            print("[SMTP] ✅ Email envoyé avec succès via Gmail SMTP !")
            return True
        except Exception as e:
            print(f"[SMTP] ⚠️ Échec Gmail SMTP : {e}")

    # 2. Fallback SFR SMTP
    if smtp_user and smtp_pass:
        try:
            print(f"[SMTP] Tentative de secours via {smtp_host}:{smtp_port}...")
            auth_user = smtp_user.split("@")[0] if "@" in smtp_user else smtp_user
            if smtp_port == 465:
                with smtplib.SMTP_SSL(smtp_host, smtp_port, timeout=30) as server:
                    server.login(auth_user, smtp_pass)
                    server.sendmail(smtp_user, recipients, msg.as_bytes())
            else:
                with smtplib.SMTP(smtp_host, smtp_port, timeout=30) as server:
                    server.ehlo(); server.starttls(); server.ehlo()
                    server.login(auth_user, smtp_pass)
                    server.sendmail(smtp_user, recipients, msg.as_bytes())
            print("[SMTP] ✅ Email envoyé avec succès via SFR SMTP !")
            return True
        except Exception as e:
            print(f"[SMTP] ❌ Échec SFR SMTP : {e}")

    print("[SMTP] ❌ Aucun mot de passe SMTP disponible — email non envoyé.")
    return False

if __name__ == "__main__":
    today = today_date()
    tomorrow = tomorrow_date()
    print(f"[SAFE] Scan 48h Unibet : Aujourd'hui = {today} | Demain = {tomorrow}")

    games = get_unibet_active_games()
    print(f"[SAFE] {len(games)} fixtures trouvées, scan des détails...")

    all_scanned = []
    with ThreadPoolExecutor(max_workers=20) as ex:
        futures = {ex.submit(scan_unibet_match_details, g): g for g in games}
        for fut in as_completed(futures):
            res = fut.result()
            if res:
                all_scanned.append(res)

    print(f"[SAFE] {len(all_scanned)} matchs avec cotes récupérées au total")

    cand_today = extract_candidates_for_day(all_scanned, today)
    print(f"[SAFE] Candidats Aujourd'hui ({today}) : {len(cand_today)}")
    tickets_today = build_tickets(cand_today)

    cand_tomorrow = extract_candidates_for_day(all_scanned, tomorrow)
    print(f"[SAFE] Candidats Demain ({tomorrow}) : {len(cand_tomorrow)}")
    tickets_tomorrow = build_tickets(cand_tomorrow)

    if not tickets_today and not tickets_tomorrow:
        print("[SAFE] 0 ticket buildable sur les 48h — pas d'email.")
        sys.exit(0)

    mise = 7.0
    print(f"\n--- TICKETS AUJOURD'HUI ({len(tickets_today)}) ---")
    for i, t in enumerate(tickets_today, 1):
        cote = round(t["matches"][0]["cote_jouee"] * t["matches"][1]["cote_jouee"] * t["matches"][2]["cote_jouee"], 2)
        print(f"  T{i}: {' + '.join(m['home'] for m in t['matches'])} → @{cote}")

    print(f"\n--- TICKETS DEMAIN ({len(tickets_tomorrow)}) ---")
    for i, t in enumerate(tickets_tomorrow, len(tickets_today) + 1):
        cote = round(t["matches"][0]["cote_jouee"] * t["matches"][1]["cote_jouee"] * t["matches"][2]["cote_jouee"], 2)
        print(f"  T{i}: {' + '.join(m['home'] for m in t['matches'])} → @{cote}")

    today_fmt = today.strftime("%d/%m")
    now_hour = get_paris_now().strftime("%Hh%M")
    subject = f"⚽ STRATÉGIE OFFICIELLE UNIBET · +2 GAGNANT · {today_fmt} à {now_hour}"
    html = build_full_html(tickets_today, tickets_tomorrow, mise=mise)

    # Sauvegarde locale / GitHub Pages
    try:
        os.makedirs("docs", exist_ok=True)
        with open("docs/email.html", "w", encoding="utf-8") as f_out:
            f_out.write(html)
        with open("docs/mail.html", "w", encoding="utf-8") as f_out2:
            f_out2.write(html)
        print("[SAFE] docs/email.html et docs/mail.html mis à jour !")
    except Exception as e:
        print(f"[WARN] Erreur écriture docs/email.html : {e}")

    send_email(html, subject)
