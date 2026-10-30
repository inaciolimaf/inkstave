"""Inkstave's server-side AI writing agent (spec 41+).

A LangGraph state machine driven by a dependency-injected LLM client. The agent
never modifies project documents directly — from spec 43 it proposes per-file diffs
the user reviews. This package's spec-41 scope is the runnable no-tool scaffold.
"""
