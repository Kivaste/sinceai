"""Per-task numeric measure columns, derived from the pets-eval task code (kit 1.0.0).

A column is listed when the task (or a helper it calls) refers to it and the kit catalog marks it
`numerical`. Only these columns are converted to numbers for a task; categorical or free-text
columns are never converted, even when their values look numeric. Regenerate when the kit changes:
tests/kiteval/test_numeric_columns.py fails if a kit task has no entry.
"""

from __future__ import annotations

NUMERIC_COLUMNS: dict[str, frozenset[tuple[str, str]]] = {
    "H-U1": frozenset(
        {
            ("ed_visits", "heart_rate"),
            ("ed_visits", "los_minutes"),
            ("ed_visits", "pain_nrs"),
            ("ed_visits", "resp_rate"),
            ("ed_visits", "spo2"),
            ("ed_visits", "systolic_bp"),
            ("ed_visits", "temp_c"),
        }
    ),
    "H-U2": frozenset(
        {
            ("ed_visits", "heart_rate"),
            ("ed_visits", "los_minutes"),
            ("ed_visits", "pain_nrs"),
            ("ed_visits", "resp_rate"),
            ("ed_visits", "spo2"),
            ("ed_visits", "systolic_bp"),
            ("ed_visits", "temp_c"),
        }
    ),
    "H-U3": frozenset(
        {
            ("ed_visits", "heart_rate"),
            ("ed_visits", "los_minutes"),
            ("ed_visits", "pain_nrs"),
            ("ed_visits", "resp_rate"),
            ("ed_visits", "spo2"),
            ("ed_visits", "systolic_bp"),
            ("ed_visits", "temp_c"),
        }
    ),
    "H-U4": frozenset(
        {
            ("ed_visits", "heart_rate"),
            ("ed_visits", "los_minutes"),
            ("ed_visits", "pain_nrs"),
            ("ed_visits", "resp_rate"),
            ("ed_visits", "spo2"),
            ("ed_visits", "systolic_bp"),
            ("ed_visits", "temp_c"),
        }
    ),
    "H-U5": frozenset(
        {
            ("ed_visits", "heart_rate"),
            ("ed_visits", "los_minutes"),
            ("ed_visits", "pain_nrs"),
            ("ed_visits", "resp_rate"),
            ("ed_visits", "spo2"),
            ("ed_visits", "systolic_bp"),
            ("ed_visits", "temp_c"),
        }
    ),
    "H-U6": frozenset(
        {
            ("ed_visits", "heart_rate"),
            ("ed_visits", "los_minutes"),
            ("ed_visits", "pain_nrs"),
            ("ed_visits", "resp_rate"),
            ("ed_visits", "spo2"),
            ("ed_visits", "systolic_bp"),
            ("ed_visits", "temp_c"),
        }
    ),
    "H-U7": frozenset(
        {
            ("ed_visits", "heart_rate"),
            ("ed_visits", "los_minutes"),
            ("ed_visits", "pain_nrs"),
            ("ed_visits", "resp_rate"),
            ("ed_visits", "spo2"),
            ("ed_visits", "systolic_bp"),
            ("ed_visits", "temp_c"),
            ("lab_results", "value"),
        }
    ),
    "H-U8": frozenset(
        {
            ("ed_visits", "heart_rate"),
            ("ed_visits", "los_minutes"),
            ("ed_visits", "pain_nrs"),
            ("ed_visits", "resp_rate"),
            ("ed_visits", "spo2"),
            ("ed_visits", "systolic_bp"),
            ("ed_visits", "temp_c"),
        }
    ),
    "H-DP": frozenset(
        {
            ("ed_visits", "heart_rate"),
            ("ed_visits", "los_minutes"),
            ("ed_visits", "pain_nrs"),
            ("ed_visits", "resp_rate"),
            ("ed_visits", "spo2"),
            ("ed_visits", "systolic_bp"),
            ("ed_visits", "temp_c"),
            ("lab_results", "value"),
        }
    ),
    "MOB-U1": frozenset({}),
    "MOB-U2": frozenset({}),
    "MOB-U3": frozenset({}),
    "MOB-U4": frozenset({("bike_trips", "duration_s")}),
    "MOB-U5": frozenset({}),
    "MOB-U6": frozenset({}),
    "MOB-U7": frozenset({("bike_trips", "distance_m")}),
    "MOB-U8": frozenset({}),
    "CITY-U1": frozenset({}),
    "CITY-U2": frozenset({}),
    "CITY-U3": frozenset({}),
    "CITY-U4": frozenset({}),
    "CITY-U5": frozenset({}),
    "CITY-U6": frozenset({}),
    "ENERGY-U1": frozenset(
        {("customers", "late_payment_count"), ("meter_readings_hourly", "kwh")}
    ),
    "ENERGY-U2": frozenset(
        {("customers", "late_payment_count"), ("meter_readings_hourly", "kwh")}
    ),
    "ENERGY-U3": frozenset(
        {
            ("customers", "late_payment_count"),
            ("meter_readings_hourly", "kwh"),
            ("weather_hourly", "temperature_c"),
        }
    ),
    "ENERGY-U4": frozenset(
        {
            ("customers", "late_payment_count"),
            ("meter_readings_hourly", "kwh"),
            ("weather_hourly", "temperature_c"),
        }
    ),
    "ENERGY-U5": frozenset(
        {("customers", "late_payment_count"), ("meter_readings_hourly", "kwh")}
    ),
    "ENERGY-U6": frozenset(
        {
            ("customers", "late_payment_count"),
            ("meter_readings_hourly", "kwh"),
            ("weather_hourly", "temperature_c"),
        }
    ),
    "ENERGY-U7": frozenset(
        {("customers", "late_payment_count"), ("meter_readings_hourly", "kwh")}
    ),
    "FIN-U1": frozenset(
        {("card_transactions", "amount_eur"), ("transfers", "amount_eur")}
    ),
    "FIN-U2": frozenset(
        {("card_transactions", "amount_eur"), ("transfers", "amount_eur")}
    ),
    "FIN-U3": frozenset(
        {("card_transactions", "amount_eur"), ("transfers", "amount_eur")}
    ),
    "FIN-U4": frozenset(
        {("card_transactions", "amount_eur"), ("transfers", "amount_eur")}
    ),
    "FIN-U5": frozenset(
        {("card_transactions", "amount_eur"), ("transfers", "amount_eur")}
    ),
    "FIN-U6": frozenset(
        {("card_transactions", "amount_eur"), ("transfers", "amount_eur")}
    ),
    "CYBER-U1": frozenset({}),
    "CYBER-U2": frozenset({}),
    "CYBER-U3": frozenset({}),
    "CYBER-U4": frozenset({("proxy_logs", "bytes_sent")}),
    "CYBER-U5": frozenset({}),
    "CYBER-U6": frozenset({}),
    "CYBER-U7": frozenset({}),
    "CYBER-U8": frozenset({}),
    "CYBER-U9": frozenset({}),
    "CYBER-U10": frozenset({}),
    "CYBER-U11": frozenset({}),
    "EDU-U1": frozenset({}),
    "EDU-U2": frozenset(
        {
            ("absences", "excused_hours"),
            ("absences", "late_arrivals"),
            ("absences", "unexcused_hours"),
        }
    ),
    "EDU-U3": frozenset({}),
    "EDU-U4": frozenset({("absences", "unexcused_hours")}),
    "EDU-U5": frozenset({("matriculation_results", "grade_points")}),
    "EDU-U6": frozenset({}),
    "PUB-U1": frozenset({}),
    "PUB-U2": frozenset({}),
    "PUB-U3": frozenset({}),
    "PUB-U4": frozenset({}),
    "PUB-U5": frozenset({}),
    "PUB-U6": frozenset({}),
    "CS-U1": frozenset({("turns", "seq")}),
    "CS-U2": frozenset({("conversations", "csat")}),
    "CS-U3": frozenset({}),
    "CS-U4": frozenset({("conversations", "handle_time_s")}),
    "CS-U5": frozenset({}),
    "CS-U6": frozenset({}),
    "CS-U7": frozenset({}),
}
