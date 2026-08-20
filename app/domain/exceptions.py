"""Domain exceptions that do not depend on application or infrastructure layers."""


class InvalidWorkflowTransitionError(Exception):
    """Raised when a workflow action cannot move to the requested status."""

    def __init__(self) -> None:
        self.message = "Invalid workflow state transition."
        super().__init__(self.message)
