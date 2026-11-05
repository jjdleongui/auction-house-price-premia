"""Compare published prices across Spanish auction houses and Catawiki.

The comparison is restricted to the shared RepOD/Catawiki observation window and to
artist-technique cells observed in Catawiki and at least one Spanish house. The main
models use artist-technique fixed effects, calendar-year controls, catalogue
characteristics, and print dimensions when available. A stricter one-to-one matched
comparison is restricted to common support in observable lot characteristics.

The estimates describe associations among published sold results. They are not causal
platform effects: house choice, lot selection, fees, attribution, condition and the
publication process may differ across sources.
"""

from __future__ import annotations

import math
import re
import unicodedata
from difflib import SequenceMatcher
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.api as sm


OVERLAP_START = pd.Timestamp("2020-11-04")
OVERLAP_END = pd.Timestamp("2024-05-11")
REFERENCE_CHANNEL = "Catawiki"

SPANISH_TECHNIQUES = {
    "Calcografía": "Calcografía",
    "Litografía": "Litografía",
    "Serigrafía": "Serigrafía",
    "Digital (giclée/inkjet)": "Digital",
    "Grabado en relieve": "Relieve",
    "Fotomecánica": "Fotomecánica",
}

DERIVATIVE_PATTERN = re.compile(
    r"\b(after|segun|atribuido|attributed|school of|escuela de|circle of|circulo de|"
    r"taller de|workshop of|follower of)\b|\bd\s*apres\b",
    re.I,
)

MULTIWORK_PATTERN = re.compile(
    r"\b(carpeta|portfolio|suite|conjunto|pareja de|lot of|set of|diptych|diptico|"
    r"triptych|triptico)\b|\b\d{1,2}\s+(grabados|estampas|litografias|serigrafias|"
    r"prints|works|laminas)\b",
    re.I,
)

TITLE_STOPWORDS = {
    "a", "al", "and", "con", "d", "de", "del", "des", "di", "el", "en", "et",
    "from", "la", "las", "le", "les", "los", "of", "the", "un", "una", "y",
    "serie", "series", "sin", "titulo", "untitled", "sans", "titre", "obra",
    "composition", "composicion", "gravure", "lithograph", "lithographie", "litografia",
    "original", "originale", "print",
}


def normalise_text(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value or "").casefold())
    text = "".join(character for character in text if not unicodedata.combining(character))
    text = text.replace("&amp;", " and ")
    return " ".join(re.sub(r"[^a-z0-9]+", " ", text).split())


def extract_spanish_artist(title: object) -> str:
    raw = " ".join(str(title or "").split())
    if not raw or DERIVATIVE_PATTERN.search(normalise_text(raw)):
        return ""
    raw = re.sub(r"^\s*\d+\.?\s*", "", raw)
    if "(" in raw:
        candidate = raw.split("(", 1)[0]
    else:
        parts = re.split(r"\s+-\s+|\.\s+|,\s+[\"“]", raw, maxsplit=1)
        if len(parts) == 1:
            return ""
        candidate = parts[0]
    candidate = candidate.strip(" .,-\"“”")
    if not candidate or len(candidate.split()) > 8:
        return ""
    if any(token in normalise_text(candidate).split() for token in ("escuela", "anonimo")):
        return ""
    return candidate


def extract_catawiki_artist(value: object) -> str:
    raw = " ".join(str(value or "").split())
    if not raw or DERIVATIVE_PATTERN.search(normalise_text(raw)):
        return ""
    raw = re.sub(r"\s*\([^)]*\)", " ", raw)
    return raw.split(",", 1)[0].strip()


def artist_key(value: object) -> str:
    tokens = [
        token for token in normalise_text(value).split()
        if token not in {"de", "del", "la", "las", "los", "y", "the"}
    ]
    if not tokens:
        return ""
    if "picasso" in tokens:
        return "pablo picasso"
    if "goya" in tokens:
        return "francisco goya"
    if len(tokens) == 1:
        return tokens[0]
    return f"{tokens[0]} {tokens[-1]}"


