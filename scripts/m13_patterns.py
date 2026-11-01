"""Candidate detector expansions for existing official items, evaluated on development only."""

from backend.core.rules_loader import Detector, RuleRegistry

# Descriptive topic families, not paper names, quotations, seeded counts or answer tags.
PATTERNS: dict[str, tuple[str, ...]] = {
    "L1-1": (r"\bclassified\s+(?:assessment|information|system|capabilit\w*)\b",),
    "L1-3": (
        r"\b(?:partner\s+nation|foreign\s+government|allied\s+government)\b.{0,180}"
        r"\b(?:in\s+confidence|confidential|classified|not\s+be\s+(?:included|released))\b",
        r"\b(?:camera\s+coverage|perimeter\s+fence|intrusion\s+sensor|guard\s+patrol)\b"
        r".{0,180}\b(?:blind\s+spot|broken|gap|unseen|unprotected)\b",
        r"\b(?:convoy|sensitive\s+cargo)\b.{0,180}"
        r"\b(?:exact\s+departure|full\s+route|checkpoints|security\s+escort)\b",
        r"\b(?:public\s+social\s+media|civilian\s+(?:contractor|trucking))\b.{0,180}"
        r"\b(?:destination|week\s+of\s+travel)\b",
    ),
    "L1-4": (
        r"\b(?:pending|future|unreleased|nonpublic)\s+(?:contractor\s+)?(?:bid|proposal)s?\b",
        r"\bproprietary\b.{0,100}\b(?:algorithm|pricing|technical\s+data|financial)s?\b",
    ),
    "L1-5": (r"\battorney\s+(?:work\s+product|advice|client)\b",),
    "L1-6": (r"\b(?:attached|sent|forwarded|distributed)\b.{0,80}\b(?:spreadsheet|file|email)\b",),
    "L1-7": (
        r"\b(?:sworn\s+statement|witness\s+testimony)\b.{0,100}\b(?:investigators?|police)\b",
    ),
    "L2-01": (
        r"\b(?:trial|experiment|test\w*)\b.{0,140}\b(?:dogs?|canines?|mice|rats|primates|animals)\b",
        r"\b(?:veterinary|animals?|canines?|primates)\b.{0,100}\b(?:trial|experiment|test\w*)\b",
    ),
    "L2-03": (
        r"\b(?:hypersonic\s+weapons?|attritable\s+(?:aircraft|weapons?))\b",
        r"\b(?:concept|prototype|new|proposed)\b.{0,140}\b(?:weapons?|unmanned\s+aircraft)\b",
    ),
    "L2-04": (r"\bunmanned\s+(?:aircraft|systems?)\b",),
    "L2-07": (
        r"\b(?:tingling|light[- ]headed?|hypoxic|oxygen\s+deprivation)\b.{0,140}"
        r"\b(?:altitude|flight|aircraft|pilot|aircrew)\b",
    ),
    "L2-09": (r"\bmilitary\b.{0,100}\bsatellites?\b|\bsatellites?\b.{0,100}\bmilitary\b",),
    "L2-12": (
        r"\b(?:generat\w*\s+sorties|mission[- ]capable|non[- ]mission[- ]capable)\b",
        r"\b(?:authorized|assigned)\s+[\d,]+\s+(?:airmen|personnel|aircraft|pilots)\b",
        r"\b(?:military\s+operations|flying\s+mission)\b.{0,160}"
        r"\b(?:loss|degrade|restore|reconstitute|depend)\w*\b",
        r"\b(?:loss|degrad\w*|deny|corrupt)\b.{0,100}\b(?:military\s+operations|satellite\s+navigation)\b",
        r"\breadiness\b",
    ),
    "L2-13": (
        r"\b(?:single\s+point\s+of\s+failure|single\s+(?:fuel|power|communication)\s+"
        r"(?:(?:pumping|distribution)\s+)?(?:station|node|line))\b",
        r"\bvulnerabilit\w*\b.{0,100}\b(?:base|recovery|capabilit|mission)\w*\b",
    ),
    "L2-14": (r"\b(?:number|type|armament)\b.{0,100}\b(?:vehicles?|convoy|escort)\b",),
    "L2-15": (
        r"\b(?:exercise|wargame)\b.{0,160}\b(?:modeled|rehearsed|measured|required|sequence)\b",
    ),
    "L2-17": (
        r"\b(?:detailed\s+sequence|order\s+in\s+which)\b.{0,120}"
        r"\b(?:mission|restore|strike|aircraft|runways?|sorties)\b",
        r"\b(?:strike|wargame)\b.{0,160}\b(?:saturated|suppress|disperse|sortie\s+rate)\w*\b",
    ),
    "L2-19": (r"\bPentagon\b",),
    "L2-18": (r"\b(?:upcoming\s+(?:move|movement)|week\s+of\s+travel)\b",),
    "L2-20": (
        r"\b(?:national\s+news|congressional\s+hearings?|political\s+attention|news\s+coverage)\b",
    ),
    "L2-22": (
        r"\bDepartment\s+of\s+Defense\b.{0,100}\b(?:strategy|guidance)\b.{0,100}\b(?:adopting|responsible)\b",
    ),
    "L2-27": (
        r"\b(?:no|without)\b.{0,60}\b(?:agreement|coordination|memo)\b.{0,60}"
        r"\b(?:signed|documented|approved)\b",
    ),
    "L2-28": (
        r"\b(?:no|without)\b.{0,60}\b(?:agreement|coordination|memo)\b.{0,60}"
        r"\b(?:signed|documented|approved)\b",
    ),
    "L2-29": (
        r"\b(?:authorized|assigned)\s+[\d,]+\s+(?:airmen|personnel|aircraft|pilots)\b",
        r"\b(?:tail\s+numbers?|flying\s+schedule)\b",
    ),
}


