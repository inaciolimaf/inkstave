"""Test-fixture plugin modules (spec 04 / refactor).

The shared pytest fixtures that used to live in a single oversized
``tests/conftest.py`` are split here by domain. The root ``tests/conftest.py``
registers them with ``pytest_plugins`` so every fixture remains available to all
tests by the same name, scope, and autouse behaviour.
"""
