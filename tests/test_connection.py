"""Unit tests for the connection model."""

import pytest

from connection import Connection


def test_reversed_declarations_share_a_key() -> None:
    """a-b and b-a are the same link, so they must share a key."""
    assert Connection("roof1", "roof2").key == Connection("roof2", "roof1").key


def test_name_preserves_declaration_order() -> None:
    """name follows the map file, since it is what gets printed."""
    assert Connection("roof2", "roof1").name == "roof2-roof1"


def test_other_returns_the_far_endpoint() -> None:
    """other() answers from whichever end you ask."""
    link = Connection("roof1", "roof2")
    assert link.other("roof1") == "roof2"
    assert link.other("roof2") == "roof1"


def test_other_rejects_a_stranger() -> None:
    """Asking from a zone that is not an endpoint is a caller bug."""
    with pytest.raises(ValueError):
        Connection("roof1", "roof2").other("nowhere")
