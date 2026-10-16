"""Unit tests for the map parser."""

from pathlib import Path

import pytest

from errors import ParseError, ValidationError
from parser import MapParser
from zone import ZoneType

BODY = """\
start_hub: s 0 0
end_hub: g 2 0
hub: a 1 0
connection: s-a
connection: a-g"""


def parse(text: str) -> None:
    """Parse a map given as one string.

    Args:
        text: The whole map file content.
    """
    MapParser().parse_lines(text.splitlines())


def test_valid_map_parses() -> None:
    """A well formed map yields its zones, links and fleet size."""
    network = MapParser().parse_lines(
        f"nb_drones: 3\n{BODY}".splitlines()
    )
    assert network.nb_drones == 3
    assert network.start.name == "s"
    assert network.end.name == "g"
    assert len(network.connections) == 2


def test_comments_whitespace_and_tag_order_are_accepted() -> None:
    """Comments, blank lines and any tag order are all legal."""
    network = MapParser().parse_lines("""
# a comment
   nb_drones:  2   # trailing comment

start_hub: s 0 0 [color=green]
end_hub: g 2 0
hub: a 1 0 [max_drones=2 color=blue zone=priority]
connection: s-a [max_link_capacity=2]
connection: a-g
""".splitlines())
    zone = network.zone("a")
    assert zone.zone_type is ZoneType.PRIORITY
    assert zone.capacity == 2
    assert zone.color == "blue"


def test_negative_coordinates_are_accepted() -> None:
    """Coordinates only have to be integers."""
    MapParser().parse_lines(f"nb_drones: 1\n{BODY}\nhub: b -1 -4".splitlines())


@pytest.mark.parametrize(
    ("text", "line", "cause"),
    [
        (BODY, 1, "first directive must be nb_drones"),
        (f"nb_drones: 0\n{BODY}", 1, "must be positive"),
        (f"nb_drones: -3\n{BODY}", 1, "must be positive"),
        (f"nb_drones: 2.5\n{BODY}", 1, "must be an integer"),
        (f"nb_drones: 2\nnb_drones: 3\n{BODY}", 2, "declared twice"),
        (f"nb_drones: 1\n{BODY}\nstart_hub: t 5 5", 7, "two start hubs"),
        (f"nb_drones: 1\n{BODY}\nend_hub: h 5 5", 7, "two end hubs"),
        (f"nb_drones: 1\n{BODY}\nhub: a 3 3", 7, "duplicate zone name"),
        (f"nb_drones: 1\n{BODY}\nhub: b 1.5 0", 7, "must be an integer"),
        (f"nb_drones: 1\n{BODY}\nhub: b 1", 7, "expected '<name> <x> <y>'"),
        (f"nb_drones: 1\n{BODY}\nhub: b-c 1 0", 7, "may not contain a dash"),
        (f"nb_drones: 1\n{BODY}\nconnection: a-zzz", 7, "unknown zone"),
        (f"nb_drones: 1\n{BODY}\nconnection: a-s", 7, "duplicate connection"),
        (f"nb_drones: 1\n{BODY}\nconnection: a-a", 7, "self loop"),
        (f"nb_drones: 1\n{BODY}\nhub: b 1 0 [zone=lava]", 7,
         "unknown zone type"),
        (f"nb_drones: 1\n{BODY}\nhub: b 1 0 [zone=normal", 7,
         "malformed metadata"),
        (f"nb_drones: 1\n{BODY}\nhub: b 1 0 [zone]", 7, "key=value"),
        (f"nb_drones: 1\n{BODY}\nhub: b 1 0 [speed=3]", 7,
         "unknown zone tag"),
        (f"nb_drones: 1\n{BODY}\nhub: b 1 0 [zone=normal zone=blocked]", 7,
         "duplicate tag"),
        (f"nb_drones: 1\n{BODY}\nhub: b 1 0 [max_drones=0]", 7,
         "must be positive"),
        (f"nb_drones: 1\n{BODY}\nconnection: s-g [max_link_capacity=-1]",
         7, "must be positive"),
        (f"nb_drones: 1\n{BODY}\nconnection: s-g [max_drones=2]", 7,
         "unknown connection tag"),
        (f"nb_drones: 1\n{BODY}\nbridge: s-g", 7, "unknown directive"),
    ],
)
def test_invalid_maps_report_line_and_cause(
    text: str, line: int, cause: str
) -> None:
    """Every syntax error names the offending line and what is wrong."""
    with pytest.raises(ParseError) as caught:
        parse(text)
    assert caught.value.line_num == line
    assert cause in caught.value.cause


@pytest.mark.parametrize(
    "text",
    [
        "",
        "# only a comment",
        "nb_drones: 1\nstart_hub: s 0 0\nhub: a 1 0\nconnection: s-a",
        "nb_drones: 1\nend_hub: g 0 0\nhub: a 1 0\nconnection: a-g",
    ],
)
def test_incomplete_maps_are_rejected(text: str) -> None:
    """A map missing nb_drones, the start or the end cannot be used."""
    with pytest.raises((ParseError, ValidationError)):
        parse(text)


def test_binary_file_is_a_parse_error(tmp_path: Path) -> None:
    """A file that is not text fails cleanly instead of crashing."""
    path = tmp_path / "binary.txt"
    path.write_bytes(b"\xdb\xff\x00\x81nb_drones")
    with pytest.raises(ParseError, match="UTF-8"):
        MapParser().parse_file(str(path))
