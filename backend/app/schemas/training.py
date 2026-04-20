from pydantic import BaseModel, Field


class TrainingJobStartRequest(BaseModel):
    model_type: str = Field(default="ml")
    template_id: str | None = Field(default=None)
    symbols: list[str] = Field(default_factory=lambda: ["AAPL", "MSFT", "NVDA", "SPY"])
    start_date: str = Field(default="2020-01-01")
    end_date: str = Field(default="2026-04-02")
    horizon_days: int = Field(default=5)
    buy_threshold: float = Field(default=0.02)
    sell_threshold: float = Field(default=-0.02)
    run_optuna: bool = Field(default=False)
    trial_count: int = Field(default=10)
    sequence_length: int = Field(default=20)
    epochs: int = Field(default=8)
    hidden_size: int = Field(default=48)
    learning_rate: float = Field(default=0.001)


class PaperOrderCreateRequest(BaseModel):
    symbol: str = Field(default="AAPL")
    side: str = Field(default="BUY")
    quantity: float = Field(default=1.0)
    order_type: str = Field(default="market")
    limit_price: float | None = Field(default=None)
    strategy_mode: str | None = Field(default="manual")
    notes: str | None = Field(default=None)
    client_order_id: str | None = Field(
        default=None,
        description=(
            "Optional caller-supplied idempotency key. "
            "If an order with this ID already exists it is returned as-is "
            "without creating a duplicate."
        ),
    )
