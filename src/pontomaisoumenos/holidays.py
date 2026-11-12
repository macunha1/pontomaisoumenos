from calendar import monthrange
from datetime import date
from typing import Literal

from holidays import OPTIONAL, country_holidays

type OptionalHoliday = Literal[
    "carnival", "ash_wednesday", "corpus_christi", "public_servants_day", "christmas_eve", "new_years_eve"
]

DEFAULT_ENABLED_OPTIONAL_HOLIDAYS: tuple[OptionalHoliday, ...] = ("carnival",)
OPTIONAL_HOLIDAY_NAMES: dict[OptionalHoliday, str] = {
    "carnival": "Carnaval",
    "ash_wednesday": "Quarta-feira de Cinzas",
    "corpus_christi": "Corpus Christi",
    "public_servants_day": "Dia do Servidor Público",
    "christmas_eve": "Véspera de Natal",
    "new_years_eve": "Véspera de Ano-Novo",
}


def business_days(
    year: int,
    month: int,
    subdivision: str = "SP",
    *,
    enabled_optional_holidays: tuple[OptionalHoliday, ...] = DEFAULT_ENABLED_OPTIONAL_HOLIDAYS,
) -> list[date]:
    """Exclude public holidays and explicitly enabled optional full days off."""
    calendar = country_holidays("BR", subdiv=subdivision or None, years=year)
    if enabled_optional_holidays:
        # Fix the language so name lookup is independent of the process locale.
        optional = country_holidays("BR", years=year, categories=OPTIONAL, language="pt_BR")
        for holiday in enabled_optional_holidays:
            dates = optional.get_named(OPTIONAL_HOLIDAY_NAMES[holiday], "exact")
            calendar.update({day: optional[day] for day in dates})
    return [
        current
        for day in range(1, monthrange(year, month)[1] + 1)
        if (current := date(year, month, day)).weekday() < 5 and current not in calendar
    ]
