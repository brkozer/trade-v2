from decimal import ROUND_DOWN, Decimal

from pydantic import Field

from tradev2.domain.account import PortfolioRisk
from tradev2.domain.base import FrozenModel
from tradev2.domain.decisions import RiskDecision
from tradev2.domain.instruments import InstrumentRules
from tradev2.domain.orders import OrderIntent


class RiskLimits(FrozenModel):
    per_trade: Decimal = Field(gt=0)
    total_open: Decimal = Field(gt=0)
    directional_notional: Decimal = Field(gt=0)
    correlated_notional: Decimal = Field(gt=0)
    symbol_notional: Decimal | None = Field(default=None, gt=0)
    daily_loss: Decimal = Field(gt=0)
    equity_floor: Decimal = Field(ge=0)
    leverage: Decimal = Field(default=Decimal(1), ge=1)
    roundtrip_cost_rate: Decimal = Field(default=Decimal("0.002"), ge=0)


def assess(intent: OrderIntent, rules: InstrumentRules, portfolio: PortfolioRisk,
           limits: RiskLimits) -> RiskDecision:
    if intent.reduce_only:
        return RiskDecision(action="REJECT", reason="EXIT_REQUIRES_POSITION_CHECK")
    if not portfolio.reconciled or not portfolio.protection_healthy:
        return RiskDecision(action="HALT", reason="RECONCILIATION_OR_PROTECTION")
    if portfolio.equity is None or portfolio.available_margin is None or portfolio.daily_pnl is None:
        return RiskDecision(action="HALT", reason="ACCOUNT_UNKNOWN")
    if portfolio.equity <= limits.equity_floor or portfolio.daily_pnl <= -limits.daily_loss:
        return RiskDecision(action="HALT", reason="ACCOUNT_LIMIT")
    if intent.symbol != rules.symbol:
        return RiskDecision(action="REJECT", reason="INSTRUMENT_MISMATCH")
    distance = intent.reference_price - intent.stop_price
    if (intent.side == "Buy" and distance <= 0) or (intent.side == "Sell" and distance >= 0):
        return RiskDecision(action="REJECT", reason="STOP_DIRECTION")
    if intent.stop_price % rules.tick_size or intent.reference_price % rules.tick_size:
        return RiskDecision(action="REJECT", reason="PRICE_OFF_GRID")
    unit_risk = abs(distance) + intent.reference_price * limits.roundtrip_cost_rate
    budget = min(limits.per_trade, limits.total_open - portfolio.open_risk - portfolio.pending_risk)
    notional_cap = min(limits.directional_notional - portfolio.directional_notional,
                       limits.correlated_notional - portfolio.correlated_notional,
                       portfolio.available_margin * limits.leverage)
    if limits.symbol_notional is not None:
        notional_cap = min(notional_cap, limits.symbol_notional - portfolio.symbol_notional)
    raw = min(intent.quantity, budget / unit_risk, notional_cap / intent.reference_price)
    if rules.max_qty is not None:
        raw = min(raw, rules.max_qty)
    quantity = max(Decimal(0), (raw / rules.qty_step).to_integral_value(rounding=ROUND_DOWN) * rules.qty_step)
    notional = quantity * intent.reference_price
    if quantity < rules.min_qty or quantity <= 0 or notional < rules.min_notional:
        return RiskDecision(action="REJECT", reason="BELOW_MINIMUM_OR_BUDGET", risk=budget)
    return RiskDecision(action="ALLOW" if quantity == intent.quantity else "RESIZE",
                        reason="WITHIN_LIMITS", quantity=quantity,
                        risk=quantity * unit_risk, notional=notional)
