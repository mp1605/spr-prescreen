"""Reviewable paraphrases for the existing official IDs; no evaluation identities."""

from backend.core.rules_loader import Detector, RuleRegistry

# (source pattern, required contextual topic). Context is bounded by SourceContext.
PATTERNS: dict[str, tuple[tuple[str, str | None], ...]] = {
    "L1-3": (
        (
            r"\b(?:MSgt|TSgt|SrA|SSgt)\.?\s+[A-Z][a-z]+\s+(?:[A-Z]\.\s+)?[A-Z][a-z]+\b",
            r"\b(?:expeditionary|deployed)\b.{0,140}\b(?:team|unit|communications)\b",
        ),
    ),
    "L1-4": (
        (
            r"\b(?:proposed\s+prices|pricing\s+model|salary\s+rates)\b",
            r"\b(?:competing|confidential|proprietary|in\s+confidence)\b",
        ),
        (
            r"\bindependent\s+(?:government\s+)?cost\s+estimate\b",
            r"\b(?:before\s+(?:an?\s+)?award|source\s+selection|competing|proposal)\b",
        ),
    ),
    "L1-5": ((r"\bdraft\s+(?:evaluation|scores?|ranking)\w*\b", None),),
    "L2-02": ((r"\blaser\s+(?:prototype|weapon|system)\w*\b", None),),
    "L2-03": ((r"\bprototype\b", r"\b(?:laser|weapon|military|defen[cs]e)\b"),),
    "L2-04": ((r"\b(?:quadcopters?|drone\s+swarm)\b", None),),
    "L2-05": ((r"\bcyber[- ]?attacks?\b", None),),
    "L2-09": (
        (
            r"\bspace[- ]based\s+(?:navigation|timing|communications?)\b",
            r"\b(?:Air\s+Force|Space\s+Force|military)\b",
        ),
    ),
    "L2-11": (
        (
            r"\b(?:virus|viral|toxin|pathogen)\b",
            r"\b(?:laboratory|research|strain|experiment)\w*\b",
        ),
    ),
    "L2-12": (
        (
            r"\b(?:navigation|timing)\b.{0,100}\bsatellites?\b.{0,60}"
            r"\bunderpins?\s+military\s+operations\b",
            None,
        ),
        (
            r"\b(?:readiness|shortfalls?)\b",
            r"\b(?:unit|reserve|training|mobiliz\w*|operational|force|reported|evaluation)\b",
        ),
        (
            r"\b(?:depend\w*|loss|degrad\w*)\b.{0,160}\b(?:satellite|space[- ]based)\w*\b|"
            r"\b(?:satellites?|space[- ]based)\b.{0,160}\b(?:depend\w*|loss|degrad\w*)\b",
            r"\b(?:military|operations?|navigation|timing|communications?)\b",
        ),
    ),
    "L2-13": (
        (
            r"\b(?:only|limited)\b.{0,60}\b(?:track|engage)\b.{0,60}\bat\s+a\s+time\b",
            r"\b(?:laser|military|weapon|squadron|defen[cs]e)\b",
        ),
        (
            r"\b(?:loss|jamming|spoofing|shortfalls?|insufficient)\b|"
            r"\black\w*\b.{0,80}\b(?:encryption|authentication|protections?|backup)\b",
            r"\b(?:military|operations?|sorties|readiness|mobiliz\w*|satellite|control\s+system)\b",
        ),
        (r"\bwarning\s+systems?\b.{0,120}\b(?:only|limited|compressed)\b.{0,60}\bminutes?\b", None),
    ),
    "L2-14": ((r"\b\d+\s+fighters?\b", None),),
    "L2-15": ((r"\b[A-Z][\w-]+\s+Flag\s+\d{2}(?:-\d)?\b", None),),
    "L2-17": (
        (
            r"\b(?:techniques?|sequence|tactics)\b",
            r"\b(?:squadron|aircraft|refuel|sorties|strike|military)\b",
        ),
        (r"\b(?:track|engage)\b.{0,60}\bat\s+a\s+time\b", r"\b(?:laser|weapon|defen[cs]e)\b"),
    ),
    "L2-18": ((r"\b(?:expeditionary|deployed)\b.{0,120}\b(?:team|unit)\b", None),),
    "L2-23": (
        (
            r"\b(?:oppose|opposed|opposition|controversy|disagreement)\b",
            r"\b(?:Army|Navy|Marine|DoD|Department\s+of\s+Defense)\b",
        ),
    ),
    "L2-26": (
        (
            r"\b(?:professional\s+military\s+education|burnout|readiness\s+of\s+the\s+force)\b",
            r"\b(?:senior[- ]leader|senior\s+levels|Department\s+of\s+Defense)\b",
        ),
    ),
    "L2-31": (
        (
            r"\b(?:response\s+plan|activated\s+carbon|filtration|bottled\s+water)\b",
            r"\b(?:PFAS|PFOA|PFOS|perfluoro\w*)\b",
        ),
    ),
}


def candidate(registry: RuleRegistry) -> RuleRegistry:
    def expand(item):
        additions = tuple(
            Detector(
                kind="regex",
                name=f"Official topic contextual coverage {n + 1}",
                item_id=item.id,
                pattern=pattern,
                context_pattern=context,
                context_scope=("document" if item.id == "L2-31" else "nearby")
                if context
                else "unit",
            )
            for n, (pattern, context) in enumerate(PATTERNS.get(item.id, ()))
        )
        return item.model_copy(update={"detectors": (*item.detectors, *additions)})

    return registry.model_copy(
        update={
            "policy_version": "accuracy-development-candidate",
            "list1": tuple(expand(i) for i in registry.list1),
            "list2": tuple(expand(i) for i in registry.list2),
        }
    )
