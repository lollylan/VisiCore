"""
VisiCore - Routenoptimierung
Berechnet optimale Routen fuer Hausbesuche.
Portiert von Visicycle mit Anpassungen fuer VisiCore.
"""

import math
from typing import List, Tuple, Dict, Any


def haversine_distance(lat1, lon1, lat2, lon2):
    """
    Berechnet die Grosskreis-Distanz in Kilometern zwischen
    zwei Punkten auf der Erde (Dezimalgrad).
    """
    if lat1 is None or lon1 is None or lat2 is None or lon2 is None:
        return float('inf')

    lon1, lat1, lon2, lat2 = map(math.radians, [lon1, lat1, lon2, lat2])
    dlon = lon2 - lon1
    dlat = lat2 - lat1
    a = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon/2)**2
    c = 2 * math.asin(math.sqrt(a))
    r = 6371  # Erdradius in km
    return c * r


TRANSPORTMODUS_CONFIG = {
    'auto': {'geschwindigkeit_kmh': 30, 'umweg_faktor': 1.3, 'puffer_min': 5},
    'fahrrad': {'geschwindigkeit_kmh': 15, 'umweg_faktor': 1.2, 'puffer_min': 3},
    'fuss': {'geschwindigkeit_kmh': 5, 'umweg_faktor': 1.2, 'puffer_min': 2},
}


def berechne_fahrzeit_minuten(distanz_km, geschwindigkeit_kmh=30, umweg_faktor=1.3, puffer_min=5):
    """
    Schaetzt die Fahrzeit basierend auf Distanz, Durchschnittsgeschwindigkeit
    und einem Umwegfaktor (Luftlinie vs. Strasse).
    Standard: 30 km/h Stadtverkehr, Faktor 1.3 fuer Strassenumwege.
    """
    if distanz_km == float('inf'):
        return 15  # Fallback fuer unbekannte Standorte

    reale_distanz = distanz_km * umweg_faktor
    stunden = reale_distanz / geschwindigkeit_kmh
    minuten = round(stunden * 60)
    return minuten + puffer_min


def optimiere_route(start_coords: Tuple[float, float],
                    patienten: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Nearest-Neighbor-Algorithmus fuer TSP.
    start_coords: (lat, lon) der Praxis
    patienten: Liste von Dicts mit 'latitude' und 'longitude'
    Gibt: Sortierte Liste der Patienten in optimaler Reihenfolge zurueck.
    """
    gueltige = [p for p in patienten if p.get('latitude') and p.get('longitude')]
    ungueltige = [p for p in patienten if not (p.get('latitude') and p.get('longitude'))]

    if not gueltige:
        return ungueltige

    route = []
    aktuelle_pos = start_coords
    unbesucht = gueltige.copy()

    while unbesucht:
        naechster = min(unbesucht, key=lambda p:
            haversine_distance(aktuelle_pos[0], aktuelle_pos[1],
                               p['latitude'], p['longitude']))
        route.append(naechster)
        aktuelle_pos = (naechster['latitude'], naechster['longitude'])
        unbesucht.remove(naechster)

    return route + ungueltige


def berechne_routen_stats(start_coords: Tuple[float, float],
                          route: List[Dict[str, Any]],
                          transportmodus: str = 'auto') -> Dict[str, Any]:
    """
    Berechnet Statistiken fuer eine Route:
    - Gesamt-Fahrzeit
    - Gesamt-Besuchszeit
    - Gesamt-Distanz
    - Einzelne Strecken-Segmente
    """
    config = TRANSPORTMODUS_CONFIG.get(transportmodus, TRANSPORTMODUS_CONFIG['auto'])
    gesamt_fahrzeit = 0
    gesamt_distanz = 0.0
    gesamt_besuchszeit = 0
    segmente = []
    aktuelle_pos = start_coords

    for p in route:
        if p.get('latitude') and p.get('longitude'):
            distanz = haversine_distance(
                aktuelle_pos[0], aktuelle_pos[1],
                p['latitude'], p['longitude']
            )
            fahrzeit = berechne_fahrzeit_minuten(distanz, **config)
            gesamt_fahrzeit += fahrzeit
            gesamt_distanz += distanz
            segmente.append({
                'patient_id': p.get('id'),
                'distanz_km': round(distanz, 1),
                'fahrzeit_min': fahrzeit,
            })
            aktuelle_pos = (p['latitude'], p['longitude'])

        besuchszeit = p.get('besuchsdauer_minuten', 30)
        gesamt_besuchszeit += besuchszeit

    # Rueckfahrt zur Praxis
    if route and aktuelle_pos != start_coords:
        distanz = haversine_distance(
            aktuelle_pos[0], aktuelle_pos[1],
            start_coords[0], start_coords[1]
        )
        rueckfahrt = berechne_fahrzeit_minuten(distanz, **config)
        gesamt_fahrzeit += rueckfahrt
        gesamt_distanz += distanz

    return {
        'gesamt_fahrzeit_min': gesamt_fahrzeit,
        'gesamt_besuchszeit_min': gesamt_besuchszeit,
        'gesamt_zeit_min': gesamt_fahrzeit + gesamt_besuchszeit,
        'gesamt_distanz_km': round(gesamt_distanz, 1),
        'anzahl_patienten': len(route),
        'segmente': segmente,
    }


def google_maps_route_url(start_coords: Tuple[float, float],
                          route: List[Dict[str, Any]]) -> str:
    """
    Generiert einen Google Maps Directions-Link fuer die Route.
    Nuetzlich als 'Route in Google Maps oeffnen'-Button.
    """
    if not route:
        return ''

    waypoints = []
    for p in route:
        if p.get('latitude') and p.get('longitude'):
            waypoints.append(f"{p['latitude']},{p['longitude']}")
        elif p.get('adresse'):
            waypoints.append(p['adresse'].replace(' ', '+'))

    if not waypoints:
        return ''

    origin = f"{start_coords[0]},{start_coords[1]}"
    destination = origin  # Zurueck zur Praxis

    if len(waypoints) == 1:
        return (f"https://www.google.com/maps/dir/{origin}/"
                f"{waypoints[0]}/{destination}")

    # Google Maps unterstuetzt bis zu 25 Wegpunkte
    wp_str = "/".join(waypoints)
    return f"https://www.google.com/maps/dir/{origin}/{wp_str}/{destination}"
