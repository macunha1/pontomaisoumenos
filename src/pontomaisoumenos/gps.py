from random import Random


class GpsOscilator:
    """Small coordinate variation, retaining the original public class spelling."""

    def __init__(self, static_latitude: float, static_longitude: float, *, rng: Random | None = None) -> None:
        self.latitude = static_latitude
        self.longitude = static_longitude
        self.rng = rng if rng is not None else Random()

    def generate_latlong(self) -> tuple[float, float]:
        latitude = self.rng.uniform(max(-90, self.latitude - 0.00002), min(90, self.latitude + 0.00002))
        longitude = self.rng.uniform(max(-180, self.longitude - 0.00002), min(180, self.longitude + 0.00002))
        return latitude, longitude
