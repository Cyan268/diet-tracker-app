import asyncio
import os
from pathlib import Path, PurePosixPath
from uuid import uuid4


class UploadStorageError(RuntimeError):
    pass


class UploadObjectNotFoundError(UploadStorageError):
    pass


class LocalPrivateUploadStore:
    """Private filesystem object store with generated keys and atomic writes."""

    def __init__(self, root: Path):
        self.root = root.resolve()

    def _path(self, object_key: str) -> Path:
        key = PurePosixPath(object_key)
        if key.is_absolute() or ".." in key.parts or not key.parts:
            raise UploadStorageError("invalid object key")
        target = self.root.joinpath(*key.parts).resolve()
        if target != self.root and self.root not in target.parents:
            raise UploadStorageError("invalid object key")
        return target

    async def write_staging(self, object_key: str, content: bytes) -> None:
        await asyncio.to_thread(self._write_atomic, self._path(object_key), content, False)

    async def read(self, object_key: str) -> bytes:
        def read_bytes() -> bytes:
            try:
                return self._path(object_key).read_bytes()
            except FileNotFoundError as error:
                raise UploadObjectNotFoundError("upload object is unavailable") from error
            except OSError as error:
                raise UploadStorageError("upload object cannot be read") from error

        return await asyncio.to_thread(read_bytes)

    async def seal(self, object_key: str, content: bytes) -> None:
        await asyncio.to_thread(self._write_atomic, self._path(object_key), content, True)

    async def delete(self, object_key: str | None) -> None:
        if object_key is None:
            return

        def unlink() -> None:
            try:
                self._path(object_key).unlink(missing_ok=True)
            except OSError as error:
                raise UploadStorageError("upload object cannot be deleted") from error

        await asyncio.to_thread(unlink)

    @staticmethod
    def _write_atomic(target: Path, content: bytes, exclusive: bool) -> None:
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_name(f".{target.name}.{uuid4().hex}.tmp")
        try:
            temporary.write_bytes(content)
            if exclusive and target.exists():
                raise UploadStorageError("sealed upload already exists")
            os.replace(temporary, target)
        except UploadStorageError:
            raise
        except OSError as error:
            raise UploadStorageError("upload object cannot be written") from error
        finally:
            temporary.unlink(missing_ok=True)
