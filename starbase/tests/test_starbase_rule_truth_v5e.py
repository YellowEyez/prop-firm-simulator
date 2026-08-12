import unittest
from datetime import date

from starbase_rulebook import filter_rows, flatten_rulebook, load_rulebook, product_details, rulebook_freshness
from starbase_rule_semantics import can_rank, stage_truth


class TestRuleTruthV5E(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rb = load_rulebook()
        cls.rows = flatten_rulebook(cls.rb)

    def test_rulebook_current_date_and_freshness(self):
        self.assertEqual(self.rb['verified_as_of'], '2026-08-12')
        f = rulebook_freshness(self.rb, as_of=date(2026, 8, 12))
        self.assertEqual(f['grade'], 'FRESH')
        self.assertEqual(f['age_days'], 0)

    def test_fundednext_flex_50k_current_contract_limit_is_three_minis(self):
        p = product_details(self.rb, 'fundednext_flex')['product']
        self.assertEqual(p['account_sizes']['50000']['evaluation']['max_minis'], 3)
        self.assertEqual(p['account_sizes']['50000']['sim_funded']['max_minis'], 3)
        payout = p['account_sizes']['50000']['sim_funded']['payout']
        self.assertEqual(payout['qualifying_days'], 5)
        self.assertEqual(payout['qualifying_day_profit'], 200)
        self.assertEqual(payout['maximum_payout'], 1500)
        self.assertEqual(payout['reward_share_variants']['STANDARD'], 80)
        self.assertEqual(payout['reward_share_variants']['CURRENT_PROMOTIONAL_NEW_PURCHASE'], 95)

    def test_tradeify_select_daily_is_separate_from_flex(self):
        flex = product_details(self.rb, 'tradeify_select_flex')['product']['account_sizes']['50000']['sim_funded']
        daily = product_details(self.rb, 'tradeify_select_daily')['product']['account_sizes']['50000']['sim_funded']
        self.assertIsNone(flex['dll']['amount'])
        self.assertEqual(daily['dll']['amount'], 1000)
        self.assertEqual(daily['payout']['buffer_amount'], 2100)
        self.assertEqual(daily['payout']['minimum_payout'], 250)
        self.assertFalse(can_rank(self.rb, 'tradeify_select_daily', 'sim_funded'))

    def test_topstep_standard_and_consistency_are_distinct_paths(self):
        std = product_details(self.rb, 'topstep_standard')['product']['account_sizes']['50000']['sim_funded']['payout']
        con = product_details(self.rb, 'topstep_consistency')['product']['account_sizes']['50000']['sim_funded']['payout']
        self.assertEqual(std['qualifying_days'], 5)
        self.assertEqual(std['qualifying_day_profit'], 150)
        self.assertEqual(con['qualifying_days'], 3)
        self.assertEqual(con['consistency_percent'], 40)
        self.assertEqual(con['maximum_payout'], 3000)
        self.assertFalse(can_rank(self.rb, 'topstep_consistency', 'sim_funded'))

    def test_consistency_filter_can_isolate_no_funded_consistency(self):
        rows = filter_rows(self.rows, funded_consistency=['NONE'])
        pids = {r.product_id for r in rows}
        self.assertIn('lucid_flex', pids)
        self.assertIn('tradeify_select_flex', pids)
        self.assertIn('fundednext_flex', pids)
        self.assertIn('mffu_flex_50k', pids)
        self.assertNotIn('lucid_direct', pids)
        self.assertNotIn('topstep_consistency', pids)

    def test_tpt_is_visible_but_not_rankable_for_funded(self):
        t = stage_truth(self.rb, 'tpt_test_pro', 'sim_funded')
        self.assertEqual(t['grade'], 'RESEARCH_ONLY')
        self.assertFalse(t['rankable'])
        self.assertTrue(t['unmodeled_reasons'])

    def test_lucid_daily_requires_variant_selection_for_eval(self):
        t = stage_truth(self.rb, 'lucid_daily', 'evaluation')
        self.assertEqual(t['grade'], 'VARIANT_SELECTION_REQUIRED')
        self.assertFalse(t['rankable'])

    def test_production_ready_core_stays_rankable(self):
        self.assertTrue(can_rank(self.rb, 'lucid_flex', 'sim_funded'))
        self.assertFalse(can_rank(self.rb, 'apex_eod', 'sim_funded'))
        self.assertEqual(stage_truth(self.rb, 'apex_eod', 'sim_funded')['grade'], 'RULES_VERIFIED_ENGINE_PENDING')
        self.assertFalse(can_rank(self.rb, 'fundednext_flex', 'sim_funded'))
        self.assertEqual(stage_truth(self.rb, 'fundednext_flex', 'sim_funded')['grade'], 'VARIANT_SELECTION_REQUIRED')

    def test_apex_eod_tiered_dll_is_encoded(self):
        fd = product_details(self.rb, 'apex_eod')['product']['account_sizes']['50000']['sim_funded']
        tiers = fd['scaling_tiers']
        self.assertEqual(tiers[0]['max_minis'], 2)
        self.assertEqual(tiers[0]['dll_amount'], 1000)
        self.assertEqual(tiers[-1]['max_minis'], 4)
        self.assertEqual(tiers[-1]['dll_amount'], 3000)


if __name__ == '__main__':
    unittest.main()
