import os
import re
import sys
import json
import time
import random
import shutil
from datetime import datetime, timezone, timedelta
import pytz
from collections import OrderedDict
from urllib.parse import urlparse, urljoin
import cloudscraper

BASE_URL = os.getenv("BASE_URL")
DEFAULT_STREAM_DOMAIN = "chatgpt.hereisman.net"
OUTPUT_FILE = "Goozapp.json"
FIXED_TEAM_LOGO = "https://i.ibb.co/1Yh8PdLH/1000459066.png"

SPORT_CATEGORY_MAP = {
    "EFL Cup": "Soccer",
    "Soccer": "Soccer",
    "CFB": "American Football",
    "NCAAF": "American Football",
    "NFL": "American Football",
    "NBA": "Basketball",
    "WNBA": "Basketball",
    "NHL": "Hockey",
    "MLB": "Baseball",
    "Nascar Cup Series": "Racing",
    "F1": "Racing",
    "WWE": "Wrestling",
    "Boxing": "Boxing",
    "MMA": "MMA"
}

SPORT_DURATION_HOURS = {
    "Soccer": 2.0,
    "EFL Cup": 2.0,
    "Basketball": 2.5,
    "NBA": 2.5,
    "WNBA": 2.5,
    "Hockey": 2.5,
    "NHL": 2.5,
    "Baseball": 3.0,
    "MLB": 3.0,
    "American Football": 3.5,
    "NFL": 3.5,
    "CFB": 3.5,
    "NCAAF": 3.5,
    "Racing": 3.0,
    "Nascar Cup Series": 3.5,
    "F1": 2.0,
    "Wrestling": 3.0,
    "WWE": 3.0,
    "Boxing": 3.0,
    "MMA": 3.0
}

SOFASCORE_LEAGUE_LOGOS = {
    "NFL": "https://api.sofascore.app/api/v1/unique-tournament/9464/image",
    "CFB": "https://api.sofascore.app/api/v1/unique-tournament/11200/image",
    "NCAAF": "https://api.sofascore.app/api/v1/unique-tournament/11200/image",
    "NCAA Football": "https://api.sofascore.app/api/v1/unique-tournament/11200/image",
    "NBA": "https://api.sofascore.app/api/v1/unique-tournament/132/image",
    "WNBA": "https://api.sofascore.app/api/v1/unique-tournament/11186/image",
    "MLB": "https://api.sofascore.app/api/v1/unique-tournament/11205/image",
    "NHL": "https://api.sofascore.app/api/v1/unique-tournament/234/image",
    "EFL Cup": "https://api.sofascore.app/api/v1/unique-tournament/3666/image",
    "Premier League": "https://api.sofascore.app/api/v1/unique-tournament/17/image",
    "LaLiga": "https://api.sofascore.app/api/v1/unique-tournament/8/image",
    "Serie A": "https://api.sofascore.app/api/v1/unique-tournament/23/image",
    "Bundesliga": "https://api.sofascore.app/api/v1/unique-tournament/35/image",
    "Ligue 1": "https://api.sofascore.app/api/v1/unique-tournament/34/image",
    "Champions League": "https://api.sofascore.app/api/v1/unique-tournament/7/image",
    "Europa League": "https://api.sofascore.app/api/v1/unique-tournament/679/image",
    "MLS": "https://api.sofascore.app/api/v1/unique-tournament/242/image",
    "Nascar Cup Series": "https://api.sofascore.app/api/v1/unique-tournament/11234/image",
    "Formula 1": "https://api.sofascore.app/api/v1/unique-tournament/10839/image",
    "UFC": "https://api.sofascore.app/api/v1/unique-tournament/11187/image",
    "Boxing": "https://api.sofascore.app/api/v1/unique-tournament/11235/image",
    "WWE": "https://api.sofascore.app/api/v1/unique-tournament/11235/image"
}

def get_ist_time():
    ist = pytz.timezone('Asia/Kolkata')
    return datetime.now(ist).strftime('%d/%m/%y %H:%M:%S IST')

def log_to_console(message):
    print(message, file=sys.stderr)

def deduplicate(seq):
    seen = set()
    return [x for x in seq if not (x in seen or seen.add(x))]

def get_league_logo(league_name):
    for key, logo_url in SOFASCORE_LEAGUE_LOGOS.items():
        if key.lower() in league_name.lower():
            return logo_url
    return FIXED_TEAM_LOGO

