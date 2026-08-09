import os
import tempfile
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class FilesystemObjectStorageProbe:
    path: Path
    name: str = "object_storage"

    def prepare(self) -> None:
        self.path.mkdir(parents=True, exist_ok=True)

    async def check(self) -> bool:
        if not self.path.is_dir() or not os.access(self.path, os.R_OK | os.W_OK):
            return False
        try:
            with tempfile.NamedTemporaryFile(dir=self.path, prefix=".health-", delete=True):
                pass
        except OSError:
            return False
        return True
