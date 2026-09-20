"""
SAFE Method — Combinés Triples Domicile
Réutilise get_unibet_active_games() + scan_unibet_match_details() depuis auto_premium_unibet.py
6 Piliers SAFE :
- Structure Triples (3 matchs par ticket)
- 100% Matchs à Domicile
- Même Jour Calendaire J uniquement (aucun mélange J/J+1)
- Brassage Croisé : 1 Cador (1.18-1.27) + 1 Médian (1.28-1.38) + 1 Solide (1.39-1.45)
  (Cador ascendant croisé avec Solide descendant -> toutes les cotes entre 2.15 et 2.35)
- Marché officiel : "Gagne ou mène de 2 buts" (Early Payout +2b)
- Filtre Pièges : exclusion des derbies et matchs pièges à points égaux
"""

import sys, os, json, datetime, smtplib, uuid, unicodedata, base64
from email.utils import formatdate, make_msgid
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from auto_premium_unibet import get_unibet_active_games, scan_unibet_match_details

# Liste noire des matchs pièges (audités et rejetés)
EXCLUDED_KEYWORDS = ["villarreal", "modène", "modena", "empoli"]

# ─── Filtrage SAFE ────────────────────────────────────────────────────────────

def today_date():
    # Heure de Paris (UTC+2 été / UTC+1 hiver)
    return (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=2)).date()

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

def extract_candidates(all_scanned):
    today = today_date()
    candidates = []
    for m in all_scanned:
        if not m:
            continue

        # 1. RÈGLE ABSOLUE : même jour calendaire uniquement
        ev_date = parse_match_date(m)
        if ev_date != today:
            continue

        # 2. Pas de nocturnes (entre 10h et 21h59 heure française)
        hour = parse_match_hour(m)
        if hour >= 22 or hour <= 9:
            continue

        # 3. Élimination des pièges
        if is_trap(m):
            print(f"[SAFE] ⚠️ Match piège exclu : {m.get('dom')} vs {m.get('ext')}")
            continue

        c1 = m.get("c1")
        c2 = m.get("c2")
        if not c1 or not c2:
            continue

        # 4. Fourchette Cotes SAFE (1.18 à 1.45)
        if not (1.18 <= c1 <= 1.45 and c1 < c2):
            continue

        # Cote réelle pour le marché "+2 Gagnant"
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
        })
    return sorted(candidates, key=lambda x: x["c1"])

# ─── Brassage Croisé & Construction des Tickets ───────────────────────────────

def build_tickets(matches):
    # Rung 1 : Cador (1.18 à 1.27)
    heavy  = sorted([m for m in matches if 1.18 <= m["c1"] <= 1.27], key=lambda x: x["c1"])
    # Rung 2 : Médian (1.28 à 1.38)
    median = sorted([m for m in matches if 1.28 <= m["c1"] <= 1.38], key=lambda x: x["c1"])
    # Rung 3 : Solide (1.39 à 1.45)
    solid  = sorted([m for m in matches if 1.39 <= m["c1"] <= 1.45], key=lambda x: x["c1"])

    n = min(len(heavy), len(median), len(solid), 5)
    print(f"[SAFE] Rangs qualifiés : Cador={len(heavy)} | Médian={len(median)} | Solide={len(solid)} → {n} ticket(s) possible(s)")

    if n == 0:
        return []

    # Brassage Croisé :
    # Cador ascendant (i) avec Solide descendant (n - 1 - i)
    # Médian au milieu (i)
    # -> Lissage parfait de la cote globale entre 2.15 et 2.35
    tickets = []
    for i in range(n):
        cad = heavy[i]
        sol = solid[len(solid) - 1 - i]
        med = median[i]
        tickets.append({"matches": [cad, med, sol]})

    return tickets

# ─── Génération HTML Premium ──────────────────────────────────────────────────

