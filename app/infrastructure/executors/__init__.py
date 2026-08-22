"""Communication action executor adapters. Write SDKs stay inside adapter packages."""

from app.infrastructure.executors.factory import ProviderCommunicationActionExecutorFactory
from app.infrastructure.executors.fake import FakeCommunicationActionExecutor
from app.infrastructure.executors.gmail import GmailCommunicationActionExecutor
from app.infrastructure.executors.microsoft_graph import MicrosoftGraphCommunicationActionExecutor

__all__ = [
    "FakeCommunicationActionExecutor",
    "GmailCommunicationActionExecutor",
    "MicrosoftGraphCommunicationActionExecutor",
    "ProviderCommunicationActionExecutorFactory",
]
