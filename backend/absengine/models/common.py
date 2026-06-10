from enum import Enum


class DayCount(str, Enum):
    THIRTY_360 = "30/360"
    ACT_360 = "ACT/360"  # Phase 2
    ACT_365 = "ACT/365"  # Phase 2


class Frequency(str, Enum):
    MONTHLY = "monthly"


class AmortType(str, Enum):
    LEVEL_PAY = "level_pay"


class PoolBalanceBasis(str, Enum):
    """Which pool balance a fee / PDA / trigger references.

    trust      = performing + defaulted-not-yet-charged-off
    performing = net of all defaults
    adjusted   = basis balance minus YSOA (Phase 2)
    """

    TRUST = "trust"
    PERFORMING = "performing"
    ADJUSTED = "adjusted"