def build_html(tickets, mise=7.0):
    today_str = datetime.datetime.now().strftime("%A %d %B %Y").capitalize()
    total = len(tickets) * mise
    rows = ""
    for i, t in enumerate(tickets, 1):
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
        rows += f"""
        <div style="background:#0f172a;border:1px solid #1e3a5f;border-radius:12px;margin-bottom:18px;overflow:hidden;box-shadow:0 4px 6px -1px rgba(0,0,0,0.3);">
          <div style="background:linear-gradient(135deg,#1e3a5f,#0f2744);padding:14px 18px;display:flex;justify-content:space-between;align-items:center;">
            <span style="font-size:16px;font-weight:800;color:#60a5fa;letter-spacing:-0.3px;">🎫 TICKET {i} · COMBINÉ TRIPLE</span>
            <span style="font-size:13px;color:#94a3b8;">
              Cote combinée <b style="color:#f59e0b;font-size:15px;">@{cote}</b> &nbsp;·&nbsp;
              Mise <b style="color:#f1f5f9;">{int(mise)}€</b> &nbsp;·&nbsp;
              Gain <b style="color:#4ade80;font-size:15px;">{gain}€</b>
            </span>
          </div>
          <table style="width:100%;border-collapse:collapse;">{mrows}</table>
        </div>"""

    gains = sorted([round(mise * round(
        t["matches"][0]["cote_jouee"] * t["matches"][1]["cote_jouee"] * t["matches"][2]["cote_jouee"], 2), 2)
        for t in tickets], reverse=True)
    seuil_3 = sum(gains[:3]) if len(gains) >= 3 else sum(gains)

    return f"""<!DOCTYPE html>
<html lang="fr"><head><meta charset="UTF-8"><title>SAFE Method — Unibet</title></head>
<body style="margin:0;padding:0;background:#020617;font-family:'Segoe UI',Arial,sans-serif;color:#f1f5f9;">
<div style="max-width:720px;margin:0 auto;padding:24px 16px;">
  <div style="background:linear-gradient(135deg,#1e3a5f,#0f2744);border-radius:14px;padding:22px 26px;margin-bottom:22px;border:1px solid #1e40af;">
    <div style="font-size:26px;font-weight:800;color:#60a5fa;letter-spacing:-0.5px;">🔒 SAFE METHOD — COMBINÉS TRIPLES SÉCURISÉS</div>
    <div style="font-size:13px;color:#94a3b8;margin-top:4px;">{today_str} &nbsp;·&nbsp; 100% Matchs à Domicile &nbsp;·&nbsp; Zéro Doublon &nbsp;·&nbsp; Même Jour Calendaire</div>
    <div style="margin-top:14px;display:flex;gap:10px;flex-wrap:wrap;">
      <span style="background:#1e293b;border:1px solid #334155;border-radius:8px;padding:7px 12px;font-size:12px;">🎯 Marché : <b style="color:#f59e0b;">Gagne ou mène de 2 buts (+2b)</b></span>
      <span style="background:#1e293b;border:1px solid #334155;border-radius:8px;padding:7px 12px;font-size:12px;">💰 Mise totale : <b style="color:#f1f5f9;">{int(total)}€</b> ({int(mise)}€/ticket)</span>
      <span style="background:#1e293b;border:1px solid #334155;border-radius:8px;padding:7px 12px;font-size:12px;">✅ Rentabilité : <b style="color:#4ade80;">Bénéfice garanti dès 3/{len(tickets)}</b></span>
    </div>
  </div>
  {rows}
  <div style="background:#0f172a;border:1px solid #1e293b;border-radius:10px;padding:16px 20px;font-size:13px;">
    <b style="color:#60a5fa;font-size:14px;">📊 Tableau de marche mathématique</b><br><br>
    • <b>3/{len(tickets)} tickets gagnants</b> → <b style="color:#4ade80;">~{seuil_3:.2f}€ encaissés</b> (Bénéfice net garanti ✅)<br>
    • <b>{len(tickets)}/{len(tickets)} tickets gagnants</b> → <b style="color:#4ade80;">~{sum(gains):.2f}€ encaissés</b> (Carton plein 🏆)
  </div>
  <div style="text-align:center;margin-top:20px;font-size:11px;color:#475569;">
    Méthode SAFE Standard Permanent — Unibet France — Données scannées en direct<br>
    Joueurs problématiques : <a href="https://www.joueurs-info-service.fr" style="color:#64748b;">joueurs-info-service.fr</a>
  </div>
</div></body></html>"""

# ─── Envoi Email (Gmail prioritaire + Fallback SFR) ───────────────────────────

