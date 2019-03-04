import numpy


class GpsOscilator:
    def __init__(self,
                 static_latitude: float,
                 static_longitude: float):
        self.latitude_arange = numpy.arange(start=static_latitude - 30,
                                            stop=static_latitude + 30)
        self.longitude_arange = numpy.arange(start=static_longitude - 30,
                                             stop=static_longitude + 30)

    def generate_latlong(self) -> (float, float):
        return \
            numpy.random.choice(self.latitude_arange), \
            numpy.random.choice(self.longitude_arange)
