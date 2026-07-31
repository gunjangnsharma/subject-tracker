"""Repository layer: the only place that talks to the ORM/session.

Services depend on these narrow classes rather than on SQLAlchemy directly,
keeping data access swappable and business logic DB-agnostic.
"""
