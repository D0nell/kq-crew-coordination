# data/

- `generate_dataset.py` — regenerates the full synthetic dataset (7 CSVs).
  Run with `python3 generate_dataset.py --outdir output`.
- `output/` — where generated CSVs land locally. **Gitignored** — the
  CSVs themselves live on Google Drive (`KQ-Capstone/dataset/raw/`), not
  in this repo. Only the generator script is version-controlled, since
  that's what makes the data reproducible.
- Full column-by-column documentation: see `../docs/data_dictionary.md`.

To pull the latest data locally instead of regenerating, download the
current version from the Drive folder into `data/output/`.
