MAGIC_PREFIXES = {
    "image/jpeg": (b"\xff\xd8\xff",),
    "image/png": (b"\x89PNG\r\n\x1a\n",),
    "application/pdf": (b"%PDF",),
}


def scan_receipt(content: bytes, content_type: str) -> str:
    """Local malware-scan stand-in: type, emptiness, and magic-byte checks."""
    if not content:
        raise ValueError("The uploaded file is empty")
    prefixes = MAGIC_PREFIXES.get(content_type)
    if not prefixes:
        raise ValueError("Unsupported content type")
    if not any(content.startswith(prefix) for prefix in prefixes):
        raise ValueError("File content does not match the declared type")
    if b"%!PS" in content[:1024] and content_type != "application/pdf":
        raise ValueError("Suspicious file content")
    return "clean"
