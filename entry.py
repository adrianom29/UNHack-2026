from dataclasses import dataclass, asdict


@dataclass
class Entry:
    """One day of sales data for a single product."""

    sold: int        # units sold that day
    produced: int    # units produced / prepared that day
    cost: float      # cost to make one unit
    price: float     # price one unit sells for

    def __post_init__(self):
        if self.produced < 1:
            raise ValueError("Produced must be at least 1")
        if self.sold < 0:
            raise ValueError("Sold cannot be negative")
        if self.sold > self.produced:
            raise ValueError("Sold cannot exceed produced")
        if self.cost < 0 or self.price < 0:
            raise ValueError("Cost and price cannot be negative")

    @property
    def wasted(self) -> int:
        return self.produced - self.sold

    @property
    def sold_out(self) -> bool:
        return self.sold == self.produced

    @property
    def profit(self) -> float:
        return self.sold * self.price - self.produced * self.cost

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Entry":
        return cls(
            sold=int(data["sold"]),
            produced=int(data["produced"]),
            cost=float(data["cost"]),
            price=float(data["price"]),
        )
