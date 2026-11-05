from __future__ import annotations

import csv
import hashlib
import json
import re
import unicodedata
from enum import Enum
from pathlib import Path


PROTOCOL_VERSION = "graphic-art-classification-v1"
OTHER = "Otra/no especificada"
CLASSIFICATION_FIELDS = [
    "research_classification",
    "research_is_graphic_art",
    "research_classification_method",
    "research_classification_confidence",
    "research_classification_evidence",
    "research_protocol_version",
    "research_classification_fingerprint",
]


class ResearchClass(str, Enum):
    CALCOGRAPHY = "Calcografía"
    LITHOGRAPHY = "Litografía"
    SCREENPRINT = "Serigrafía"
    RELIEF = "Grabado en relieve"
    MONOTYPE = "Monotipo"
    PHOTOMECHANICAL = "Fotomecánica"
    DIGITAL = "Digital (giclée/inkjet)"
    EMBOSSING = "Gofrado/relieve sin tinta"
    STENCIL = "Estarcido/pochoir"
    COLLAGRAPH = "Collagraph/colografía"
    MIXOGRAPHY = "Mixografía/estampación mixta"
    UNSPECIFIED_PRINT = "Grabado/estampa sin técnica especificada"
    POSTER = "Cartel/impresión comercial"
    REPRODUCTION = "Reproducción/facsímil"
    PHOTOGRAPHY = "Fotografía"
    PHOTO_EQUIPMENT = "Equipo/material fotográfico"
    DRAWING = "Dibujo/obra única sobre papel"
    PAINTING = "Pintura/obra única"
    MIXED = "Collage/técnica mixta"
    BOOK = "Libro/carpeta/documentación"
    OBJECT = "Objeto/otro no gráfico"
    OTHER = OTHER


class Confidence(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


GRAPHIC_CLASSES = {
    ResearchClass.CALCOGRAPHY.value,
    ResearchClass.LITHOGRAPHY.value,
    ResearchClass.SCREENPRINT.value,
    ResearchClass.RELIEF.value,
    ResearchClass.MONOTYPE.value,
    ResearchClass.PHOTOMECHANICAL.value,
    ResearchClass.DIGITAL.value,
    ResearchClass.EMBOSSING.value,
    ResearchClass.STENCIL.value,
    ResearchClass.COLLAGRAPH.value,
    ResearchClass.MIXOGRAPHY.value,
    ResearchClass.UNSPECIFIED_PRINT.value,
}


def normalized_text(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value or "").casefold())
    return "".join(character for character in text if not unicodedata.combining(character))


def classification_fingerprint(row: dict[str, str]) -> str:
    text = normalized_text("\n".join((row.get("title", ""), row.get("description", ""))))
    text = re.sub(r"\s+", " ", text).strip()
    return hashlib.sha256(text.encode()).hexdigest()


def _match(text: str, pattern: str) -> str:
    found = re.search(pattern, text)
    return found.group(0) if found else ""


def _result(label: str, method: str, confidence: str, evidence: str) -> dict[str, str]:
    applicable = "1" if label in GRAPHIC_CLASSES else "0" if label != OTHER else ""
    return {
        "research_classification": label,
        "research_is_graphic_art": applicable,
        "research_classification_method": method,
        "research_classification_confidence": confidence,
        "research_classification_evidence": evidence[:240],
        "research_protocol_version": PROTOCOL_VERSION,
        "research_classification_fingerprint": "",
    }


