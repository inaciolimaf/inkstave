"""Smart HTTP protocol pieces, synchronous (spec 121). Callers run these in threads.

Advertisements and fetches are dulwich's own handlers, driven over in-memory streams. A push is parsed
here: its commands are read, and its pack is ingested into the repository, but the ref is never moved by
dulwich. The push module decides that after validation.
"""

from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import TYPE_CHECKING

from dulwich.objects import ObjectID
from dulwich.protocol import ReceivableProtocol, extract_capabilities, pkt_line
from dulwich.server import Backend, ReceivePackHandler, UploadPackHandler

from inkstave.modules.git.errors import GitProtocolRequestError
from inkstave.modules.git.repo.repository import open_or_create

if TYPE_CHECKING:
    from dulwich.repo import Repo

ZERO_SHA = b"0" * 40
SERVICES = ("git-upload-pack", "git-receive-pack")


class _SingleRepoBackend(Backend):
    """Serves exactly one already-open repository, whatever path dulwich asks for."""

    def __init__(self, repo: Repo) -> None:
        self._repo = repo

    def open_repository(self, path: str | bytes) -> Repo:
        return self._repo


def advertise(path: Path, service: str) -> bytes:
    """The ``info/refs`` body for ``service``: the service banner, then dulwich's advertisement."""
    with open_or_create(path) as repo:
        out = BytesIO()
        proto = ReceivableProtocol(BytesIO().read, out.write)
        proto.write_pkt_line(b"# service=" + service.encode("ascii") + b"\n")
        proto.write_pkt_line(None)
        handler_cls = UploadPackHandler if service == "git-upload-pack" else ReceivePackHandler
        handler = handler_cls(
            _SingleRepoBackend(repo),
            [str(path)],
            proto,
            stateless_rpc=True,
            advertise_refs=True,
        )
        handler.handle()
        return out.getvalue()


def run_upload_pack(path: Path, body: bytes) -> bytes:
    """Answer one fetch request (``git-upload-pack`` POST) with dulwich's pack generation."""
    with open_or_create(path) as repo:
        out = BytesIO()
        proto = ReceivableProtocol(BytesIO(body).read, out.write)
        UploadPackHandler(_SingleRepoBackend(repo), [str(path)], proto, stateless_rpc=True).handle()
        return out.getvalue()


@dataclass(frozen=True, slots=True)
class PushCommand:
    old: ObjectID
    new: ObjectID
    ref: bytes


def parse_commands(body: bytes) -> tuple[list[PushCommand], set[bytes], ReceivableProtocol]:
    """Read the command list of a receive-pack body. The pack follows the flush packet, unread."""
    proto = ReceivableProtocol(BytesIO(body).read, BytesIO().write)
    commands: list[PushCommand] = []
    capabilities: set[bytes] = set()
    first = True
    while True:
        line = proto.read_pkt_line()
        if line is None:
            break
        if first:
            line, extra = extract_capabilities(line)
            capabilities = set(extra)
            first = False
        parts = line.rstrip(b"\n").split(b" ")
        if len(parts) != 3 or len(parts[0]) != 40 or len(parts[1]) != 40:
            raise GitProtocolRequestError("Invalid ref update line from client.")
        commands.append(PushCommand(ObjectID(parts[0]), ObjectID(parts[1]), parts[2]))
    return commands, capabilities, proto


def ingest_pack(repo: Repo, proto: ReceivableProtocol, max_bytes: int) -> None:
    """Store the pack that follows the commands as a thin pack, refusing more than ``max_bytes``."""
    repo.object_store.add_thin_pack(proto.read, proto.recv, max_input_size=max_bytes)


def report_lines(capabilities: set[bytes], unpack: str, statuses: list[tuple[bytes, str]]) -> bytes:
    """The ``report-status`` body: ``unpack`` then one ``ok``/``ng`` line per ref, wrapped in side-band
    channel 1 when the client asked for side-band-64k."""
    payload = pkt_line(f"unpack {unpack}\n".encode()) if unpack else b""
    for ref, message in statuses:
        if message == "ok":
            payload += pkt_line(b"ok " + ref + b"\n")
        else:
            payload += pkt_line(b"ng " + ref + b" " + message.encode("utf-8") + b"\n")
    payload += b"0000"
    if b"side-band-64k" in capabilities:
        return _sideband(1, payload) + b"0000"
    return payload


def _sideband(channel: int, payload: bytes, chunk: int = 65515) -> bytes:
    out = b""
    for start in range(0, len(payload), chunk):
        out += pkt_line(bytes([channel]) + payload[start : start + chunk])
    return out


def progress_lines(capabilities: set[bytes], messages: list[str]) -> bytes:
    """Human messages for the client's terminal, on side-band channel 2 when it can show them."""
    if b"side-band-64k" not in capabilities or not messages:
        return b""
    text = "".join(f"remote: {message}\n" for message in messages).encode("utf-8")
    return _sideband(2, text)
