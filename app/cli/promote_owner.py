"""Promote an existing ECI user to the first platform owner.

Usage:

    python -m app.cli.promote_owner --user-id <uuid>

Requires ``DATABASE_URL``. Targets an existing internal ``users.id`` only.
Does not create users. Does not accept email, JWT roles, or mailbox identity.
Does not embed or require real owner ``(iss, sub)`` values in source.

Why ``--user-id``:
    Operators verify External ID sign-in separately, then resolve the opaque
    ``users.id`` from ``external_identities`` outside this command. Passing the
    UUID avoids putting durable ``(iss, sub)`` values into shell history.
"""

from __future__ import annotations

import argparse
import sys
from uuid import UUID

from app.application.exceptions import (
    OwnerAlreadyExistsError,
    OwnerBootstrapConflictError,
    OwnerBootstrapExternalIdentityRequiredError,
    OwnerBootstrapTargetNotFoundError,
)
from app.application.services.owner_bootstrap import (
    FirstOwnerBootstrapResult,
    FirstOwnerBootstrapService,
)
from app.core.config import get_settings
from app.core.exceptions import ServiceUnavailableError
from app.core.logging import configure_logging
from app.infrastructure.storage.runtime import (
    dispose_persistence_runtime,
    get_unit_of_work_factory,
)


def build_parser() -> argparse.ArgumentParser:
    """Return the promote-owner argument parser."""
    parser = argparse.ArgumentParser(
        prog="python -m app.cli.promote_owner",
        description=(
            "Promote an existing ECI user to the first platform owner. "
            "Identify the target by internal users.id only."
        ),
    )
    parser.add_argument(
        "--user-id",
        required=True,
        help="Existing internal users.id UUID to promote (not email, not iss/sub).",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run first-owner bootstrap and return a process exit code."""
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        user_id = UUID(args.user_id)
    except ValueError:
        print("error: --user-id must be a UUID", file=sys.stderr)
        return 2

    get_settings.cache_clear()
    settings = get_settings()
    configure_logging(settings.log_level, settings.app_env)
    if not settings.database_url:
        print("error: DATABASE_URL is required", file=sys.stderr)
        return 2

    service = FirstOwnerBootstrapService(get_unit_of_work_factory(settings.database_url))
    try:
        result = service.promote_first_owner(user_id)
    except OwnerBootstrapTargetNotFoundError as exc:
        print(f"error: {exc.message}", file=sys.stderr)
        return 1
    except OwnerBootstrapExternalIdentityRequiredError as exc:
        print(f"error: {exc.message}", file=sys.stderr)
        return 1
    except OwnerAlreadyExistsError as exc:
        print(f"error: {exc.message}", file=sys.stderr)
        return 1
    except OwnerBootstrapConflictError as exc:
        print(f"error: {exc.message}", file=sys.stderr)
        return 1
    except ServiceUnavailableError as exc:
        print(f"error: {exc.message}", file=sys.stderr)
        return 1
    finally:
        dispose_persistence_runtime()

    if result is FirstOwnerBootstrapResult.PROMOTED:
        print(f"promoted user_id={user_id} application_role=owner")
        return 0
    print(f"already_owner user_id={user_id} application_role=owner")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
