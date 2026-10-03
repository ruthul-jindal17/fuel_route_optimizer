import csv
import json
import os
import re
import time
import requests
import geonamescache

CANADIAN_PROVINCES = {'AB', 'BC', 'MB', 'NB', 'NL', 'NS', 'NT', 'NU', 'ON', 'PE', 'QC', 'SK', 'YT'}

def normalize_name(s: str) -> str:
    s = s.strip().lower()
    s = s.replace('saint ', 'st. ').replace('st ', 'st. ')
    s = re.sub(r' (city|town|village|cdp|borough|township|ccd|plantation|charter township)$', '', s)
    return re.sub(r'[^a-z0-9]', '', s)

def load_gazetteer():
    geo_cities = {}
    
    # 1. Census Places
    if os.path.exists('2023_Gaz_place_national.txt'):
        with open('2023_Gaz_place_national.txt', encoding='latin1') as f:
            f.readline()
            for line in f:
                parts = [p.strip() for p in line.strip().split('\t')]
                if len(parts) >= 12:
                    st = parts[0].strip().upper()
                    name = normalize_name(parts[3])
                    geo_cities[(name, st)] = (float(parts[10]), float(parts[11]))
                    
    # 2. Census County Subdivisions
    if os.path.exists('2023_Gaz_cousubs_national.txt'):
        with open('2023_Gaz_cousubs_national.txt', encoding='latin1') as f:
            f.readline()
            for line in f:
                parts = [p.strip() for p in line.strip().split('\t')]
                if len(parts) >= 11:
                    st = parts[0].strip().upper()
                    name = normalize_name(parts[3])
                    if (name, st) not in geo_cities:
                        geo_cities[(name, st)] = (float(parts[9]), float(parts[10]))
                        
    # 3. Simplemaps US Cities
    if os.path.exists('uscities.csv'):
        with open('uscities.csv', mode='r', encoding='utf-8') as f:
            for row in csv.DictReader(f):
                c = normalize_name(row['city'])
                st = row['state_id'].strip().upper()
                if (c, st) not in geo_cities:
                    geo_cities[(c, st)] = (float(row['lat']), float(row['lng']))
                    
    # 4. Geonamescache
    gc = geonamescache.GeonamesCache()
    for c in gc.get_cities().values():
        if c.get('countrycode') == 'US':
            state = c.get('admin1code', '').strip().upper()
            name = normalize_name(c.get('name', ''))
            if (name, state) not in geo_cities:
                geo_cities[(name, state)] = (float(c['latitude']), float(c['longitude']))
                
    return geo_cities

def main():
    print("Loading gazetteer and city datasets...")
    geo_cities = load_gazetteer()
    print(f"Loaded {len(geo_cities)} city locations.")
    
    # Load or initialize cached geocodes
    cache_file = 'cached_geocoding.json'
    cached_geocodes = {}
    if os.path.exists(cache_file):
        try:
            with open(cache_file, 'r', encoding='utf-8') as f:
                cached_geocodes = json.load(f)
        except Exception:
            cached_geocodes = {}

    # Read fuel prices CSV
    csv_file = 'fuel_prices.csv'
    stations = []
    unmatched_cities = set()
    
    with open(csv_file, mode='r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            state = row['State'].strip().upper()
            if state in CANADIAN_PROVINCES:
                continue
            city = row['City'].strip()
            c_norm = normalize_name(city)
            key = f"{city}, {state}"
            
            lat, lng = None, None
            if (c_norm, state) in geo_cities:
                lat, lng = geo_cities[(c_norm, state)]
            elif key in cached_geocodes:
                lat, lng = cached_geocodes[key]
            else:
                unmatched_cities.add((city, state))
                
            try:
                price = float(row['Retail Price'].strip())
            except ValueError:
                price = 0.0
                
            stations.append({
                'opis_id': int(row['OPIS Truckstop ID'].strip()),
                'name': row['Truckstop Name'].strip(),
                'address': row['Address'].strip(),
                'city': city,
                'state': state,
                'rack_id': row['Rack ID'].strip(),
                'price': price,
                'lat': lat,
                'lng': lng
            })
            
    print(f"Total US stations: {len(stations)}. Unmatched cities to geocode: {len(unmatched_cities)}")
    
    if unmatched_cities:
        headers = {'User-Agent': 'TruckStopFuelOptimizer/1.0 (contact@project.internal)'}
        for idx, (city, state) in enumerate(sorted(unmatched_cities)):
            key = f"{city}, {state}"
            if key in cached_geocodes:
                continue
            q = f"{city}, {state}, USA"
            print(f"[{idx+1}/{len(unmatched_cities)}] Geocoding {q}...")
            try:
                r = requests.get(
                    'https://nominatim.openstreetmap.org/search',
                    params={'q': q, 'format': 'json', 'limit': 1},
                    headers=headers,
                    timeout=10
                )
                if r.status_code == 200:
                    data = r.json()
                    if data:
                        cached_geocodes[key] = (float(data[0]['lat']), float(data[0]['lon']))
                        print(f"  -> Found: {cached_geocodes[key]}")
                    else:
                        print(f"  -> Not found in Nominatim")
                else:
                    print(f"  -> Error status {r.status_code}")
            except Exception as e:
                print(f"  -> Exception: {e}")
            time.sleep(1.0)
            
        with open(cache_file, 'w', encoding='utf-8') as f:
            json.dump(cached_geocodes, f, indent=2)
            
    # Assign newly geocoded coords
    valid_stations = []
    seen = {}
    for st in stations:
        if st['lat'] is None or st['lng'] is None:
            key = f"{st['city']}, {st['state']}"
            if key in cached_geocodes:
                st['lat'], st['lng'] = cached_geocodes[key]
                
        if st['lat'] is not None and st['lng'] is not None and st['price'] > 0:
            # Group by OPIS ID and keep lowest price
            uid = st['opis_id']
            if uid not in seen or st['price'] < seen[uid]['price']:
                seen[uid] = st

    valid_stations = list(seen.values())
    print(f"Successfully compiled {len(valid_stations)} unique US truckstops with coordinates.")
    
    with open('geocoded_fuel_stations.json', 'w', encoding='utf-8') as f:
        json.dump(valid_stations, f, indent=2)
    print("Saved to geocoded_fuel_stations.json")

if __name__ == '__main__':
    main()