def classify_by_rules(row: dict[str, str]) -> dict[str, str]:
    existing = str(row.get("technique_family") or "")
    if existing and existing != OTHER:
        return _result(existing, "catalogue_rule_existing", "high", str(row.get("classification_terms") or existing))

    text = normalized_text(" ".join((row.get("title", ""), row.get("description", ""))))
    rules = [
        (ResearchClass.PHOTO_EQUIPMENT.value, r"\b(?:camaras?|cinecamaras?|proyector(?:es)?|objetivo fotografico|visor(?:es)? de (?:diapositivas|postales)|linterna magica|material fotografico|ampliadora fotografica)\b", "high"),
        (ResearchClass.PHOTO_EQUIPMENT.value, r"\bpostales estereoscopicas\b", "medium"),
        (ResearchClass.PHOTO_EQUIPMENT.value, r"\b(?:broches?|colgantes?|placas?)\b[^.]{0,100}\b(?:imagenes?|retratos?) fotografic[oa]s?\b", "high"),
        (ResearchClass.PHOTOGRAPHY.value, r"\b(?:fotograf(?:ia|ias|ico|ica|icos|icas)|fogorafia|fotoacuarela|copia analogica|revelado de epoca|daguerrotipos?|ferrotipos?|ambrotipos?|gelatina(?: de)? plata|gelatino[ -]?bromuro|c-?prints?|cibachrome|impresion cromogenica|platinotipia|albumina|cianotipia)\b", "high"),
        (ResearchClass.DIGITAL.value, r"\b(?:impresion(?:es)? laser|impresion(?:es)? digital(?:es)?|tintas? pigmentadas?|pigment prints?|glicee|giclee|digigraphie|digigrafia)\b", "high"),
        (ResearchClass.PHOTOMECHANICAL.value, r"\b(?:huecograbados?|rotograbados?|heliograbados?|heliografias?|photogravures?|fotograbados?|impresion(?:es)? ofset|offset)\b", "high"),
        (ResearchClass.STENCIL.value, r"\b(?:pochoirs?|estarcido)\b", "high"),
        (ResearchClass.COLLAGRAPH.value, r"\b(?:collagraphs?|collagrafias?|colografias?)\b", "high"),
        (ResearchClass.MIXOGRAPHY.value, r"\b(?:mixografias?|mixographias?)\b", "high"),
        (ResearchClass.SCREENPRINT.value, r"\b(?:serigrafias?|serigrafi?a|seriagrafias?|serigrfias?|serigraifas?|serigraias?|serigafrias?|serigafias?|seirigrafias?|seirgrafias?|serirafias?|serografias?|seritrafias?|serigradias?|serifrafias?|sriegrafias?|srigrafias?|setigrafias?|rerigrafias?|seriagrias?|sergrafias?|silkscreens?|screenprints?)\b", "high"),
        (ResearchClass.LITHOGRAPHY.value, r"\b(?:litografias?|litograifias?|litograafias?|litograifas?|litorgrafias?|litogragias?|litgrafias?|litorafias?|litofrafias?|litgorafias?|lithograph(?:e|es|s)?|alugrafrias?|alugrafias?|cincografias?|zincografias?)\b", "high"),
        (ResearchClass.RELIEF.value, r"\b(?:xilografias?|xilogarias?|woodcuts?|linoleos?|linoleum|linoleums?|linografias?|linograbados?|linocuts?)\b", "high"),
        (ResearchClass.MONOTYPE.value, r"\b(?:monotipos?|monotypes?)\b", "high"),
        (ResearchClass.CALCOGRAPHY.value, r"\b(?:aguafuertes?|aguafuerttes?|aguafertes?|aguarfiertes?|aguarfuer?tes?|aguaguerfes?|agufuer(?:te|tes)|aguafueres?|guafuertes?|afguafuertes?|agafuertes?|afuafuertes?|agusfuertes?|acuafuertes?|afuaguertes?|aguatintas?|aguatinas?|aguatitntas?|puntas? secas?|puntasecas?|mezzotintas?|maneras? negras?|buriles?|carborundos?|etchings?|drypoints?|aquatints?)\b", "high"),
        (ResearchClass.DRAWING.value, r"\b(?:dibujo|carboncillo|lapiz sobre|tinta sobre papel|acuarela|gouache|pastel sobre)\b", "high"),
        (ResearchClass.PAINTING.value, r"\b(?:oleo sobre|acrilico sobre|temple sobre)\b", "high"),
        (ResearchClass.MIXED.value, r"\b(?:collage|tecnica mixta|mixed media)\b", "medium"),
        (ResearchClass.OBJECT.value, r"\b(?:bronce|multiples?(?:\b| (?:de|realizad|compuest))|escultura|objeto tridimensional|anillos? de plata|alfombra|tapiz|ceramica|porcelana|loza|camiseta|placas? de piedra|bajorrelieve en plata|movil de mesa|metacrilatos?|resina y pintura|fibra de vidrio)\b", "high"),
        (ResearchClass.BOOK.value, r"\b(?:libro|catalogo de exposicion|documentacion|archivo documental|barajas?|juego de naipes|tarot|postales?|tarjetas?|cromos?|periodico|invitaciones?|felicitaciones?)\b", "medium"),
        (ResearchClass.REPRODUCTION.value, r"\b(?:reproduccion(?:es)?|facsimiles?|laminas?|copia impresa|oleografias?)\b", "high"),
        (ResearchClass.REPRODUCTION.value, r"\bsegun\b[^.]{0,180}\bimpresion(?:es)?\b|\bimpresion(?:es)?\b[^.]{0,180}\b(?:segun (?:el |un )?original|copyright|estate of|foundation for the visual arts)\b", "high"),
        (ResearchClass.REPRODUCTION.value, r"\bsegun\b[\s\S]{0,300}\bimpresion(?:es)?\b|\bimpresion(?:es)?\b[\s\S]{0,220}\b(?:segun (?:el |un )?original|copyright|estate of|foundation for the visual arts|succession)\b", "high"),
        (ResearchClass.POSTER.value, r"\b(?:cartel(?:es)?|posters?|affiches?)\b", "high"),
        (ResearchClass.EMBOSSING.value, r"\b(?:gofrados?|relieve en seco|embossing)\b", "high"),
        (ResearchClass.CALCOGRAPHY.value, r"\bhuella\b", "medium"),
        (ResearchClass.CALCOGRAPHY.value, r"\b(?:grabado|estampa|plancha)\b[^.]{0,80}\b(?:cobre|matriz metalica|huella)\b|\b(?:cobre|matriz metalica|huella)\b[^.]{0,80}\b(?:grabado|estampa|plancha)\b", "medium"),
        (ResearchClass.UNSPECIFIED_PRINT.value, r"\b(?:grabado|grabados|estampa|estampas|estampacion)\b", "medium"),
        (ResearchClass.UNSPECIFIED_PRINT.value, r"\bimpresion(?:es)?\b[^.]{0,100}\b(?:ejemplar|tirada|edicion|numerad[oa]|prueba de artista|firmad[oa])\b|\b(?:ejemplar|tirada|edicion|numerad[oa]|prueba de artista|firmad[oa])\b[^.]{0,100}\bimpresion(?:es)?\b", "medium"),
        (ResearchClass.UNSPECIFIED_PRINT.value, r"\bobra grafica\b[^.]{0,120}\b(?:ejemplar|tirada|edicion|numerad[oa])\b|\b(?:ejemplar|tirada|edicion|numerad[oa])\b[^.]{0,120}\bobra grafica\b", "medium"),
        (ResearchClass.UNSPECIFIED_PRINT.value, r"\bobra grafica\b", "medium"),
        (ResearchClass.UNSPECIFIED_PRINT.value, r"\b(?:prueba de artista|epreuve d[' ]artiste|prova d[' ]artista|firmad[oa] en plancha|sculp\.?|excudit)\b", "medium"),
        (ResearchClass.UNSPECIFIED_PRINT.value, r"\bfirmad[oa]\b[\s\S]{0,260}\bnumerad[oa]\b|\bnumerad[oa]\b[\s\S]{0,260}\bfirmad[oa]\b", "medium"),
        (ResearchClass.UNSPECIFIED_PRINT.value, r"\bplancha\b[^.]{0,100}\b(?:edicion|impres[oa]|tirada)\b|\b(?:edicion|impres[oa]|tirada)\b[^.]{0,100}\bplancha\b", "medium"),
        (ResearchClass.RELIEF.value, r"\bukiyo-e\b", "medium"),
        (ResearchClass.UNSPECIFIED_PRINT.value, r"\b(?:mapa|carta nautica|vista naval)\b[^.]{0,120}\b(?:publicad[oa]|huella|sculp)\b", "medium"),
        (ResearchClass.OBJECT.value, r"\b(?:escultura|objeto|joya|broche|colgante|ceramica|reloj|mueble)\b", "medium"),
    ]
    for label, pattern, confidence in rules:
        evidence = _match(text, pattern)
        if evidence:
            return _result(label, "deterministic_rule", confidence, evidence)
    return _result(OTHER, "unresolved_after_rules", "low", "No hay evidencia técnica suficiente en el texto")


