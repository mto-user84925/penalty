import os, sys, json, re, time
from datetime import datetime, timezone
import requests
from difflib import SequenceMatcher

TEAM_ALIASES = {
    "potriglias": ["iraklis", "triglias", "potrigliasiraklis"],
    "iraklis": ["potriglias", "triglias"],
    "unicraiova": ["craiova", "csuniversitateacraiova", "ucraiova"],
    "universitcluj": ["universitateacluj", "ucluj"],
    "fcnarva": ["narvatrans", "transnarva", "narva"],
    "palerme": ["palermo"],
    "dlimache": ["deporteslimache", "limache"],
    "vitoriaba": ["vitoria"],
    "mantafc": ["manta"],
    "nommeunite": ["nommeunited"],
    "aekathenes": ["aekathens", "aek"],
    "intermilan": ["inter"],
}

STOPWORDS = {'fc', 'cf', 'sc', 'cd', 'cs', 'de', 'la', 'le', 'el', 'club', 'deportes', 'real', 'city', 'united', 'athletic', 'sporting'}

def clean_name(x):
    if not x: return ""
    return re.sub(r'[^a-z0-9]', '', x.lower())

def sim_score(a, b):
    ca, cb = clean_name(a), clean_name(b)
    if not ca or not cb: return 0.0
    if ca == cb: return 1.0
    if ca in cb or cb in ca: return 0.90
    
    # Check aliases
    for k, alias_list in TEAM_ALIASES.items():
        if k in ca or ca in k:
            for al in alias_list:
                if al in cb or cb in al: return 0.92
        if k in cb or cb in k:
            for al in alias_list:
                if al in ca or ca in al: return 0.92

    # Distinctive keyword token match (words with 4+ letters)
    words_a = [w for w in re.split(r'[^a-z0-9]+', str(a).lower()) if len(w) >= 4 and w not in STOPWORDS]
    words_b = [w for w in re.split(r'[^a-z0-9]+', str(b).lower()) if len(w) >= 4 and w not in STOPWORDS]
    if set(words_a).intersection(set(words_b)):
        return 0.85

    return SequenceMatcher(None, ca, cb).ratio()

