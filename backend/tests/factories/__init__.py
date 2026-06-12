"""Test data factories.

Convention (followed by every feature spec): a factory is a small class with a
monotonic sequence for unique defaults and two classmethods —

* ``build(**kwargs)`` returns an unsaved model instance, and
* ``await create(session, **kwargs)`` adds it to the given ``AsyncSession`` and
  flushes (so the row exists within the test's rolled-back transaction).

Keep factories dependency-light and async-explicit (no factory_boy magic).
"""

from tests.factories.ping import PingFactory
from tests.factories.user import UserFactory

__all__ = ["PingFactory", "UserFactory"]
