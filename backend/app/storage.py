from pathlib import Path


class ObjectStorage:
    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def put(self, organization_id: str, receipt_id: str, filename: str, content: bytes) -> str:
        safe_name = Path(filename).name or "receipt"
        relative = Path(organization_id) / receipt_id / safe_name
        destination = (self.root / relative).resolve()
        if not str(destination).startswith(str(self.root.resolve())):
            raise ValueError("Object key escaped the storage root")
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(content)
        return relative.as_posix()

    def get(self, object_key: str) -> bytes:
        path = self._resolve(object_key)
        return path.read_bytes()

    def exists(self, object_key: str) -> bool:
        return self._resolve(object_key).is_file()

    def _resolve(self, object_key: str) -> Path:
        destination = (self.root / object_key).resolve()
        if not str(destination).startswith(str(self.root.resolve())):
            raise ValueError("Object key escaped the storage root")
        return destination
