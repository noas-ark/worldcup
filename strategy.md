# Strategy

## Rules
- BRA vs MAR: Prioritize defensive structure over individual attacking talent.
- AUS vs TUR: Prioritize low-blocks and transition over possession metrics.
- NED vs JPN: Prioritize defensive resilience over individual talent.
- QAT vs SUI: Prioritize compact defense over midfield reputation.
- HAI vs SCO: Prioritize conservative setups and midfield fitness over offensive projections.

## Data sources
- use: Tournament metrics (https://skim402.com/api/v2/read) — analyze defensive structure (BRA vs MAR)
- use: Tactical previews (https://news-x402.com/news/recent) — identify wing-neutralizing schemes (BRA vs MAR)
- use: Tactical previews (https://news-x402.com/news/recent) — identify low-block transitions (AUS vs TUR)
- use: Tournament metrics (https://skim402.com/api/v2/read) — evaluate defensive resilience and conversion rates (NED vs JPN)
- use: Tactical previews (https://news-x402.com/news/recent) — identify compact setups (QAT vs SUI)
- use: Tactical previews (https://news-x402.com/news/recent) — identify conservative tactical structures (HAI vs SCO)
- use: Individual fitness news (https://news-x402.com/news/recent) — verify key midfield availability (HAI vs SCO)
- skip: Individual fitness news (https://news-x402.com/news/recent) — tactical setups dictate outcomes (BRA vs MAR)
- skip: Pitch mapping data (https://skim402.com/api/v2/read) — surface details lack predictive value (AUS vs TUR)
- skip: Qualification math (https://news-x402.com/news/recent) — scenarios do not affect performance (AUS vs TUR)
- skip: Individual fitness news (https://news-x402.com/news/recent) — fitness does not fix defensive flaws (NED vs JPN)
- skip: Betting market data (https://news-x402.com/news/recent) — reflects public sentiment, not tactics (NED vs JPN)
- skip: Tournament metrics (https://skim402.com/api/v2/read) — historical friendlies do not impact dynamics (QAT vs SUI)
- skip: Venue analysis (https://news-x402.com/news/recent) — turf and climate do not affect outcome (HAI vs SCO)
- skip: Training whispers (https://news-x402.com/news/recent) — camp rumors lack lineup impact (HAI vs SCO)