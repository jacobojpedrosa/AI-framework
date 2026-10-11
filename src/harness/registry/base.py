from collections.abc import Iterable
from typing import Literal

from pydantic import Field

from harness.config.models import StrictModel
from harness.errors import RegistryError

Status = Literal["planned", "experimental", "supported", "deprecated"]


class Descriptor(StrictModel):
    id: str = Field(pattern=r"^[a-z][a-z0-9]*(?:[.-][a-z0-9]+)*$")
    status: Status = "planned"
    requires: tuple[str, ...] = ()
    conflicts: tuple[str, ...] = ()


class Registry[T: Descriptor]:
    def __init__(self, entries: Iterable[T] = ()):
        self._entries: dict[str, T] = {}
        for entry in entries:
            self.register(entry)

    def register(self, entry: T) -> None:
        if entry.id in self._entries:
            raise RegistryError("Duplicate registry identifier")
        self._entries[entry.id] = entry

    def get(self, identifier: str) -> T:
        try:
            return self._entries[identifier]
        except KeyError:
            raise RegistryError("Unknown registry identifier") from None

    def entries(self) -> tuple[T, ...]:
        return tuple(self._entries[key] for key in sorted(self._entries))

    def validate(self) -> None:
        for entry in self.entries():
            references = (*entry.requires, *entry.conflicts)
            if any(ref not in self._entries for ref in references):
                raise RegistryError("Unknown metadata reference")
            if entry.id in references:
                raise RegistryError("Self-referencing registry entry")
            if set(entry.requires) & set(entry.conflicts):
                raise RegistryError("A requirement cannot also be a conflict")
            if len(set(entry.requires)) != len(entry.requires):
                raise RegistryError("Duplicate requirement")
            if len(set(entry.conflicts)) != len(entry.conflicts):
                raise RegistryError("Duplicate conflict")
        visited: set[str] = set()
        visiting: set[str] = set()

        def visit(identifier: str) -> None:
            if identifier in visiting:
                raise RegistryError("Cyclic registry requirements")
            if identifier in visited:
                return
            visiting.add(identifier)
            for dependency in self.get(identifier).requires:
                visit(dependency)
            visiting.remove(identifier)
            visited.add(identifier)

        for identifier in self._entries:
            visit(identifier)