def parse_event_time(et_time_str, category_name, league_name):
    now_utc = datetime.now(timezone.utc)
    ist_tz = pytz.timezone('Asia/Kolkata')
    et_tz = pytz.timezone('America/New_York')

    dt_utc = None
    if et_time_str:
        clean_str = re.sub(r'(ET|EDT|EST)', '', et_time_str).strip()
        try:
            dt_naive = datetime.strptime(clean_str, "%Y-%m-%d %H:%M")
            dt_et = et_tz.localize(dt_naive)
            dt_utc = dt_et.astimezone(timezone.utc)
        except Exception:
            pass

    if not dt_utc:
        dt_utc = now_utc

    duration_hours = SPORT_DURATION_HOURS.get(league_name, SPORT_DURATION_HOURS.get(category_name, 3.0))
    end_utc = dt_utc + timedelta(hours=duration_hours)

    dt_ist = dt_utc.astimezone(ist_tz)
    end_ist = end_utc.astimezone(ist_tz)

    return {
        "UTC_Start": dt_utc.strftime("%Y/%m/%d %H:%M:%S +0000"),
        "UTC_End": end_utc.strftime("%Y/%m/%d %H:%M:%S +0000"),
        "Start_Time": dt_ist.strftime("%d/%m/%Y; %H:%M:%S IST"),
        "End_Time": end_ist.strftime("%d/%m/%Y; %H:%M:%S IST")
    }

def push_to_github():
    GITHUB_TOKEN = os.getenv("GH_TOKEN")
    GITHUB_USER = os.getenv("TGITHUB_USER")
    GITHUB_REPO = os.getenv("TGITHUB_REPO")
    GITHUB_EMAIL = os.getenv("TGITHUB_EMAIL")
    
    if not GITHUB_TOKEN or not GITHUB_USER or not GITHUB_REPO:
        log_to_console("[ERROR] GitHub secrets are missing. Skipping push.")
        return

    temp_dir = "temp_external_repo"
    remote_url = f"https://{GITHUB_TOKEN}@github.com/{GITHUB_USER}/{GITHUB_REPO}.git"

    try:
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)
            
        clone_status = os.system(f"git clone --depth 1 {remote_url} {temp_dir}")
        if clone_status != 0:
            raise Exception("Git Clone failed. Please check your token or repo permissions.")
        
        shutil.copy(OUTPUT_FILE, os.path.join(temp_dir, OUTPUT_FILE))
        
        current_dir = os.getcwd()
        os.chdir(temp_dir)
        
        os.system(f'git config user.email "{GITHUB_EMAIL if GITHUB_EMAIL else "action@github.com"}"')
        os.system(f'git config user.name "{GITHUB_USER}"')
        os.system(f"git add {OUTPUT_FILE}")
        os.system(f'git commit -m "Auto Update: {get_ist_time()}" --allow-empty')
        push_status = os.system("git push origin main")
        
        os.chdir(current_dir)
        shutil.rmtree(temp_dir)
        
        if push_status == 0:
            log_to_console(f"[SUCCESS] {OUTPUT_FILE} successfully updated in {GITHUB_USER}/{GITHUB_REPO}.")
        else:
            log_to_console("[ERROR] Git push command failed.")
            
    except Exception as e:
        log_to_console(f"[ERROR] Push failed: {e}")

