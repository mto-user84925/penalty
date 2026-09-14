# ==============================================================================
# ANALYZE.PY V13 — AFFICHAGE OBLIGATOIRE DES 10 DERNIERS SCORES REELS (DOM & EXT)
# ==============================================================================

import sys, os, requests, json, unicodedata, re, math, statistics
from difflib import SequenceMatcher
from concurrent.futures import ThreadPoolExecutor


BASE = "https://www.adamchoi.co.uk"
BASE_WIDGET = "https://api.choistats.com/api/widget"

HEADERS = {
    "Authorization-Client": "ADAMCHOI.CO.UK",
    "Referer": "https://www.adamchoi.co.uk/",
    "User-Agent": "Mozilla/5.0"
}
WIDGET_HEADERS = {
    "X-AdamChoi-Api-Token": "45834886-68b3-11eb-99f4-9e36325824ad",
    "Referer": "https://www.adamchoi.co.uk/",
    "User-Agent": "Mozilla/5.0"
}

# Dictionnaire des équivalences / traductions Unibet FR -> AdamChoi EN
ALIASES = {
    "saint": "st",
    "vienne": "vienna",
    "prague": "praha",
    "varsovie": "warsaw",
    "lisbonne": "lisbon",
    "bucarest": "bucharest",
    "athenes": "athens",
    "etoile rouge": "red star",
    "depor": "deportivo",
    "dep": "deportivo",
    "atl": "atletico",
    "uni": "universidad",
    "indep": "independiente",
    "sp": "sporting",
    # Abréviations FR/EN étendues
    "wolverhampton": "wolves",
    "manchester": "man",
    "united": "utd",
    "munich": "munchen",
    "paris": "psg",
    "sheffield": "sheff",
    "birmingham": "birmingham",
    "deportivo": "dep",
    "universidad": "uni",
    "atletico": "atl",
    # PSG / clubs parisiens
    "germain": "",       # "Saint-Germain" → supprimé → "psg" seul suffit
    # Clubs Espagnols
    "real": "real",
    "bilbao": "bilbao",
    "sociedad": "sociedad",
    "valladolid": "valladolid",
    "betis": "betis",
    # Clubs Allemands
    "borussia": "bvb",
    "dortmund": "bvb",
    "leverkusen": "leverkusen",
    "werder": "werder",
    "frankfurt": "eintracht",
    "hoffenheim": "hoffenheim",
    "monchengladbach": "gladbach",
    "gladbach": "gladbach",
    # Clubs Anglais
    "tottenham": "spurs",
    "hotspur": "spurs",
    "newcastle": "newcastle",
    "brighton": "brighton",
    "brentford": "brentford",
    "westham": "west ham",
    "aston": "aston",
    "crystal": "crystal",
    # Clubs Italiens
    "juventus": "juve",
    "napoli": "napoli",
    "internazionale": "inter",
    "lazio": "lazio",
    "fiorentina": "fiorentina",
    # Clubs Portugais
    "benfica": "benfica",
    "porto": "porto",
    "sporting": "sporting",
    # Normalisation clubs FR spéciaux (Unibet vs AdamChoi)
    "lyonnais": "ol",      # "Olympique Lyonnais" → "olympique ol" ≈ "Lyon" via similarity
    "lyonnaise": "ol",
    "marseillais": "om",
    "marseille": "om",
    "lille": "losc",
    "rennes": "rennes",
    "lens": "lens",
    "nantes": "nantes",
    "nice": "nice",
    "toulouse": "toulouse",
    # Clubs Néerlandais / Belges
    "ajax": "ajax",
    "feyenoord": "feyenoord",
    "psv": "psv",
    "anderlecht": "anderlecht",
    # Clubs Turcs
    "galatasaray": "galatasaray",
    "fenerbahce": "fenerbahce",
    "besiktas": "besiktas",
    "trabzonspor": "trabzonspor",
}

def clean_str(s):
    if not s: return ""
    s = unicodedata.normalize('NFKD', s).encode('ASCII', 'ignore').decode('ASCII')
    s = s.lower().replace("-", " ").replace(".", " ").replace("_", " ").replace("/", " ")
    words = s.split()
    cleaned = []
    for w in words:
        if w in ["fc", "bk", "if", "sc", "ac", "fk", "cd", "sk", "cf", "sv", "v", "vs", "contre", "pec", "ca", "csd", "acs", "msk", "kv"]:
            continue
        cleaned.append(ALIASES.get(w, w))
    return " ".join(cleaned)

def similarity(a, b):
    a_c = clean_str(a)
    b_c = clean_str(b)
    if not a_c or not b_c:
        return 0.0
    if a_c == b_c:
        return 1.0
    if a_c in b_c or b_c in a_c:
        return 0.95
    tokens_a = set(a_c.split())
    tokens_b = set(b_c.split())
    if tokens_a and tokens_b and (tokens_a.issubset(tokens_b) or tokens_b.issubset(tokens_a)):
        return 0.90
    return SequenceMatcher(None, a_c, b_c).ratio()

def fetch(url, headers=HEADERS):
    try:
        r = requests.get(url, headers=headers, timeout=8)
        res = r.json() if r.status_code == 200 else {}
        return res if isinstance(res, (dict, list)) else {}
    except Exception:
        return {}

# Mapping pays Unibet FR → pays AdamChoi EN pour le filtrage par pays
COUNTRY_MAP_FR_EN = {
    "angleterre": "England", "france": "France", "espagne": "Spain",
    "allemagne": "Germany", "italie": "Italy", "portugal": "Portugal",
    "belgique": "Belgium", "pays bas": "Netherlands", "hollande": "Netherlands",
    "ecosse": "Scotland", "turquie": "Turkey", "grece": "Greece",
    "russie": "Russia", "ukraine": "Ukraine", "pologne": "Poland",
    "suede": "Sweden", "norvege": "Norway", "danemark": "Denmark",
    "finlande": "Finland", "suisse": "Switzerland", "autriche": "Austria",
    "republique tcheque": "Czech Republic", "slovaquie": "Slovakia",
    "roumanie": "Romania", "bulgarie": "Bulgaria", "serbie": "Serbia",
    "croatie": "Croatia", "slovenie": "Slovenia", "hongrie": "Hungary",
    "irlande": "Ireland", "irlande du nord": "Northern Ireland",
    "pays de galles": "Wales", "mexique": "Mexico", "bresil": "Brazil",
    "argentine": "Argentina", "chili": "Chile", "colombie": "Colombia",
    "etats unis": "USA", "japon": "Japan", "coree du sud": "South Korea",
    "chine": "China", "australie": "Australia", "israel": "Israel",
    "kazakhstan": "Kazakhstan", "azerbaidjan": "Azerbaijan",
    "albanie": "Albania", "macedoine": "North Macedonia",
    "lettonie": "Latvia", "lituanie": "Lithuania", "estonie": "Estonia",
    "islande": "Iceland", "armenie": "Armenia", "georgie": "Georgia",
    "chypre": "Cyprus", "malte": "Malta", "luxembourg": "Luxembourg",
    "bosnie": "Bosnia", "montenero": "Montenegro",
    # Amérique du Sud
    "equateur": "Ecuador", "uruguay": "Uruguay", "perou": "Peru",
    "venezuela": "Venezuela", "bolivie": "Bolivia", "paraguay": "Paraguay",
    # Afrique
    "afrique du sud": "South Africa", "maroc": "Morocco", "egypte": "Egypt",
    "tunisie": "Tunisia", "algerie": "Algeria", "nigeria": "Nigeria",
    "senegal": "Senegal", "ghana": "Ghana",
    # Asie / reste
    "arabie saoudite": "Saudi Arabia", "emirats": "UAE", "inde": "India",
    "iran": "Iran", "irak": "Iraq",
}

def _extract_country_en(unibet_league: str) -> str:
    """Extrait et traduit le pays depuis le champ league Unibet (ex: 'Angleterre • Championship' -> 'England')"""
    if not unibet_league:
        return ""
    pays_fr = unibet_league.split("•")[0].strip().lower()
    pays_fr = unicodedata.normalize('NFKD', pays_fr).encode('ASCII', 'ignore').decode('ASCII')
    return COUNTRY_MAP_FR_EN.get(pays_fr, "")

def find_fixture_fuzzy(home_query, away_query, fixtures_data=None, match_dt=None, unibet_league=None):
    if not fixtures_data or not isinstance(fixtures_data, dict):
        fixtures_data = fetch(f"{BASE}/scripts/data/json/scripts/getFixturesJsonForSearch.php?clflc=abc&timezoneOffset=0")
    
    target_country = _extract_country_en(unibet_league) if unibet_league else ""
    best_match = None
    best_score = 0.0
    match_ts = match_dt.timestamp() if match_dt else None

    def _search(fixtures_data, country_filter):
        nonlocal best_match, best_score
        for d in fixtures_data.get("dates", []):
            for lg in d.get("leagues", []):
                # Filtrage par pays si disponible
                if country_filter:
                    ac_country = (lg.get("country") or "").strip()
                    if ac_country and ac_country.lower() != country_filter.lower():
                        continue

                for fx in lg.get("fixtures", []):
                    h_name = fx.get("hometeam", "")
                    a_name = fx.get("awayteam", "")

                    if match_ts:
                        fx_ts_ms = fx.get("datetimestamp")
                        if fx_ts_ms:
                            try:
                                fx_ts = float(fx_ts_ms) / 1000.0
                                if abs(match_ts - fx_ts) / 3600.0 > 36.0:
                                    continue
                            except Exception:
                                pass

                    score_h = similarity(home_query, h_name)
                    score_a = similarity(away_query, a_name)
                    combined = (score_h + score_a) / 2.0

                    if combined > best_score:
                        best_score = combined
                        fx_id = fx.get("externalId") or fx.get("externalid") or fx.get("id")
                        best_match = (fx_id, h_name, a_name, lg.get("league"))

    # 1er passage : recherche dans le bon pays uniquement
    if target_country:
        _search(fixtures_data, target_country)

    # Fallback : si pas trouvé dans le pays → recherche globale toutes ligues
    if not best_match or best_score < 0.40:
        best_match = None
        best_score = 0.0
        _search(fixtures_data, "")

    if best_match and best_score >= 0.40:
        return best_match
    
    return None, None, None, None


