import os
import re
import json
from datetime import datetime
import pytz
from collections import OrderedDict
import requests
from flask import Flask, Response

app = Flask(__name__)

M3U_URL = "https://raw.githubusercontent.com/doctor-8trange/zyphx8/refs/heads/main/data/fancode.m3u"

def get_ist_time():
    ist = pytz.timezone('Asia/Kolkata')
    return datetime.now(ist).strftime('%d/%m/%Y %H:%M:%S IST')

def parse_m3u_to_json(m3u_text):
    lines = [line.strip() for line in m3u_text.splitlines() if line.strip()]
    matches = []
    i = 0
    idx = 1

    while i < len(lines):
        line = lines[i]
        if line.startswith("#EXTINF:"):
            name_match = re.search(r'tvg-name="([^"]*)"', line, re.I)
            logo_match = re.search(r'tvg-logo="([^"]*)"', line, re.I)
            lang_match = re.search(r'tvg-language="([^"]*)"', line, re.I)
            group_match = re.search(r'group-title="([^"]*)"', line, re.I)

            comma_name = line.split(",", 1)[-1].strip() if "," in line else ""
            if " | " in comma_name:
                comma_name = comma_name.split(" | ", 1)[-1].strip()

            event_name = name_match.group(1).strip() if name_match else comma_name
            team_logo = logo_match.group(1).strip() if logo_match else ""
            language = lang_match.group(1).strip() if lang_match else "English"
            category = group_match.group(1).strip() if group_match else "Sports"

            i += 1
            stream_url = ""
            while i < len(lines) and lines[i].startswith("#"):
                i += 1

            if i < len(lines):
                stream_url = lines[i].strip()

            if stream_url:
                split_parts = re.split(r'\s+(?:vs|at|-)\s+', event_name, maxsplit=1, flags=re.I)
                if len(split_parts) == 2:
                    team_a = split_parts[0].strip()
                    team_b = split_parts[1].strip()
                else:
                    team_a = event_name
                    team_b = event_name

                stream_name = f"{language.upper()} SERVER" if language else "ENGLISH SERVER"

                matches.append(OrderedDict([
                    ("Id", str(idx)),
                    ("Category", category),
                    ("Event_Name", event_name),
                    ("League_Name", category),
                    ("Stream_Name", stream_name),
                    ("Team_A", team_a),
                    ("Team_B", team_b),
                    ("Team_Logo", team_logo),
                    ("Link", stream_url)
                ]))
                idx += 1
        else:
            i += 1

    final_package = OrderedDict([
        ("Owner", "Ivan-FluX"),
        ("App name", "fancode-m3u-to-json"),
        ("Last update", get_ist_time()),
        ("Total_Matches", len(matches)),
        ("Live_Data", matches)
    ])

    return final_package

@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def live_m3u_to_json(path):
    try:
        res = requests.get(M3U_URL, timeout=12)
        if res.status_code == 200:
            json_data = parse_m3u_to_json(res.text)
            json_output = json.dumps(json_data, indent=4, ensure_ascii=False)
            return Response(json_output, mimetype='application/json')
        else:
            error_resp = {
                "Status": "Failed",
                "Error": f"M3U URL returned status code {res.status_code}"
            }
            return Response(json.dumps(error_resp, indent=4), mimetype='application/json', status=502)
    except Exception as e:
        error_resp = {
            "Status": "Failed",
            "Error": str(e)
        }
        return Response(json.dumps(error_resp, indent=4), mimetype='application/json', status=500)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)
