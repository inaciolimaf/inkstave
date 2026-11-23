"""The ``--shard=K/N`` split used by CI's integration shards (``tests/fixtures/shard.py``)."""

from collections import Counter

import pytest

from tests.fixtures.shard import assign_files, parse_shard


def test_every_file_goes_to_exactly_one_shard_and_the_loads_stay_close() -> None:
    sizes = Counter({"a.py": 10, "b.py": 7, "c.py": 5, "d.py": 4, "e.py": 3, "f.py": 1})

    owner = assign_files(sizes, 3)

    assert set(owner) == set(sizes)
    loads: Counter[int] = Counter(dict.fromkeys((1, 2, 3), 0))
    for path, shard in owner.items():
        loads[shard] += sizes[path]
    assert sorted(loads.values()) == [10, 10, 10]


def test_the_split_does_not_depend_on_the_collection_order() -> None:
    forward = Counter({"a.py": 2, "b.py": 2, "c.py": 2})
    backward = Counter({"c.py": 2, "b.py": 2, "a.py": 2})

    assert assign_files(forward, 2) == assign_files(backward, 2)


def test_parse_shard_accepts_k_of_n() -> None:
    assert parse_shard("2/3") == (2, 3)


@pytest.mark.parametrize("value", ["0/3", "4/3", "x/3", "3"])
def test_parse_shard_rejects_anything_else(value: str) -> None:
    with pytest.raises(pytest.UsageError):
        parse_shard(value)
