"""Canonical H3 index utility functions.

Centralizes all H3 conversions, validations, resolution checks, and geometry conversions
across the backend and API to prevent duplicated or conflicting implementations.
"""

from typing import Union
import h3
from core.errors import InvalidH3IndexError


def is_valid_h3(h3_val: Union[str, int]) -> bool:
    """Checks whether the supplied H3 identifier is valid (accepts hex string or integer)."""
    if isinstance(h3_val, int):
        if h3_val <= 0:
            return False
        try:
            h3_str = h3.int_to_str(h3_val)
            return h3.is_valid_cell(h3_str)
        except Exception:
            return False
    elif isinstance(h3_val, str):
        cleaned = h3_val.strip().lower()
        if not cleaned:
            return False
        try:
            return h3.is_valid_cell(cleaned)
        except Exception:
            return False
    return False


def h3_to_str(h3_val: Union[str, int]) -> str:
    """Converts an H3 identifier to canonical lowercase hexadecimal string.
    
    Raises:
        InvalidH3IndexError: if h3_val is not a valid H3 index.
    """
    if isinstance(h3_val, int):
        if not is_valid_h3(h3_val):
            raise InvalidH3IndexError(h3_val)
        return h3.int_to_str(h3_val).lower()
    elif isinstance(h3_val, str):
        cleaned = h3_val.strip().lower()
        if not is_valid_h3(cleaned):
            raise InvalidH3IndexError(h3_val)
        return cleaned
    raise InvalidH3IndexError(str(h3_val))


def h3_to_int(h3_val: Union[str, int]) -> int:
    """Converts an H3 identifier to 64-bit integer.
    
    Raises:
        InvalidH3IndexError: if h3_val is not a valid H3 index.
    """
    if isinstance(h3_val, int):
        if not is_valid_h3(h3_val):
            raise InvalidH3IndexError(h3_val)
        return h3_val
    elif isinstance(h3_val, str):
        cleaned = h3_val.strip().lower()
        if not is_valid_h3(cleaned):
            raise InvalidH3IndexError(h3_val)
        return h3.str_to_int(cleaned)
    raise InvalidH3IndexError(str(h3_val))


def h3_get_resolution(h3_val: Union[str, int]) -> int:
    """Returns the resolution (0-15) of an H3 cell."""
    h3_str = h3_to_str(h3_val)
    return h3.get_resolution(h3_str)


def h3_to_centroid(h3_val: Union[str, int]) -> tuple[float, float]:
    """Returns the centroid coordinates of an H3 cell as (longitude, latitude)."""
    h3_str = h3_to_str(h3_val)
    lat, lng = h3.cell_to_latlng(h3_str)
    return round(lng, 6), round(lat, 6)


def h3_to_boundary_coords(h3_val: Union[str, int]) -> list[list[float]]:
    """Returns boundary coordinates as GeoJSON [[lon, lat], ...] closed polygon."""
    h3_str = h3_to_str(h3_val)
    boundary = h3.cell_to_boundary(h3_str)  # list of (lat, lng)
    coords = [[round(lng, 6), round(lat, 6)] for lat, lng in boundary]
    if coords and coords[0] != coords[-1]:
        coords.append(coords[0])  # close ring
    return coords


def h3_to_wkt_polygon(h3_val: Union[str, int]) -> str:
    """Returns the WKT Polygon representation for PostGIS / GeoAlchemy2."""
    coords = h3_to_boundary_coords(h3_val)
    coord_strs = [f"{pt[0]} {pt[1]}" for pt in coords]
    return f"POLYGON(({', '.join(coord_strs)}))"


def h3_to_wkt_point(h3_val: Union[str, int]) -> str:
    """Returns the WKT Point representation for the cell centroid."""
    lon, lat = h3_to_centroid(h3_val)
    return f"POINT({lon} {lat})"
