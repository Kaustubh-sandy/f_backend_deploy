from flask_cors import CORS
from flask import Flask, request, jsonify
import csv
import io
import json

app = Flask(__name__)
CORS(app)

# ✅ Health check route
@app.route('/', methods=['GET'])
def health_check():
    return jsonify({'status': 'Backend is live 🚀'}), 200

def clean_key(key):
    return key.replace('\ufeff', '').replace('"', '').strip()

def normalize(s):
    return s.strip().lower()

def parse_lap_time(time_str):
    # Convert time string like "1:30.685" to total seconds for comparison
    try:
        parts = time_str.strip().split(':')
        if len(parts) == 2:
            mins = int(parts[0])
            secs = float(parts[1])
            return mins * 60 + secs
    except Exception:
        pass
    return float('inf')  # fallback for invalid/missing times

@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return jsonify({'error': 'No file part'}), 400

    mapping_json = request.form.get('mapping')
    mapping = []
    if mapping_json:
        try:
            mapping = json.loads(mapping_json)
        except Exception:
            mapping = []

    alias_lookup = {}
    for player in mapping:
        cur_name = player.get('currentName', '').strip()
        cur_team = player.get('currentTeam', '').strip()
        for alias in player.get('aliases', []):
            old_name = alias.get('name', '').strip()
            old_team = alias.get('team', '').strip()
            if old_name and old_team:
                alias_lookup[(normalize(old_name), normalize(old_team))] = (cur_name, cur_team)
        if cur_name and cur_team:
            alias_lookup[(normalize(cur_name), normalize(cur_team))] = (cur_name, cur_team)

    standings = {}
    constructors = {}
    wins = {}
    podiums = []
    fastest_laps = []
    most_positions_gained = []

    files = request.files.getlist('file')
    for file in files:
        content = file.read().decode('utf-8')
        sections = content.strip().split('\n\n')
        race_table = sections[0]

        reader = csv.DictReader(io.StringIO(race_table))
        reader.fieldnames = [clean_key(h) for h in reader.fieldnames]

        race_rows = []
        fastest_lap_time = float('inf')
        fastest_driver = None
        max_positions_gained = float('-inf')
        best_gain_driver = None

        for row in reader:
            driver = row.get('Driver', '').strip()
            team = row.get('Team', '').strip()
            pos = row.get('Pos.') or row.get('Position') or ''
            grid = row.get('Grid', '')
            points_str = row.get('Pts.') or row.get('Points')
            best_lap = row.get('Best', '').strip()

            try:
                points = float(points_str) if points_str else 0
            except:
                points = 0

            key = (normalize(driver), normalize(team))
            canonical = alias_lookup.get(key, (driver, team))
            standings[canonical] = standings.get(canonical, 0) + points
            constructors[canonical[1]] = constructors.get(canonical[1], 0) + points

            race_rows.append({
                'driver': canonical[0],
                'team': canonical[1],
                'pos': str(pos).strip(),
                'grid': str(grid).strip()
            })

            # Fastest lap tracking
            lap_time_sec = parse_lap_time(best_lap)
            if lap_time_sec < fastest_lap_time:
                fastest_lap_time = lap_time_sec
                fastest_driver = {'driver': canonical[0], 'team': canonical[1], 'lap_time': best_lap}

            # Position gained tracking
            try:
                start_pos = int(grid)
                finish_pos = int(pos)
                gained = start_pos - finish_pos
                if gained > max_positions_gained:
                    max_positions_gained = gained
                    best_gain_driver = {'driver': canonical[0], 'team': canonical[1], 'positions_gained': gained}
            except:
                pass

        if fastest_driver:
            fastest_laps.append(fastest_driver)
        if best_gain_driver:
            most_positions_gained.append(best_gain_driver)

        # Wins
        for r in race_rows:
            if r['pos'] == '1':
                win_key = (r['driver'], r['team'])
                wins[win_key] = wins.get(win_key, 0) + 1

        # Podiums
        podium = sorted(
            [r for r in race_rows if r['pos'].isdigit()],
            key=lambda r: int(r['pos'])
        )[:3]
        podiums.append(podium)
        
    standings_list = [
        {'driver': driver, 'team': team, 'points': points}
        for (driver, team), points in standings.items()
    ]
    standings_list.sort(key=lambda x: -x['points'])
    
    constructors_list = [
        {'team': team, 'points': points}
        for team, points in constructors.items()
    ]
    constructors_list.sort(key=lambda x: -x['points'])

    # Prepare output
    most_wins = [
        {'driver': d, 'team': t, 'wins': w}
        for (d, t), w in wins.items()
    ]
    most_wins.sort(key=lambda x: -x['wins'])

    fastest_lap_count = {}
    for entry in fastest_laps:
        key = (entry['driver'], entry['team'])  # Count by driver AND team combination
        fastest_lap_count[key] = fastest_lap_count.get(key, 0) + 1

    most_fastest_laps = [
        {'driver': driver, 'team': team, 'count': count}
        for (driver, team), count in fastest_lap_count.items()
    ]   
    most_fastest_laps.sort(key=lambda x: -x['count'])

    # Format per-race fastest laps and position gain data
    fastest_lap_per_race = [
        {**entry, 'race': i + 1}
        for i, entry in enumerate(fastest_laps)
    ]

    positions_gained_per_race = [
        {'driver': entry['driver'], 'team': entry['team'], 'gained': entry['positions_gained'], 'race': i + 1}
        for i, entry in enumerate(most_positions_gained)
    ]

    # Final JSON response
    return jsonify({
        'status': 'success',
        'standings': standings_list,
        'team_standings': constructors_list,
        'most_wins': most_wins,
        'podiums': podiums,
        'fastest_lap_per_race': fastest_lap_per_race,
        'positions_gained': positions_gained_per_race,
        'most_fastest_laps': most_fastest_laps
})

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