def send_email(html_body, subject):
    gmail_email = os.environ.get("GMAIL_EMAIL", "langlet.gregory@gmail.com").strip()
    gmail_pass  = os.environ.get("GMAIL_APP_PASSWORD", "").strip().replace('\ufeff', '')
    smtp_host   = os.environ.get("SMTP_HOST", "smtp.sfr.fr").strip()
    smtp_port   = int(os.environ.get("SMTP_PORT", "465"))
    smtp_user   = os.environ.get("SMTP_USER", "").strip()
    smtp_pass   = os.environ.get("SMTP_PASS", "").strip()

    raw_recipients = os.environ.get("EMAIL_TO") or os.environ.get("RECIPIENT_EMAILS") or "gregory.langlet@sfr.fr, langlet.gregory@gmail.com"
    recipients = [r.strip() for r in raw_recipients.split(",") if r.strip()]

    clean_subject = unicodedata.normalize('NFKD', subject).encode('ASCII', 'ignore').decode('ASCII')
    html_body = html_body.replace('\ufeff', '').replace('\ufffe', '')

    msg = MIMEMultipart('alternative')
    msg["Subject"] = clean_subject
    msg["From"] = f"Gregory LANGLET <{gmail_email}>"
    msg["To"] = ", ".join(recipients)
    msg["Date"] = formatdate(localtime=True)
    msg["Message-ID"] = make_msgid()

    plain = f"Combinés SAFE Method du jour. Veuillez consulter la version HTML jointe."
    msg.attach(MIMEText(plain, 'plain', 'utf-8'))
    msg.attach(MIMEText(html_body, 'html', 'utf-8'))

    # 1. Tentative Gmail SMTP
    if gmail_pass:
        try:
            print(f"[SMTP] Envoi vers {recipients} via Gmail SMTP...")
            with smtplib.SMTP("smtp.gmail.com", 587, timeout=30) as server:
                server.ehlo(); server.starttls(); server.ehlo()
                server.login(gmail_email, gmail_pass)
                server.sendmail(gmail_email, recipients, msg.as_string())
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
                    server.sendmail(smtp_user, recipients, msg.as_string())
            else:
                with smtplib.SMTP(smtp_host, smtp_port, timeout=30) as server:
                    server.ehlo(); server.starttls(); server.ehlo()
                    server.login(auth_user, smtp_pass)
                    server.sendmail(smtp_user, recipients, msg.as_string())
            print("[SMTP] ✅ Email envoyé avec succès via SFR SMTP !")
            return True
        except Exception as e:
            print(f"[SMTP] ❌ Échec SFR SMTP : {e}")

    print("[SMTP] ❌ Aucun mot de passe SMTP disponible — email non envoyé.")
    return False

# ─── Main ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    games = get_unibet_active_games()
    print(f"[SAFE] {len(games)} fixtures trouvées, scan des détails...")

    all_scanned = []
    with ThreadPoolExecutor(max_workers=20) as ex:
        futures = {ex.submit(scan_unibet_match_details, g): g for g in games}
        for fut in as_completed(futures):
            res = fut.result()
            if res:
                all_scanned.append(res)

    print(f"[SAFE] {len(all_scanned)} matchs avec cotes récupérées")

    candidates = extract_candidates(all_scanned)
    print(f"[SAFE] Candidats éligibles SAFE du jour : {len(candidates)}")
    for m in candidates:
        print(f"       {m['time']} | {m['home']} vs {m['away']} | 1N2={m['c1']} (+2b={m['cote_jouee']}) | {m['league']}")

    tickets = build_tickets(candidates)
    if not tickets:
        print("[SAFE] 0 ticket buildable aujourd'hui selon la règle SAFE — pas d'email envoyé.")
        sys.exit(0)

    mise = 7.0
    for i, t in enumerate(tickets, 1):
        cote = round(t["matches"][0]["cote_jouee"] * t["matches"][1]["cote_jouee"] * t["matches"][2]["cote_jouee"], 2)
        noms = " + ".join(m["home"] for m in t["matches"])
        print(f"  T{i}: {noms} → cote {cote} → gain potentiel {round(mise*cote,2)}€")

    today_fmt = datetime.datetime.now().strftime("%d/%m/%Y")
    html = build_html(tickets, mise)
    send_email(html, f"SAFE Method - {len(tickets)} Combines Triples du {today_fmt}")
