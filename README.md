# Auction-House Price Premia in a Digitally Connected Art Market

Public data and reproducible transformation code supporting the analysis of prints and
multiples sold through Spanish auction houses and Catawiki.

This repository contains the materials that can be shared publicly. It separates
licensed row-level data from aggregate results derived from source records that cannot
be redistributed.

## Key sample information

| Measure | Value |
| --- | ---: |
| Common-support observations | 12,364 |
| Artist–technique cells | 263 |
| Characteristic-matched pairs | 292 |
| Same-title pairs | 34 |
| Strict same-title, similar-size pairs | 12 |

## Contents

- `data/public/`: the licensed Catawiki analysis data, synthetic validation data,
  classification and sample audits, and aggregate model outputs.
- `data/reference/`: Spanish HICP series used to express prices in constant 2025 euros.
- `src/auction_data/`: deterministic normalization, classification, validation,
  common-support, matching and estimation functions.
- `scripts/reproduce_public_results.py`: checks the released result tables and executes
  a model on the synthetic validation data.
- `tests/`: tests of artist, technique, title, dimensions and documentation transforms.
- `docs/`: classification rules, transformation workflow and data-availability limits.

## Data availability

The Catawiki component derives from the RepOD deposit at
<https://doi.org/10.18150/AEQF8C> and is released under ODbL 1.0. Spanish auction-house
records were collected from publicly accessible historical catalogues and results, but
the row-level extracts and cached pages are not redistributed because public access does
not establish a right to republish those databases. Only aggregate Spanish-house outputs
are included here.

No bidder information, credentials, raw Spanish-house records, catalogue images or
catalogue descriptions are included.

## Run the public checks

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
PYTHONPATH=src python scripts/reproduce_public_results.py
PYTHONPATH=src python -m pytest -q
```

Re-estimating cross-channel models from individual Spanish lots requires the restricted
source layer retained for verification. The released aggregate results and synthetic
data allow inspection and testing without redistributing that layer.

## Licences

Code is provided under the MIT License. Data licences and attribution are described in
`DATA_LICENSE.md`.
