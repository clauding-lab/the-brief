from datetime import date, datetime, timezone

from brief.builders import BuilderContext
from brief.builders.fiscal import build
from brief.econdelta import EconDeltaSnapshot
from brief.history import HistoryRow


def test_bank_borrowing_card_reads_bank_only_series():
    class History:
        def get_latest(self, mid):
            values = {"fiscal_bank_borrow_trn": -1.20, "fiscal_govt_borrow_trn": 1.80}
            return HistoryRow(mid, date(2026, 6, 30), values[mid], "BB") if mid in values else None
    ctx = BuilderContext(EconDeltaSnapshot(datetime(2026, 9, 25, tzinfo=timezone.utc), {}, {}),
                         History(), date(2026, 9, 25))
    card = next(m for m in build(ctx).metrics if m.id == "fiscal_govt_borrow_trn")
    assert card.label == "Govt bank borrow YTD"
    assert card.value == -1.20
    assert card.as_of == date(2026, 6, 30)
