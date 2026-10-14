# Known limitations (end of Sprint II)

1. **Synthetic data.** Results show the pipeline works; they say nothing about real Kenya Airways operations.
2. **F1 ceiling.** The delay outcome includes random noise, so the best possible F1 for the delayed class is about 0.645 and flagging every trip scores 0.58. The model's test F1 is about 0.59 to 0.60. The 0.80 target in the proposal cannot be reached on this data (see `docs/evaluation_results.md`).
3. **Small-sample metrics are noisy.** The dashboard's replay precision, recall and F1 cover only the transits scored so far. Scoring 50 transits can show an F1 far from the full-test figure.
4. **No authentication (FR-01/FR-02).** Anyone who can reach the server can use the dashboard. Do not expose it to the internet before Sprint III.
5. **No Kotlin crew app, live GPS or fleet map (FR-02, FR-03, FR-10)** and **no automatic schedule generation (FR-06 to FR-08).** Planned for Sprint III.
6. **Scoring is on demand.** A dispatcher presses Score; nothing scores new transits automatically yet.
7. **One alert threshold for all corridors and ranks**, set in `.env`.
8. **Model categories are fixed at training time.** A transit with a corridor, rank, base, vehicle type or destination the model has never seen is reported as "failed" instead of scored (tested, TC-31).
9. **No database connection pool.** One connection per request is fine for a demo, not for production load.
10. **Test environment differs slightly from the working one:** CI uses PostgreSQL 16 and a small generated dataset; the developer machine runs PostgreSQL 18.
