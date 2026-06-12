"""Pluggable object storage (spec 14): local filesystem and S3-compatible."""

from inkstave.storage.base import ObjectNotFoundError, ObjectStat, ObjectStore

__all__ = ["ObjectNotFoundError", "ObjectStat", "ObjectStore"]
