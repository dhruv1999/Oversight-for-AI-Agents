import pytest

from oversight.policies import DEFAULT_POLICY
from oversight.schema import Action

POLICY_PATH = DEFAULT_POLICY


@pytest.fixture
def policy_path():
    return POLICY_PATH


def make_action(**kw):
    base = dict(
        id="a1",
        tool="t",
        description="synthetic action",
        category="read",
        reversibility="reversible",
        blast_radius="self",
        sensitivity="none",
    )
    base.update(kw)
    return Action(**base)


@pytest.fixture
def act():
    return make_action
