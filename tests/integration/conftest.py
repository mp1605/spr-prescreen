import pytest


@pytest.fixture
def orthogonal_semantics(client):
    """Numerical nonmatches isolate the existing flagless-review UI contract.

    This is not a claim that an uncalibrated real model never flags a heading.
    Real BGE integration is exercised separately with official wording.
    """
    from tests.semantic.conftest import NumericProvider

    host = client.app.state.semantic_engine
    host.provider = NumericProvider(host.registry)
    host.references = None
