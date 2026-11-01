"""Official wording and atomic numeric/coordinate contracts, never paper datasets."""

from datetime import date

import pytest

from backend.core.engines.context import SourceContext
from backend.core.specificity import SpecificityEngine
from tests.conftest import ROOT
from tests.screen import conftest as source_fixtures

registry = source_fixtures.registry
atom_document = source_fixtures.atom_document
AS_OF = date(2030, 1, 1)


@pytest.fixture
def assessor(registry):
    return SpecificityEngine(ROOT, registry, use_local_entities=False)


@pytest.fixture
def facts(assessor, atom_document):
    def read(text, as_of=AS_OF):
        document = atom_document(text)
        return assessor.features(
            document.units[0], 0, len(text), as_of=as_of, context=SourceContext(document)
        )

    return read
