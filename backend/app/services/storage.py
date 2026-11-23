"""File storage abstraction.

Application code talks only to `StorageBackend` (save / open / delete by opaque key). `LocalStorage`
keeps files under UPLOAD_FOLDER (a Docker volume). An S3-compatible backend can implement the same
three methods and be selected with STORAGE_BACKEND, without touching any service or route.
"""
import os
import shutil

from flask import current_app


class StorageBackend:
    def save(self, key, stream):
        raise NotImplementedError

    def open(self, key):
        raise NotImplementedError

    def delete(self, key):
        raise NotImplementedError


class LocalStorage(StorageBackend):
    def __init__(self, root):
        self.root = os.path.realpath(root)

    def _path(self, key):
        """Resolve a key inside the root; refuse anything that escapes it (directory traversal)."""
        path = os.path.realpath(os.path.join(self.root, key))
        if os.path.commonpath([self.root, path]) != self.root or path == self.root:
            raise ValueError("Invalid storage key")
        return path

    def save(self, key, stream):
        path = self._path(key)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as out:
            shutil.copyfileobj(stream, out)

    def open(self, key):
        return open(self._path(key), "rb")

    def delete(self, key):
        try:
            os.remove(self._path(key))
        except FileNotFoundError:
            pass


def get_storage():
    backend = current_app.config.get("STORAGE_BACKEND", "local")
    if backend == "local":
        return LocalStorage(current_app.config["UPLOAD_FOLDER"])
    raise RuntimeError(f"Unsupported STORAGE_BACKEND '{backend}'")
