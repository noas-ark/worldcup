# Strategy

## Rules
- BRA vs MAR: Defense over attack.
- AUS vs TUR: Low-block over possession.
- NED vs JPN: Resilience over volume.
- QAT vs SUI: Compactness over reputation.
- GER vs CUW: Form over history.
- CIV vs ECU: Fitness over risk.
- SWE vs TUN: Efficiency over low-block.
- ESP vs CPV: Low-block over possession.
- BEL vs EGY: Discipline over favorite.
- KSA vs URU: Heat/squad over history.
- IRN vs NZL: Fatigue over quality.
- FRA vs SEN: Fitness over venue.
- IRQ vs NOR: Multi-attack over stars.
- ARG vs ALG: Fitness over venue.
- AUT vs JOR: Transition over history.
- POR vs COD: Weather over tempo.
- ENG vs CRO: Transition over microclimate.
- GHA vs PAN: Aerials over low-block.
- UZB vs COL: Midfield over environment.
- CZE vs RSA: Defense over physical.
- SUI vs BIH: Squad over venue.
- CAN vs QAT: Turf over counter.
- MEX vs KOR: Opponent transition inefficiency over passive defense.

## Data sources
- use: Search (https://api.signalfuse.co/v1/gateway/search/tavily) — squad (SUI vs BIH)
- use: Search (https://api.signalfuse.co/v1/gateway/search/brave) — vulnerability (CAN vs QAT)
- use: Venue (https://websearch--gw.swerver.net/search) — turf (CAN vs QAT)
- use: Search (https://api.signalfuse.co/v1/gateway/search/tavily) — efficiency (MEX vs KOR)
- skip: Previews (https://news-x402.com/news/recent) — venue (SUI vs BIH)
- skip: Metrics (https://skim402.com/api/v2/read) — history (SUI vs BIH)
- skip: Search (https://api.signalfuse.co/v1/gateway/search/tavily) — counters (CAN vs QAT)
- skip: Venue (https://websearch--gw.swerver.net/search) — climate (MEX vs KOR)
- skip: Previews (https://news-x402.com/news/recent) — sentiment (MEX vs KOR)