def catawiki_technique(value: object) -> str:
    text = normalise_text(value)
    rules = [
        ("Digital", ("gicl", "digital", "inkjet")),
        ("Serigrafía", ("silkscreen", "silk screen", "screen print", "screenprint", "serigraph")),
        ("Litografía", ("lithograph", "lithography")),
        ("Calcografía", ("etching", "engraving", "aquatint", "drypoint", "mezzotint", "intaglio", "burin")),
        ("Relieve", ("woodcut", "linocut", "woodblock")),
        ("Fotomecánica", ("photogravure", "heliogravure", "photolith", "collotype", "offset", "rotogravure")),
    ]
    for label, terms in rules:
        if any(normalise_text(term) in text for term in terms):
            return label
    return ""


def parse_area(value: object) -> float:
    text = unicodedata.normalize("NFKD", str(value or "")).replace("×", "x").replace("✕", "x")
    match = re.search(
        r"(?<!\d)(\d{1,3}(?:[.,]\d+)?)\s*[xX]\s*(\d{1,3}(?:[.,]\d+)?)",
        text,
    )
    if not match:
        return math.nan
    width = float(match.group(1).replace(",", "."))
    height = float(match.group(2).replace(",", "."))
    if not (3 <= width <= 300 and 3 <= height <= 300):
        return math.nan
    return width * height


def has_catawiki_documentation(signature: object, edition: object) -> int:
    signature_text = normalise_text(signature)
    edition_text = normalise_text(edition)
    signed = bool(signature_text) and signature_text not in {"not signed", "unsigned", "no signature"}
    edition_present = bool(edition_text) and edition_text not in {"nan", "none", "unknown"}
    return int(signed or edition_present)


def signed_documented(value: object) -> int:
    """Return one only when the catalogue positively records a signature."""
    text = normalise_text(value)
    if re.search(r"\b(sin firmar|not signed|unsigned|no signature)\b", text):
        return 0
    return int(bool(re.search(r"\b(firmad[oa]?|hand signed|plate signed|signed)\b", text)))


def edition_documented(value: object) -> int:
    """Return one when the catalogue field positively documents an edition."""
    text = normalise_text(value)
    return int(bool(text) and text not in {"nan", "none", "unknown"})


def extract_creation_year(value: object) -> float:
    """Extract a plausible work date, avoiding artist life dates already removed."""
    years = [
        int(year)
        for year in re.findall(r"(?<!\d)(1[45-9]\d{2}|20[0-2]\d)(?!\d)", str(value or ""))
    ]
    return float(years[-1]) if years else math.nan


def work_title_spanish(value: object) -> str:
    raw = " ".join(str(value or "").split())
    if ")" in raw:
        return raw.rsplit(")", 1)[1].strip(" .,-\"“”")
    parts = re.split(r"\s+-\s+|\.\s+|,\s+[\"“]", raw, maxsplit=1)
    return parts[1].strip(" .,-\"“”") if len(parts) > 1 else ""


def title_key(value: object, artist: object = "") -> str:
    artist_tokens = set(normalise_text(artist).split())
    tokens = [
        token for token in normalise_text(value).split()
        if token not in TITLE_STOPWORDS
        and token not in artist_tokens
        and not re.fullmatch(r"(?:18|19|20)\d{2}", token)
    ]
    if not tokens or not any(len(token) >= 4 for token in tokens):
        return ""
    return " ".join(tokens)


def title_similarity(left: str, right: str) -> float:
    if not left or not right:
        return 0.0
    sequence = SequenceMatcher(None, left, right).ratio()
    left_tokens, right_tokens = set(left.split()), set(right.split())
    union = left_tokens | right_tokens
    jaccard = len(left_tokens & right_tokens) / len(union) if union else 0.0
    return max(sequence, jaccard)


def load_hicp(project: Path) -> dict[int, float]:
    frame = pd.read_csv(project / "data" / "reference" / "spain_hicp_annual_2014_2025.csv")
    return dict(zip(frame["year"].astype(int), frame["hicp_annual_average"].astype(float)))


