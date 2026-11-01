"""Engineering features from MASTER_PROMPT section 4, not additional policy rules."""

import re

from backend.core.color_models import FeatureKind
from backend.core.specificity_disclosure import EXTRA_PATTERNS

SYSTEM = r"(?:F[ -]*(?:22|35)[A-Z]*|[A-Z]{1,5} *- *\d{1,4}[A-Z0-9]*)(?:s)?"
NUMBER = (
    r"(?:\d{1,3}(?:,\d{3})+|\d{1,6}|zero|one|two|three|four|five|six|seven|eight|"
    r"nine|ten|eleven|twelve|thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|"
    r"nineteen|twenty)"
)
ASSETS = (
    rf"(?:aircraft|planes?|drones?|ships?|vehicles?|assets?|personnel|troops?|"
    rf"pilots?|operators?|airmen|technicians?|crew\s+chiefs?|physiological?\s+events?|{SYSTEM})"
)
QUALIFIER = (
    r"(?:(?:assigned|authorized|available|operational|deployed|mission[- ]capable|"
    r"trained|qualified|small|large|unexplained)\s+){0,2}"
)
MONTH = r"(?:January|February|March|April|May|June|July|August|September|October|November|December)"

PATTERNS: tuple[tuple[FeatureKind, re.Pattern[str]], ...] = (
    (
        "quantity",
        re.compile(
            rf"(?<![\w-]){NUMBER}\s+(?:(?:of|out\s+of)\s+(?:the\s+)?{NUMBER}\s+)?"
            rf"{QUALIFIER}{ASSETS}\b",
            re.I,
        ),
    ),
    (
        "unit",
        re.compile(
            r"\b\d{1,4}(?:st|nd|rd|th)?\s+(?:(?:Fighter|Air|Airborne|Operations|Training|"
            r"Support|Combat|Expeditionary)\s+){0,3}(?:Wing|Squadron|Group|Battalion|"
            r"Brigade|Regiment|Division)\b",
            re.I,
        ),
    ),
    (
        "unit",
        re.compile(
            r"\b(?!(?:The|This|Our|A|An)\b)[A-Z][a-zA-Z]+\s+"
            r"(?i:(?:(?:Security|Forces|Training|Operations|Air|Expeditionary|Combat|Fighter)\s+){1,4}"
            r"(?:Group|Wing|Squadron))\b"
        ),
    ),
    (
        "location",
        re.compile(
            r"\b(?!(?:Air|Force|The|Department)\b)[A-Z][A-Za-z'’-]+(?:\s+[A-Z][A-Za-z'"
            r"’-]+){0,2}\s+(?:Air\s+Force\s+Base|Air\s+Base|AFB|Naval\s+Base|Airfield)\b"
        ),
    ),
    ("location", re.compile(r"\bWashington(?:,?\s+D\.?C\.?)?\b")),
    ("system", re.compile(rf"\b{SYSTEM}\b")),
    (
        "program",
        re.compile(
            r"\b(?:Project|Program|Operation|Exercise)\s+[A-Z][A-Za-z0-9'’-]+(?:\s+[A-"
            r"Z][A-Za-z0-9'’-]+){0,2}\b"
        ),
    ),
    (
        "measurement",
        re.compile(
            r"\b\d+(?:\.\d+)?\s*(?:km|kilometers?|miles?|MHz|GHz|kW|MW|mm|milliseconds"
            r"?|ms|seconds?|minutes?|hours?|meters?|metres?|percent|ng/L|mg/L|µg/L|ppb|ppt|%)(?!\w)",
            re.I,
        ),
    ),
    (
        "operational",
        re.compile(
            r"\b(?:mission[- ]capable|assigned|authorized|readiness|operational|capabi"
            r"lit(?:y|ies)|shortfall|vulnerabilit(?:y|ies)|deployed|deploying|schedule"
            r"d|generating\s+sorties|flying\s+operations|detection\s+range)\b",
            re.I,
        ),
    ),
    (
        "procedure",
        re.compile(r"\b(?:first\b[^.!?]{0,140}\bthen|step\s*1\b[^.!?]{0,140}\bstep\s*2)\b", re.I),
    ),
    (
        "procedure",
        re.compile(
            r"\b(?:repair|restore)\b.{0,140}\b(?:resume|return|restor\w*)\b.{0,80}"
            r"\b(?:operations|sorties|mission)\b|"
            r"\b(?:sequence|order|timeline)\b.{0,140}\b(?:restore|runways?|sorties|mission)\b",
            re.I,
        ),
    ),
    (
        "control",
        re.compile(r"\b(?:ITAR|International\s+Traffic\s+in\s+Arms\s+Regulations)\b", re.I),
    ),
    (
        "actor",
        re.compile(
            r"\b(?:U\.?S\.?\s+(?:Army|Navy|Marine\s+Corps|Space\s+Force)|Department\s+"
            r"of\s+(?:Defense|the\s+Navy)|Defense\s+Intelligence\s+Agency)\b",
            re.I,
        ),
    ),
    (
        "coordination_gap",
        re.compile(
            r"\b(?:no\s+(?:documented\s+)?coordination|without\s+documented\s+coordina"
            r"tion|undocumented\s+coordination|coordination\s+(?:has\s+)?(?:not(?:\s+b"
            r"een)?|was\s+not|is\s+not)\s+documented|coordination\s+documentation\s+is"
            r"\s+missing)\b",
            re.I,
        ),
    ),
    (
        "origin_release",
        re.compile(
            r"\b(?:originates?\s+(?:from|in)|(?:is|was)\s+proposed\s+for\s+release\s+in)\b", re.I
        ),
    ),
    (
        "authority_action",
        re.compile(
            r"\b(?:(?:authorized|ordered|directed|approved)\s+by\s+(?:the\s+)?(?:Presi"
            r"dent|Secretary\s+of\s+Defense)|(?:President|Secretary\s+of\s+Defense)(?:"
            r"'s)?\s+(?:order|directive|authorization))\b",
            re.I,
        ),
    ),
    (
        "release_event",
        re.compile(
            r"\b(?:released|spilled|detected|leaked|responded|containment|remediation|sampling\s+found)\b",
            re.I,
        ),
    ),
    (
        "uncertainty",
        re.compile(
            r"\b(?:hypothetical|illustrative|suppose|could|might|"
            r"may(?=\s+(?:be|have|include|contain|deploy|affect|become|require))|"
            r"would|if|for\s+example|e\.g\.)(?!\w)",
            re.I,
        ),
    ),
    (
        "negation",
        re.compile(
            r"\b(?:(?:does\s+not|do\s+not|never)\s+(?:provide|include|contain|disclose"
            r"|reveal|report|describe|specify)|no\s+(?:deployment|release)\b|not\s+sch"
            r"eduled)\b",
            re.I,
        ),
    ),
)
PATTERNS += EXTRA_PATTERNS
DATE = re.compile(rf"\b(?:{MONTH}\s+(?:\d{{1,2}},?\s+)?\d{{4}}|\d{{4}}-\d{{2}}-\d{{2}})\b", re.I)
MONTH_ONLY = re.compile(rf"\b{MONTH}\b", re.I)
FUTURE = re.compile(r"\b(?:will|scheduled|upcoming|next|planned)\b", re.I)
URI = re.compile(r"https?://\S+|\bdoi:\s*\S+|\b10\.\d{4,9}/\S+", re.I)
