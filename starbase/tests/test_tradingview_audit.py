import io
import unittest
import pandas as pd

from tradingview_audit import AuditPolicy, audit_tradingview_files

COLS = [
    'Trade number','Type','Date and time','Signal','Price USD','Size (qty)','Size (value)',
    'Net PnL USD','Return %','Commission USD','Favorable excursion USD','Favorable excursion %',
    'Adverse excursion USD','Adverse excursion %','Cumulative PnL USD','Cumulative PnL %','Duration (bars)'
]


def make_trade(tn, entry_time, exit_time, direction='long', entry_price=20000, exit_price=20010,
               qty=1, net=200, commission=0, mfe=220, mae=-40, bars=10,
               entry_signal='Entry', exit_signal='Exit'):
    etype = 'Entry long' if direction == 'long' else 'Entry short'
    xtype = 'Exit long' if direction == 'long' else 'Exit short'
    common = dict(**{
        'Trade number': tn, 'Price USD': entry_price, 'Size (qty)': qty, 'Size (value)': 0,
        'Net PnL USD': net, 'Return %': 0, 'Commission USD': commission,
        'Favorable excursion USD': mfe, 'Favorable excursion %': 0,
        'Adverse excursion USD': mae, 'Adverse excursion %': 0,
        'Cumulative PnL USD': net, 'Cumulative PnL %': 0, 'Duration (bars)': bars,
    })
    entry = dict(common); entry.update({'Type':etype,'Date and time':entry_time,'Signal':entry_signal,'Price USD':entry_price})
    exitr = dict(common); exitr.update({'Type':xtype,'Date and time':exit_time,'Signal':exit_signal,'Price USD':exit_price})
    return [exitr, entry]


def csv_bytes(rows):
    df=pd.DataFrame(rows, columns=COLS)
    return io.BytesIO(df.to_csv(index=False).encode())


class TradingViewAuditTests(unittest.TestCase):
    def audit(self, rows, **kwargs):
        pol=AuditPolicy(**kwargs)
        return audit_tradingview_files([csv_bytes(rows)], strategy_id='Test', profile_id='1NQ', policy=pol)

    def test_cross_6pm_session_rejected(self):
        r=self.audit(make_trade(1,'2026-08-10 17:55:00','2026-08-10 18:05:00'))
        row=r.ledger.iloc[0]
        self.assertEqual(row.validity_status,'INVALID')
        self.assertIn('entry_in_16_18_et_forbidden_window',row.validity_reason)
        self.assertIn('crossed_next_18_et_futures_session',row.validity_reason)

    def test_forbidden_window_rejected(self):
        r=self.audit(make_trade(1,'2026-08-10 16:30:00','2026-08-10 16:40:00'))
        self.assertIn('entry_in_16_18_et_forbidden_window',r.ledger.iloc[0].validity_reason)

    def test_hold_review_and_reject(self):
        rows=[]
        rows += make_trade(1,'2026-08-10 10:00:00','2026-08-10 11:15:00',bars=450)
        rows += make_trade(2,'2026-08-10 12:00:00','2026-08-10 14:01:00',bars=726)
        r=self.audit(rows)
        a=r.ledger.iloc[0]; b=r.ledger.iloc[1]
        self.assertEqual(a.validity_status,'REVIEW')
        self.assertIn('hold_1_to_2_hours',a.review_status)
        self.assertEqual(b.validity_status,'INVALID')
        self.assertIn('hold_over_2_hours',b.validity_reason)

    def test_same_source_rapid_reentry_survives(self):
        rows=[]
        rows += make_trade(1,'2026-08-10 10:00:00','2026-08-10 10:00:20',bars=2)
        rows += make_trade(2,'2026-08-10 10:00:30','2026-08-10 10:00:50',bars=2)
        r=self.audit(rows)
        self.assertEqual((r.ledger.validity_status=='VALID').sum(),2)
        self.assertEqual(r.summary['exact_duplicate_count'],0)

    def test_exact_overlap_duplicate_across_files_rejected(self):
        rows=make_trade(1,'2026-08-10 10:00:00','2026-08-10 10:01:00',bars=6)
        r=audit_tradingview_files([csv_bytes(rows),csv_bytes(rows)],strategy_id='Test',profile_id='1NQ')
        self.assertEqual(r.summary['exact_duplicate_count'],1)
        self.assertEqual((r.ledger.validity_status=='INVALID').sum(),1)
        self.assertIn('exact_overlap_duplicate',r.ledger.iloc[1].validity_reason)

    def test_commission_reversed_to_normalized_gross(self):
        rows=make_trade(1,'2026-08-10 10:00:00','2026-08-10 10:01:00',net=188,commission=12,bars=6)
        r=self.audit(rows)
        row=r.ledger.iloc[0]
        self.assertAlmostEqual(row.exported_net_pnl,188)
        self.assertAlmostEqual(row.normalized_gross_pnl,200)
        self.assertAlmostEqual(row.firm_commission_pnl,0)

    def test_pnl_math_mismatch_is_warning_not_quarantine(self):
        rows=make_trade(1,'2026-08-10 10:00:00','2026-08-10 10:01:00',entry_price=20000,exit_price=20010,qty=2,net=100,commission=0,bars=6)
        r=self.audit(rows)
        row=r.ledger.iloc[0]
        self.assertEqual(row.validity_status,'VALID')
        self.assertIn('pnl_price_math_mismatch',row.audit_warnings)
        self.assertEqual(r.summary['warning_trades'],1)

    def test_open_pseudo_trade_rejected(self):
        rows=make_trade(1,'2026-08-10 10:00:00','2026-08-10 10:01:00',exit_signal='Open',bars=6)
        r=self.audit(rows)
        self.assertIn('backtest_end_open_pseudo_trade',r.ledger.iloc[0].validity_reason)

    def test_session_id_before_6pm_uses_prior_date(self):
        rows=make_trade(1,'2026-08-10 05:00:00','2026-08-10 05:01:00',bars=6)
        r=self.audit(rows)
        self.assertEqual(r.ledger.iloc[0].futures_session_id,'2026-08-09')

if __name__ == '__main__':
    unittest.main()
