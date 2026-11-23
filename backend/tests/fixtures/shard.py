"""``--shard=K/N``: run one of N disjoint slices of the collected tests (CI's integration shards).

Whole files go to one shard, so a module's fixtures are set up once. Files are dealt greedily,
largest first, to the shard with the fewest tests, which keeps the shards within a few tests of
each other. The split depends only on the collected node ids, so every xdist worker and every CI
job computes the same one.
"""

from __future__ import annotations

from collections import Counter

import pytest


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption("--shard", default=None, help="K/N: run the K-th of N slices of the tests")


def parse_shard(value: str) -> tuple[int, int]:
    """``"2/3"`` -> ``(2, 3)``; anything else is a usage error."""
    try:
        index, total = (int(part) for part in value.split("/"))
    except ValueError:
        raise pytest.UsageError(f"--shard expects K/N, got {value!r}") from None
    if not 1 <= index <= total:
        raise pytest.UsageError(f"--shard {value!r}: K must be between 1 and N")
    return index, total


def assign_files(sizes: Counter[str], total: int) -> dict[str, int]:
    """Map each file to a shard number in 1..total, balancing the test counts."""
    loads = [0] * total
    owner: dict[str, int] = {}
    for path, size in sorted(sizes.items(), key=lambda item: (-item[1], item[0])):
        shard = loads.index(min(loads))
        loads[shard] += size
        owner[path] = shard + 1
    return owner


@pytest.hookimpl(trylast=True)
def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    value = config.getoption("--shard")
    if not value:
        return
    index, total = parse_shard(value)
    owner = assign_files(Counter(item.nodeid.split("::")[0] for item in items), total)
    keep = [item for item in items if owner[item.nodeid.split("::")[0]] == index]
    config.hook.pytest_deselected(items=[item for item in items if item not in keep])
    items[:] = keep
