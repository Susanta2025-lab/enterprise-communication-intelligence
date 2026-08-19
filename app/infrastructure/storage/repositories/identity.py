"""SQLAlchemy IdentityRepository implementation."""

from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.exceptions import PersistenceError
from app.domain.interfaces.identity_repository import IdentityRepository
from app.infrastructure.storage.models import ExternalIdentity, User

_EXTERNAL_IDENTITY_UNIQUE = "uq_external_identities_issuer_subject"


class SqlAlchemyIdentityRepository(IdentityRepository):
    """Persist OIDC issuer+subject mappings without exposing ORM types."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def get_user_id_by_external_identity(self, issuer: str, subject: str) -> UUID | None:
        """Return the internal user id for ``(issuer, subject)``, if one exists."""
        statement = select(ExternalIdentity.user_id).where(
            ExternalIdentity.issuer == issuer,
            ExternalIdentity.subject == subject,
        )
        return self._session.scalars(statement).first()

    def create_user_with_external_identity(self, issuer: str, subject: str) -> UUID:
        """Create a user and unique external identity mapping."""
        existing = self.get_user_id_by_external_identity(issuer, subject)
        if existing is not None:
            raise PersistenceError("External identity is already registered.")

        user = User(id=uuid4())
        identity = ExternalIdentity(
            id=uuid4(),
            user_id=user.id,
            issuer=issuer,
            subject=subject,
        )
        try:
            with self._session.begin_nested():
                self._session.add(user)
                self._session.add(identity)
                self._session.flush()
        except IntegrityError as exc:
            if _is_external_identity_unique_violation(exc):
                raise PersistenceError("External identity is already registered.") from exc
            raise PersistenceError("Could not persist identity.") from exc
        return user.id


def _constraint_name(exc: IntegrityError) -> str | None:
    """Return a driver constraint name when one is available (psycopg ``diag``)."""
    orig = exc.orig
    if orig is None:
        return None
    diag = getattr(orig, "diag", None)
    name = getattr(diag, "constraint_name", None)
    if isinstance(name, str) and name:
        return name
    return None


def _is_external_identity_unique_violation(exc: IntegrityError) -> bool:
    """Return True only for the issuer+subject uniqueness constraint.

    PostgreSQL/psycopg exposes ``diag.constraint_name``. SQLite reports
    ``UNIQUE constraint failed: external_identities.issuer, external_identities.subject``.
    Unrelated integrity failures must not be classified as duplicates.
    """
    if _constraint_name(exc) == _EXTERNAL_IDENTITY_UNIQUE:
        return True
    orig = exc.orig
    diagnostic = str(orig) if orig is not None else ""
    if _EXTERNAL_IDENTITY_UNIQUE in diagnostic:
        return True
    lowered = diagnostic.lower()
    return (
        "unique constraint failed" in lowered
        and "external_identities.issuer" in lowered
        and "external_identities.subject" in lowered
    )