def prepare_spanish(project: Path, hicp: dict[int, float]) -> pd.DataFrame:
    source = project / "data" / "derived" / "spanish_prints_classified.csv"
    frame = pd.read_csv(source, low_memory=False)
    frame["date"] = pd.to_datetime(frame["auction_date"], errors="coerce")
    frame["price_eur"] = pd.to_numeric(frame["realized_price"], errors="coerce")
    frame = frame[
        frame["research_is_graphic_art"].eq(1)
        & frame["sold_status"].eq("sold")
        & frame["price_eur"].gt(0)
        & frame["currency"].eq("EUR")
        & frame["date"].between(OVERLAP_START, OVERLAP_END)
    ].copy()
    frame["technique"] = frame["research_classification"].map(SPANISH_TECHNIQUES).fillna("")
    frame["artist_display"] = frame["title"].map(extract_spanish_artist)
    frame["artist_key"] = frame["artist_display"].map(artist_key)
    combined_text = frame["title"].fillna("") + " " + frame["description"].fillna("")
    frame["multiwork"] = combined_text.map(lambda value: bool(MULTIWORK_PATTERN.search(normalise_text(value))))
    frame["area_cm2"] = combined_text.map(parse_area)
    frame["documented"] = pd.to_numeric(frame["edition_evidence"], errors="coerce").fillna(0).astype(int)
    frame["work_title"] = frame["title"].map(work_title_spanish)
    frame["creation_year_comparable"] = frame["work_title"].map(extract_creation_year)
    frame["signed_documented"] = combined_text.map(signed_documented)
    frame["edition_documented"] = frame["documented"]
    frame["title_key"] = [
        title_key(title, artist) for title, artist in zip(frame["work_title"], frame["artist_display"])
    ]
    frame["channel"] = frame["auction_house"].astype(str)
    frame["source"] = "Casas españolas"
    frame["record_source_id"] = frame["record_id"].astype(str)
    frame["year"] = frame["date"].dt.year.astype(int)
    frame["real_price_2025"] = frame["price_eur"] * hicp[2025] / frame["year"].map(hicp)
    return frame[
        frame["technique"].ne("")
        & frame["artist_key"].ne("")
        & ~frame["multiwork"]
        & frame["real_price_2025"].gt(0)
    ].copy()


def prepare_catawiki(project: Path, hicp: dict[int, float]) -> pd.DataFrame:
    source = project / "data" / "normalized" / "repod_prints_deduplicated.csv"
    frame = pd.read_csv(source, low_memory=False)
    frame["date"] = pd.to_datetime(frame["auction_date"], errors="coerce")
    frame["price_eur"] = pd.to_numeric(frame["price_amount"], errors="coerce")
    object_type = frame["object_type"].fillna("").map(normalise_text)
    frame = frame[
        frame["price_eur"].gt(0)
        & frame["currency"].eq("EUR")
        & frame["date"].between(OVERLAP_START, OVERLAP_END)
        & (object_type.eq("") | object_type.eq("print"))
    ].copy()
    frame["technique"] = frame["technique"].map(catawiki_technique)
    frame["artist_display"] = frame["artist"].map(extract_catawiki_artist)
    frame["artist_key"] = frame["artist_display"].map(artist_key)
    combined_text = frame["title"].fillna("") + " " + frame["technique"].fillna("")
    frame["multiwork"] = combined_text.map(lambda value: bool(MULTIWORK_PATTERN.search(normalise_text(value))))
    frame["area_cm2"] = frame["dimensions_text"].map(parse_area)
    frame["documented"] = [
        has_catawiki_documentation(signature, edition)
        for signature, edition in zip(frame["signature"], frame["edition"])
    ]
    frame["work_title"] = frame["title"].fillna("").astype(str)
    frame["creation_year_comparable"] = pd.to_numeric(frame["creation_year"], errors="coerce")
    frame.loc[
        ~frame["creation_year_comparable"].between(1400, 2026), "creation_year_comparable"
    ] = math.nan
    frame["signed_documented"] = frame["signature"].map(signed_documented)
    frame["edition_documented"] = frame["edition"].map(edition_documented)
    frame["title_key"] = [
        title_key(title, artist) for title, artist in zip(frame["work_title"], frame["artist_display"])
    ]
    frame["channel"] = REFERENCE_CHANNEL
    frame["source"] = REFERENCE_CHANNEL
    frame["record_source_id"] = frame["record_id"].astype(str)
    frame["year"] = frame["date"].dt.year.astype(int)
    frame["real_price_2025"] = frame["price_eur"] * hicp[2025] / frame["year"].map(hicp)
    return frame[
        frame["technique"].ne("")
        & frame["artist_key"].ne("")
        & ~frame["multiwork"]
        & frame["real_price_2025"].gt(0)
    ].copy()


