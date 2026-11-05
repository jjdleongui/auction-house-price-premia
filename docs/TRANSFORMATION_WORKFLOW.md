# Transformation workflow

1. Download the RepOD workbook using `config/repod.json` and verify its MD5 checksum.
2. Normalize source fields using `src/auction_data/repod.py` and the declared schema in
   `src/auction_data/schema.py`.
3. Assign printmaking families with the deterministic, versioned rules in
   `src/auction_data/classification.py`.
4. Convert nominal prices to constant 2025 euros using the reference HICP files.
5. Restrict observations to the common date window and shared artist-technique support.
6. Construct fixed-effects samples, characteristic matches and same-title comparisons
   using `src/auction_data/comparable_sales.py`.
7. Release the licensed Catawiki rows, synthetic validation data and aggregate outputs.
   Do not release Spanish-house row-level records or cached catalogue material.

The public data dictionary documents every released analysis field. Zeros in the
documentation indicators mean that a feature was not explicitly documented in the
fields used; they do not establish that the feature was absent.
