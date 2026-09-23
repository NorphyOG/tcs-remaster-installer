import unittest

from helpers import BASE
from recipe_overlays import PINNED, choose_overlay


def versions(modules, hashes=None):
    return [{'module': module, 'sha256': digest} for module, digest in zip(modules, hashes or ['a'*64]*len(modules))]


class RecipeOverlayTests(unittest.TestCase):
    def test_documented_author_model_order(self):
        pairs = [
            ('CHARS/ANAKIN/ANAKIN_JEDI_PC.GHG', ['modern-overhaul', 'infinities']),
            ('CHARS/BOBA/BODY.GSC', ['modern-overhaul', 'infinities', 'infinities']),
            ('CHARS/ANAKIN/ANAKIN_JEDI_ORDER66_PC.GHG', ['additional-levels-mo', 'infinities-al-patch']),
            ('CHARS/ANAKIN/ANAKIN_MUST_PC.GHG', ['ep3-additions', 'infinities-vader-patch']),
        ]
        for path, modules in pairs:
            with self.subTest(path=path):
                result = choose_overlay(path, versions(modules))
                self.assertEqual(result[0], len(modules)-1)
                self.assertIn('kein Binär-Merge', result[1])

    def test_unknown_binary_combination_remains_blocked(self):
        self.assertIsNone(choose_overlay('CHARS/BOBA/BODY.GHG', versions(['modern-overhaul', 'additional-levels-mo'])))
        self.assertIsNone(choose_overlay('LEVELS/EPISODE_III/ENDING/E3ENDING.GHG', versions(['modern-overhaul', 'infinities'])))
        self.assertIsNone(choose_overlay('CHARS/BOBA/BODY.TXT', versions(['modern-overhaul', 'infinities'])))

    def test_all_checked_text_and_script_rules_require_exact_bytes(self):
        self.assertEqual(len(PINNED), 10)
        for path, (modules, hashes, winner) in PINNED.items():
            with self.subTest(path=path):
                self.assertEqual(choose_overlay(path, versions(modules, hashes))[0], winner)
                changed = list(hashes)
                changed[-1] = '0'*64
                self.assertIsNone(choose_overlay(path, versions(modules, changed)))
                self.assertIsNone(choose_overlay(path, versions(tuple(reversed(modules)), hashes)))


if __name__ == '__main__':
    unittest.main()