def candidate(registry: RuleRegistry) -> RuleRegistry:
    def expand(item):
        additions = []
        for n, pattern in enumerate(PATTERNS.get(item.id, ())):
            context = None
            if item.id == "L1-3" and n == 3:
                context = r"\b(?:convoy|sensitive\s+cargo|security\s+escort)\b"
            if item.id == "L1-6":
                context = (
                    r"\b(?:personal\s+(?:data|medical)|medical\s+(?:restrictions|conditions)|"
                    r"date\s+of\s+birth|social\s+security|home\s+address)\b"
                )
            if item.id == "L2-12" and pattern == r"\breadiness\b":
                context = (
                    r"\b(?:\d+(?:,\d{3})*\s+(?:aircraft|planes?|personnel|pilots?|airmen)|"
                    r"F[- ](?:22|35))\b"
                )
            if item.id == "L2-27":
                context = r"\b(?:Navy|Army|Marines?|Space\s+Force|sister\s+service)\b"
            if item.id == "L2-28":
                context = (
                    r"\b(?:another|other|neighboring)\b.{0,60}\b(?:Air\s+Force|wing|installation)\b"
                )
            additions.append(
                Detector(
                    kind="regex",
                    name=f"Contextual official-topic paraphrase {n + 1}",
                    item_id=item.id,
                    pattern=pattern,
                    context_pattern=context,
                    context_scope="nearby" if context and item.id != "L2-12" else "unit",
                )
            )
        previous = list(item.detectors)
        if item.id == "L2-12":
            previous = [
                d.model_copy(update={"terms": tuple(t for t in d.terms if t != "readiness")})
                if d.kind == "keywords" and "readiness" in d.terms
                else d
                for d in previous
            ]
        if item.id == "L2-05":
            previous = [
                d.model_copy(update={"terms": tuple(t for t in d.terms if t != "cyber")})
                if d.kind == "keywords" and "cyber" in d.terms
                else d
                for d in previous
            ]
            additions.append(
                Detector(
                    kind="regex",
                    name="Cyber technical context",
                    item_id=item.id,
                    pattern=r"\bcyber\b(?!\s+(?:operators?|personnel|staff|careers?|officers?))",
                )
            )
        if item.id == "L2-18":
            previous = [
                d.model_copy(
                    update={
                        "pattern": (
                            r"\bdeploy(?:ment|ments|ed|ing|s)?\b(?=.{0,120}\b(?:to|schedules?|"
                            r"locations?|dates?|base|week|month|year|January|February|March|April|"
                            r"May|June|July|August|September|October|November|December)\b)"
                        )
                    }
                )
                if d.name == "Deployment topic"
                else d
                for d in previous
            ]
        if item.id == "L2-28":
            additions.append(
                Detector(
                    kind="regex",
                    name="Uncoordinated neighboring installation work",
                    item_id=item.id,
                    pattern=r"\b(?:neither|no)\b.{0,100}\b(?:reviewed|coordinated|signed)\b",
                    context_pattern=r"\b(?:neighboring|another|other)\b.{0,60}\b(?:wing|installation|base)\b",
                    context_scope="nearby",
                )
            )
        return item.model_copy(update={"detectors": (*previous, *additions)})

    return registry.model_copy(
        update={
            "policy_version": "M13-development-candidate",
            "list1": tuple(expand(i) for i in registry.list1),
            "list2": tuple(expand(i) for i in registry.list2),
        }
    )
