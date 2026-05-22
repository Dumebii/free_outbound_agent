from abc import ABC, abstractmethod


class EmailSender(ABC):
    """Abstract base class for all email sending backends."""

    @abstractmethod
    def send(self, to_email: str, to_name: str, subject: str, html_body: str) -> bool:
        """
        Send an email.

        Returns:
            True if sent successfully, False otherwise.
        """
        raise NotImplementedError
