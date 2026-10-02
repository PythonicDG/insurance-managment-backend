"""Create a private local environment from the committed development defaults."""

import os
from pathlib import Path
import secrets


def configure_local(repository: Path) -> bool:
    target = repository / ".env"
    if target.exists():
        return False
    template = (repository / ".env.example").read_text(encoding="utf-8")
    content = template.replace("replace-with-generated-secret", secrets.token_urlsafe(64))
    descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as environment:
        environment.write(content)
    return True


if __name__ == "__main__":
    created = configure_local(Path(__file__).resolve().parent.parent)
    print("Created .env with local settings and a generated secret." if created else "Existing .env retained.")
