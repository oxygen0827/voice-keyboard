"""Platform text I/O adapter for the Voice Keyboard Engine Input Environment."""

from dataclasses import dataclass
from typing import Protocol

from agent import typer


class TextIO(Protocol):
    def get_selection(self) -> str:
        ...

    def type_text(self, text: str) -> None:
        ...

    def jump_to_end(self) -> None:
        ...

    def replace_selection(self, text: str) -> None:
        ...

    def delete_selection(self) -> None:
        ...

    def erase_last(self, text: str) -> None:
        ...

    def list_shortcuts(self) -> list[str]:
        ...

    def send_shortcut(self, name: str) -> bool:
        ...


@dataclass(frozen=True)
class TyperTextIO:
    """Adapter that keeps platform typing details out of Input Environment rules."""

    def get_selection(self) -> str:
        return typer.get_selection()

    def type_text(self, text: str) -> None:
        typer.type_text(text)

    def jump_to_end(self) -> None:
        typer.jump_to_end()

    def replace_selection(self, text: str) -> None:
        typer.replace_selection(text)

    def delete_selection(self) -> None:
        typer.delete_selection()

    def erase_last(self, text: str) -> None:
        typer.erase_last(text)

    def list_shortcuts(self) -> list[str]:
        return typer.list_shortcuts()

    def send_shortcut(self, name: str) -> bool:
        return typer.send_shortcut(name)
