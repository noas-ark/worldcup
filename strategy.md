# Strategy

## Rules
- BRA vs MAR: Prioritize collective defensive organization over individual attacking talent.
- AUS vs TUR: Prioritize low-block discipline and transition efficiency over possession metrics.
- NED vs JPN: Prioritize collective defensive resilience over high-volume chance creation.
- QAT vs SUI: Prioritize compact defensive organization over midfield reputation.
- GER vs CUW: Prioritize tier disparities and warm-up form over head-to-head history.
- CIV vs ECU: Prioritize home-field advantage and key player fitness over default defensive risk aversion.
- SWE vs TUN: Prioritize recent high-scoring offensive efficiency over theoretical low-block defensive setups.

## Data sources
- use: Tournament metrics (https://skim402.com/api/v2/read) — analyze defensive structure (BRA vs MAR)
- use: Tactical previews (https://news-x402.com/news/recent) — identify wing defense (BRA vs MAR)
- use: Tactical previews (https://news-x402.com/news/recent) — identify low-block transitions (AUS vs TUR)
- use: Tournament metrics (https://skim402.com/api/v2/read) — evaluate organization against top teams (NED vs JPN)
- use: Tactical previews (https://news-x402.com/news/recent) — evaluate compact setups (QAT vs SUI)
- use: Tournament metrics (https://skim402.com/api/v2/read) — evaluate warm-up form and tier gaps (GER vs CUW)
- use: Tactical previews (https://news-x402.com/news/recent) — evaluate squad fitness and training (CIV vs ECU)
- use: Search API (https://api.signalfuse.co/v1/gateway/search/brave) — analyze offensive efficiency (SWE vs TUN)
- skip: Tactical previews (https://news-x402.com/news/recent) — tactics dictate outcomes (BRA vs MAR)
- skip: Tournament metrics (https://skim402.com/api/v2/read) — pitch mapping lacks value (AUS vs TUR)
- skip: Tactical previews (https://news-x402.com/news/recent) — math irrelevant (AUS vs TUR)
- skip: Tactical previews (https://news-x402.com/news/recent) — fitness irrelevant (NED vs JPN)
- skip: Tactical previews (https://news-x402.com/news/recent) — odds reflect sentiment (NED vs JPN)
- skip: Tournament metrics (https://skim402.com/api/v2/read) — friendlies irrelevant (QAT vs SUI)
- skip: Tournament metrics (https://skim402.com/api/v2/read) — metrics inapplicable (GER vs CUW)
- skip: Tournament metrics (https://skim402.com/api/v2/read) — history lacks value (CIV vs ECU)
- skip: Venue search (https://websearch--gw.swerver.net/search) — environment irrelevant (SWE vs TUN)
- skip: Tactical previews (https://news-x402.com/news/recent) — context misses fragility (SWE vs TUN)