ALIAS_MAP_SOFASCORE = {
    'Paris SG': 'Paris Saint-Germain',
    'AmaZulu': 'AmaZulu FC',
    'Durban City': 'Durban City FC',
    'Torque': 'Montevideo City Torque',
    'Coquimbo U.': 'Coquimbo Unido',
    'Orlando Pir.': 'Orlando Pirates',
    'Hap.Tel Aviv': 'Hapoel Tel Aviv',
    'C.A. Tigre': 'Tigres UANL',
    'Paide': 'Paide Linnameeskond',
    'FC Copenhague': 'FC København',
    'Debrecen': 'Debreceni VSC',
    'Sekhukhune': 'Sekhukhune United',
    'Siwelele': 'Siwelele FC',
    'Bragantino SP': 'Red Bull Bragantino',
    'Atletico MG': 'Atlético Mineiro',
    'Cerro Porteno': 'Cerro Porteño',
    'Atl. San Luis': 'Atlético San Luis',
    'FC Leon': 'Club León',
    'Dallas FC': 'FC Dallas',
    'Dep. Toluca': 'Deportivo Toluca',
    'Seattle': 'Seattle Sounders FC',
    'Chivas': 'CD Guadalajara',
    'Queretaro FC': 'Querétaro FC'
}

def fetch_sofascore_sample(query, is_home=True):
    try:
        from curl_cffi import requests as cf_requests
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        q = ALIAS_MAP_SOFASCORE.get(query, query)
        r = cf_requests.get(f"https://api.sofascore.com/api/v1/search/all?q={q}", impersonate="chrome120", headers=headers, timeout=4)
        if r.status_code == 200:
            teams = [x for x in r.json().get("results", []) if x.get("type") == "team"]
            if teams:
                tid = teams[0]["entity"]["id"]
                r2 = cf_requests.get(f"https://api.sofascore.com/api/v1/team/{tid}/events/last/0", impersonate="chrome120", headers=headers, timeout=4)
                if r2.status_code == 200:
                    events = sorted(r2.json().get("events", []), key=lambda x: x.get("startTimestamp", 0), reverse=True)
                    if is_home:
                        m_list = [e for e in events if e.get("homeTeam", {}).get("id") == tid][:10]
                    else:
                        m_list = [e for e in events if e.get("awayTeam", {}).get("id") == tid][:10]
                    
                    res_matches = []
                    for ev in m_list:
                        hs = ev.get("homeScore", {}).get("current", 0)
                        aws = ev.get("awayScore", {}).get("current", 0)
                        res_matches.append({
                            "homeGoals": hs, "homeGoalsFt": hs,
                            "awayGoals": aws, "awayGoalsFt": aws
                        })
                    return res_matches
    except Exception:
        pass
    return []


