import numpy


class GpsOscilator:
    # To make the game interesting, GpsOsciltor generates random positions
    # based on the original one provided. Otherwise it would be easy to
    # spot the robotic behavior of this application, always sending the
    # exactly same coordinates
    def __init__(self,
                 static_latitude: float,
                 static_longitude: float):
        self.latitude_arange = numpy.arange(start=static_latitude - 0.00002,
                                            stop=static_latitude + 0.00002)
        self.longitude_arange = numpy.arange(start=static_longitude - 0.00002,
                                             stop=static_longitude + 0.00002)

    def generate_latlong(self) -> (float, float):
        return \
            numpy.random.choice(self.latitude_arange), \
            numpy.random.choice(self.longitude_arange)
