"""Literal capability/disclosure facts; no case identities or evaluation labels."""

import re

from backend.core.color_models import FeatureKind

COUNT = r"(?:\d+(?:\.\d+)?|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve)"
EXTRA_PATTERNS: tuple[tuple[FeatureKind, re.Pattern[str]], ...] = (
    (
        "measurement",
        re.compile(r"\b\d{1,3}(?:,\d{3})*(?:\.\d+)?\s+square\s+(?:miles|kilometers)\b", re.I),
    ),
    (
        "measurement",
        re.compile(
            rf"\b{COUNT}[ -]+(?:kilowatts?|watts?|kilometers?|metres?|meters?|miles?|"
            r"seconds?|minutes?|hours?|days?|percent)\b",
            re.I,
        ),
    ),
    ("date", re.compile(r"(?<![\w-])(?:19|20)\d{2}(?![\w-])")),
    (
        "quantity",
        re.compile(
            rf"\b{COUNT}\s+(?:(?:of\s+(?:the\s+)?{COUNT}|small|ground|drone|fire)\s+)*"
            r"(?:fighters?|targets?|operators?|patrols?|trucks?|generators?|homes?|wells?)\b",
            re.I,
        ),
    ),
    ("program", re.compile(r"\b[A-Z][\w-]+\s+Flag\s+\d{2}(?:-\d)?\b")),
    (
        "operational_context",
        re.compile(
            r"\b(?:aircraft|fighters?|squadron|military|sorties|strike|flightline|"
            r"fuel\s+(?:system|distribution)|runways?|command\s+post|base.?s\s+operational|"
            r"cyber\s+(?:defen[cs]e|attack)|navigation|readiness|missile\s+warning|"
            r"mobiliz\w*|operations?)\b",
            re.I,
        ),
    ),
    (
        "performance",
        re.compile(
            r"\b(?:destroyed|intercept(?:ed)?|tracked|struck|launched|suppress\w*|detect\w*|"
            r"failed\s+to\s+contain|cut\s+(?:simulated\s+)?losses|cover\s+the\s+same\s+perimeter|"
            r"maneuver\s+during\s+flight)\b",
            re.I,
        ),
    ),
    (
        "dependency",
        re.compile(
            r"\b(?:navigation|timing)\b.{0,80}\bunderpins?\b|"
            r"\b(?:depend\w*|rely|relied)\b.{0,110}\b(?:navigation|timing|tankers?|fuel|satellites?)\b|"
            r"\b(?:loss|jamming|spoofing|failure|lack\w*)\b.{0,150}"
            r"\b(?:degrad\w*|deny|halt|prevent|sustain|disrupt|collapse|encryption|authentication)\b|"
            r"\b(?:only|limited)\b.{0,60}\b(?:track|engage)\b.{0,60}\bat\s+a\s+time\b|"
            r"\b(?:insufficient|could\s+not|no\s+qualified\s+backup)\b.{0,100}"
            r"\b(?:sorties?|sustain|missions?|operations?|mobiliz\w*)\b|"
            r"\b(?:personnel|equipment)\b.{0,100}\bcould\s+not\s+perform\b|"
            r"\b(?:readiness\s+shortfalls?|training\s+time)\b.{0,130}\binsufficient\b",
            re.I,
        ),
    ),
    (
        "disclosure",
        re.compile(
            r"\b(?:reveal\w*|show\w*|reproduc\w*|includ\w*|list\w*)\b.{0,100}"
            r"\b(?:exact|specific|detailed|full)\b.{0,80}"
            r"\b(?:dimensions|tolerances|settings|tactics|composition|capabilities|route|status)\b|"
            r"\b(?:exact|specific|detailed)\s+(?:dimensions|tolerances|tactics|composition)\b",
            re.I,
        ),
    ),
    (
        "procedure",
        re.compile(
            r"\b(?:held|sequenc\w*|timed)\b.{0,100}\b(?:until|before|after)\b|"
            r"\b(?:exact|specific|detailed)\s+(?:sequence|tactics|procedures?)\b",
            re.I,
        ),
    ),
    (
        "release_event",
        re.compile(r"\b(?:response\s+plan|activated\s+carbon|filtration|bottled\s+water)\b", re.I),
    ),
)