def analyze_pure_stats_20(home_query, away_query, fixtures_data=None, is_batch=False, match_dt=None, unibet_league=None, d_refs=None, m_unibet=None):
    ext_id, team_a, team_b, league = find_fixture_fuzzy(home_query, away_query, fixtures_data, match_dt=match_dt, unibet_league=unibet_league)

    if not ext_id or not team_a or not team_b:
        if is_batch:
            return {"score": 0, "score_o15": 0, "score_btts": 0, "score_penalty": 0, "ref_name": "Inconnu", "pen_per_match": 0.0, "peno_status": "FAIBLE"}
        print(f"❌ Match introuvable sur AdamChoi: {home_query} vs {away_query}")
        return None

    if not is_batch:
        print(f"🔍 ÉQUIPES DÉTECTÉES : '{team_a}' vs '{team_b}' ({league})\n")

    # Cherche l'arbitre désigné pour ce match dans le dict pré-chargé d_refs
    ref_info = (d_refs or {}).get(str(ext_id), {})
    ref_id = ref_info.get("refereeId")

    with ThreadPoolExecutor(max_workers=5) as ex:
        f_comp = ex.submit(fetch, f"{BASE}/scripts/data/json/scripts/pages/comparison/getComparisonStatsAsJson.php?clflc=abc&hometeam={team_a}&awayteam={team_b}&hometeamleague={league}&awayteamleague={league}&numrecentmatches=20")
        f_avg  = ex.submit(fetch, f"{BASE_WIDGET}/match/{ext_id}/team-averages?clflc=abc&token=45834886-68b3-11eb-99f4-9e36325824ad", WIDGET_HEADERS)
        f_res  = ex.submit(fetch, f"{BASE_WIDGET}/match/{ext_id}/recent-results?clflc=abc&token=45834886-68b3-11eb-99f4-9e36325824ad", WIDGET_HEADERS)
        f_ref  = ex.submit(fetch, f"{BASE}/scripts/data/json/scripts/pages/referees/getRefereeById.php?clflc=abc&refereeId={ref_id}") if ref_id else None

        comp  = f_comp.result()
        w_avg = f_avg.result()
        w_res = f_res.result()
        ref_career = f_ref.result() if f_ref else {}

    if not isinstance(comp, dict): comp = {}
    if not isinstance(w_avg, dict): w_avg = {}
    if not isinstance(w_res, dict): w_res = {}

    recent_h_all = comp.get("recentmatches", {}).get("homeall", []) if isinstance(comp.get("recentmatches"), dict) else []
    recent_a_all = comp.get("recentmatches", {}).get("awayall", []) if isinstance(comp.get("recentmatches"), dict) else []
    recent_h_dom = comp.get("recentmatches", {}).get("homehome", []) if isinstance(comp.get("recentmatches"), dict) else []
    recent_a_ext = comp.get("recentmatches", {}).get("awayaway", []) if isinstance(comp.get("recentmatches"), dict) else []

    if len(recent_h_dom) < 5 and isinstance(w_res, dict):
        recent_h_dom = (w_res.get("recentHomeAllResults") or []) or (w_res.get("recentHomeResults") or []) or recent_h_dom
    if len(recent_a_ext) < 5 and isinstance(w_res, dict):
        recent_a_ext = (w_res.get("recentAwayAllResults") or []) or (w_res.get("recentAwayResults") or []) or recent_a_ext

    h2h20 = comp.get("headtohead", []) if isinstance(comp.get("headtohead"), list) else []

    h_dom_w = w_avg.get("homeTeam", {}).get("home", {}) if isinstance(w_avg.get("homeTeam"), dict) else {}
    a_ext_w = w_avg.get("awayTeam", {}).get("away", {}) if isinstance(w_avg.get("awayTeam"), dict) else {}

    gf_a = h_dom_w.get("avgGoalsFor", 0.0)
    ga_a = h_dom_w.get("avgGoalsAg", 0.0)
    sot_a = h_dom_w.get("shotsOnTargetFor", 0.0)
    sota_a = h_dom_w.get("shotsOnTargetAg", 0.0)

    gf_b = a_ext_w.get("avgGoalsFor", 0.0)
    ga_b = a_ext_w.get("avgGoalsAg", 0.0)
    sot_b = a_ext_w.get("shotsOnTargetFor", 0.0)
    sota_b = a_ext_w.get("shotsOnTargetAg", 0.0)

    if gf_a == 0.0 and recent_h_dom:
        gf_a = sum(int(m.get("homeGoals", m.get("homeGoalsFt", 0))) for m in recent_h_dom) / len(recent_h_dom)
        ga_a = sum(int(m.get("awayGoals", m.get("awayGoalsFt", 0))) for m in recent_h_dom) / len(recent_h_dom)
        sot_a = (gf_a * 2.3) + 1.8
        sota_a = (ga_a * 2.1) + 1.5

    if gf_b == 0.0 and recent_a_ext:
        gf_b = sum(int(m.get("awayGoals", m.get("awayGoalsFt", 0))) for m in recent_a_ext) / len(recent_a_ext)
        ga_b = sum(int(m.get("homeGoals", m.get("homeGoalsFt", 0))) for m in recent_a_ext) / len(recent_a_ext)
        sot_b = (gf_b * 2.3) + 1.8
        sota_b = (ga_b * 2.1) + 1.5

    # Regress stats to league average if sample N < 5 to prevent extreme anomalies
    n_h = len(recent_h_dom) if isinstance(recent_h_dom, list) else 0
    n_a = len(recent_a_ext) if isinstance(recent_a_ext, list) else 0

    if gf_a == 0.0 and recent_h_dom:
        gf_a = sum(int(m.get("homeGoals", m.get("homeGoalsFt", 0))) for m in recent_h_dom) / max(1, len(recent_h_dom))
        ga_a = sum(int(m.get("awayGoals", m.get("awayGoalsFt", 0))) for m in recent_h_dom) / max(1, len(recent_h_dom))
        sot_a = (gf_a * 2.3) + 1.8
        sota_a = (ga_a * 2.1) + 1.5

    if gf_b == 0.0 and recent_a_ext:
        gf_b = sum(int(m.get("awayGoals", m.get("awayGoalsFt", 0))) for m in recent_a_ext) / max(1, len(recent_a_ext))
        ga_b = sum(int(m.get("homeGoals", m.get("homeGoalsFt", 0))) for m in recent_a_ext) / max(1, len(recent_a_ext))
        sot_b = (gf_b * 2.3) + 1.8
        sota_b = (ga_b * 2.1) + 1.5

    # ponytail: régression douce des stats si échantillon < 5 matchs
    if 0 < n_h < 5:
        gf_a = round((gf_a * n_h + 1.35 * (5 - n_h)) / 5.0, 2)
        ga_a = round((ga_a * n_h + 1.25 * (5 - n_h)) / 5.0, 2)
    if 0 < n_a < 5:
        gf_b = round((gf_b * n_a + 1.15 * (5 - n_a)) / 5.0, 2)
        ga_b = round((ga_b * n_a + 1.35 * (5 - n_a)) / 5.0, 2)

    # Fallback Sofascore Token 0 si AdamChoi n'a pas de données pour ces noms d'équipes
    has_real_data = bool(recent_h_dom or recent_a_ext or h_dom_w or a_ext_w)
    if not has_real_data:
        recent_h_dom = fetch_sofascore_sample(home_query, True)
        recent_a_ext = fetch_sofascore_sample(away_query, False)
        has_real_data = bool(recent_h_dom or recent_a_ext)

    if not has_real_data:
        if is_batch:
            return {
                "score": 0, "classe": "❓ Non analysé", "calibrated_prob": 0,
                "pts_ipo": 0, "ipo_comb": 0, "pts_buts": 0, "avg_buts": 0,
                "pts_freq": 0, "o25_avg_rate": 0, "pts_sot": 0, "sot_comb": 0,
                "pts_ha": 0, "avg_freq_ha": 0, "pts_league": 0,
                "xg_total": 0, "sot_total": 0,
                "verdict": "Équipe non trouvée — données insuffisantes.",
                "red_flags": ["Aucune donnée disponible"],
                "recent_h_dom": [], "recent_a_ext": []
            }
        print(f"❓ {home_query} vs {away_query} — Équipe non trouvée, score non calculé.")
        return

    if gf_a == 0.0: gf_a = 1.4; ga_a = 1.2; sot_a = 4.5; sota_a = 3.2
    if gf_b == 0.0: gf_b = 1.2; ga_b = 1.4; sot_b = 4.1; sota_b = 4.0

    xg_a = (sot_a * 0.28) + (gf_a * 0.5)
    xga_a = (sota_a * 0.28) + (ga_a * 0.5)
    xg_b = (sot_b * 0.28) + (gf_b * 0.5)
    xga_b = (sota_b * 0.28) + (ga_b * 0.5)

    def count_o25(matches_list):
        cnt = 0
        if isinstance(matches_list, list):
            for m in matches_list:
                if isinstance(m, dict):
                    gh = m.get("homeGoals", m.get("homeGoalsFt", 0))
                    ga = m.get("awayGoals", m.get("awayGoalsFt", 0))
                    try:
                        if (int(gh) + int(ga)) >= 3: cnt += 1
                    except Exception: pass
        return cnt

    def count_o15(matches_list):
        cnt = 0
        if isinstance(matches_list, list):
            for m in matches_list:
                if isinstance(m, dict):
                    gh = m.get("homeGoals", m.get("homeGoalsFt", 0))
                    ga = m.get("awayGoals", m.get("awayGoalsFt", 0))
                    try:
                        if (int(gh) + int(ga)) >= 2: cnt += 1
                    except Exception: pass
        return cnt

    def count_btts(matches_list):
        cnt = 0
        if isinstance(matches_list, list):
            for m in matches_list:
                if isinstance(m, dict):
                    gh = m.get("homeGoals", m.get("homeGoalsFt", 0))
                    ga = m.get("awayGoals", m.get("awayGoalsFt", 0))
                    try:
                        if int(gh) >= 1 and int(ga) >= 1: cnt += 1
                    except Exception: pass
        return cnt

    def count_u25(matches_list):
        cnt = 0
        if isinstance(matches_list, list):
            for m in matches_list:
                if isinstance(m, dict):
                    gh = m.get("homeGoals", m.get("homeGoalsFt", 0))
                    ga = m.get("awayGoals", m.get("awayGoalsFt", 0))
                    try:
                        if (int(gh) + int(ga)) <= 2: cnt += 1
                    except Exception: pass
        return cnt

    def count_u35(matches_list):
        cnt = 0
        if isinstance(matches_list, list):
            for m in matches_list:
                if isinstance(m, dict):
                    gh = m.get("homeGoals", m.get("homeGoalsFt", 0))
                    ga = m.get("awayGoals", m.get("awayGoalsFt", 0))
                    try:
                        if (int(gh) + int(ga)) <= 3: cnt += 1
                    except Exception: pass
        return cnt

    def count_4plus(matches_list):
        cnt = 0
        if isinstance(matches_list, list):
            for m in matches_list:
                if isinstance(m, dict):
                    gh = m.get("homeGoals", m.get("homeGoalsFt", 0))
                    ga = m.get("awayGoals", m.get("awayGoalsFt", 0))
                    try:
                        if (int(gh) + int(ga)) >= 4: cnt += 1
                    except Exception: pass
        return cnt

    o25_h_cnt = count_o25(recent_h_all[:20])
    o25_a_cnt = count_o25(recent_a_all[:20])
    o25_avg_rate = (((o25_h_cnt / max(1, len(recent_h_all[:20]))) + (o25_a_cnt / max(1, len(recent_a_all[:20])))) / 2.0) * 100

    # ── Calcul fréquence Over 1.5 sur 10 matchs Dom/Ext ──
    o15_h_cnt = count_o15(recent_h_dom[:10])
    o15_a_cnt = count_o15(recent_a_ext[:10])
    freq_o15_dom = (o15_h_cnt / max(1, len(recent_h_dom[:10]))) * 100
    freq_o15_ext = (o15_a_cnt / max(1, len(recent_a_ext[:10]))) * 100
    freq_o15 = round((freq_o15_dom + freq_o15_ext) / 2.0, 1)

    # ── Calcul fréquence BTTS sur 10 matchs Dom/Ext ──
    btts_h_cnt = count_btts(recent_h_dom[:10])
    btts_a_cnt = count_btts(recent_a_ext[:10])
    freq_btts_dom = (btts_h_cnt / max(1, len(recent_h_dom[:10]))) * 100
    freq_btts_ext = (btts_a_cnt / max(1, len(recent_a_ext[:10]))) * 100
    freq_btts = round((freq_btts_dom + freq_btts_ext) / 2.0, 1)

    # ── Moteur Probabiliste Poisson Under 2.5 & Under 3.5 ──
    l_dom = max(0.4, (gf_a * 0.6) + (ga_b * 0.4))
    l_ext = max(0.4, (gf_b * 0.6) + (ga_a * 0.4))
    
    p_u25_sum = 0.0
    p_u35_sum = 0.0
    for x in range(7):
        px = (math.exp(-l_dom) * (l_dom**x)) / math.factorial(x)
        for y in range(7):
            py = (math.exp(-l_ext) * (l_ext**y)) / math.factorial(y)
            pxy = px * py
            if x + y <= 2:
                p_u25_sum += pxy
            if x + y <= 3:
                p_u35_sum += pxy
    
    prob_u25 = round(p_u25_sum * 100.0, 1)
    prob_u35 = round(p_u35_sum * 100.0, 1)


    xg_total = xg_a + ga_b*0.5 + xg_b + ga_a*0.5
    sot_total = sot_a + sot_b

    ds_a = (sot_a >= 5.5 and sota_b >= 4.5) or (gf_a >= 1.7 and ga_b >= 1.4) or (xg_a >= 1.8 and ga_b >= 1.4)
    ds_b = (sot_b >= 5.0 and sota_a >= 4.5) or (gf_b >= 1.6 and ga_a >= 1.4) or (xg_b >= 1.6 and ga_a >= 1.4)

    convergences = []
    if gf_a >= 1.8 and ga_b >= 1.4: convergences.append("Attaque domicile forte × défense extérieure fragile")
    if gf_b >= 1.6 and ga_a >= 1.4: convergences.append("Attaque extérieure productive × défense domicile permissive")
    if xg_a >= 1.7 and xg_b >= 1.5: convergences.append("xG des deux équipes favorables à la création d'occasions")
    if sot_a >= 5.5 and sot_b >= 5.0: convergences.append("Volume de tirs cadrés élevé des deux côtés")
    if o25_avg_rate >= 60.0: convergences.append(f"Forte fréquence historique de matchs à 3+ buts sur 20 matchs ({o25_avg_rate:.0f}%)")
    h2h_o25 = count_o25(h2h20[:10])
    if h2h20 and (h2h_o25 / max(1, len(h2h20[:10]))) >= 0.70:
        convergences.append(f"Historique H2H à {int(h2h_o25/len(h2h20[:10])*100)}%+ d'Over 2.5")

    red_flags = []
    if gf_a < 1.0: red_flags.append(f"Attaque A faible ({gf_a:.1f} goal/m)")
    if gf_b < 1.0: red_flags.append(f"Attaque B faible ({gf_b:.1f} goal/m)")
    if sot_total < 6.5: red_flags.append(f"Tirs cadrés faibles ({sot_total:.1f}/m)")
    if n_h < 3: red_flags.append(f"Échantillon DOM faible ({n_h} m)")
    if n_a < 3: red_flags.append(f"Échantillon EXT faible ({n_a} m)")

    # ══════════════════════════════════════════════════════════════
    # 🟥 MODULE 3 — OVER 2,5 BUTS V3 (/100) — Dual Over Analyzer Spec
    # ══════════════════════════════════════════════════════════════
    ipo_dom = (sot_a * 0.28) + (gf_a * 0.50)
    ipo_ext = (sot_b * 0.28) + (gf_b * 0.50)
    ipo_comb = ipo_dom + ipo_ext

    # Bloc 1 — Potentiel offensif IPO (25 pts max)
    if ipo_comb >= 4.00: o25_b1 = 25
    elif ipo_comb >= 3.70: o25_b1 = 23
    elif ipo_comb >= 3.40: o25_b1 = 21
    elif ipo_comb >= 3.10: o25_b1 = 18
    elif ipo_comb >= 2.80: o25_b1 = 15
    elif ipo_comb >= 2.50: o25_b1 = 11
    elif ipo_comb >= 2.20: o25_b1 = 7
    else: o25_b1 = 4
    if gf_a < 0.80 or gf_b < 0.80: o25_b1 = min(18, o25_b1)

    # Bloc 2 — Buts marqués + encaissés (20 pts max)
    tot_goals_avg = gf_a + ga_a + gf_b + ga_b
    if tot_goals_avg >= 3.40: o25_b2 = 20
    elif tot_goals_avg >= 3.10: o25_b2 = 18
    elif tot_goals_avg >= 2.90: o25_b2 = 16
    elif tot_goals_avg >= 2.70: o25_b2 = 13
    elif tot_goals_avg >= 2.50: o25_b2 = 10
    elif tot_goals_avg >= 2.30: o25_b2 = 6
    else: o25_b2 = 4

    # Bloc 3 — Fréquence Over 2.5 (20 pts max)
    o25_h_dom_cnt = count_o25(recent_h_dom[:10])
    o25_a_ext_cnt = count_o25(recent_a_ext[:10])
    o25_h_dom_rate = (o25_h_dom_cnt / max(1, len(recent_h_dom[:10]))) * 100
    o25_a_ext_rate = (o25_a_ext_cnt / max(1, len(recent_a_ext[:10]))) * 100
    comb_o25_pct = (o25_h_dom_rate + o25_a_ext_rate) / 2.0

    if comb_o25_pct >= 75.0: o25_b3_raw = 20
    elif comb_o25_pct >= 70.0: o25_b3_raw = 18
    elif comb_o25_pct >= 65.0: o25_b3_raw = 16
    elif comb_o25_pct >= 60.0: o25_b3_raw = 13
    elif comb_o25_pct >= 55.0: o25_b3_raw = 10
    elif comb_o25_pct >= 50.0: o25_b3_raw = 6
    elif comb_o25_pct >= 45.0: o25_b3_raw = 3
    else: o25_b3_raw = 0

    o25_b3 = o25_b3_raw
    if min(o25_h_dom_rate, o25_a_ext_rate) < 30.0: o25_b3 = min(6, o25_b3)
    elif min(o25_h_dom_rate, o25_a_ext_rate) < 40.0: o25_b3 = min(10, o25_b3)
    elif min(o25_h_dom_rate, o25_a_ext_rate) < 50.0: o25_b3 = min(14, o25_b3)

    # Bloc 4 — Tirs cadrés (15 pts max)
    sot_comb = sot_a + sot_b
    if sot_comb >= 11.0: o25_b4 = 15
    elif sot_comb >= 10.0: o25_b4 = 13
    elif sot_comb >= 9.0: o25_b4 = 11
    elif sot_comb >= 8.0: o25_b4 = 8
    elif sot_comb >= 7.0: o25_b4 = 5
    else: o25_b4 = 3

    # Bloc 5 — Profil Dom/Ext (10 pts max)
    if o25_h_dom_rate >= 70 and o25_a_ext_rate >= 70: o25_b5 = 10
    elif o25_h_dom_rate >= 50 and o25_a_ext_rate >= 50: o25_b5 = 8
    elif o25_h_dom_rate >= 40 or o25_a_ext_rate >= 40: o25_b5 = 6
    else: o25_b5 = 4

    # Bloc 6 — Ligue/Contexte (10 pts max)
    o25_b6 = 8

    rf_pen_o25 = min(20, len(red_flags) * 10)
    total_score = max(0, min(100, o25_b1 + o25_b2 + o25_b3 + o25_b4 + o25_b5 + o25_b6 - rf_pen_o25))

    if total_score >= 90: classe = "🔥🔥🔥 Exceptionnel"
    elif total_score >= 85: classe = "🔥🔥 Très fort"
    elif total_score >= 80: classe = "🔥 Fort"
    elif total_score >= 75: classe = "✅ Bon potentiel"
    elif total_score >= 70: classe = "🟡 Intéressant mais à confirmer"
    elif total_score >= 65: classe = "⚠️ Moyen"
    elif total_score >= 60: classe = "⚠️ Fragile"
    else: classe = "❌ À écarter"

    verdict = f"{classe} ({total_score}/100)"

    # ══════════════════════════════════════════════════════════════
    # 🟦 MODULE 2 — OVER 1.5 BUTS (/100) — Dual Over Analyzer Spec
    # ══════════════════════════════════════════════════════════════
    # Bloc 1 — Buts marqués + encaissés (25 pts max)
    if tot_goals_avg >= 3.20: o15_b1 = 25
    elif tot_goals_avg >= 3.00: o15_b1 = 23
    elif tot_goals_avg >= 2.80: o15_b1 = 21
    elif tot_goals_avg >= 2.60: o15_b1 = 18
    elif tot_goals_avg >= 2.40: o15_b1 = 15
    elif tot_goals_avg >= 2.20: o15_b1 = 11
    elif tot_goals_avg >= 2.00: o15_b1 = 7
    else: o15_b1 = 4

    # Bloc 2 — Fréquence Over 1.5 (25 pts max)
    o15_h_dom_cnt = count_o15(recent_h_dom[:10])
    o15_a_ext_cnt = count_o15(recent_a_ext[:10])
    pct_o15_h = (o15_h_dom_cnt / max(1, len(recent_h_dom[:10]))) * 100.0
    pct_o15_a = (o15_a_ext_cnt / max(1, len(recent_a_ext[:10]))) * 100.0
    comb_o15_pct = (pct_o15_h + pct_o15_a) / 2.0

    if comb_o15_pct >= 90.0: o15_b2_raw = 25
    elif comb_o15_pct >= 85.0: o15_b2_raw = 23
    elif comb_o15_pct >= 80.0: o15_b2_raw = 21
    elif comb_o15_pct >= 75.0: o15_b2_raw = 18
    elif comb_o15_pct >= 70.0: o15_b2_raw = 15
    elif comb_o15_pct >= 65.0: o15_b2_raw = 11
    elif comb_o15_pct >= 60.0: o15_b2_raw = 7
    else: o15_b2_raw = 4

    o15_b2 = o15_b2_raw
    if min(pct_o15_h, pct_o15_a) < 50.0: o15_b2 = min(8, o15_b2)
    elif min(pct_o15_h, pct_o15_a) < 60.0: o15_b2 = min(13, o15_b2)
    elif min(pct_o15_h, pct_o15_a) < 70.0: o15_b2 = min(18, o15_b2)

    # Bloc 3 — Potentiel offensif (15 pts max)
    if ipo_comb >= 4.00: o15_b3 = 15
    elif ipo_comb >= 3.60: o15_b3 = 13
    elif ipo_comb >= 3.20: o15_b3 = 11
    elif ipo_comb >= 2.80: o15_b3 = 8
    elif ipo_comb >= 2.40: o15_b3 = 5
    else: o15_b3 = 3

    # Bloc 4 — Tirs cadrés (15 pts max)
    if sot_comb >= 10.0: o15_b4 = 15
    elif sot_comb >= 9.0: o15_b4 = 13
    elif sot_comb >= 8.0: o15_b4 = 11
    elif sot_comb >= 7.0: o15_b4 = 8
    elif sot_comb >= 6.0: o15_b4 = 5
    else: o15_b4 = 3

    # Bloc 5 — Profil Dom/Ext (10 pts max)
    o15_b5 = 10 if (pct_o15_h >= 80 and pct_o15_a >= 80) else (8 if (pct_o15_h >= 70 or pct_o15_a >= 70) else 6)

    # Bloc 6 — Ligue/Contexte (10 pts max)
    o15_b6 = 9

    rf_o15 = [f for f in red_flags if "Attaque" in f or "Échantillon" in f]
    rf_pen_o15 = min(15, len(rf_o15) * 5)
    score_o15 = max(0, min(100, o15_b1 + o15_b2 + o15_b3 + o15_b4 + o15_b5 + o15_b6 - rf_pen_o15))

    # ══════════════════════════════════════════════════════════════
    # 🟩 MODULE 4 — BTTS OUI (/100) — BTTS Analyzer Spec
    # ══════════════════════════════════════════════════════════════
    btts_h_cnt = count_btts(recent_h_dom[:10])
    btts_a_cnt = count_btts(recent_a_ext[:10])
    pct_btts_h = (btts_h_cnt / max(1, len(recent_h_dom[:10]))) * 100.0
    pct_btts_a = (btts_a_cnt / max(1, len(recent_a_ext[:10]))) * 100.0
    comb_btts_pct = (pct_btts_h + pct_btts_a) / 2.0

    score_cnt_h = sum(1 for m in recent_h_dom[:10] if int(m.get("homeGoals", m.get("homeGoalsFt", 0))) > 0)
    score_cnt_a = sum(1 for m in recent_a_ext[:10] if int(m.get("awayGoals", m.get("awayGoalsFt", 0))) > 0)
    pct_score_h = (score_cnt_h / max(1, len(recent_h_dom[:10]))) * 100.0
    pct_score_a = (score_cnt_a / max(1, len(recent_a_ext[:10]))) * 100.0
    avg_score_pct = (pct_score_h + pct_score_a) / 2.0

    concede_cnt_h = sum(1 for m in recent_h_dom[:10] if int(m.get("awayGoals", m.get("awayGoalsFt", 0))) > 0)
    concede_cnt_a = sum(1 for m in recent_a_ext[:10] if int(m.get("homeGoals", m.get("homeGoalsFt", 0))) > 0)
    pct_concede_h = (concede_cnt_h / max(1, len(recent_h_dom[:10]))) * 100.0
    pct_concede_a = (concede_cnt_a / max(1, len(recent_a_ext[:10]))) * 100.0
    avg_concede_pct = (pct_concede_h + pct_concede_a) / 2.0

    pct_cs_h = 100.0 - pct_concede_h
    pct_cs_a = 100.0 - pct_concede_a

    # Bloc 1 — Fréquence BTTS (25 pts max)
    if comb_btts_pct >= 75.0: btts_b1_raw = 25
    elif comb_btts_pct >= 70.0: btts_b1_raw = 23
    elif comb_btts_pct >= 65.0: btts_b1_raw = 21
    elif comb_btts_pct >= 60.0: btts_b1_raw = 18
    elif comb_btts_pct >= 55.0: btts_b1_raw = 14
    elif comb_btts_pct >= 50.0: btts_b1_raw = 10
    elif comb_btts_pct >= 45.0: btts_b1_raw = 5
    else: btts_b1_raw = 3

    btts_b1 = btts_b1_raw
    if min(pct_btts_h, pct_btts_a) < 30.0: btts_b1 = min(7, btts_b1)
    elif min(pct_btts_h, pct_btts_a) < 40.0: btts_b1 = min(12, btts_b1)
    elif min(pct_btts_h, pct_btts_a) < 50.0: btts_b1 = min(17, btts_b1)

    # Bloc 2 — Capacité à marquer (20 pts max)
    if avg_score_pct >= 90.0: btts_b2_raw = 20
    elif avg_score_pct >= 85.0: btts_b2_raw = 18
    elif avg_score_pct >= 80.0: btts_b2_raw = 16
    elif avg_score_pct >= 75.0: btts_b2_raw = 13
    elif avg_score_pct >= 70.0: btts_b2_raw = 10
    elif avg_score_pct >= 65.0: btts_b2_raw = 7
    else: btts_b2_raw = 4

    btts_b2 = btts_b2_raw
    if gf_a < 0.70 or gf_b < 0.70: btts_b2 = min(8, btts_b2)
    elif gf_a < 0.90 or gf_b < 0.90: btts_b2 = min(13, btts_b2)

    # Bloc 3 — Capacité à encaisser (20 pts max)
    if avg_concede_pct >= 80.0: btts_b3_raw = 20
    elif avg_concede_pct >= 75.0: btts_b3_raw = 18
    elif avg_concede_pct >= 70.0: btts_b3_raw = 16
    elif avg_concede_pct >= 65.0: btts_b3_raw = 13
    elif avg_concede_pct >= 60.0: btts_b3_raw = 10
    elif avg_concede_pct >= 55.0: btts_b3_raw = 7
    else: btts_b3_raw = 4

    btts_b3 = btts_b3_raw
    max_cs = max(pct_cs_h, pct_cs_a)
    if max_cs >= 70.0: btts_b3 = min(5, btts_b3)
    elif max_cs >= 60.0: btts_b3 = min(8, btts_b3)
    elif max_cs >= 50.0: btts_b3 = min(12, btts_b3)

    # Bloc 4 — Tirs cadrés (15 pts max)
    if sot_comb >= 11.0: btts_b4_raw = 15
    elif sot_comb >= 10.0: btts_b4_raw = 13
    elif sot_comb >= 9.0: btts_b4_raw = 11
    elif sot_comb >= 8.0: btts_b4_raw = 8
    elif sot_comb >= 7.0: btts_b4_raw = 5
    else: btts_b4_raw = 3

    btts_b4 = btts_b4_raw
    if min(sot_a, sot_b) < 2.5: btts_b4 = min(7, btts_b4)
    elif min(sot_a, sot_b) < 3.0: btts_b4 = min(10, btts_b4)

    # Bloc 5 & 6 — Profil Dom/Ext (10 pts) & Ligue (10 pts)
    btts_b5 = 10 if (pct_btts_h >= 70 and pct_btts_a >= 70) else (8 if (pct_btts_h >= 55 and pct_btts_a >= 55) else 6)
    btts_b6 = 8

    rf_btts = []
    if gf_a < 0.8: rf_btts.append(f"Attaque DOM trop faible ({gf_a:.1f} goal/m)")
    if gf_b < 0.8: rf_btts.append(f"Attaque EXT trop faible ({gf_b:.1f} goal/m)")

    unibet_o25 = m_unibet.get("over25") if isinstance(m_unibet, dict) else None
    unibet_btts = m_unibet.get("btts_oui") if isinstance(m_unibet, dict) else None
    if (gf_a >= 2.2 and gf_b < 1.0) or (gf_b >= 2.0 and gf_a < 1.0):
        rf_btts.append(f"Risque Clean Sheet / Déséquilibre offensif majeur ({gf_a:.1f} vs {gf_b:.1f})")
    elif unibet_o25 and unibet_btts and unibet_o25 <= 1.42 and unibet_btts >= 2.00:
        rf_btts.append(f"Risque Clean Sheet Bookmaker (Over 2.5 @{unibet_o25:.2f} vs BTTS @{unibet_btts:.2f})")

    rf_pen_btts = min(25, len(rf_btts) * 12)
    score_btts = max(0, min(100, btts_b1 + btts_b2 + btts_b3 + btts_b4 + btts_b5 + btts_b6 - rf_pen_btts))

    # ══════════════════════════════════════════════════════════════
    # 🔒 MODULE UNDER 2.5 BUTS (/100) — Score Verrou Défensif
    # ══════════════════════════════════════════════════════════════
    # Pilier 1 — Fréquence réelle Dom/Ext <= 2 buts (20 pts max)
    u25_h_dom_cnt = count_u25(recent_h_dom[:10])
    u25_a_ext_cnt = count_u25(recent_a_ext[:10])
    pct_u25_h = (u25_h_dom_cnt / max(1, len(recent_h_dom[:10]))) * 100.0
    pct_u25_a = (u25_a_ext_cnt / max(1, len(recent_a_ext[:10]))) * 100.0
    freq_u25 = round((pct_u25_h + pct_u25_a) / 2.0, 1)

    if freq_u25 >= 75.0: u25_b1 = 20
    elif freq_u25 >= 70.0: u25_b1 = 18
    elif freq_u25 >= 65.0: u25_b1 = 16
    elif freq_u25 >= 60.0: u25_b1 = 14
    elif freq_u25 >= 55.0: u25_b1 = 10
    elif freq_u25 >= 50.0: u25_b1 = 7
    else: u25_b1 = 3

    if min(pct_u25_h, pct_u25_a) < 30.0: u25_b1 = min(6, u25_b1)
    elif min(pct_u25_h, pct_u25_a) < 40.0: u25_b1 = min(10, u25_b1)

    # Pilier 2 — Expected Goals & Lambda total attendu (20 pts max)
    tot_lambda = l_dom + l_ext
    if tot_lambda <= 1.90: u25_b2 = 20
    elif tot_lambda <= 2.15: u25_b2 = 18
    elif tot_lambda <= 2.40: u25_b2 = 15
    elif tot_lambda <= 2.65: u25_b2 = 11
    elif tot_lambda <= 2.90: u25_b2 = 7
    else: u25_b2 = 3

    # Pilier 3 — Buts réels marqués + encaissés (15 pts max)
    tot_goals_u = gf_a + ga_a + gf_b + ga_b
    if tot_goals_u <= 2.10: u25_b3 = 15
    elif tot_goals_u <= 2.35: u25_b3 = 13
    elif tot_goals_u <= 2.60: u25_b3 = 10
    elif tot_goals_u <= 2.85: u25_b3 = 7
    elif tot_goals_u <= 3.10: u25_b3 = 4
    else: u25_b3 = 1

    # Pilier 4 — Volume offensif & Tirs cadrés (15 pts max)
    if sot_comb <= 6.5: u25_b4 = 15
    elif sot_comb <= 7.5: u25_b4 = 13
    elif sot_comb <= 8.5: u25_b4 = 10
    elif sot_comb <= 9.5: u25_b4 = 7
    elif sot_comb <= 10.5: u25_b4 = 4
    else: u25_b4 = 1

    # Pilier 5 — Solidité défensive & Clean Sheets (10 pts max)
    cs_h = sum(1 for m in recent_h_dom[:10] if int(m.get("awayGoals", m.get("awayGoalsFt", 0))) == 0)
    cs_a = sum(1 for m in recent_a_ext[:10] if int(m.get("homeGoals", m.get("homeGoalsFt", 0))) == 0)
    pct_cs = round(((cs_h + cs_a) / max(1, len(recent_h_dom[:10]) + len(recent_a_ext[:10]))) * 100.0, 1)
    if pct_cs >= 40.0: u25_b5 = 10
    elif pct_cs >= 30.0: u25_b5 = 8
    elif pct_cs >= 20.0: u25_b5 = 5
    else: u25_b5 = 2

    # Pilier 6 — Rythme 1ère mi-temps (10 pts max)
    ht_00_cnt = sum(1 for m in (recent_h_dom[:10] + recent_a_ext[:10]) if (m.get("homeGoalsHt", 0) == 0 and m.get("awayGoalsHt", 0) == 0))
    pct_ht00 = (ht_00_cnt / max(1, len(recent_h_dom[:10]) + len(recent_a_ext[:10]))) * 100.0
    if pct_ht00 >= 40.0: u25_b6 = 10
    elif pct_ht00 >= 30.0: u25_b6 = 8
    elif pct_ht00 >= 20.0: u25_b6 = 5
    else: u25_b6 = 2

    # Pilier 7 — Contexte & Marché (10 pts max)
    u25_b7 = 8
    unibet_u25 = m_unibet.get("under25") if isinstance(m_unibet, dict) else None
    unibet_o25 = m_unibet.get("over25") if isinstance(m_unibet, dict) else None
    if unibet_u25 and unibet_o25 and unibet_u25 < unibet_o25:
        u25_b7 = 10

    # Malus Red Flags Under 2.5
    rf_pen_u25 = 0
    if max(gf_a, gf_b) >= 2.2: rf_pen_u25 += 10
    if max(ga_a, ga_b) >= 2.0: rf_pen_u25 += 10
    p4_tot = count_4plus(recent_h_dom[:10]) + count_4plus(recent_a_ext[:10])
    if p4_tot >= 4: rf_pen_u25 += 15

    score_u25 = max(0, min(100, u25_b1 + u25_b2 + u25_b3 + u25_b4 + u25_b5 + u25_b6 + u25_b7 - rf_pen_u25))

    # ══════════════════════════════════════════════════════════════
    # 🛡️ MODULE UNDER 3.5 BUTS (/100) — Score Banque Défensive
    # ══════════════════════════════════════════════════════════════
    # Pilier 1 — Fréquence <= 3 buts (25 pts max)
    u35_h_cnt = count_u35(recent_h_dom[:10])
    u35_a_cnt = count_u35(recent_a_ext[:10])
    pct_u35_h = (u35_h_cnt / max(1, len(recent_h_dom[:10]))) * 100.0
    pct_u35_a = (u35_a_cnt / max(1, len(recent_a_ext[:10]))) * 100.0
    freq_u35 = round((pct_u35_h + pct_u35_a) / 2.0, 1)

    if freq_u35 >= 90.0: u35_b1 = 25
    elif freq_u35 >= 80.0: u35_b1 = 22
    elif freq_u35 >= 70.0: u35_b1 = 17
    elif freq_u35 >= 60.0: u35_b1 = 12
    else: u35_b1 = 5

    # Pilier 2 — Risque réel de 4+ buts (20 pts max)
    p4_h = count_4plus(recent_h_dom[:10])
    p4_a = count_4plus(recent_a_ext[:10])
    risk_4plus = round((((p4_h / max(1, len(recent_h_dom[:10]))) + (p4_a / max(1, len(recent_a_ext[:10])))) / 2.0) * 100.0, 1)

    if risk_4plus <= 10.0: u35_b2 = 20
    elif risk_4plus <= 15.0: u35_b2 = 17
    elif risk_4plus <= 20.0: u35_b2 = 13
    elif risk_4plus <= 25.0: u35_b2 = 8
    else: u35_b2 = 2

    # Pilier 3 — xG et Lambda attendu (20 pts max)
    if tot_lambda <= 2.30: u35_b3 = 20
    elif tot_lambda <= 2.60: u35_b3 = 17
    elif tot_lambda <= 2.90: u35_b3 = 13
    elif tot_lambda <= 3.20: u35_b3 = 8
    else: u35_b3 = 2

    # Pilier 4 — Défense & Résistance aux gros scores (15 pts max)
    heavy_conceded = sum(1 for m in recent_h_dom[:10] if int(m.get("awayGoals", 0)) >= 3) + sum(1 for m in recent_a_ext[:10] if int(m.get("homeGoals", 0)) >= 3)
    if heavy_conceded == 0: u35_b4 = 15
    elif heavy_conceded == 1: u35_b4 = 11
    elif heavy_conceded == 2: u35_b4 = 7
    else: u35_b4 = 2

    # Pilier 5 — Volatilité & Écart-type des scores (10 pts max)
    import statistics
    all_goals = []
    for m in (recent_h_dom[:10] + recent_a_ext[:10]):
        try:
            gh = int(m.get("homeGoals", m.get("homeGoalsFt", 0)))
            ga = int(m.get("awayGoals", m.get("awayGoalsFt", 0)))
            all_goals.append(gh + ga)
        except Exception: pass
    stdev_goals = round(statistics.stdev(all_goals), 2) if len(all_goals) > 1 else 1.2

    if stdev_goals <= 1.10: u35_b5 = 10
    elif stdev_goals <= 1.35: u35_b5 = 8
    elif stdev_goals <= 1.60: u35_b5 = 5
    else: u35_b5 = 2

    # Pilier 6 — Contexte (10 pts max)
    u35_b6 = 9

    score_u35 = max(0, min(100, u35_b1 + u35_b2 + u35_b3 + u35_b4 + u35_b5 + u35_b6))


    # ══════════════════════════════════════════════════════════════
    # BARÈME V2.1 PENALTY /100 — Refonte prioritaire (Total exact 100 pts)
    # ══════════════════════════════════════════════════════════════

    # 1. Arbitre Désigné avec Facteur de Fiabilité (35 pts max si connu)
    ref_name = ref_info.get("refereeName") or ""
    pen_per_match = 0.0
    total_games = 0
    if isinstance(ref_career, dict) and ref_career.get("seasons"):
        if not ref_name:
            ref_name = ref_career.get("name", "")
        # Saisons récentes (Europe 2025/2026, Amériques/MLS/Asie 2026 et 2025)
        accepted_seasons = ["2025/2026", "2026", "2025"]
        total_pens = 0
        for s in ref_career["seasons"]:
            if str(s.get("season", "")) in accepted_seasons:
                total_pens += s.get("totalPenalties", 0) or 0
                total_games += s.get("fixtureCount", 0) or 0
        if total_games > 0:
            pen_per_match = total_pens / total_games
    ref_name = ref_name or "Inconnu"

    ref_is_known = bool(ref_name != "Inconnu")
    if ref_is_known:
        if pen_per_match >= 0.50: p_pen_ref_raw = 35
        elif pen_per_match >= 0.40: p_pen_ref_raw = 30
        elif pen_per_match >= 0.30: p_pen_ref_raw = 24
        elif pen_per_match >= 0.25: p_pen_ref_raw = 18
        elif pen_per_match >= 0.20: p_pen_ref_raw = 12
        elif pen_per_match >= 0.15: p_pen_ref_raw = 6
        elif pen_per_match > 0: p_pen_ref_raw = 2
        else: p_pen_ref_raw = 10 if total_games == 0 else 0

        # Facteur de Fiabilité R_ref basé sur le nombre de matchs arbitrés cette saison (cible 8+ matchs)
        r_ref = min(1.0, total_games / 8.0) if total_games > 0 else 0.50
        p_pen_ref = round(p_pen_ref_raw * r_ref + 10 * (1.0 - r_ref))
        if total_games > 0:
            ref_status = f"👨‍⚖️ Arbitre {ref_name} ({total_games} m, {pen_per_match:.2f} pen/m)"
        else:
            ref_status = f"👨‍⚖️ Arbitre {ref_name} (désigné — début de saison)"
    else:
        p_pen_ref = 0
        ref_status = "Arbitre non désigné — confiance réduite"

    # 2. Tirs Cadrés & Intensité Offensive (25 pts max)
    if sot_comb >= 13.0: p_pen_sot = 25
    elif sot_comb >= 11.0: p_pen_sot = 21
    elif sot_comb >= 9.0: p_pen_sot = 17
    elif sot_comb >= 7.0: p_pen_sot = 12
    elif sot_comb >= 5.0: p_pen_sot = 7
    else: p_pen_sot = 2

    # 3. Fautes, Cartons & Booking Points (20 pts max — poids réduit)
    h2h_booking = []
    for m in h2h20:
        hbp = m.get("homeBookingPts", 0) or m.get("homeBookingPoints", 0)
        abp = m.get("awayBookingPts", 0) or m.get("awayBookingPoints", 0)
        try:
            h2h_booking.append(int(hbp) + int(abp))
        except (ValueError, TypeError):
            pass

    # ── COMPÉTENCE PENO : Sofascore Token 0 (curl_cffi) + Fallback Physique Hybride ──
    def fetch_sofascore_penalties(t_name):
        if not t_name: return None
        try:
            from curl_cffi import requests as cf_requests
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
            q_name = ALIAS_MAP_SOFASCORE.get(t_name, t_name)
            r = cf_requests.get(f"https://api.sofascore.com/api/v1/search/all?q={q_name}", impersonate="chrome120", headers=headers, timeout=6)
            if r.status_code == 200:
                teams = [x for x in r.json().get("results", []) if x.get("type") == "team"]
                if teams:
                    t_id = teams[0]["entity"]["id"]
                    r_ev = cf_requests.get(f"https://api.sofascore.com/api/v1/team/{t_id}/events/last/0", impersonate="chrome120", headers=headers, timeout=6)
                    if r_ev.status_code == 200:
                        events = sorted(r_ev.json().get("events", []), key=lambda x: x.get("startTimestamp", 0), reverse=True)
                        def _chk_inc(ev_id):
                            try:
                                r_inc = cf_requests.get(f"https://api.sofascore.com/api/v1/event/{ev_id}/incidents", impersonate="chrome120", headers=headers, timeout=6)
                                if r_inc.status_code == 200:
                                    return sum(1 for inc in r_inc.json().get("incidents", []) if (inc.get("incidentClass") == "penalty" or inc.get("incidentType") in ["penalty", "penalty_missed", "inGamePenalty"] or inc.get("isPenalty")))
                            except Exception:
                                pass
                            return 0
                        with ThreadPoolExecutor(max_workers=5) as p_ex:
                            res_list = p_ex.map(_chk_inc, [ev.get("id") for ev in events[:10] if ev.get("id")])
                            return sum(res_list)
        except Exception:
            pass
        return None

    p_dom_sf = fetch_sofascore_penalties(team_a)
    p_ext_sf = fetch_sofascore_penalties(team_b)

    bp_dom = h_dom_w.get("bookingPointsTotal", 0.0) or (h_dom_w.get("cardsTotal", 0.0) * 10.0)
    bp_ext = a_ext_w.get("bookingPointsTotal", 0.0) or (a_ext_w.get("cardsTotal", 0.0) * 10.0)

    if p_dom_sf is not None:
        p_dom_10m = p_dom_sf
    else:
        p_dom_10m = min(4, max(2, round(gf_a + (sot_a / 3.0)))) if (gf_a >= 1.2 or sot_a >= 4.0) else 1

    if p_ext_sf is not None:
        p_ext_10m = p_ext_sf
    else:
        p_ext_10m = min(4, max(2, round(gf_b + (sot_b / 3.0)))) if (gf_b >= 1.2 or sot_b >= 4.0) else 1

    p_tot_10m = p_dom_10m + p_ext_10m

    rf_peno_penalty = 0
    peno_double_signal_bonus = 0  # bonus appliqué après calcul de p_pen_goals
    if p_dom_10m >= 3 and p_ext_10m >= 3 and p_tot_10m >= 6:
        peno_badge = f"🔥 DOUBLE SIGNAL PENO ({p_dom_10m} dom / {p_ext_10m} ext — total {p_tot_10m})"
        peno_status = "DOUBLE_SIGNAL"
        peno_double_signal_bonus = 5  # appliqué après définition de p_pen_goals
    elif p_dom_10m >= 2 and p_ext_10m >= 2 and p_tot_10m >= 4:
        peno_badge = f"🟢 VALIDE PENO ({p_dom_10m} dom / {p_ext_10m} ext — total {p_tot_10m})"
        peno_status = "VALIDE"
    else:
        peno_badge = f"🛑 REJET PENO (<2 pen/équipe sur 10m : dom {p_dom_10m}, ext {p_ext_10m})"
        peno_status = "REJET"
        rf_peno_penalty = 25

    bp_dom = h_dom_w.get("bookingPointsTotal", 0.0) or (h_dom_w.get("cardsTotal", 0.0) * 10.0)
    bp_ext = a_ext_w.get("bookingPointsTotal", 0.0) or (a_ext_w.get("cardsTotal", 0.0) * 10.0)
    team_avg_booking = bp_dom + bp_ext

    if h2h_booking:
        avg_booking = sum(h2h_booking) / len(h2h_booking)
    elif team_avg_booking > 0:
        avg_booking = team_avg_booking
    else:
        avg_booking = 40.0

    if avg_booking >= 70: p_pen_cards = 20
    elif avg_booking >= 55: p_pen_cards = 16
    elif avg_booking >= 40: p_pen_cards = 12
    elif avg_booking >= 30: p_pen_cards = 8
    else: p_pen_cards = 3

    # 4. Activité Offensive Globale (20 pts max)
    total_goals_brut = tot_goals_avg
    if total_goals_brut >= 5.5 or ipo_comb >= 3.5: p_pen_goals = 20
    elif total_goals_brut >= 4.5 or ipo_comb >= 3.0: p_pen_goals = 16
    elif total_goals_brut >= 3.8 or ipo_comb >= 2.5: p_pen_goals = 12
    elif total_goals_brut >= 3.0: p_pen_goals = 8
    else: p_pen_goals = 3
    p_pen_goals = min(25, p_pen_goals + peno_double_signal_bonus)  # bonus DOUBLE SIGNAL appliqué ici

    if ref_is_known:
        score_penalty = max(0, min(100, p_pen_ref + p_pen_sot + p_pen_cards + p_pen_goals - rf_peno_penalty))
    else:
        raw_avail = p_pen_sot + p_pen_cards + p_pen_goals
        norm_score = (raw_avail / 65.0) * 100.0
        score_penalty = max(0, min(100, round(norm_score * 0.90) - rf_peno_penalty))
    pts_ipo = o25_b1
    pts_goals = o25_b2
    pts_freq = o25_b3
    pts_sot = o25_b4
    pts_ha = o25_b5
    pts_league = o25_b6
    avg_freq_ha = comb_o25_pct

    # ── Score 2ème mi-temps plus prolifique ──────────────────────────────────
    def _pct_2t_more(matches):
        """% matchs où buts 2T > buts 1T, sur les matchs avec données HT."""
        valid, wins = 0, 0
        for m in matches:
            ht_h = m.get("homeGoalsHt")
            ht_a = m.get("awayGoalsHt")
            ft_h = m.get("homeGoalsFt", m.get("homeGoals"))
            ft_a = m.get("awayGoalsFt", m.get("awayGoals"))
            if None in (ht_h, ht_a, ft_h, ft_a):
                continue
            goals_1t = int(ht_h) + int(ht_a)
            goals_2t = int(ft_h) + int(ft_a) - goals_1t
            valid += 1
            if goals_2t > goals_1t:
                wins += 1
        return round(wins / valid * 100) if valid >= 3 else 0

    pct_2t_dom = _pct_2t_more(recent_h_dom[:10])
    pct_2t_ext = _pct_2t_more(recent_a_ext[:10])
    # Score combiné : moyenne pondérée des deux équipes (0-100)
    if pct_2t_dom > 0 and pct_2t_ext > 0:
        score_2t = round((pct_2t_dom + pct_2t_ext) / 2)
    elif pct_2t_dom > 0:
        score_2t = pct_2t_dom
    elif pct_2t_ext > 0:
        score_2t = pct_2t_ext
    else:
        score_2t = 0

    # ── Score 1ère mi-temps plus prolifique ──────────────────────────────────
    def _pct_1t_more(matches):
        """% matchs où buts 1T > buts 2T, sur les matchs avec données HT."""
        valid, wins = 0, 0
        for m in matches:
            ht_h = m.get("homeGoalsHt")
            ht_a = m.get("awayGoalsHt")
            ft_h = m.get("homeGoalsFt", m.get("homeGoals"))
            ft_a = m.get("awayGoalsFt", m.get("awayGoals"))
            if None in (ht_h, ht_a, ft_h, ft_a):
                continue
            goals_1t = int(ht_h) + int(ht_a)
            goals_2t = int(ft_h) + int(ft_a) - goals_1t
            valid += 1
            if goals_1t > goals_2t:
                wins += 1
        return round(wins / valid * 100) if valid >= 3 else 0

    pct_1t_dom = _pct_1t_more(recent_h_dom[:10])
    pct_1t_ext = _pct_1t_more(recent_a_ext[:10])
    if pct_1t_dom > 0 and pct_1t_ext > 0:
        score_1t = round((pct_1t_dom + pct_1t_ext) / 2)
    elif pct_1t_dom > 0:
        score_1t = pct_1t_dom
    elif pct_1t_ext > 0:
        score_1t = pct_1t_ext
    else:
        score_1t = 0

    if is_batch:
        return {
            "team_a": team_a,
            "team_b": team_b,
            "league": league,
            "score": total_score,
            "classe": classe,
            "prob": round(total_score * 0.78, 1),
            "pts_ipo": pts_ipo, "ipo_comb": round(ipo_comb, 2),
            "pts_goals": pts_goals, "total_goals_brut": round(total_goals_brut, 1),
            "pts_freq": pts_freq, "avg_freq_all": round(o25_avg_rate, 1),
            "pts_sot": pts_sot, "sot_comb": round(sot_comb, 1),
            "pts_ha": pts_ha, "avg_freq_ha": round(avg_freq_ha, 1),
            "pts_league": pts_league,
            "xg_total": round(xg_total, 2),
            "sot_total": round(sot_total, 1),
            "verdict": verdict,
            "red_flags": red_flags,
            "recent_h_dom": recent_h_dom[:20],
            "recent_a_ext": recent_a_ext[:20],
            "recent_h_dom_20": recent_h_dom[:20],
            "recent_a_ext_20": recent_a_ext[:20],
            "freq_o15": freq_o15,
            "freq_btts": freq_btts,
            "score_o15": score_o15,
            "score_btts": score_btts,
            "score_u25": score_u25,
            "score_u35": score_u35,
            "prob_u25": prob_u25,
            "prob_u35": prob_u35,
            "freq_u25": freq_u25,
            "freq_u35": freq_u35,
            "risk_4plus": risk_4plus,
            "stdev_goals": stdev_goals,
            "pct_cs": pct_cs,
            "score_penalty": score_penalty,
            "ref_name": ref_name,
            "ref_status": ref_status,
            "pen_per_match": round(pen_per_match, 3),
            "avg_booking": round(avg_booking, 1),
            "peno_badge": peno_badge,
            "peno_status": peno_status,
            "p_dom_10m": p_dom_10m,
            "p_ext_10m": p_ext_10m,
            "p_tot_10m": p_tot_10m,
            "score_2t": score_2t,
            "pct_2t_dom": pct_2t_dom,
            "pct_2t_ext": pct_2t_ext,
            "score_1t": score_1t,
            "pct_1t_dom": pct_1t_dom,
            "pct_1t_ext": pct_1t_ext,
        }




    print(f"⚽ {team_a.upper()} — {team_b.upper()}")
    print(f"\n🔥 SCORE OVER 2,5 : {total_score}/100")
    print(f"📊 CLASSEMENT : {classe}")
    print(f"🛡️ PROBABILITÉ STATISTIQUE : {round(total_score * 0.78, 1)} %\n")
    print(f"1. Potentiel offensif (IPO {ipo_comb:.2f}) : {pts_ipo}/25")
    print(f"2. Buts marqués/encaissés ({total_goals_brut:.1f}b) : {pts_goals}/15")
    print(f"3. Historique Over 2,5 ({o25_avg_rate:.0f}%) : {pts_freq}/20")
    print(f"4. Tirs cadrés ({sot_comb:.1f}t) : {pts_sot}/10")
    print(f"5. Home/Away ({avg_freq_ha:.0f}%) : {pts_ha}/20")
    print(f"6. Ligue : {pts_league}/10")
    print(f"\nTOTAL : {total_score}/100\n")

    print(f"### POTENTIEL ÉQUIPE A ({team_a} à Domicile)")
    print(f"• Buts marqués domicile : {gf_a:.1f}/match")
    print(f"• xG domicile implicite : {xg_a:.2f}")
    print(f"• Tirs cadrés produits : {sot_a:.1f}/match")
    print(f"• Défense adverse / buts encaissés extérieur : {ga_b:.1f}/match")
    print(f"• Tirs cadrés concédés par l'adversaire : {sota_b:.1f}/match")

    print(f"\n### POTENTIEL ÉQUIPE B ({team_b} à l'Extérieur)")
    print(f"• Buts marqués extérieur : {gf_b:.1f}/match")
    print(f"• xG extérieur implicite : {xg_b:.2f}")
    print(f"• Tirs cadrés produits : {sot_b:.1f}/match")
    print(f"• Défense adverse / buts encaissés domicile : {ga_a:.1f}/match")
    print(f"• Tirs cadrés concédés par l'adversaire : {sota_a:.1f}/match")

    print("\n### CONVERGENCES")
    if convergences:
        for c in convergences: print(f"✅ {c}")
    else: print("ℹ️ Aucune convergence multi-signaux majeure identifiée.")

    print("\n### DOUBLE SIGNAUX")
    if ds_a: print(f"✅ DOUBLE SIGNAL ÉQUIPE A ({team_a}) : Attaque domicile forte + Défense adverse fragile")
    else: print(f"❌ Pas de Double Signal complet pour l'Équipe A ({team_a})")

    if ds_b: print(f"✅ DOUBLE SIGNAL ÉQUIPE B ({team_b}) : Attaque extérieure productive + Défense adverse permissive")
    else: print(f"❌ Pas de Double Signal complet pour l'Équipe B ({team_b})")

    print("\n### RED FLAGS")
    if red_flags:
        for rf in red_flags: print(f"⚠️ RED FLAG : {rf}")
    else: print("✅ Aucun Red Flag majeur détecté.")

    print("\n### 📜 10 DERNIERS SCORES À DOMICILE — " + team_a.upper())
    for m in recent_h_dom[:10]:
        dt = m.get("date", "N/A")
        opp = m.get("vs", m.get("awayTeam", "Adversaire"))
        opp_str = opp.get("name", str(opp)) if isinstance(opp, dict) else str(opp)
        hg = m.get("homeGoals", m.get("homeGoalsFt", 0))
        ag = m.get("awayGoals", m.get("awayGoalsFt", 0))
        tot = int(hg) + int(ag)
        icon = "🔥 3+ buts" if tot >= 3 else "⚪ < 3 buts"
        print(f"  • {dt} vs {opp_str:<20} | Score : {hg}-{ag} ({tot} buts) [{icon}]")

    print("\n### 📜 10 DERNIERS SCORES À L'EXTÉRIEUR — " + team_b.upper())
    for m in recent_a_ext[:10]:
        dt = m.get("date", "N/A")
        opp = m.get("vs", m.get("homeTeam", "Adversaire"))
        opp_str = opp.get("name", str(opp)) if isinstance(opp, dict) else str(opp)
        hg = m.get("homeGoals", m.get("homeGoalsFt", 0))
        ag = m.get("awayGoals", m.get("awayGoalsFt", 0))
        tot = int(hg) + int(ag)
        icon = "🔥 3+ buts" if tot >= 3 else "⚪ < 3 buts"
        print(f"  • {dt} vs {opp_str:<20} | Score : {hg}-{ag} ({tot} buts) [{icon}]")

    print("\n### VERDICT FINAL")
    print(f"{verdict}\n")

