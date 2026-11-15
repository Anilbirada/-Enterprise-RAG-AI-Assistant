import logging
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Union

logger = logging.getLogger("enterprise_rag.antivirus")


class AntivirusScanner(ABC):
    """Abstract interface for optional malware / antivirus scanning integration."""

    @abstractmethod
    async def scan_file(self, file_path: Union[str, Path]) -> bool:
        """Scans a staged file for malware.
        
        Returns:
            True if file is clean, False if threat is detected.
        """
        pass


class NoOpAntivirusScanner(AntivirusScanner):
    """Default no-op scanner for development and environments without daemon scanner."""

    async def scan_file(self, file_path: Union[str, Path]) -> bool:
        logger.debug(f"Antivirus scan skipped (NoOpAntivirusScanner active) for '{file_path}'")
        return True


def get_antivirus_scanner() -> AntivirusScanner:
    """Dependency / Factory providing the configured AntivirusScanner."""
    # Future integration: return ClamAVScanner(host, port) when enabled in settings
    return NoOpAntivirusScanner()
