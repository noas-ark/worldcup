# Strategy

## Rules
- BRA vs MAR: Prioritize defensive organization over individual attack.
- AUS vs TUR: Prioritize low-block discipline over possession metrics.
- NED vs JPN: Prioritize defensive resilience over chance volume.
- QAT vs SUI: Prioritize compact defense over reputation.
- GER vs CUW: Prioritize tier gaps and form over history.
- CIV vs ECU: Prioritize home advantage and fitness over risk aversion.
- SWE vs TUN: Prioritize scoring efficiency over low-block setups.
- ESP vs CPV: Prioritize physical low-block organization over possession dominance.

## Data sources
- use: Tournament metrics (https://skim402.com/api/v2/read) — defense (BRA vs MAR)
- use: Tactical previews (https://news-x402.com/news/recent) — wings (BRA vs MAR)
- use: Tactical previews (https://news-x402.com/news/recent) — transitions (AUS vs TUR)
- use: Tournament metrics (https://skim402.com/api/v2/read) — organization (NED vs JPN)
- use: Tactical previews (https://news-x402.com/news/recent) — compact (QAT vs SUI)
- use: Tournament metrics (https://skim402.com/api/v2/read) — form (GER vs CUW)
- use: Tactical previews (https://news-x402.com/news/recent) — fitness (CIV vs ECU)
- use: Search API (https://api.signalfuse.co/v1/gateway/search/brave) — efficiency (SWE vs TUN)
- use: Tournament metrics (https://skim402.com/api/v2/read) — conversion (ESP vs CPV)
- use: Search API (https://api.signalfuse.co/v1/gateway/search/brave) — tactics (ESP vs CPV)
- skip: Tactical previews (https://news-x402.com/news/recent) — outcomes (BRA vs MAR)
- skip: Tournament metrics (https://skim402.com/api/v2/read) — mapping (AUS vs TUR)
- skip: Tactical previews (https://news-x402.com/news/recent) — math (AUS vs TUR)
- skip: Tactical previews (https://news-x402.com/news/recent) — fitness (NED vs JPN)
- skip: Tactical previews (https://news-x402.com/news/recent) — sentiment (NED vs JPN)
- skip: Tournament metrics (https://skim402.com/api/v2/read) — friendlies (QAT vs SUI)
- skip: Tournament metrics (https://skim402.com/api/v2/read) — metrics (GER vs CUW)
- skip: Tournament metrics (https://skim402.com/api/v2/read) — history (CIV vs ECU)
- skip: Venue search (https://websearch--gw.swerver.net/search) — environment (SWE vs TUN)
- skip: Tactical previews (https://news-x402.com/news/recent) — fragility (SWE vs TUN)
- skip: Tactical previews (https://news-x402.com/news/recent) — rules (ESP vs CPV)