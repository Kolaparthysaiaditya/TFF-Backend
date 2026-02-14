from math import radians, cos, sin, asin, sqrt
from geopy.geocoders import Nominatim

def get_lat_lng_from_address(address):
    geolocator = Nominatim(user_agent="your_django_app")
    location = geolocator.geocode(address)

    if location:
        return location.latitude, location.longitude
    return None, None


def haversine(lat1, lon1, lat2, lon2):
    R = 6371000  # meters
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat/2)**2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon/2)**2
    c = 2 * asin(sqrt(a))
    return R * c