def parse_line(line):
    line = re.sub(r'^\d{1,2}:\d{2}\s*', '', line.strip())
    for sep in [" vs ", " v ", " contre ", " - ", " / ", " – ", " — "]:
        if sep in line.lower():
            parts = line.lower().split(sep, 1)
            return parts[0].strip(), parts[1].strip()
    words = line.strip().split()
    if len(words) == 2:
        return words[0], words[1]
    if len(words) == 4:
        return f"{words[0]} {words[1]}", f"{words[2]} {words[3]}"
    if len(words) == 3:
        return f"{words[0]} {words[1]}", words[2]
    return None, None

def process_batch_lines(lines):
    matches_list = []
    for line in lines:
        if not line.strip(): continue
        h, a = parse_line(line)
        if h and a:
            matches_list.append((h, a))

    if not matches_list:
        print("⚠️ Aucun match valide détecté dans votre copier-coller.")
        return

    print(f"\n================================================================================")
    print(f"📊 CLASSEMENT BATCH ({len(matches_list)} MATCHS ANALYSÉS EN PARALLÈLE)")
    print(f"================================================================================")
    fx_data = fetch(f"{BASE}/scripts/data/json/scripts/getFixturesJsonForSearch.php?clflc=abc&timezoneOffset=0")
    results = []
    with ThreadPoolExecutor(max_workers=10) as ex:
        futs = [ex.submit(analyze_pure_stats_20, h, a, fx_data, True) for h, a in matches_list]
        for f in futs:
            try:
                res = f.result()
                if res: results.append(res)
            except Exception: pass

    results.sort(key=lambda x: x["score"], reverse=True)
    for i, res in enumerate(results, 1):
        rf_str = f" | ⚠️ {', '.join(res['red_flags'])}" if res['red_flags'] else ""
        print(f"#{i:02d} {res['team_a'].upper()} vs {res['team_b'].upper()} ({res['league']}) — SCORE: {res['score']}/100 | Prob: {res['prob']}%")
        print(f"     VERDICT: {res['verdict']}{rf_str}")
    print("================================================================================\n")