def build_classified_dataset(
    project_root: Path,
) -> dict:
    source = project_root / "data" / "derived" / "spanish_prints_for_paper.csv"
    output = project_root / "data" / "derived" / "spanish_prints_classified.csv"
    temporary_output = output.with_suffix(".csv.tmp")
    report_path = project_root / "data" / "derived" / "spanish_prints_classification_report.json"
    queue_path = project_root / "data" / "derived" / "classification_review_queue.csv"
    manual_path = project_root / "data" / "derived" / "manual_classification_overrides.csv"
    manual: dict[str, dict[str, str]] = {}
    if manual_path.exists():
        valid_labels = {value.value for value in ResearchClass}
        with manual_path.open(newline="", encoding="utf-8") as handle:
            for override in csv.DictReader(handle):
                fingerprint = override.get("fingerprint", "")
                label = override.get("classification", "")
                if not fingerprint or label not in valid_labels:
                    raise ValueError(f"Invalid manual classification override: {override}")
                manual[fingerprint] = _result(
                    label,
                    "curated_rule_override",
                    override.get("confidence") or "medium",
                    override.get("evidence") or "Revisión individual del texto de catálogo",
                )
    counts: dict[str, int] = {}
    method_counts: dict[str, int] = {}
    applicability_counts: dict[str, int] = {}
    unresolved_queue: list[dict[str, str]] = []
    unresolved_fingerprints: set[str] = set()
    with source.open(newline="", encoding="utf-8") as handle, temporary_output.open(
        "w", newline="", encoding="utf-8"
    ) as destination:
        reader = csv.DictReader(handle)
        fields = list(reader.fieldnames or []) + CLASSIFICATION_FIELDS
        writer = csv.DictWriter(destination, fieldnames=fields)
        writer.writeheader()
        for row in reader:
            fingerprint = classification_fingerprint(row)
            classification = classify_by_rules(row)
            if classification["research_classification"] == OTHER and fingerprint in manual:
                classification = manual[fingerprint]
            classification["research_classification_fingerprint"] = fingerprint
            writer.writerow({**row, **classification})
            label = classification["research_classification"]
            method = classification["research_classification_method"]
            applicable = classification["research_is_graphic_art"] or "indeterminate"
            counts[label] = counts.get(label, 0) + 1
            method_counts[method] = method_counts.get(method, 0) + 1
            applicability_counts[applicable] = applicability_counts.get(applicable, 0) + 1
            if label == OTHER:
                unresolved_fingerprints.add(fingerprint)
                unresolved_queue.append(
                    {
                        "record_id": row["record_id"],
                        "fingerprint": fingerprint,
                        "auction_house": row.get("auction_house", ""),
                        "category": row.get("category", ""),
                        "title": row.get("title", ""),
                        "description": row.get("description", ""),
                    }
                )

    temporary_output.replace(output)

    with queue_path.open("w", newline="", encoding="utf-8") as queue:
        queue_fields = ["record_id", "fingerprint", "auction_house", "category", "title", "description"]
        writer = csv.DictWriter(queue, fieldnames=queue_fields)
        writer.writeheader()
        writer.writerows(unresolved_queue)

    report = {
        "source": str(source),
        "output": str(output),
        "rows": sum(counts.values()),
        "classification_protocol_version": PROTOCOL_VERSION,
        "classification_counts": counts,
        "method_counts": method_counts,
        "applicability_counts": applicability_counts,
        "newly_classified_rows": sum(counts.values())
        - method_counts.get("catalogue_rule_existing", 0)
        - counts.get(OTHER, 0),
        "manual_override_file": str(manual_path),
        "curated_override_rows": method_counts.get("curated_rule_override", 0),
        "curated_but_indeterminate_unique_texts": sum(
            1
            for fingerprint, classification in manual.items()
            if classification["research_classification"] == OTHER
        ),
        "curated_unique_texts": len(manual),
        "unresolved_rows": counts.get(OTHER, 0),
        "unresolved_unique_texts": len(unresolved_fingerprints),
        "review_queue": str(queue_path),
        "protocol": "docs/classification-protocol-es.md",
    }
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    return report
