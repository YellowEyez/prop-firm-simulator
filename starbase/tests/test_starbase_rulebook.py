import unittest

from starbase_rulebook import filter_rows, flatten_rulebook, load_rulebook, product_details


class StarBaseRulebookTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = load_rulebook()
        cls.rows = flatten_rulebook(cls.data)

    def test_rulebook_loads_and_has_current_schema(self):
        self.assertEqual(self.data['schema_version'], '3.1.0')
        self.assertEqual(self.data['verified_as_of'], '2026-08-12')
        self.assertGreaterEqual(len(self.data['firms']), 7)

    def test_all_active_products_have_official_sources(self):
        for firm in self.data['firms']:
            for product in firm.get('products', []):
                if product['status'] == 'ACTIVE':
                    self.assertTrue(product.get('sources'))
                    self.assertTrue(product.get('verified_date'))

    def test_apex_eod_and_intraday_are_separate_products(self):
        eod = product_details(self.data, 'apex_eod')['product']
        intra = product_details(self.data, 'apex_intraday')['product']
        self.assertEqual(eod['account_sizes']['50000']['sim_funded']['drawdown_type'], 'EOD_TRAILING')
        self.assertEqual(intra['account_sizes']['50000']['sim_funded']['drawdown_type'], 'INTRADAY_TRAILING')

    def test_research_all_keeps_intraday_funded_products(self):
        cfg = self.data['policy_presets']['research_all']
        rows = filter_rows(self.rows, funded_drawdowns=cfg['allowed_funded_drawdowns'])
        self.assertTrue(any(r.funded_drawdown == 'INTRADAY_TRAILING' for r in rows))
        self.assertTrue(any(r.funded_drawdown == 'EOD_TRAILING' for r in rows))

    def test_eod_focus_filters_intraday_funded_products_without_deleting_them(self):
        cfg = self.data['policy_presets']['eod_funded_focus']
        rows = filter_rows(self.rows, funded_drawdowns=cfg['allowed_funded_drawdowns'])
        self.assertFalse(any(r.funded_drawdown == 'INTRADAY_TRAILING' for r in rows))
        all_rows = filter_rows(self.rows, funded_drawdowns=self.data['policy_presets']['research_all']['allowed_funded_drawdowns'])
        self.assertGreater(len(all_rows), len(rows))

    def test_lucid_daily_is_intraday_funded_but_eod_live(self):
        p = product_details(self.data, 'lucid_daily')['product']
        s = p['account_sizes']['50000']
        self.assertEqual(s['sim_funded']['drawdown_type'], 'INTRADAY_TRAILING')
        self.assertEqual(s['live']['drawdown_type'], 'EOD_TRAILING')

    def test_take_profit_trader_pro_and_proplus_are_classified_separately_by_stage(self):
        p = product_details(self.data, 'tpt_test_pro')['product']
        s = p['account_sizes']['50000']
        self.assertEqual(s['sim_funded']['drawdown_type'], 'INTRADAY_TRAILING')
        self.assertEqual(s['live']['drawdown_type'], 'EOD_TRAILING')
        self.assertEqual(p['verification_status'], 'VERIFIED_CURRENT_PARTIAL_AUTOMATION_2026_08_12')

    def test_mffu_rapid_remains_available_for_intraday_research(self):
        p = product_details(self.data, 'mffu_rapid_50k')['product']
        self.assertEqual(p['account_sizes']['50000']['sim_funded']['drawdown_type'], 'INTRADAY_TRAILING')
        self.assertEqual(p['status'], 'ACTIVE')

    def test_v3_does_not_replace_legacy_prop_firms_file(self):
        import pathlib
        self.assertTrue(pathlib.Path('prop_firms.json').exists())
        self.assertTrue(pathlib.Path('starbase_rules_v3.json').exists())


if __name__ == '__main__':
    unittest.main()
