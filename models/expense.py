from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class Expense:
    amount: float
    category: str
    description: str
    date: str = field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d"))
    source: str = "text"

    def to_row(self) -> list:
        return [self.date, self.amount, self.category, self.description, self.source]

    @classmethod
    def from_dict(cls, data: dict, source: str = "text") -> "Expense":
        return cls(
            amount=float(data["amount"]),
            category=data.get("category", "Other"),
            description=data.get("description", ""),
            date=data.get("date", datetime.now().strftime("%Y-%m-%d")),
            source=source,
        )
