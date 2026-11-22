"""Integration tests for the complete offline event/highlight analysis command."""

import copy
import io
import unittest
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path
from unittest.mock import patch

import preview_match_analysis as command
from match_service import summarize_plan
from validate_match_schema import ValidationError, validate_match


class MatchAnalysisPreviewTests(unittest.TestCase):
    def setUp(self):
        for guard in (
            patch("urllib.request.OpenerDirector.open", side_effect=AssertionError("No network allowed")),
            patch("firebase_admin.initialize_app", side_effect=AssertionError("No credentials allowed")),
            patch("firebase_admin.firestore.client", side_effect=AssertionError("No database allowed")),
        ):
            guard.start()
            self.addCleanup(guard.stop)

    def test_complete_offline_command_never_opens_files_for_writing(self):
        real_open = Path.open
        def read_only_open(path, mode="r", *args, **kwargs):
            self.assertFalse(any(flag in mode for flag in "wax+"))
            return real_open(path, mode, *args, **kwargs)
        output = io.StringIO()
        with patch.object(Path, "open", read_only_open), patch.dict("os.environ", {}, clear=True), redirect_stdout(output):
            self.assertEqual(command.main([]), 0)
        text = output.getvalue()
        for message in ("FICTIONAL DEMONSTRATION", "Playback eligible: False", "Match clock: unknown",
                        "Simulated CREATE", "Simulated UPDATE", "Simulated NO CHANGE", command.MESSAGE):
            self.assertIn(message, text)
        self.assertIn("events: CREATE 2", text)
        self.assertIn("highlights: CREATE 1", text)

    def test_all_three_states_cover_matches_events_highlights_without_mutation(self):
        prepared, teams, catalog = command.load_demo_analysis()
        original = copy.deepcopy((prepared, teams, catalog))
        validate_match(prepared["match"])
        self.assertTrue(prepared["match"]["isDemo"])
        for operation in ("CREATE", "UPDATE", "NO CHANGE"):
            plans = command.simulate_analysis(prepared, teams, catalog, operation)
            for collection, count in (("matches", 1), ("events", 2), ("highlights", 1)):
                self.assertEqual(summarize_plan(plans[collection])[operation], count)
            self.assertEqual((prepared, teams, catalog), original)

    def test_bad_simulation_operation_is_rejected(self):
        prepared, teams, catalog = command.load_demo_analysis()
        with self.assertRaises(ValidationError):
            command.simulate_analysis(prepared, teams, catalog, "APPLY")

    def test_file_errors_fail_with_offline_message(self):
        for error in (FileNotFoundError(), PermissionError(), ValueError()):
            output = io.StringIO()
            with self.subTest(error=type(error).__name__), patch.object(command, "load_demo_analysis", side_effect=error), \
                 redirect_stdout(output):
                self.assertEqual(command.main([]), 1)
            self.assertIn("FAILED", output.getvalue())
            self.assertIn(command.MESSAGE, output.getvalue())

    def test_demo_loader_rejects_unmarked_or_duplicate_examples(self):
        for raw in ('{"matches": []}', '{"matches": [{"matchId":"demo_regular_001","isDemo":false}]}',
                    '{"matches":[],"matches":[]}', '{"matches":[null]}', '[]'):
            with self.subTest(raw=raw), patch.object(Path, "open", return_value=io.StringIO(raw)), \
                 self.assertRaises(ValidationError):
                command.load_demo_analysis()

    def test_write_live_or_output_flags_do_not_exist(self):
        for argv in (["--apply"], ["--live"], ["--output", "unwanted.json"]):
            with self.subTest(argv=argv), redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as context:
                command.main(argv)
            self.assertEqual(context.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
