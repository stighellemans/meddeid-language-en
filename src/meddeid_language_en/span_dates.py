"""Render event dates and clinical ages from their original context."""

from datetime import date, timedelta

from meddeid_core.age_policy import load_age_granularity_policy

from . import dates


def date_body(text, *, offset, reference, profile_id, before="", after=""):
    return dates.pseudonymize_date_text(
        text,
        label="Date",
        profile_id=profile_id,
        date_shift_days=offset,
        reference_date=reference,
        context_before=before,
        context_after=after,
    )


def age_body(text, *, offset, reference, profile_id, before="", after=""):
    parsed = dates.parse_date_text(
        text,
        label="Age_Birthdate",
        profile_id=profile_id,
        reference_date=reference,
        context_before=before,
        context_after=after,
    )
    if parsed is None:
        return None
    if parsed.precision == "relative":
        return dates.pseudonymize_date_text(
            text,
            label="Age_Birthdate",
            profile_id=profile_id,
            date_shift_days=0,
            reference_date=reference,
            context_before=before,
            context_after=after,
        )
    if parsed.value is None:
        return None
    # Month/year precision needs an interval, never a fabricated exact birthday.
    start = parsed.value
    if parsed.precision == "year":
        end = date(start.year, 12, 31)
    elif parsed.precision == "month":
        import calendar

        end = date(
            start.year, start.month, calendar.monthrange(start.year, start.month)[1]
        )
    elif parsed.precision == "day":
        end = start
    else:
        return None
    if reference is not None:
        policy = load_age_granularity_policy()
        ages = [policy.generalize(value, reference) for value in (start, end)]
        if any(value is None for value in ages):
            return None
        bodies = [dates._render_english_age_parts(parts) + " old" for parts in ages]
        return bodies[0] if bodies[0] == bodies[1] else "/".join(bodies)
    if offset:
        years = [(value + timedelta(days=offset)).year for value in (start, end)]
        return str(years[0]) if years[0] == years[1] else f"{years[0]}/{years[1]}"
    return None
