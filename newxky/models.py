from dataclasses import dataclass, field


@dataclass(frozen=True)
class Question:
    number: int
    kind: str
    stem: str
    options: dict[str, str]
    answers: tuple[str, ...]
    pages: tuple[int, ...]
    source: str = ""


@dataclass
class Bank:
    questions: list[Question] = field(default_factory=list)
    issues: list[str] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)
    page_count: int = 0
    duplicates: int = 0
