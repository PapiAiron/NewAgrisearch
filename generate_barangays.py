"""
Script to fetch Victoria, Laguna barangay boundaries from OpenStreetMap
and save as a static GeoJSON file at app/static/victoria_barangays.json
Run once: python generate_barangays.py
Requires: pip install shapely
"""

import json
import urllib.request
import urllib.parse
import os
from shapely.geometry import mapping, MultiLineString
from shapely.ops import polygonize, unary_union

VICTORIA_BARANGAYS = {
    'Banca-banca', 'Daniw', 'Masapang', 'Nanhaya', 'Pagalangan',
    'San Benito', 'San Felix', 'San Francisco', 'San Roque'
}
VICTORIA_POSTAL = '4011'

OUTPUT_PATH = os.path.join(os.path.dirname(__file__), 'app', 'static', 'victoria_barangays.json')


OVERPASS_MIRRORS = [
    'https://overpass-api.de/api/interpreter',
    'https://overpass.kumi.systems/api/interpreter',
    'https://overpass.private.coffee/api/interpreter',
    'https://maps.mail.ru/osm/tools/overpass/api/interpreter',
]


def fetch_overpass(query):
    data = urllib.parse.urlencode({'data': query}).encode()
    for url in OVERPASS_MIRRORS:
        try:
            req = urllib.request.Request(url, data=data, headers={
                'User-Agent': 'AgriSearch/1.0 (barangay boundary fetch)',
                'Content-Type': 'application/x-www-form-urlencoded'
            })
            print(f"Trying {url} ...")
            with urllib.request.urlopen(req, timeout=90) as resp:
                result = json.loads(resp.read().decode())
                print(f"  Success!")
                return result
        except Exception as e:
            print(f"  Failed: {e}")
    raise RuntimeError("All Overpass mirrors failed")


def relation_to_feature(elem):
    tags = elem.get('tags', {})
    name = tags.get('name', '')

    # Collect outer way linestrings
    outer_lines = []
    inner_lines = []
    for member in elem.get('members', []):
        if member.get('type') != 'way' or 'geometry' not in member:
            continue
        pts = [(pt['lon'], pt['lat']) for pt in member['geometry']]
        if len(pts) < 2:
            continue
        role = member.get('role', 'outer')
        if role in ('outer', ''):
            outer_lines.append(pts)
        elif role == 'inner':
            inner_lines.append(pts)

    if not outer_lines:
        return None

    # Use shapely polygonize to assemble ways into proper closed rings
    from shapely.geometry import LineString
    outer_geom = unary_union([LineString(line) for line in outer_lines])
    outer_polys = list(polygonize(outer_geom))

    if not outer_polys:
        print(f"    WARNING: polygonize produced no polygons for {name}, falling back to chain")
        return None

    # Merge into one geometry
    merged = unary_union(outer_polys)

    # Subtract inner (hole) polygons if any
    if inner_lines:
        inner_geom = unary_union([LineString(line) for line in inner_lines])
        inner_polys = list(polygonize(inner_geom))
        if inner_polys:
            merged = merged.difference(unary_union(inner_polys))

    geojson_geom = mapping(merged)

    # Normalize coordinate precision to 7 decimal places
    def round_coords(obj):
        if isinstance(obj, (list, tuple)):
            return [round_coords(x) for x in obj]
        return round(obj, 7)

    geojson_geom['coordinates'] = round_coords(geojson_geom['coordinates'])

    return {
        'type': 'Feature',
        'properties': {'name': name, 'postal_code': tags.get('postal_code', '')},
        'geometry': geojson_geom
    }


def main():
    # Fetch all admin_level=10 boundaries in Victoria's bounding box
    query = (
        '[out:json][timeout:120][bbox:14.18,121.29,14.27,121.38];'
        '(relation["admin_level"="10"]["boundary"="administrative"];);'
        'out geom;'
    )

    try:
        raw = fetch_overpass(query)
    except Exception as e:
        print(f"ERROR fetching from Overpass: {e}")
        return

    elements = raw.get('elements', [])
    print(f"Got {len(elements)} relations total")

    features = []
    for elem in elements:
        if elem.get('type') != 'relation':
            continue
        tags = elem.get('tags', {})
        name = tags.get('name', '')
        postal = tags.get('postal_code', '')

        # Only keep Victoria barangays (postal code 4011)
        if postal != VICTORIA_POSTAL:
            continue

        print(f"  Processing: {name} (postal {postal})")
        feat = relation_to_feature(elem)
        if feat:
            features.append(feat)
        else:
            print(f"    WARNING: could not build geometry for {name}")

    if not features:
        print("ERROR: No Victoria barangay features found!")
        print("Barangay names seen in data:")
        for elem in elements:
            if elem.get('type') == 'relation':
                name = elem.get('tags', {}).get('name', '?')
                postal = elem.get('tags', {}).get('postal_code', '?')
                print(f"  {name} ({postal})")
        return

    geojson = {
        'type': 'FeatureCollection',
        'features': features,
        'source': 'osm'
    }

    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    with open(OUTPUT_PATH, 'w', encoding='utf-8') as f:
        json.dump(geojson, f)

    print(f"\nSaved {len(features)} barangay boundaries to:")
    print(f"  {OUTPUT_PATH}")
    names = [f['properties']['name'] for f in features]
    print(f"Barangays: {', '.join(sorted(names))}")


if __name__ == '__main__':
    main()
