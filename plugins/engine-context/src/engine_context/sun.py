from __future__ import annotations

import math
from datetime import UTC, datetime
from typing import Literal

SunPhase = Literal["day", "civil_twilight", "night"]


def solar_position(
    latitude_deg: float, longitude_deg: float, when: datetime
) -> tuple[float, bool, SunPhase]:
    """NOAA solar elevation, horizon flag, and coarse phase.

    Elevation is apparent (refraction-corrected) and in degrees. Civil
    twilight is the NOAA band ``-6° <= elevation < 0°``.
    """
    if when.tzinfo is None:
        when = when.replace(tzinfo=UTC)
    else:
        when = when.astimezone(UTC)
    elevation = apparent_solar_elevation_deg(latitude_deg, longitude_deg, when)
    if elevation >= 0.0:
        phase: SunPhase = "day"
    elif elevation >= -6.0:
        phase = "civil_twilight"
    else:
        phase = "night"
    return elevation, elevation >= 0.0, phase


def apparent_solar_elevation_deg(
    latitude_deg: float, longitude_deg: float, when: datetime
) -> float:
    julian = _julian_day(when)
    century = (julian - 2451545.0) / 36525.0
    declination = _sun_declination_deg(century)
    hour_angle = _hour_angle_deg(longitude_deg, century, when)
    lat = math.radians(latitude_deg)
    dec = math.radians(declination)
    ha = math.radians(hour_angle)
    cosine_zenith = (
        math.sin(lat) * math.sin(dec)
        + math.cos(lat) * math.cos(dec) * math.cos(ha)
    )
    cosine_zenith = min(1.0, max(-1.0, cosine_zenith))
    zenith = math.degrees(math.acos(cosine_zenith))
    return 90.0 - zenith + _refraction_deg(90.0 - zenith)


def _julian_day(when: datetime) -> float:
    year, month, day = when.year, when.month, when.day
    hour = (
        when.hour
        + when.minute / 60.0
        + when.second / 3600.0
        + when.microsecond / 3.6e9
    )
    if month <= 2:
        year -= 1
        month += 12
    a = year // 100
    b = 2 - a + a // 4
    return (
        int(365.25 * (year + 4716))
        + int(30.6001 * (month + 1))
        + day
        + hour / 24.0
        + b
        - 1524.5
    )


def _geom_mean_longitude_deg(century: float) -> float:
    value = 280.46646 + century * (36000.76983 + 0.0003032 * century)
    return value % 360.0


def _geom_mean_anomaly_deg(century: float) -> float:
    return 357.52911 + century * (35999.05029 - 0.0001537 * century)


def _eccentricity(century: float) -> float:
    return 0.016708634 - century * (0.000042037 + 0.0000001267 * century)


def _sun_eq_of_center_deg(century: float) -> float:
    anomaly = math.radians(_geom_mean_anomaly_deg(century))
    return (
        math.sin(anomaly) * (1.914602 - century * (0.004817 + 0.000014 * century))
        + math.sin(2.0 * anomaly) * (0.019993 - 0.000101 * century)
        + math.sin(3.0 * anomaly) * 0.000289
    )


def _sun_apparent_longitude_deg(century: float) -> float:
    true_long = _geom_mean_longitude_deg(century) + _sun_eq_of_center_deg(century)
    omega = math.radians(125.04 - 1934.136 * century)
    return true_long - 0.00569 - 0.00478 * math.sin(omega)


def _obliquity_correction_deg(century: float) -> float:
    seconds = 21.448 - century * (
        46.8150 + century * (0.00059 - century * 0.001813)
    )
    mean = 23.0 + (26.0 + seconds / 60.0) / 60.0
    omega = math.radians(125.04 - 1934.136 * century)
    return mean + 0.00256 * math.cos(omega)


def _sun_declination_deg(century: float) -> float:
    obliquity = math.radians(_obliquity_correction_deg(century))
    apparent = math.radians(_sun_apparent_longitude_deg(century))
    return math.degrees(math.asin(math.sin(obliquity) * math.sin(apparent)))


def _equation_of_time_minutes(century: float) -> float:
    epsilon = math.radians(_obliquity_correction_deg(century))
    l0 = math.radians(_geom_mean_longitude_deg(century))
    e = _eccentricity(century)
    m = math.radians(_geom_mean_anomaly_deg(century))
    y = math.tan(epsilon / 2.0) ** 2
    sin2l0 = math.sin(2.0 * l0)
    sinm = math.sin(m)
    cos2l0 = math.cos(2.0 * l0)
    sin4l0 = math.sin(4.0 * l0)
    sin2m = math.sin(2.0 * m)
    etime = (
        y * sin2l0
        - 2.0 * e * sinm
        + 4.0 * e * y * sinm * cos2l0
        - 0.5 * y * y * sin4l0
        - 1.25 * e * e * sin2m
    )
    return math.degrees(etime) * 4.0


def _hour_angle_deg(longitude_deg: float, century: float, when: datetime) -> float:
    minutes = when.hour * 60.0 + when.minute + when.second / 60.0
    true_solar = (
        minutes + _equation_of_time_minutes(century) + 4.0 * longitude_deg
    ) % 1440.0
    hour_angle = true_solar / 4.0 - 180.0
    if hour_angle < -180.0:
        hour_angle += 360.0
    return hour_angle


def _refraction_deg(elevation_deg: float) -> float:
    if elevation_deg > 85.0:
        return 0.0
    te = math.tan(math.radians(elevation_deg))
    if elevation_deg > 5.0:
        refraction = (
            58.1 / te - 0.07 / (te**3) + 0.000086 / (te**5)
        )
    elif elevation_deg > -0.575:
        refraction = 1735.0 + elevation_deg * (
            -518.2
            + elevation_deg
            * (103.4 + elevation_deg * (-12.79 + elevation_deg * 0.711))
        )
    else:
        refraction = -20.774 / te
    return refraction / 3600.0
