"""The one area every check-in, check-out and monitoring log must be made inside: a circle set under Settings, Organization."""
from math import asin, cos, radians, sin, sqrt

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from .organization import get_organization, work_area
from .settings import get_setting


def distance_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    a = sin(radians(lat2 - lat1) / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(radians(lon2 - lon1) / 2) ** 2
    return 2 * 6371000 * asin(sqrt(a))


def enforce_work_area(db: Session, latitude: float | None, longitude: float | None, accuracy: float | None, action: str) -> float | None:
    """Refuses a position outside the work area or too vague to trust, and returns the distance from its centre (none when no area is set)."""
    area = work_area(db)
    if not area:
        return None
    centre_lat, centre_lon, radius = area
    place = get_organization(db)["name"] or "the site"
    if latitude is None or longitude is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Allow location access in your browser to {action} at {place}")
    limit = get_setting(db, "attendance.max_accuracy_m")
    if limit and accuracy and accuracy > limit:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Your location is too imprecise (within {round(accuracy)} m, the limit is {limit} m). Move to open sky or turn Wi-Fi on and try again")
    away = distance_m(latitude, longitude, centre_lat, centre_lon)
    if away > radius:
        raise HTTPException(status.HTTP_403_FORBIDDEN, f"You are about {round(away)} m from {place}. You can {action} only within {radius} m")
    return away