def comparable_sample(spanish: pd.DataFrame, catawiki: pd.DataFrame) -> pd.DataFrame:
    spanish = spanish.copy()
    catawiki = catawiki.copy()
    spanish["pair"] = spanish["artist_key"] + " | " + spanish["technique"]
    catawiki["pair"] = catawiki["artist_key"] + " | " + catawiki["technique"]
    common_pairs = set(spanish["pair"]) & set(catawiki["pair"])
    combined = pd.concat(
        [spanish[spanish["pair"].isin(common_pairs)], catawiki[catawiki["pair"].isin(common_pairs)]],
        ignore_index=True,
        sort=False,
    )
    combined["log_price"] = np.log(combined["real_price_2025"])
    combined["area_missing"] = combined["area_cm2"].isna().astype(int)
    combined["log_area"] = np.log(combined["area_cm2"])
    pair_median = combined.groupby("pair", observed=True)["log_area"].transform("median")
    combined["log_area_filled"] = combined["log_area"].fillna(pair_median)
    combined["log_area_filled"] = combined["log_area_filled"].fillna(combined["log_area"].median())
    return combined


def _within_model(
    frame: pd.DataFrame,
    include_characteristics: bool,
    pooled_spanish: bool = False,
) -> tuple[object, list[str]]:
    if pooled_spanish:
        channel_frame = pd.DataFrame(
            {"Casas españolas": frame["channel"].ne(REFERENCE_CHANNEL).astype(float)},
            index=frame.index,
        )
        channel_columns = ["Casas españolas"]
    else:
        channel_frame = pd.get_dummies(frame["channel"], dtype=float)
        channel_frame = channel_frame.drop(columns=[REFERENCE_CHANNEL], errors="ignore")
        channel_columns = sorted(channel_frame.columns.tolist())
        channel_frame = channel_frame.reindex(columns=channel_columns)
    years = pd.get_dummies(frame["year"].astype(str), prefix="Año", dtype=float)
    years = years.drop(columns=["Año_2020"], errors="ignore")
    blocks = [channel_frame, years]
    if include_characteristics:
        blocks.append(frame[["documented", "log_area_filled", "area_missing"]].astype(float))
    design = pd.concat(blocks, axis=1).astype(float)
    within_y = frame["log_price"] - frame.groupby("pair", observed=True)["log_price"].transform("mean")
    within_x = design - design.groupby(frame["pair"], observed=True).transform("mean")
    active = within_x.columns[within_x.std().gt(1e-10)]
    within_x = within_x[active]
    model = sm.OLS(within_y, within_x).fit(
        cov_type="cluster",
        cov_kwds={"groups": frame["pair"], "use_correction": True},
    )
    return model, [column for column in channel_columns if column in active]


def effect_row(model: object, term: str) -> dict[str, float]:
    beta = float(model.params[term])
    standard_error = float(model.bse[term])
    low = beta - 1.959963984540054 * standard_error
    high = beta + 1.959963984540054 * standard_error
    return {
        "log_coefficient": beta,
        "standard_error": standard_error,
        "percent_difference": 100 * math.expm1(beta),
        "ci95_low_percent": 100 * math.expm1(low),
        "ci95_high_percent": 100 * math.expm1(high),
        "p_value": float(model.pvalues[term]),
    }