def interactive_paste_mode():
    print("📋 MODE COPIER-COLLER INTERACTIF POWERSHELL")
    print("Collez votre liste de matchs ci-dessous (un match par ligne).")
    print("👉 Appuyez sur ENTRÉE DEUX FOIS lorsque vous avez fini de coller :\n")
    
    lines = []
    while True:
        try:
            line = input()
            if not line.strip():
                break
            lines.append(line.strip())
        except EOFError:
            break
            
    if lines:
        process_batch_lines(lines)

def parse_cli_args():
    if len(sys.argv) <= 1:
        return None, None
    args = sys.argv[1:]
    if len(args) == 2:
        return args[0], args[1]
    full_str = " ".join(args)
    for sep in [" vs ", " v ", " contre ", " - ", " / ", " – ", " — "]:
        if sep in full_str.lower():
            parts = full_str.lower().split(sep, 1)
            return parts[0].strip(), parts[1].strip()
    if len(args) == 4:
        return f"{args[0]} {args[1]}", f"{args[2]} {args[3]}"
    if len(args) == 3:
        return f"{args[0]} {args[1]}", args[2]
    return args[0], " ".join(args[1:])

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--file":
        filepath = sys.argv[2] if len(sys.argv) > 2 else "matches.txt"
        if not os.path.exists(filepath):
            print(f"❌ Fichier '{filepath}' introuvable.")
            sys.exit(0)
        with open(filepath, "r", encoding="utf-8") as f:
            lines = [l.strip() for l in f.readlines() if l.strip()]
        process_batch_lines(lines)

    elif len(sys.argv) > 1 and sys.argv[1] == "--today":
        print("\n================================================================================")
        print("📊 CLASSEMENT AUTOMATIQUE DE TOUS LES MATCHS DU JOUR (PARALLÈLE)")
        print("================================================================================")
        fx_data = fetch(f"{BASE}/scripts/data/json/scripts/getFixturesJsonForSearch.php?clflc=abc&timezoneOffset=0")
        matches_list = []
        for d in fx_data.get("dates", [])[:1]:
            for lg in d.get("leagues", []):
                for fx in lg.get("fixtures", []):
                    matches_list.append((fx["hometeam"], fx["awayteam"]))
        results = []
        with ThreadPoolExecutor(max_workers=10) as ex:
            futs = [ex.submit(analyze_pure_stats_20, h, a, fx_data, True) for h, a in matches_list]
            for f in futs:
                try:
                    res = f.result()
                    if res and res["score"] >= 50: results.append(res)
                except Exception: pass
        results.sort(key=lambda x: x["score"], reverse=True)
        for i, res in enumerate(results, 1):
            rf_str = f" | ⚠️ {', '.join(res['red_flags'])}" if res['red_flags'] else ""
            print(f"#{i:02d} {res['team_a'].upper()} vs {res['team_b'].upper()} ({res['league']}) — SCORE: {res['score']}/100 | Prob: {res['prob']}%")
            print(f"     VERDICT: {res['verdict']}{rf_str}")
        print("================================================================================\n")

    elif len(sys.argv) > 1 and sys.argv[1] == "--paste":
        interactive_paste_mode()

    elif len(sys.argv) == 1:
        interactive_paste_mode()

    else:
        home, away = parse_cli_args()
        if home and away:
            analyze_pure_stats_20(home, away)
        else:
            interactive_paste_mode()
