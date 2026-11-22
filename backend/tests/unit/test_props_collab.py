"""Property test for CRDT convergence (spec 28): replicas converge under any interleaving. Pure.

Replicas are ``YDocument`` instances exchanging their local updates through in-memory inboxes, with
no WebSocket and no server. Remote updates are applied with ``origin="remote"`` so the observer does
not echo them back.

Each inbox is FIFO. That is the order the server relays (one log, causally ordered, because a client
only edits after it has received what it edits against). Reordering within one inbox is NOT covered:
With pycrdt, a delete set that arrives before the items it deletes is observed to stay unapplied after
those items arrive. Two replicas that get the same updates in a shuffled order can then
diverge until the whole log is delivered again. Measured with deletions: about 45% of random orders
diverged, and re-delivering the log fixed every one. The server never produces such an order.
"""

from __future__ import annotations

from collections.abc import Callable

from hypothesis import given
from hypothesis import strategies as st
from pycrdt import Doc, merge_updates

from inkstave.modules.collab.crdt.ydocument import YDocument
from inkstave.modules.history.versions.reconstruct import text_from_state

_REMOTE = "remote"
_INSERT = st.text(alphabet="abc \n é", max_size=4)


class _Mesh:
    """N replicas, one inbox each; every local update is queued for every other replica."""

    def __init__(self, size: int) -> None:
        # fixed client ids: pycrdt draws a random one per Doc, which would make the examples differ per run
        self.replicas = [YDocument(Doc(client_id=index + 1)) for index in range(size)]
        self.inboxes: list[list[bytes]] = [[] for _ in range(size)]
        self.local_updates: list[bytes] = []
        for index, replica in enumerate(self.replicas):
            replica.observe(self._observer(index))

    def _observer(self, index: int) -> Callable[[bytes, str | None], None]:
        return lambda update, origin: self._broadcast(index, update, origin)

    def _broadcast(self, sender: int, update: bytes, origin: str | None) -> None:
        if origin == _REMOTE:
            return
        self.local_updates.append(update)
        for peer in range(len(self.inboxes)):
            if peer != sender:
                self.inboxes[peer].append(update)

    def deliver(self, peer: int) -> None:
        self.replicas[peer].apply_update(self.inboxes[peer].pop(0), origin=_REMOTE)


def _edit(data: st.DataObject, replica: YDocument) -> None:
    current = replica.text
    start = data.draw(st.integers(0, len(current)))
    end = data.draw(st.integers(start, min(len(current), start + 3)))
    replica.apply_edits([(start, end, data.draw(_INSERT))])


@given(size=st.integers(2, 4), data=st.data())
def test_replicas_converge_and_match_the_flushed_text(size: int, data: st.DataObject) -> None:
    mesh = _Mesh(size)
    for _ in range(data.draw(st.integers(0, 30))):  # random peers, random lag between edits and delivery
        peer = data.draw(st.integers(0, size - 1))
        deliver_now = data.draw(st.booleans()) if mesh.inboxes[peer] else False
        if deliver_now:
            mesh.deliver(peer)
        else:
            _edit(data, mesh.replicas[peer])
    for peer in range(size):
        while mesh.inboxes[peer]:
            mesh.deliver(peer)

    texts = {replica.text for replica in mesh.replicas}
    assert len(texts) == 1
    # the server's flush: the merged log of every update reproduces the text the clients converged on
    flushed = text_from_state(merge_updates(*mesh.local_updates))
    assert flushed == texts.pop()