def fit_models(frame: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    basic, basic_channels = _within_model(frame, include_characteristics=False)
    adjusted, adjusted_channels = _within_model(frame, include_characteristics=True)
    lower, upper = frame["real_price_2025"].quantile([0.01, 0.99])
    trimmed_frame = frame[frame["real_price_2025"].between(lower, upper)].copy()
    trimmed, trimmed_channels = _within_model(trimmed_frame, include_characteristics=True)
    pooled, pooled_channels = _within_model(frame, include_characteristics=True, pooled_spanish=True)

    complete_frame = frame[frame["area_cm2"].notna()].copy()
    complete_pair_scope = complete_frame.groupby("pair", observed=True)["channel"].agg(
        lambda values: values.eq(REFERENCE_CHANNEL).any() and values.ne(REFERENCE_CHANNEL).any()
    )
    complete_frame = complete_frame[
        complete_frame["pair"].isin(complete_pair_scope[complete_pair_scope].index)
    ].copy()
    complete_frame["area_missing"] = 0
    complete_frame["log_area_filled"] = np.log(complete_frame["area_cm2"])
    complete, complete_channels = _within_model(complete_frame, include_characteristics=True)
    pooled_complete, pooled_complete_channels = _within_model(
        complete_frame, include_characteristics=True, pooled_spanish=True
    )

    houses = sorted(set(basic_channels) | set(adjusted_channels) | set(trimmed_channels))
    rows = []
    for house in houses:
        house_data = frame[frame["channel"].eq(house)]
        row = {
            "house": house,
            "observations": int(len(house_data)),
            "artist_technique_pairs": int(house_data["pair"].nunique()),
        }
        for label, model, available in (
            ("basic", basic, basic_channels),
            ("adjusted", adjusted, adjusted_channels),
            ("trimmed", trimmed, trimmed_channels),
            ("complete_dimensions", complete, complete_channels),
        ):
            if house in available:
                for key, value in effect_row(model, house).items():
                    row[f"{label}_{key}"] = value
        rows.append(row)
    effects = pd.DataFrame(rows)
    pooled_effect = effect_row(pooled, pooled_channels[0])
    diagnostics = {
        "observations": int(len(frame)),
        "artist_technique_pairs": int(frame["pair"].nunique()),
        "artists": int(frame["artist_key"].nunique()),
        "clusters": int(frame["pair"].nunique()),
        "period": [OVERLAP_START.date().isoformat(), OVERLAP_END.date().isoformat()],
        "catawiki_observations": int(frame["channel"].eq(REFERENCE_CHANNEL).sum()),
        "spanish_observations": int(frame["channel"].ne(REFERENCE_CHANNEL).sum()),
        "pooled_spanish_vs_catawiki": pooled_effect,
        "pooled_complete_dimensions_vs_catawiki": effect_row(
            pooled_complete, pooled_complete_channels[0]
        ),
        "complete_dimensions_observations": int(len(complete_frame)),
        "complete_dimensions_pairs": int(complete_frame["pair"].nunique()),
        "dimension_observed_percent_by_channel": {
            str(channel): float(100 * group["area_cm2"].notna().mean())
            for channel, group in frame.groupby("channel", observed=True)
        },
        "price_trim_limits_2025_eur": [float(lower), float(upper)],
        "trimmed_observations": int(len(trimmed_frame)),
        "trimmed_pairs": int(trimmed_frame["pair"].nunique()),
    }
    return effects, diagnostics


def greedy_title_matches(frame: pd.DataFrame, threshold: float = 1.0) -> pd.DataFrame:
    spanish = frame[frame["channel"].ne(REFERENCE_CHANNEL) & frame["title_key"].ne("")]
    catawiki = frame[frame["channel"].eq(REFERENCE_CHANNEL) & frame["title_key"].ne("")]
    cata_by_pair = {key: group for key, group in catawiki.groupby("pair", observed=True)}
    candidates = []
    for spanish_index, row in spanish.iterrows():
        possible = cata_by_pair.get(row["pair"])
        if possible is None:
            continue
        possible = possible[(possible["year"] - row["year"]).abs().le(2)]
        for cata_index, candidate in possible.iterrows():
            similarity = title_similarity(row["title_key"], candidate["title_key"])
            if similarity < threshold:
                continue
            candidates.append(
                {
                    "spanish_index": spanish_index,
                    "catawiki_index": cata_index,
                    "score": similarity,
                    "year_gap": abs(int(row["year"]) - int(candidate["year"])),
                }
            )
    candidates.sort(key=lambda item: (-item["score"], item["year_gap"]))
    used_spanish, used_catawiki, selected = set(), set(), []
    for candidate in candidates:
        if candidate["spanish_index"] in used_spanish or candidate["catawiki_index"] in used_catawiki:
            continue
        used_spanish.add(candidate["spanish_index"])
        used_catawiki.add(candidate["catawiki_index"])
        selected.append(candidate)
    rows = []
    for match in selected:
        left = frame.loc[match["spanish_index"]]
        right = frame.loc[match["catawiki_index"]]
        rows.append(
            {
                "house": left["channel"],
                "artist": left["artist_display"],
                "technique": left["technique"],
                "spanish_title": left["work_title"],
                "catawiki_title": right["work_title"],
                "title_similarity": match["score"],
                "spanish_year": int(left["year"]),
                "catawiki_year": int(right["year"]),
                "spanish_price_2025_eur": float(left["real_price_2025"]),
                "catawiki_price_2025_eur": float(right["real_price_2025"]),
                "log_price_ratio": float(left["log_price"] - right["log_price"]),
                "work_id": f"{left['artist_key']} | {left['title_key']} | {left['technique']}",
                "spanish_area_cm2": left["area_cm2"],
                "catawiki_area_cm2": right["area_cm2"],
                "spanish_record_id": left["record_source_id"],
                "catawiki_record_id": right["record_source_id"],
            }
        )
    return pd.DataFrame(rows)


def summarise_title_matches(matches: pd.DataFrame) -> pd.DataFrame:
    rows = []
    if matches.empty:
        return pd.DataFrame()
    for house, group in matches.groupby("house", observed=True):
        values = group["log_price_ratio"].to_numpy(float)
        mean = float(values.mean())
        standard_error = float(values.std(ddof=1) / math.sqrt(len(values))) if len(values) > 1 else math.nan
        low = mean - 1.959963984540054 * standard_error if math.isfinite(standard_error) else math.nan
        high = mean + 1.959963984540054 * standard_error if math.isfinite(standard_error) else math.nan
        rows.append(
            {
                "house": house,
                "matched_pairs": int(len(group)),
                "median_title_similarity": float(group["title_similarity"].median()),
                "median_spanish_price_2025_eur": float(group["spanish_price_2025_eur"].median()),
                "median_catawiki_price_2025_eur": float(group["catawiki_price_2025_eur"].median()),
                "mean_log_difference": mean,
                "standard_error_log_difference": standard_error,
                "p_value": (
                    float(math.erfc(abs(mean / standard_error) / math.sqrt(2)))
                    if math.isfinite(standard_error) and standard_error > 0
                    else math.nan
                ),
                "mean_percent_difference": 100 * math.expm1(mean),
                "ci95_low_percent": 100 * math.expm1(low) if math.isfinite(low) else math.nan,
                "ci95_high_percent": 100 * math.expm1(high) if math.isfinite(high) else math.nan,
            }
        )
    return pd.DataFrame(rows).sort_values("house").reset_index(drop=True)


def estimate_same_work_channel_effect(matches: pd.DataFrame) -> dict:
    """Estimate the channel effect within exact works and a strict dimension caliper."""
    if matches.empty:
        return {}
    broad_model = sm.OLS(
        matches["log_price_ratio"].astype(float).to_numpy(),
        np.ones((len(matches), 1)),
    ).fit(
        cov_type="cluster",
        cov_kwds={"groups": matches["work_id"], "use_correction": True},
    )
    broad_coefficient = float(broad_model.params[0])
    broad_low, broad_high = np.asarray(broad_model.conf_int())[0]
    strict = matches[
        matches["spanish_area_cm2"].notna()
        & matches["catawiki_area_cm2"].notna()
        & np.log(matches["spanish_area_cm2"] / matches["catawiki_area_cm2"])
        .abs()
        .le(math.log(1.10))
    ].copy()
    if strict.empty:
        return {}
    model = sm.OLS(
        strict["log_price_ratio"].astype(float).to_numpy(),
        np.ones((len(strict), 1)),
    ).fit(
        cov_type="cluster",
        cov_kwds={"groups": strict["work_id"], "use_correction": True},
    )
    coefficient = float(model.params[0])
    low, high = np.asarray(model.conf_int())[0]
    return {
        "broad_matched_pairs": int(len(matches)),
        "broad_works": int(matches["work_id"].nunique()),
        "broad_percent_effect": float(100 * math.expm1(broad_coefficient)),
        "broad_ci95_low_percent": float(100 * math.expm1(broad_low)),
        "broad_ci95_high_percent": float(100 * math.expm1(broad_high)),
        "broad_p_value": float(broad_model.pvalues[0]),
        "matched_pairs": int(len(strict)),
        "works": int(strict["work_id"].nunique()),
        "log_effect": coefficient,
        "standard_error": float(model.bse[0]),
        "percent_effect": float(100 * math.expm1(coefficient)),
        "ci95_low_percent": float(100 * math.expm1(low)),
        "ci95_high_percent": float(100 * math.expm1(high)),
        "p_value": float(model.pvalues[0]),
    }


def _standardised_difference(left: pd.Series, right: pd.Series) -> float:
    paired = pd.concat([left.rename("left"), right.rename("right")], axis=1).dropna()
    if paired.empty:
        return math.nan
    pooled_variance = (paired["left"].var(ddof=1) + paired["right"].var(ddof=1)) / 2
    if not math.isfinite(pooled_variance) or pooled_variance <= 0:
        return 0.0 if paired["left"].mean() == paired["right"].mean() else math.nan
    return float((paired["left"].mean() - paired["right"].mean()) / math.sqrt(pooled_variance))


def characteristic_matches(frame: pd.DataFrame) -> pd.DataFrame:
    """One-to-one nearest matches within artist-technique and explicit calipers.

    Catawiki lots can be reused across different house comparisons, but not twice
    within a given house. Missing catalogue statements are treated as 'not
    documented', not as proof that a characteristic is absent.
    """
    catawiki = frame[
        frame["channel"].eq(REFERENCE_CHANNEL) & frame["area_cm2"].notna()
    ]
    cata_by_pair = {key: group for key, group in catawiki.groupby("pair", observed=True)}
    selected_rows = []
    for house in sorted(set(frame["channel"]) - {REFERENCE_CHANNEL}):
        spanish = frame[
            frame["channel"].eq(house) & frame["area_cm2"].notna()
        ]
        candidates = []
        for spanish_index, row in spanish.iterrows():
            possible = cata_by_pair.get(row["pair"])
            if possible is None:
                continue
            year_gap = (possible["year"] - row["year"]).abs()
            area_gap = np.log(possible["area_cm2"] / row["area_cm2"]).abs()
            possible = possible[
                year_gap.eq(0) & area_gap.le(math.log(1.40))
            ]
            possible = possible[
                possible["signed_documented"].eq(row["signed_documented"])
                & possible["edition_documented"].eq(row["edition_documented"])
            ]
            for catawiki_index, candidate in possible.iterrows():
                creation_gap = math.nan
                if (
                    math.isfinite(float(row["creation_year_comparable"]))
                    and math.isfinite(float(candidate["creation_year_comparable"]))
                ):
                    creation_gap = abs(
                        float(row["creation_year_comparable"])
                        - float(candidate["creation_year_comparable"])
                    )
                    if creation_gap > 10:
                        continue
                # Area and sale date dominate; catalogue characteristics refine ties.
                distance = (
                    abs(math.log(float(candidate["area_cm2"]) / float(row["area_cm2"])))
                    / math.log(1.40)
                    + abs(int(candidate["year"]) - int(row["year"])) / 2
                    + (creation_gap / 10 if math.isfinite(creation_gap) else 0.25)
                )
                candidates.append((distance, spanish_index, catawiki_index))
        candidates.sort(key=lambda item: item[0])
        used_spanish, used_catawiki = set(), set()
        for distance, spanish_index, catawiki_index in candidates:
            if spanish_index in used_spanish or catawiki_index in used_catawiki:
                continue
            used_spanish.add(spanish_index)
            used_catawiki.add(catawiki_index)
            left, right = frame.loc[spanish_index], frame.loc[catawiki_index]
            selected_rows.append(
                {
                    "house": house,
                    "pair": left["pair"],
                    "artist": left["artist_display"],
                    "technique": left["technique"],
                    "spanish_title": left["work_title"],
                    "catawiki_title": right["work_title"],
                    "distance": distance,
                    "spanish_year": int(left["year"]),
                    "catawiki_year": int(right["year"]),
                    "spanish_area_cm2": float(left["area_cm2"]),
                    "catawiki_area_cm2": float(right["area_cm2"]),
                    "spanish_creation_year": left["creation_year_comparable"],
                    "catawiki_creation_year": right["creation_year_comparable"],
                    "spanish_signed_documented": int(left["signed_documented"]),
                    "catawiki_signed_documented": int(right["signed_documented"]),
                    "spanish_edition_documented": int(left["edition_documented"]),
                    "catawiki_edition_documented": int(right["edition_documented"]),
                    "spanish_price_2025_eur": float(left["real_price_2025"]),
                    "catawiki_price_2025_eur": float(right["real_price_2025"]),
                    "log_price_ratio": float(left["log_price"] - right["log_price"]),
                    "spanish_record_id": left["record_source_id"],
                    "catawiki_record_id": right["record_source_id"],
                }
            )
    return pd.DataFrame(selected_rows)


def summarise_characteristic_matches(matches: pd.DataFrame) -> pd.DataFrame:
    rows = []
    if matches.empty:
        return pd.DataFrame()
    for house, group in matches.groupby("house", observed=True):
        values = group["log_price_ratio"].astype(float)
        # Clustered inference recognises that several matched lots can share an artist-technique cell.
        model = sm.OLS(values.to_numpy(), np.ones((len(values), 1))).fit(
            cov_type="cluster",
            cov_kwds={"groups": group["pair"], "use_correction": True},
        )
        mean = float(model.params[0])
        standard_error = float(model.bse[0])
        low, high = mean - 1.959963984540054 * standard_error, mean + 1.959963984540054 * standard_error
        balance = [
            _standardised_difference(np.log(group["spanish_area_cm2"]), np.log(group["catawiki_area_cm2"])),
            _standardised_difference(group["spanish_year"], group["catawiki_year"]),
            _standardised_difference(group["spanish_creation_year"], group["catawiki_creation_year"]),
            _standardised_difference(group["spanish_signed_documented"], group["catawiki_signed_documented"]),
            _standardised_difference(group["spanish_edition_documented"], group["catawiki_edition_documented"]),
        ]
        finite_balance = [abs(value) for value in balance if math.isfinite(value)]
        rows.append(
            {
                "house": house,
                "matched_pairs": int(len(group)),
                "artist_technique_cells": int(group["pair"].nunique()),
                "mean_log_difference": mean,
                "standard_error_log_difference": standard_error,
                "p_value": float(model.pvalues[0]),
                "mean_percent_difference": 100 * math.expm1(mean),
                "ci95_low_percent": 100 * math.expm1(low),
                "ci95_high_percent": 100 * math.expm1(high),
                "max_absolute_smd": max(finite_balance) if finite_balance else math.nan,
            }
        )
    return pd.DataFrame(rows).sort_values("house").reset_index(drop=True)