def sync():
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    data_path = os.path.join(base_dir, "docs", "data.json")
    with open(data_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    from datetime import timedelta
    now = datetime.now()
    dates_to_check = [
        (now - timedelta(days=1)).strftime("%Y%m%d"),
        now.strftime("%Y%m%d")
    ]
    events = []
    for d_str in dates_to_check:
        ls_url = f"https://prod-public-api.livescore.com/v1/api/app/date/soccer/{d_str}/0"
        print(f"Fetching LiveScore for {d_str}...")
        try:
            r = requests.get(ls_url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
            if r.status_code == 200:
                for st in r.json().get("Stages", []):
                    for m_ev in st.get("Events", []):
                        eps = str(m_ev.get("Eps", ""))
                        tr1 = m_ev.get("Tr1")
                        tr2 = m_ev.get("Tr2")
                        trh1 = m_ev.get("Trh1")
                        trh2 = m_ev.get("Trh2")
                        h_sc = int(tr1) if tr1 is not None and str(tr1).isdigit() else None
                        a_sc = int(tr2) if tr2 is not None and str(tr2).isdigit() else None
                        h_ht_sc = int(trh1) if trh1 is not None and str(trh1).isdigit() else None
                        a_ht_sc = int(trh2) if trh2 is not None and str(trh2).isdigit() else None
                        t1 = m_ev.get("T1", [{}])[0].get("Nm", "")
                        t2 = m_ev.get("T2", [{}])[0].get("Nm", "")
                        events.append({
                            "home": t1,
                            "away": t2,
                            "eps": eps,
                            "h_sc": h_sc,
                            "a_sc": a_sc,
                            "h_ht_sc": h_ht_sc,
                            "a_ht_sc": a_ht_sc,
                        })
        except Exception as e:
            print(f"Error fetching LiveScore {d_str}: {e}")

    print(f"Loaded {len(events)} LiveScore events.")

    matches = data.get("matches_today", [])
    updated_count = 0

    # ponytail: Jours éligibles dynamiques (veille + aujourd'hui) pour couvrir les matchs de nuit sans matcher le futur
    DAYS_FR = ["Lun.", "Mar.", "Mer.", "Jeu.", "Ven.", "Sam.", "Dim."]
    today_day = DAYS_FR[now.weekday()]
    yesterday_day = DAYS_FR[(now.weekday() - 1) % 7]
    eligible_days = [yesterday_day, today_day]

    for m in matches:
        dom = m.get("home", "")
        ext = m.get("away", "")
        fav_team = m.get("fav_team", dom)
        is_fav_home = (fav_team == dom)
        odds_val = m.get("odds", 1.50)

        m_time = m.get("time", "")
        has_day = any(d in m_time for d in DAYS_FR)
        if has_day and not any(d in m_time for d in eligible_days):
            continue

        best_ev = None
        best_sim = 0.0
        for ev in events:
            s1 = sim_score(dom, ev["home"])
            s2 = sim_score(ext, ev["away"])
            if s1 >= 0.65 and s2 >= 0.65:
                sim = (s1 + s2) / 2.0
                if sim > best_sim:
                    best_sim = sim
                    best_ev = ev

        if best_ev and best_sim >= 0.75 and best_ev["h_sc"] is not None and best_ev["a_sc"] is not None:
            h_sc = best_ev["h_sc"]
            a_sc = best_ev["a_sc"]
            eps = best_ev["eps"]

            market = m.get("market", "FAV_1N2")
            old_sc = m.get("score_display")
            old_stat = m.get("status")

            m["home_score"] = h_sc
            m["away_score"] = a_sc
            m["score_display"] = f"{h_sc} - {a_sc}"

            if eps in ["FT", "AET", "AP"]:
                m["status"] = "FINISHED"
                m["is_finished"] = True
                m["is_live"] = False
                m["minute"] = "Terminé"
                if market == "OVER_15":
                    is_won = (h_sc + a_sc >= 2)
                    m["selection_status"] = "WON_FINAL" if is_won else "LOST"
                    m["profit"] = round(odds_val - 1.0, 2) if is_won else -1.0
                elif market == "BTTS":
                    is_won = (h_sc >= 1 and a_sc >= 1)
                    m["selection_status"] = "WON_FINAL" if is_won else "LOST"
                    m["profit"] = round(odds_val - 1.0, 2) if is_won else -1.0
                elif market == "HALF_MT2":
                    h_ht = best_ev.get("h_ht_sc")
                    a_ht = best_ev.get("a_ht_sc")
                    if h_ht is not None and a_ht is not None:
                        g_mt1 = h_ht + a_ht
                        g_mt2 = (h_sc - h_ht) + (a_sc - a_ht)
                        is_won = (g_mt2 > g_mt1)
                        m["selection_status"] = "WON_FINAL" if is_won else "LOST"
                        m["profit"] = round(odds_val - 1.0, 2) if is_won else -1.0
                        m["score_display"] = f"{h_sc} - {a_sc} (MT: {h_ht}-{a_ht})"
                    else:
                        is_won = (h_sc + a_sc >= 2)
                        m["selection_status"] = "WON_FINAL" if is_won else "LOST"
                        m["profit"] = round(odds_val - 1.0, 2) if is_won else -1.0
                else:
                    fav_goals = h_sc if is_fav_home else a_sc
                    dog_goals = a_sc if is_fav_home else h_sc
                    lead2 = (fav_goals - dog_goals >= 2)
                    win = (fav_goals > dog_goals)
                    was_lead2 = (m.get("selection_status") == "WON_LEAD2")
                    if lead2 or was_lead2:
                        m["selection_status"] = "WON_LEAD2"
                        m["profit"] = round(odds_val - 1.0, 2)
                    elif win:
                        m["selection_status"] = "WON_FINAL"
                        m["profit"] = round(odds_val - 1.0, 2)
                    else:
                        m["selection_status"] = "LOST"
                        m["profit"] = -1.0
            elif eps in ["NS", "CANC", "POST", "DEFD", "INT"]:
                pass
            else:
                m["status"] = "LIVE"
                m["is_live"] = True
                m["is_finished"] = False
                m["minute"] = "Mi-temps" if eps == "HT" else (eps + ("'" if eps.isdigit() else ""))

                if market == "OVER_15":
                    if h_sc + a_sc >= 2:
                        m["selection_status"] = "WON_FINAL"
                        m["profit"] = round(odds_val - 1.0, 2)
                    else:
                        m["selection_status"] = "IN_PROGRESS"
                        m["profit"] = 0.0
                elif market == "BTTS":
                    if h_sc >= 1 and a_sc >= 1:
                        m["selection_status"] = "WON_FINAL"
                        m["profit"] = round(odds_val - 1.0, 2)
                    else:
                        m["selection_status"] = "IN_PROGRESS"
                        m["profit"] = 0.0
                elif market == "HALF_MT2":
                    h_ht = best_ev.get("h_ht_sc")
                    a_ht = best_ev.get("a_ht_sc")
                    if h_ht is not None and a_ht is not None:
                        m["score_display"] = f"{h_sc} - {a_sc} (MT: {h_ht}-{a_ht})"
                    m["selection_status"] = "IN_PROGRESS"
                    m["profit"] = 0.0
                else:
                    fav_goals = h_sc if is_fav_home else a_sc
                    dog_goals = a_sc if is_fav_home else h_sc
                    lead2 = (fav_goals - dog_goals >= 2)
                    was_lead2 = (m.get("selection_status") == "WON_LEAD2")
                    if lead2 or was_lead2:
                        m["selection_status"] = "WON_LEAD2"
                        m["profit"] = round(odds_val - 1.0, 2)
                    else:
                        m["selection_status"] = "IN_PROGRESS"
                        m["profit"] = 0.0

            if old_sc != m["score_display"] or old_stat != m["status"]:
                updated_count += 1
                print(f"Updated {dom} vs {ext}: {m['score_display']} [{m['status']} - {m['minute']}] ({m['selection_status']})")

    match_lookup = {}
    for m in matches:
        match_lookup[(clean_name(m.get("home", "")), clean_name(m.get("away", "")))] = m

    def _update_combos(combo_list, default_stake=3.0):
        for c in combo_list:
            if c.get("ticket_status") in ["WON", "LOST"]:
                continue
            m1 = c.get("m1", {})
            m2 = c.get("m2", {})
            k1 = (clean_name(m1.get("home", "")), clean_name(m1.get("away", "")))
            k2 = (clean_name(m2.get("home", "")), clean_name(m2.get("away", "")))

            if k1 in match_lookup:
                src = match_lookup[k1]
                m1["score_display"] = src.get("score_display", m1.get("score_display"))
                m1["minute"] = src.get("minute", m1.get("minute"))
                m1["status"] = src.get("status", m1.get("status"))
                m1["selection_status"] = src.get("selection_status", m1.get("selection_status"))

            if k2 in match_lookup:
                src = match_lookup[k2]
                m2["score_display"] = src.get("score_display", m2.get("score_display"))
                m2["minute"] = src.get("minute", m2.get("minute"))
                m2["status"] = src.get("status", m2.get("status"))
                m2["selection_status"] = src.get("selection_status", m2.get("selection_status"))

            s1 = m1.get("selection_status", "PENDING")
            s2 = m2.get("selection_status", "PENDING")
            w1 = s1.startswith("WON")
            w2 = s2.startswith("WON")
            l1 = (s1 == "LOST")
            l2 = (s2 == "LOST")
            st1 = m1.get("status")
            st2 = m2.get("status")

            comb_odds = c.get("odds", 2.0)
            c_stake = c.get("default_stake", default_stake)

            if w1 and w2:
                c["ticket_status"] = "WON"
                c["profit_unit"] = round(comb_odds - 1.0, 2)
                c["profit_eur"] = round(c["profit_unit"] * c_stake, 2)
            elif l1 or l2:
                c["ticket_status"] = "LOST"
                c["profit_unit"] = -1.0
                c["profit_eur"] = round(-c_stake, 2)
            elif st1 == "LIVE" or st2 == "LIVE" or s1 == "IN_PROGRESS" or s2 == "IN_PROGRESS":
                c["ticket_status"] = "LIVE"
                c["profit_unit"] = 0.0
                c["profit_eur"] = 0.0
            else:
                c["ticket_status"] = "PENDING"
                c["profit_unit"] = 0.0
                c["profit_eur"] = 0.0

        c_won = sum(1 for c in combo_list if c.get("ticket_status") == "WON")
        c_lost = sum(1 for c in combo_list if c.get("ticket_status") == "LOST")
        c_live = sum(1 for c in combo_list if c.get("ticket_status") == "LIVE")
        c_upc = sum(1 for c in combo_list if c.get("ticket_status") == "PENDING")
        c_dec = c_won + c_lost
        c_profit_u = sum(c.get("profit_unit", 0.0) for c in combo_list)
        c_wr = round((c_won / c_dec * 100), 1) if c_dec > 0 else 0.0
        c_roi = round((c_profit_u / c_dec * 100), 2) if c_dec > 0 else 0.0

        return {
            "total_combos": len(combo_list),
            "decided_combos": c_dec,
            "won": c_won,
            "lost": c_lost,
            "live": c_live,
            "upcoming": c_upc,
            "default_stake": default_stake,
            "win_rate": c_wr,
            "profit_units": round(c_profit_u, 2),
            "profit_eur": round(c_profit_u * default_stake, 2),
            "roi_pct": c_roi
        }

    combos_m1 = data.get("combos_today", [])
    data["combos_summary"] = _update_combos(combos_m1)

    combos_m2 = data.get("methode2_combos", [])
    if combos_m2:
        data["methode2_summary"] = _update_combos(combos_m2)

    combos_m3 = data.get("methode3_combos", [])
    if combos_m3:
        data["methode3_summary"] = _update_combos(combos_m3)

    c_won = data["combos_summary"]["won"]
    c_lost = data["combos_summary"]["lost"]
    c_live = data["combos_summary"]["live"]
    c_upc = data["combos_summary"]["upcoming"]

    won_c = sum(1 for x in matches if x.get("selection_status", "").startswith("WON"))
    lost_c = sum(1 for x in matches if x.get("selection_status") == "LOST")
    live_c = sum(1 for x in matches if x.get("status") == "LIVE")
    upc_c = sum(1 for x in matches if x.get("status") == "UPCOMING")
    profit_u = sum(x.get("profit", 0.0) for x in matches)
    decided_c = won_c + lost_c
    wr = round((won_c / decided_c * 100), 1) if decided_c > 0 else 0.0
    roi = round((profit_u / decided_c * 100), 2) if decided_c > 0 else 0.0

    data["summary"] = {
        "total_matches": len(matches),
        "decided_matches": decided_c,
        "won": won_c,
        "lost": lost_c,
        "live": live_c,
        "upcoming": upc_c,
        "win_rate": wr,
        "profit_units": round(profit_u, 2),
        "roi_pct": roi,
        "last_updated": datetime.now(timezone.utc).isoformat()
    }

    with open(data_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"Sync complete. Updated {updated_count} matches. Combos: {c_won}W {c_lost}L {c_live}LIVE {c_upc}UPC.")
    return True, updated_count

if __name__ == "__main__":
    sync()
