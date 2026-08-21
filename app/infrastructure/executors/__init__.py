"""Communication action executor adapters. Write SDKs stay inside adapter packages."""

from app.infrastructure.executors.fake import FakeCommunicationActionExecutor

__all__ = ["FakeCommunicationActionExecutor"]
