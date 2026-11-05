# Protocolo de reclasificación de técnica y aplicabilidad

## Objetivo

Reducir de forma auditable los registros clasificados originalmente como
`Otra/no especificada`, sin sustituir ni borrar la categoría publicada por la casa de
subastas. El resultado se escribe en un archivo derivado y añade las columnas:

- `research_classification`: nuestra clasificación normalizada;
- `research_is_graphic_art`: `1`, `0` o vacío cuando sigue indeterminado;
- `research_classification_method`: regla de catálogo, regla nueva, decisión curada o sin resolver;
- `research_classification_confidence`: alta, media o baja;
- `research_classification_evidence`: expresión textual que fundamenta la decisión;
- `research_protocol_version`: versión del protocolo de decisión.
- `research_classification_fingerprint`: huella del título y la descripción usada para
  reutilizar una misma decisión en reofertas textualmente idénticas.

## Orden de decisión

1. Se conserva la familia técnica existente cuando el catálogo nombra una técnica
   reconocible.
2. En los casos `Otra/no especificada` se aplican reglas conservadoras al título y la
   descripción. Se distinguen técnicas gráficas, fotografía, equipo fotográfico,
   reproducciones, carteles, dibujo, pintura, técnica mixta, libros y objetos.
3. Los textos todavía ambiguos se revisan individualmente y se registran en
   `manual_classification_overrides.csv`. Una decisión puede conservar
   `Otra/no especificada` cuando no existe evidencia suficiente.
4. Después de esa revisión, todo caso sin evidencia suficiente permanece
   `Otra/no especificada`. Nunca se obliga una clasificación.

## Reglas de integridad

- El dataset de entrada no se modifica; se crea `spanish_prints_classified.csv`.
- Fotografía, aparatos, dibujos, pinturas, reproducciones y objetos no se convierten en
  obra gráfica por aparecer bajo una categoría comercial llamada `OBRA GRÁFICA`.
- Una última puja o estimación no interviene en la clasificación técnica.
- Los textos idénticos reutilizan una misma decisión mediante su huella textual.
- Las decisiones curadas se aplican por huella textual y conservan título,
  descripción, revisor y fecha de revisión para poder auditarlas una por una.
- Versión del protocolo, método, confianza y evidencia quedan en cada fila.
- La distribución final y los casos no resueltos se publican en
  `spanish_prints_classification_report.json`.

## Ejecución

```bash
.venv/bin/python scripts/build_manual_classification_overrides.py
.venv/bin/auction-data classify-paper
```
