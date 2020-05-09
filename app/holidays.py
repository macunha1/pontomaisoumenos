from pandas.tseries.holiday import Holiday, AbstractHolidayCalendar
from pandas import DateOffset
from dateutil.relativedelta import MO


class BrazilianHolidayCalendar(AbstractHolidayCalendar):
    """
    Brazilian Public Holidays Calendar based on rules specified by:
    https://www.officeholidays.com/countries/brazil/index.php
    """
    rules = [
        Holiday("New Years Day", month=1, day=1),
        # It's not trivial to infer Carnival's date
        Holiday("Carnival", month=2, day=13,
                offset=DateOffset(weekday=MO(3))),
        Holiday("Good Friday", month=3, day=30),
        Holiday("Tiradentes", month=4, day=21),
        Holiday("Labour Day", month=5, day=1),
        Holiday("Corpus Christi", month=5, day=31),
        Holiday("State Rebellion Day", month=7, day=9),
        Holiday("Independence Day", month=9, day=7),
        Holiday("Our Lady of Aparecida", month=10, day=12),
        Holiday("All Souls' Day", month=11, day=2),
        Holiday("Republic Day", month=11, day=15),
        Holiday("Black Consciousness Day", month=11, day=20),
        Holiday("Christmas", month=12, day=25),
        Holiday("New Years Day", month=12, day=31),
    ]
