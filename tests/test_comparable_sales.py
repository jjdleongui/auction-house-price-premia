import math

from auction_data.comparable_sales import (
    artist_key,
    catawiki_technique,
    edition_documented,
    extract_catawiki_artist,
    extract_creation_year,
    extract_spanish_artist,
    parse_area,
    signed_documented,
    title_key,
)


def test_artist_normalisation_matches_common_variants():
    assert artist_key("Pablo Ruiz Picasso") == "pablo picasso"
    assert artist_key("Pablo Picasso") == "pablo picasso"
    assert artist_key("Francisco de Goya y Lucientes") == "francisco goya"


def test_derivative_works_are_excluded():
    assert extract_spanish_artist("MARC CHAGALL. SEGÚN. Bouquet") == ""
    assert extract_catawiki_artist("Pablo Picasso (d'après)") == ""
    assert extract_catawiki_artist("Salvador Dali (1904-1989), after") == ""


def test_artist_extraction_keeps_primary_attributions():
    assert extract_spanish_artist("JOAN MIRÓ (Barcelona, 1893) Sculptures") == "JOAN MIRÓ"
    assert extract_catawiki_artist("Joan Miro (1893-1983)") == "Joan Miro"


def test_technique_mapping_uses_shared_families():
    assert catawiki_technique("Silkscreen / Serigraph") == "Serigrafía"
    assert catawiki_technique("Aquatint, Etching") == "Calcografía"
    assert catawiki_technique("Digital print, Giclée") == "Digital"


def test_dimensions_parse_multiplication_sign_and_decimals():
    assert math.isclose(parse_area("33×26.5×0 cm"), 874.5)
    assert math.isclose(parse_area("76 x 56 cm"), 4256.0)


def test_generic_titles_do_not_create_false_exact_matches():
    assert title_key("Litografía original I", "Joan Miró") == ""
    assert title_key("Maravillas con variaciones acrósticas", "Joan Miró")


def test_catalogue_characteristics_are_positive_documentation_only():
    assert signed_documented("Firmado y numerado") == 1
    assert signed_documented("Not signed") == 0
    assert edition_documented("75 copies") == 1
    assert edition_documented("") == 0


def test_creation_year_is_taken_from_work_title():
    assert extract_creation_year("Ritmes i Espais 2, 2005") == 2005
    assert math.isnan(extract_creation_year("Sin título"))
