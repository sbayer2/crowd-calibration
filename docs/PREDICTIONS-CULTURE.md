# Pre-registered predictions — experiment 3: pop culture, question and choices only

Written 2026-10-01, before Jev has answered any culture question and before any outcome is known.

**Design.** `culture.py`: Polymarket culture events (creators, music, film, reality TV, podcasts, gaming) closing 20
minutes to 8 days after the freeze. Jev sees **only the event title and the options**: no description, dates, rules
or prices.
- Exclusive events (one winner among brackets): one choice question.
- Independent items (words that may be said, threshold rungs): one yes/no per item.
- Crowd = the bid-ask midpoint, or the last trade if the quote is wider than 0.10.
- Jev: 3 runs, mean.

**Scores.** Per option, Brier against the outcome (1 = the option resolved Yes): crowd, Jev and a coin flip. For
exclusive events, also whether each side's top pick won. Head-to-head: how often Jev and the crowd fall on the same
side of 50%.

**Predictions.**
- **K1.** The crowd beats Jev on Brier over all resolved options. On chart and streaming markets the crowd reads
  public data mid-week; Jev does not even know the current songs.
- **K2.** On the questions where the crowd itself is unsure (crowd 35-65%: words that may be said, launch numbers),
  Jev is no worse than the crowd. Brier gap within ±0.03, reported as counts unless n ≥ 40.
- **K3.** Jev and the crowd fall on the same side of 50% on at least 70% of options. Most options are long shots both
  will reject.

**Amendment (2026-10-01, after Jev answered, before any outcome).** Options named like Polymarket's unfilled
placeholder slots ("Song A", "Song 1", "Album B") are excluded from every score. They are not real choices and always
resolve No. Jev's answers on them are kept in the run files.
