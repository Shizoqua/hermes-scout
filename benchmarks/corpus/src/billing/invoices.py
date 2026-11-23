"""Monthly invoices."""

from decimal import Decimal


def monthly_total(plan_price, days_in_month, days_on_plan):
    return (Decimal(plan_price) * days_on_plan / days_in_month).quantize(Decimal("0.01"))


def prorate_change(old_price, new_price, days_in_month, day_of_change):
    """Upgrading or downgrading part way through a month: pay each tier for the days used."""
    used_old = day_of_change - 1
    used_new = days_in_month - used_old
    return monthly_total(old_price, days_in_month, used_old) + monthly_total(new_price, days_in_month, used_new)
