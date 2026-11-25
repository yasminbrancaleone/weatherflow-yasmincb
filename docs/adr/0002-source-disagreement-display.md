# ADR 0002: Displaying source disagreements

- Status: Accepted
- Date: 2026-11-25

## Context

Open-Meteo and WeatherAPI can report different temperatures for the same city
and forecast hour. The configured cross-source tolerance is 3 °C, and neither
provider has been established as the authoritative source.

## Decision

Show both providers' readings for the selected city and flag paired forecast
hours whose absolute temperature difference is greater than the configured
tolerance. Do not select or silently prefer one provider.

## Consequences

Users can see the size and frequency of disagreements while retaining both
source values. The comparison counts only hours with readings from both sources;
the dashboard does not resolve a disagreement into a single "correct" value.

## Alternatives considered

- Prefer one provider: rejected because there is no verified basis for treating
  either feed as authoritative.
- Average the two readings: rejected because it would hide the disagreement
  and imply an accuracy neither source has established.
- Show both readings without a threshold flag: rejected because large
  disagreements would be harder to identify at a glance.
