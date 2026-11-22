from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from config import read_env, unquote


class ConfigTests(unittest.TestCase):
    def test_quotes_are_removed_without_interpreting_windows_backslashes(self):
        for quote in ("'", '"', ""):
            value = r"D:\LLM-AGENT\part1_handoff"
            self.assertEqual(unquote(quote + value + quote), value)

    def test_env_parser_preserves_literal_values_and_empty_defaults(self):
        with TemporaryDirectory() as folder:
            path = Path(folder) / ".env"
            path.write_text("\ufeff# config\nPART1_HANDOFF_PATH='D:/LLM-AGENT/part1_handoff'\n"
                            'PROGRAMME_MAP_PATH="programmes.discovered.json"\n'
                            "SEMESTER_START=''\nLLM_API_KEY='test=value$literal'\n", encoding="utf-8")
            values = read_env(path)
            self.assertEqual(values["PART1_HANDOFF_PATH"], "D:/LLM-AGENT/part1_handoff")
            self.assertEqual(values["PROGRAMME_MAP_PATH"], "programmes.discovered.json")
            self.assertEqual(values["SEMESTER_START"], "")
            self.assertEqual(values["LLM_API_KEY"], "test=value$literal")


if __name__ == "__main__":
    unittest.main()