def run_scraper():
    if not BASE_URL:
        error_package = OrderedDict([
            ("Owner", "Ivan-FluX"),
            ("App name", "Goozapp-auto-scraper"),
            ("Status", "Failed"),
            ("Error", "BASE_URL environment variable is missing. Please add BASE_URL to GitHub Secrets.")
        ])
        print(json.dumps(error_package, indent=4, ensure_ascii=False))
        return

    scraper = cloudscraper.create_scraper(browser={'browser': 'chrome', 'platform': 'android', 'desktop': False})
    raw_matches = []
    active_stream_domain = ""
    
    clean_base = BASE_URL.rstrip('/')
    clean_base = re.sub(r'/(index1|v8|v12)/?$', '', clean_base)

    target_url = f"{clean_base}/v12"
    log_to_console(f"[*] Loading homepage: {target_url}")
    try:
        res = scraper.get(target_url, timeout=15)
        homepage_html = res.text
        
        if 'class="game"' not in homepage_html:
            target_url = clean_base
            log_to_console(f"[*] Fallback to root homepage: {target_url}")
            res = scraper.get(target_url, timeout=15)
            homepage_html = res.text
            
        log_to_console("[+] Homepage loaded successfully.")
    except Exception as e:
        error_package = OrderedDict([
            ("Owner", "Ivan-FluX"),
            ("App name", "Goozapp-auto-scraper"),
            ("Status", "Failed"),
            ("Error", "Could not connect to the website."),
            ("Details", str(e))
        ])
        print(json.dumps(error_package, indent=4, ensure_ascii=False))
        return

    matches = re.findall(r'(<a[^>]*class=["\'][^"\']*(?:game|list-group-item)[^"\']*["\'][^>]*href=["\']([^"\']+)["\'][^>]*>)(.*?)</a>', homepage_html, re.S)
    log_to_console(f"[+] Total {len(matches)} raw matches found.")
    
    for a_tag, m_url, m_text in matches:
        if re.search(r'\b(ended|finished|final)\b', m_text, re.I):
            continue

        sport_attr = re.search(r'data-sport=["\']([^"\']+)["\']', a_tag)
        if sport_attr:
            league_name = sport_attr.group(1).strip()
        else:
            clean_tag_text = re.sub(r'<span[^>]*class=["\']sport-icon["\'][^>]*>.*?</span>', '', m_text, flags=re.S)
            cat_match = re.search(r'class=["\']league-tag["\'][^>]*>(.*?)</span>', clean_tag_text, re.S)
            if cat_match:
                league_name = re.sub(r'<[^>]+>', '', cat_match.group(1)).strip()
            else:
                cat_url_match = re.search(r'/(?:tv-live|watch|live)/([^/]+)/', m_url)
                league_name = cat_url_match.group(1).replace('-', ' ').title() if cat_url_match else "Live Sports"

        category_name = SPORT_CATEGORY_MAP.get(league_name, league_name)

        matchup_match = re.search(r'class=["\']matchup["\'][^>]*>(.*?)</span>', m_text, re.S)
        if matchup_match:
            clean_rivals = re.sub(r'<[^>]+>', '', matchup_match.group(1)).strip()
        else:
            temp_text = re.sub(r'<span[^>]*class=["\']league-tag["\'][^>]*>.*?</span>', '', m_text, flags=re.S | re.I)
            temp_text = re.sub(r'<span[^>]*class=["\']badge-time["\'][^>]*>.*?</span>', '', temp_text, flags=re.S | re.I)
            temp_text = re.sub(r'<span[^>]*class=["\']watch["\'][^>]*>.*?</span>', '', temp_text, flags=re.S | re.I)
            clean_rivals = re.sub(r'<[^>]+>', '', temp_text).strip()
        
        clean_rivals = clean_rivals.rstrip(':').strip()

        if " vs " in clean_rivals:
            parts = clean_rivals.split(" vs ", 1)
            team_a = parts[0].strip()
            team_b = parts[1].strip()
        elif " at " in clean_rivals:
            parts = clean_rivals.split(" at ", 1)
            team_a = parts[0].strip()
            team_b = parts[1].strip()
        elif " - " in clean_rivals:
            parts = clean_rivals.split(" - ", 1)
            team_a = parts[0].strip()
            team_b = parts[1].strip()
        else:
            team_a = clean_rivals
            team_b = clean_rivals

        full_m_url = m_url if m_url.startswith("http") else urljoin(clean_base, m_url)
        match_id_search = re.search(r'/(\d+)/?$', full_m_url)
        match_id = match_id_search.group(1) if match_id_search else ""
        
        raw_matches.append({
            "category": category_name,
            "league_name": league_name,
            "clean_rivals": clean_rivals,
            "team_a": team_a,
            "team_b": team_b,
            "full_m_url": full_m_url,
            "backup_id": match_id,
            "extracted_ids": [],
            "raw_time_str": ""
        })

    log_to_console(f"\n[*] Scanning {len(raw_matches)} matches for server IDs & exact times...")
    for item in raw_matches:
        log_to_console(f"  [-] Fetching page: {item['clean_rivals']}...")
        try:
            time.sleep(random.uniform(0.5, 1.0))
            m_res = scraper.get(item["full_m_url"], timeout=10)
            m_html = m_res.text
            
            if re.search(r'\bFinal at\b', m_html, re.I):
                log_to_console("    [!] Match is already final. Skipping stream extraction.")
                continue

            date_match = re.search(r'<dt>\s*Date:\s*</dt>\s*<dd>\s*([0-9]{4}-[0-9]{2}-[0-9]{2}\s+[0-9]{1,2}:[0-9]{2}\s*(?:ET|EDT|EST)?)\s*</dd>', m_html, re.I)
            if date_match:
                item["raw_time_str"] = date_match.group(1).strip()

            stream_ids = []
            stream_ids.extend(re.findall(r'new-stream-embed/(\d+)', m_html))
            stream_ids.extend(re.findall(r'changeStream\s*\(\s*[\'"]?(\d+)', m_html))
            stream_ids.extend(re.findall(r'stream-btn-(\d+)', m_html))
            stream_ids.extend(re.findall(r'embed/(\d+)', m_html))
            
            filtered_ids = [
                s for s in stream_ids 
                if s.lower() not in ('streamid', 'null', 'undefined', 'cx-iframe')
            ]
            
            if filtered_ids:
                item["extracted_ids"] = deduplicate(filtered_ids)
                log_to_console(f"    [+] Extracted IDs: {item['extracted_ids']}")
            else:
                log_to_console("    [!] No stream buttons found in HTML.")

            if not active_stream_domain:
                candidate_embed_urls = []
                candidate_embed_urls.extend(re.findall(r'<iframe[^>]+src=["\']([^"\']+)["\']', m_html, re.I))
                candidate_embed_urls.extend(re.findall(r'[\'"](https?://[a-zA-Z0-9.-]+/new-stream-embed/[^\'"]+)[\'"]', m_html))
                
                candidate_embed_base = re.search(r'[\'"](https?://[a-zA-Z0-9.-]+/new-stream-embed/)[\'"]', m_html)
                if candidate_embed_base:
                    test_id = item["extracted_ids"][0] if item["extracted_ids"] else item["backup_id"]
                    if test_id:
                        candidate_embed_urls.append(f"{candidate_embed_base.group(1)}{test_id}")
                
                for embed_url in deduplicate(candidate_embed_urls):
                    if not embed_url.startswith('http'):
                        if embed_url.startswith('//'):
                            embed_url = 'https:' + embed_url
                        else:
                            embed_url = urljoin(item["full_m_url"], embed_url)
                    
                    try:
                        embed_res = scraper.get(embed_url, timeout=10)
                        playlist_match = re.search(r'(https?://[a-zA-Z0-9.-]+/playlist/[a-zA-Z0-9_.-]+/load-playlist[^"\'\s>]*)', embed_res.text)
                        if playlist_match:
                            parsed_url = urlparse(playlist_match.group(1))
                            active_stream_domain = parsed_url.netloc
                            log_to_console(f"    [*] Active domain detected: {active_stream_domain}")
                            break
                    except Exception:
                        continue
        except Exception as e:
            log_to_console(f"    [ERROR] Failed to fetch or parse: {e}")
            continue

    if not active_stream_domain:
        active_stream_domain = DEFAULT_STREAM_DOMAIN
        log_to_console(f"\n[!] Using default domain: {active_stream_domain}")

    all_live_matches = []
    
    for item in raw_matches:
        ids_to_use = item["extracted_ids"]
        
        if not ids_to_use and item["backup_id"]:
            ids_to_use = [item["backup_id"]]
            
        if ids_to_use:
            time_data = parse_event_time(item["raw_time_str"], item["category"], item["league_name"])
            league_logo_url = get_league_logo(item["league_name"])

            for index, stream_id in enumerate(ids_to_use, 1):
                raw_m3u8 = f"https://{active_stream_domain}/playlist/{stream_id}/load-playlist.m3u8|Referer=https://gooz.aapmains.net"
                
                if index == 1:
                    stream_name = f"{item['league_name'].upper()} SERVER"
                else:
                    stream_name = "HD SERVER" if index == 2 else f"HD SERVER {index - 1}"

                formatted_iframe = f'<iframe src="https://ivan-player.vercel.app/?play=https://stream-proxy.goalzen.site/proxy/php?url={raw_m3u8}" style="width: 100%; aspect-ratio: 16/9; border: none;" allow="autoplay; encrypted-media; picture-in-picture; fullscreen" allowfullscreen></iframe>'

                all_live_matches.append(OrderedDict([
                    ("Id", str(len(all_live_matches) + 1)),
                    ("Category", item["category"]),
                    ("Event_Name", item["clean_rivals"]),
                    ("League_Name", item["league_name"]),
                    ("League_Logo", league_logo_url),
                    ("Stream_Name", stream_name),
                    ("Team_A", item["team_a"]),
                    ("Team_A_Logo", FIXED_TEAM_LOGO),
                    ("Team_B", item["team_b"]),
                    ("Team_B_Logo", FIXED_TEAM_LOGO),
                    ("Start_Time", time_data["Start_Time"]),
                    ("End_Time", time_data["End_Time"]),
                    ("UTC_Start", time_data["UTC_Start"]),
                    ("UTC_End", time_data["UTC_End"]),
                    ("Link", formatted_iframe)
                ]))

    final_package = OrderedDict([
        ("Owner", "Ivan-FluX"),
        ("App name", "Goozapp-auto-scraper"),
        ("Last update", get_ist_time()),
        ("Total_Matches", len(all_live_matches)),
        ("Live_Data", all_live_matches)
    ])
    
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(final_package, f, indent=4, ensure_ascii=False)
        
    push_to_github()
    print(json.dumps(final_package, indent=4, ensure_ascii=False))

if __name__ == "__main__":
    run_scraper()
