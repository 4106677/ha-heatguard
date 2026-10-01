"""Verify translated entity coverage and placeholder compatibility."""
import ast
import json
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1] / 'custom_components' / 'heatguard'

def leaves(value, prefix=''):
    if isinstance(value, dict):
        return {key: text for name, child in value.items()
                for key, text in leaves(child, f'{prefix}.{name}').items()}
    return {prefix: value}

class TranslationTests(unittest.TestCase):
    def test_languages_have_matching_keys_and_placeholders(self):
        source = json.loads((ROOT / 'strings.json').read_text())
        expected = leaves(source)
        for language in ('en', 'ru', 'uk'):
            with self.subTest(language=language):
                actual = leaves(json.loads((ROOT / 'translations' / f'{language}.json').read_text()))
                self.assertEqual(actual.keys(), expected.keys())
                for key, text in actual.items():
                    self.assertTrue(text.strip(), key)
                    self.assertEqual(re.findall(r'\{\w+\}', text),
                                     re.findall(r'\{\w+\}', expected[key]), key)
        self.assertEqual(source, json.loads((ROOT / 'translations/en.json').read_text()))

    def test_all_sensor_keys_have_translations(self):
        tree = ast.parse((ROOT / 'sensor.py').read_text())
        # Sensor enum references are intentionally not evaluated.
        specs = next(node.value.elts for node in tree.body if isinstance(node, ast.Assign)
                     and any(isinstance(t, ast.Name) and t.id == 'SENSORS' for t in node.targets))
        keys = {spec.elts[1].value for spec in specs}
        source = json.loads((ROOT / 'strings.json').read_text())
        self.assertEqual(keys, source['entity']['sensor'].keys())
        self.assertIn('coolant', source['entity']['climate'])
