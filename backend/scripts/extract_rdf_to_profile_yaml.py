"""Convert an IOF RDF/XML ontology artifact into a slim, LLM-context YAML profile.

Entities (OWL classes):
  label, iri, parent_classes, ancestors (complete hierarchy), definition,
  synonyms, abbreviations, examples, explanatory_notes,
  superclass_expressions (simple restrictions only, e.g. 'has part' some Process),
  classification_conditions (equivalent-class / sufficient conditions, full expressions),
  logical_definition, logical_axioms (copied from first-order-logic annotations)

Relationships (OWL properties):
  label, iri, definition, domain, range, inverse, extraction_constraints

A "simple" restriction is one restriction on a named, non-inverse property with
a named class filler (some / only / min / max / exactly), or a cardinality with
no filler. Anything more complex is NOT put in superclass_expressions; complex
equivalent-class definitions go to classification_conditions instead.
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Any

import yaml
from rdflib import BNode, Graph, Literal, RDF, RDFS, URIRef
from rdflib.collection import Collection
from rdflib.namespace import OWL

MAX_DEPTH = 12

DEFINITION_NAMES = ("definition", "naturalLanguageDefinition", "IAO_0000115")
# output field -> annotation local names / labels (normalised with slug())
CATEGORIES = (
    ("synonyms", {"synonym", "altlabel", "alternative_term", "alternative_label",
                  "hasexactsynonym", "has_exact_synonym", "exact_synonym", "iao_0000118"}),
    ("abbreviations", {"abbreviation", "acronym"}),
    ("examples", {"example", "example_of_usage", "iao_0000112"}),
    ("explanatory_notes", {"explanatorynote", "usagenote"}),
    ("logical_definition", {"firstorderlogicdefinition"}),
    ("logical_axioms", {"firstorderlogicaxiom"}),
)

SIMPLE_RESTRICTIONS = (
    (OWL.someValuesFrom, "some"),
    (OWL.allValuesFrom, "only"),
    (OWL.cardinality, "exactly"),
    (OWL.minCardinality, "min"),
    (OWL.maxCardinality, "max"),
    (OWL.qualifiedCardinality, "exactly"),
    (OWL.minQualifiedCardinality, "min"),
    (OWL.maxQualifiedCardinality, "max"),
)
CARDINALITY = {
    OWL.cardinality, OWL.minCardinality, OWL.maxCardinality,
    OWL.qualifiedCardinality, OWL.minQualifiedCardinality, OWL.maxQualifiedCardinality,
}

# BFO identifiers replaced by readable labels everywhere a label or text appears.
# NOTE: BFO_0000167 (used by IOF Maintenance) is deliberately absent: its label is
# not in the file and I could not confirm it. Add it here once you know it.
BFO_LABELS = {
    "BFO_0000054": "has realization",
    "BFO_0000057": "has participant",
    "BFO_0000063": "precedes",
    "BFO_0000117": "has occurrent part",
    "BFO_0000199": "occupies temporal region",
    "BFO_0000202": "temporal interval",
    "BFO_0000203": "temporal instant",
    "BFO_0000001": "entity",
    "BFO_0000002": "continuant",
    "BFO_0000003": "occurrent",
    "BFO_0000004": "independent continuant",
    "BFO_0000006": "spatial region",
    "BFO_0000008": "temporal region",
    "BFO_0000009": "two-dimensional spatial region",
    "BFO_0000011": "spatiotemporal region",
    "BFO_0000015": "process",
    "BFO_0000016": "disposition",
    "BFO_0000017": "realizable entity",
    "BFO_0000018": "zero-dimensional spatial region",
    "BFO_0000019": "quality",
    "BFO_0000020": "specifically dependent continuant",
    "BFO_0000023": "role",
    "BFO_0000024": "fiat object part",
    "BFO_0000026": "one-dimensional spatial region",
    "BFO_0000027": "object aggregate",
    "BFO_0000028": "three-dimensional spatial region",
    "BFO_0000029": "site",
    "BFO_0000030": "object",
    "BFO_0000031": "generically dependent continuant",
    "BFO_0000034": "function",
    "BFO_0000035": "process boundary",
    "BFO_0000038": "one-dimensional temporal region",
    "BFO_0000040": "material entity",
    "BFO_0000140": "continuant fiat boundary",
    "BFO_0000141": "immaterial entity",
    "BFO_0000142": "one-dimensional continuant fiat boundary",
    "BFO_0000144": "process profile",
    "BFO_0000145": "relational quality",
    "BFO_0000146": "two-dimensional continuant fiat boundary",
    "BFO_0000147": "zero-dimensional continuant fiat boundary",
    "BFO_0000148": "zero-dimensional temporal region",
    "BFO_0000182": "history",
    "BFO_0000050": "part of",
    "BFO_0000051": "has part",
    "BFO_0000052": "inheres in",
    "BFO_0000053": "bearer of",
    "BFO_0000055": "realizes",
    "BFO_0000056": "participates in",
    "BFO_0000062": "preceded by",
    "BFO_0000066": "occurs in",
    "BFO_0000067": "contains process",
    "BFO_0000108": "exists at",
    "BFO_0000121": "has temporal part",
    "BFO_0000124": "location of",
    "BFO_0000139": "temporal part of",
    "BFO_0000171": "located in",
    "BFO_0000110": "has member",
    "BFO_0000177": "part of continuant",
    "BFO_0000174": "continuant part",
}
BFO_PATTERN = re.compile(r"\bBFO_\d{7}\b")


def replace_bfo(text: str) -> str:
    return BFO_PATTERN.sub(lambda m: BFO_LABELS.get(m.group(0), m.group(0)), text)


def local_name(iri: URIRef) -> str:
    return str(iri).rsplit("#", 1)[-1].rsplit("/", 1)[-1]


def slug(text: str) -> str:
    return re.sub(r"[^0-9a-zA-Z]+", "_", text).strip("_").lower()


def manchester(e: dict, nested: bool = False) -> str:
    """Render a structured expression as a Manchester-style string."""
    if not e:
        return "<complex>"
    if "label" in e and "on_property" not in e and not any(
        k in e for k in ("intersection_of", "union_of", "one_of", "complement_of")
    ):
        name = e["label"]
        return f"'{name}'" if re.search(r"\s", name) else name
    if "intersection_of" in e or "union_of" in e:
        key, sep = ("intersection_of", " and ") if "intersection_of" in e else ("union_of", " or ")
        text = sep.join(manchester(x, True) for x in e[key])
        return f"({text})" if nested else text
    if "one_of" in e:
        return "{" + ", ".join(manchester(x, True) for x in e["one_of"]) + "}"
    if "complement_of" in e:
        return f"not {manchester(e['complement_of'], True)}"
    if "on_property" in e:
        parts = [manchester(e["on_property"], True), e["quantifier"]]
        if "cardinality" in e:
            parts.append(str(e["cardinality"]))
        if e.get("filler") is not None:
            parts.append(manchester(e["filler"], True))
        text = " ".join(parts)
        return f"({text})" if nested else text
    return "<complex>"


class Extractor:
    def __init__(self, graph: Graph, langs: list[str], include_iri: bool) -> None:
        self.g = graph
        self.langs = langs
        self.include_iri = include_iri

    # -- text ---------------------------------------------------------------- #
    def lang_rank(self, lit: Literal) -> int | None:
        lang = (lit.language or "").lower()
        if not lang:
            return len(self.langs)
        for i, want in enumerate(self.langs):
            if lang == want or lang.startswith(want + "-"):
                return i
        return None

    def best(self, literals: list[Literal]) -> str:
        ranked = [
            (rank, str(l).strip())
            for l in literals
            if str(l).strip() and (rank := self.lang_rank(l)) is not None
        ]
        if not ranked:
            ranked = [(0, str(l).strip()) for l in literals if str(l).strip()]
        return min(ranked)[1] if ranked else ""

    def texts(self, subject, predicate) -> list[Literal]:
        return [o for o in self.g.objects(subject, predicate) if isinstance(o, Literal)]

    def label(self, iri: URIRef) -> str:
        name = local_name(iri)
        if name in BFO_LABELS:
            return BFO_LABELS[name]
        return self.best(self.texts(iri, RDFS.label)) or name

    def definition(self, subject) -> str:
        for name in DEFINITION_NAMES:
            lits = [
                o for p, o in self.g.predicate_objects(subject)
                if isinstance(p, URIRef) and isinstance(o, Literal) and local_name(p) == name
            ]
            text = self.best(lits)
            if text:
                return replace_bfo(text)
        return replace_bfo(self.best(self.texts(subject, RDFS.comment)))

    def categorized(self, subject) -> dict[str, list[str]]:
        found: dict[str, set[str]] = {name: set() for name, _ in CATEGORIES}
        for p, o in self.g.predicate_objects(subject):
            if not (isinstance(p, URIRef) and isinstance(o, Literal)):
                continue
            if self.lang_rank(o) is None or not str(o).strip():
                continue
            names = {slug(local_name(p))} | {slug(str(l)) for l in self.texts(p, RDFS.label)}
            for field, keys in CATEGORIES:
                if names & keys:
                    found[field].add(replace_bfo(str(o).strip()))
        return {field: sorted(vals) for field, vals in found.items() if vals}

    # -- expressions --------------------------------------------------------- #
    def named(self, iri: URIRef) -> dict:
        return {"label": self.label(iri), "iri": str(iri)}

    def items(self, head) -> list:
        try:
            return list(Collection(self.g, head))
        except Exception:
            return []

    def prop_expr(self, node) -> dict:
        """A property: named, or an inverse expression."""
        if isinstance(node, URIRef):
            return self.named(node)
        inv = self.g.value(node, OWL.inverseOf)
        if isinstance(inv, URIRef):
            return {"label": f"inverse({self.label(inv)})", "iri": str(inv)}
        return {}

    def expr(self, node, depth: int = 0) -> dict:
        """Full class expression: named, boolean, enumeration or restriction."""
        if isinstance(node, URIRef):
            return self.named(node)
        if depth > MAX_DEPTH:
            return {}
        d = depth + 1
        for predicate, key in ((OWL.intersectionOf, "intersection_of"),
                               (OWL.unionOf, "union_of"), (OWL.oneOf, "one_of")):
            head = self.g.value(node, predicate)
            if head is not None:
                return {key: [self.expr(i, d) for i in self.items(head)]}
        comp = self.g.value(node, OWL.complementOf)
        if comp is not None:
            return {"complement_of": self.expr(comp, d)}
        if (node, RDF.type, OWL.Restriction) in self.g or self.g.value(node, OWL.onProperty) is not None:
            return self.restriction(node, d)
        return {}

    def restriction(self, node, depth: int) -> dict:
        g = self.g
        prop = self.prop_expr(g.value(node, OWL.onProperty))
        if not prop:
            return {}
        for predicate, quantifier in SIMPLE_RESTRICTIONS:
            value = g.value(node, predicate)
            if value is None:
                continue
            out: dict[str, Any] = {"on_property": prop, "quantifier": quantifier}
            if predicate in CARDINALITY:
                out["cardinality"] = int(value)
                filler = g.value(node, OWL.onClass) or g.value(node, OWL.onDataRange)
                out["filler"] = self.expr(filler, depth) if filler is not None else None
            else:
                out["filler"] = self.expr(value, depth)
            return out
        value = g.value(node, OWL.hasValue)
        if value is not None:
            filler = self.named(value) if isinstance(value, URIRef) else {"label": str(value)}
            return {"on_property": prop, "quantifier": "value", "filler": filler}
        if (node, OWL.hasSelf, None) in g:
            return {"on_property": prop, "quantifier": "Self", "filler": None}
        return {}

    def simple_restriction(self, node) -> str | None:
        """Manchester string for a simple restriction, or None if not simple."""
        g = self.g
        prop = g.value(node, OWL.onProperty)
        if not isinstance(prop, URIRef):
            return None
        for predicate, quantifier in SIMPLE_RESTRICTIONS:
            value = g.value(node, predicate)
            if value is None:
                continue
            out: dict[str, Any] = {"on_property": self.named(prop), "quantifier": quantifier}
            if predicate in CARDINALITY:
                out["cardinality"] = int(value)
                filler = g.value(node, OWL.onClass) or g.value(node, OWL.onDataRange)
                if filler is not None and not isinstance(filler, URIRef):
                    return None
                out["filler"] = self.named(filler) if filler is not None else None
            else:
                if not isinstance(value, URIRef):
                    return None
                out["filler"] = self.named(value)
            return manchester(out)
        return None

    def render(self, node) -> str:
        e = self.expr(node)
        return manchester(e) if e else ""

    # -- hierarchy ----------------------------------------------------------- #
    def ancestors(self, iri: URIRef) -> list[str]:
        """All named superclasses, nearest first (breadth-first), as labels.

        Stops at classes whose own parents are not in the loaded graph (e.g. imported
        ontologies that were not parsed)."""
        seen: set[URIRef] = {iri}
        order: list[str] = []
        frontier = [iri]
        while frontier:
            nxt: list[URIRef] = []
            for cls in frontier:
                for parent in sorted(
                    (p for p in self.g.objects(cls, RDFS.subClassOf) if isinstance(p, URIRef)), key=str
                ):
                    if parent not in seen:
                        seen.add(parent)
                        order.append(self.label(parent))
                        nxt.append(parent)
            frontier = nxt
        return order

    def general_axioms(self) -> dict[URIRef, list[str]]:
        """Anonymous 'X and (restriction) SubClassOf Named' axioms: sufficient conditions."""
        out: dict[URIRef, list[str]] = {}
        for node in set(self.g.subjects(RDFS.subClassOf, None)):
            if not isinstance(node, BNode) or (node, OWL.intersectionOf, None) not in self.g:
                continue
            text = self.render(node)
            if not text:
                continue
            for target in self.g.objects(node, RDFS.subClassOf):
                if isinstance(target, URIRef):
                    out.setdefault(target, []).append(f"sufficient: {text}")
        return out

    # -- extraction ---------------------------------------------------------- #
    def classes(self) -> list[dict]:
        g = self.g
        general = self.general_axioms()
        entities = []
        for iri in sorted((s for s in g.subjects(RDF.type, OWL.Class) if isinstance(s, URIRef)), key=str):
            item: dict[str, Any] = {"label": self.label(iri)}
            if self.include_iri:
                item["iri"] = str(iri)

            supers = list(g.objects(iri, RDFS.subClassOf))
            parents = sorted({self.label(p) for p in supers if isinstance(p, URIRef)})
            if parents:
                item["parent_classes"] = parents
            anc = self.ancestors(iri)
            if anc:
                item["ancestors"] = anc
            restrictions = sorted(
                {r for p in supers if not isinstance(p, URIRef) and (r := self.simple_restriction(p))}
            )
            if restrictions:
                item["superclass_expressions"] = restrictions

            conditions = [
                f"necessary and sufficient: {s}"
                for n in g.objects(iri, OWL.equivalentClass) if (s := self.render(n))
            ] + general.get(iri, [])
            if conditions:
                item["classification_conditions"] = sorted(conditions)

            definition = self.definition(iri)
            if definition:
                item["definition"] = definition
            item.update(self.categorized(iri))
            entities.append(item)
        return entities

    def restriction_usage(self) -> dict[URIRef, list[str]]:
        """property IRI -> ["Class <simple restriction>", ...] over all classes."""
        usage: dict[URIRef, list[str]] = {}
        for cls, sup in self.g.subject_objects(RDFS.subClassOf):
            if not (isinstance(cls, URIRef) and isinstance(sup, BNode)):
                continue
            prop = self.g.value(sup, OWL.onProperty)
            text = self.simple_restriction(sup)
            if isinstance(prop, URIRef) and text:
                usage.setdefault(prop, []).append(f"{self.label(cls)}: {text}")
        return usage

    def properties(self) -> list[dict]:
        g = self.g
        nodes = {
            s for t in (OWL.ObjectProperty, OWL.DatatypeProperty)
            for s in g.subjects(RDF.type, t) if isinstance(s, URIRef)
        }
        usage = self.restriction_usage()
        relationships = []
        for iri in sorted(nodes, key=str):
            item: dict[str, Any] = {"label": self.label(iri)}
            if self.include_iri:
                item["iri"] = str(iri)
            definition = self.definition(iri)
            if definition:
                item["definition"] = definition
            domain = sorted({s for n in g.objects(iri, RDFS.domain) if (s := self.render(n))})
            range_ = sorted({s for n in g.objects(iri, RDFS.range) if (s := self.render(n))})
            if domain:
                item["domain"] = domain
            if range_:
                item["range"] = range_

            inverses = {self.label(o) for o in g.objects(iri, OWL.inverseOf) if isinstance(o, URIRef)}
            inverses |= {self.label(s) for s in g.subjects(OWL.inverseOf, iri) if isinstance(s, URIRef)}
            if inverses:
                item["inverse"] = sorted(inverses)

            constraints: list[str] = []
            if domain:
                constraints.append("source must be: " + " | ".join(domain))
            if range_:
                constraints.append("target must be: " + " | ".join(range_))
            parents = sorted({self.label(o) for o in g.objects(iri, RDFS.subPropertyOf) if isinstance(o, URIRef)})
            if parents:
                constraints.append("specialises: " + ", ".join(parents))
            constraints += [f"used in: {u}" for u in sorted(set(usage.get(iri, [])))]
            if constraints:
                item["extraction_constraints"] = constraints
            relationships.append(item)
        return relationships

    def imports(self) -> list[dict]:
        out = []
        for ont in self.g.subjects(RDF.type, OWL.Ontology):
            for imp in self.g.objects(ont, OWL.imports):
                out.append({"iri": str(imp), "label": local_name(URIRef(str(imp).rstrip("/")))})
        return sorted(out, key=lambda d: d["iri"])


def extract(
    input_path: Path,
    output_path: Path,
    *,
    rdf_format: str | None = None,
    langs: list[str] | None = None,
    include_iri: bool = True,
    profile_id: str = "test",
) -> None:
    graph = Graph()
    graph.parse(input_path, format=rdf_format)
    extractor = Extractor(graph, langs or ["en"], include_iri)
    entities = extractor.classes()
    relationships = extractor.properties()

    document: dict[str, Any] = {
        "profile": {
            "id": profile_id,
            "ontology_artifact": input_path.stem,
            "description": f"LLM-context profile generated from {input_path.name}.",
        },
    }
    imports = extractor.imports()
    if imports:
        document["imports"] = imports
    document["entities"] = entities
    document["relationships"] = relationships

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        yaml.safe_dump(document, sort_keys=False, allow_unicode=True, width=100),
        encoding="utf-8",
    )
    print(f"Wrote {len(entities)} entities and {len(relationships)} relationships to {output_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--format", dest="rdf_format", default=None,
                        help="rdflib parser format (e.g. xml, turtle); guessed from extension if omitted")
    parser.add_argument("--lang", nargs="+", default=["en"],
                        help="languages to keep (untagged text is always kept); default: en")
    parser.add_argument("--no-iri", action="store_true", help="omit IRIs from the output")
    parser.add_argument("--profile-id", default="test")
    args = parser.parse_args()
    extract(args.input, args.output, rdf_format=args.rdf_format, langs=args.lang,
            include_iri=not args.no_iri, profile_id=args.profile_id)


if __name__ == "__main__":
    main()