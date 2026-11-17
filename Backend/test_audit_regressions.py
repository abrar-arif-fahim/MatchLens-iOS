"""Offline regressions found during the repository audit. Never access real services."""

import copy
import importlib.util
import io
import json
import unittest
from contextlib import redirect_stdout
from http.client import RemoteDisconnected
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import api_football_players as profiles
import import_multiple_players
import import_players
import import_team
import preview_multiple_teams
import prepare_multiple_teams
import prepare_team_data
import discover_team_ids
import prepare_player_data
from google.api_core.exceptions import Aborted
from prepare_player_data import PlayerDataError, wikidata_birth_date


BACKEND = Path(__file__).resolve().parent


class AuditRegressionTests(unittest.TestCase):
    def setUp(self):
        for guard in (
            patch('urllib.request.OpenerDirector.open', side_effect=AssertionError('No network allowed')),
            patch('firebase_admin.initialize_app', side_effect=AssertionError('No credentials allowed')),
            patch('firebase_admin.firestore.client', side_effect=AssertionError('No real Firestore client allowed')),
        ):
            guard.start()
            self.addCleanup(guard.stop)

    def test_legacy_scripts_are_safe_to_import(self):
        for filename in ('api_football_test.py', 'wikidata_test.py'):
            spec = importlib.util.spec_from_file_location('audit_' + filename[:-3], BACKEND / filename)
            module = importlib.util.module_from_spec(spec)
            with self.subTest(filename=filename), patch.object(Path, 'read_text', side_effect=AssertionError('No credential reads on import')):
                with redirect_stdout(io.StringIO()):
                    spec.loader.exec_module(module)

    def test_all_backend_modules_can_be_imported_without_external_side_effects(self):
        with patch.object(Path, 'read_text', side_effect=AssertionError('No file reads on import')):
            for path in sorted(BACKEND.glob('*.py')):
                if not path.name.startswith('test_'):
                    with self.subTest(module=path.stem), redirect_stdout(io.StringIO()):
                        # Execute each module afresh, even if another test imported it.
                        spec = importlib.util.spec_from_file_location('audit_import_' + path.stem, path)
                        module = importlib.util.module_from_spec(spec)
                        spec.loader.exec_module(module)

    def test_placeholder_credentials_are_rejected_without_disclosing_values(self):
        for value in ('your_api_football_key_here', 'YOUR_API_FOOTBALL_KEY_HERE',
                      'PASTE_YOUR_API_KEY_HERE', 'PASTE_YOUR_ACTUAL_API_KEY_HERE', 'YOUR_API_KEY_HERE'):
            output = io.StringIO()
            with self.subTest(value=value), patch.object(Path, 'read_text', return_value='API_FOOTBALL_KEY=' + value):
                with redirect_stdout(output):
                    self.assertIsNone(profiles.read_api_key())
            self.assertNotIn(value, output.getvalue())

    def test_missing_credentials_produce_a_failure_exit_code(self):
        with patch.object(profiles, 'read_api_key', return_value=None), redirect_stdout(io.StringIO()):
            self.assertEqual(profiles.main(), 1)

    def test_disconnected_verification_reports_failure_without_a_traceback(self):
        with patch.object(prepare_player_data, 'read_api_key', return_value='fictional-test-key'), \
             patch.object(prepare_player_data, 'prepare_player', side_effect=RemoteDisconnected()), \
             redirect_stdout(io.StringIO()):
            self.assertEqual(prepare_player_data.main(), 1)
        with patch.object(import_players, 'load_player', return_value={}), \
             patch.object(import_players, 'verify_wikidata_fields', side_effect=RemoteDisconnected()), \
             patch.object(import_players, 'get_player_document') as document, redirect_stdout(io.StringIO()):
            self.assertEqual(import_players.main([]), 1)
        document.assert_not_called()

    def test_ambiguous_player_profiles_are_not_first_result_matches(self):
        first = {'player': {'id': 900001, 'name': 'Lionel Messi'}}
        second = {'player': {'id': 900002, 'name': 'Lionel Messi'}}
        self.assertIsNone(profiles.find_messi([first, second]))

    def test_profile_search_rejects_incomplete_or_malformed_results_in_one_request(self):
        first = {'player': {'id': 900001, 'name': 'Lionel Messi'}}
        valid = {'errors': [], 'results': 1, 'response': [first], 'paging': {'current': 1, 'total': 1}}
        cases = [dict(valid, results=True), dict(valid, results=2), dict(valid, errors=None),
                 dict(valid, paging={}), dict(valid, paging={'current': 1, 'total': 2}),
                 dict(valid, response=[first, first], results=2)]
        for data in cases:
            opener = Mock()
            opener.open.return_value = io.StringIO(json.dumps(data))
            with self.subTest(data=data), patch.object(profiles, 'read_api_key', return_value='fictional-test-key'), \
                 patch.object(profiles, 'build_opener', return_value=opener) as factory, \
                 patch.object(profiles, 'display_player') as display, redirect_stdout(io.StringIO()):
                self.assertEqual(profiles.main(), 1)
            opener.open.assert_called_once()
            self.assertIsInstance(factory.call_args.args[0], profiles.NoRedirects)
            display.assert_not_called()

    def test_profile_search_accepts_a_unique_complete_response(self):
        player = {'id': 900001, 'name': 'Lionel Messi'}
        data = {'errors': [], 'results': 1, 'response': [{'player': player}], 'paging': {'current': 1, 'total': 1}}
        opener = Mock()
        opener.open.return_value = io.StringIO(json.dumps(data))
        with patch.object(profiles, 'read_api_key', return_value='fictional-test-key'), \
             patch.object(profiles, 'build_opener', return_value=opener), \
             patch.object(profiles, 'display_player') as display, redirect_stdout(io.StringIO()):
            self.assertEqual(profiles.main(), 0)
        display.assert_called_once_with(player)
        opener.open.assert_called_once()

    def test_uncertain_wikidata_birth_dates_are_not_accepted_as_verified(self):
        for uncertainty in ({'before': 1}, {'after': 1}):
            value = {'time': '+1987-06-24T00:00:00Z', 'precision': 11,
                     'calendarmodel': 'http://www.wikidata.org/entity/Q1985727', **uncertainty}
            entity = {'claims': {'P569': [{'rank': 'normal', 'mainsnak': {'snaktype': 'value', 'datavalue': {'value': value}}}]}}
            with self.subTest(uncertainty=uncertainty), self.assertRaises(PlayerDataError):
                wikidata_birth_date(entity)

    def test_import_loaders_reject_duplicate_json_keys(self):
        fixtures = (
            (preview_multiple_teams, 'load_teams', {'teams': []}),
            (import_multiple_players, 'load_players', {'players': []}),
            (import_team, 'load_team', json.loads((BACKEND / 'output' / 'team_barcelona.json').read_text(encoding='utf-8-sig'))),
            (import_players, 'load_player', json.loads((BACKEND / 'output' / 'player_messi.json').read_text(encoding='utf-8-sig'))),
            (prepare_team_data, 'load_schema', json.loads((BACKEND / 'input' / 'team_schema_example.json').read_text(encoding='utf-8-sig'))),
            (prepare_multiple_teams, 'load_verified_teams', json.loads((BACKEND / 'output' / 'teams_verified.json').read_text(encoding='utf-8-sig'))),
            (discover_team_ids, 'load_teams', json.loads((BACKEND / 'input' / 'teams_to_import.json').read_text(encoding='utf-8-sig'))),
        )
        for module, function, data in fixtures:
            field = next(iter(data))
            raw = json.dumps(data)[:-1] + ', ' + json.dumps(field) + ': ' + json.dumps(data[field]) + '}'
            with self.subTest(module=module.__name__), patch.object(Path, 'open', return_value=io.StringIO(raw)):
                with self.assertRaises(ValueError):
                    getattr(module, function)()

    def test_duplicate_prepared_data_stops_before_firestore_initialization(self):
        raw = '{"teams": [], "teams": []}'
        with patch.object(Path, 'open', return_value=io.StringIO(raw)), \
             patch.object(preview_multiple_teams, 'get_firestore_client') as client, \
             redirect_stdout(io.StringIO()):
            self.assertEqual(preview_multiple_teams.main(), 1)
        client.assert_not_called()

    def test_multi_player_import_rejects_nonexistent_zero_or_padded_ids(self):
        reference = json.loads((BACKEND / 'output' / 'players_prepared.json').read_text(encoding='utf-8-sig'))['players'][0]
        for wikidata_id in ('Q0', 'Q00', 'Q0615'):
            data = {'players': [dict(reference, wikidataId=wikidata_id, documentId='wikidata_' + wikidata_id)]}
            with self.subTest(wikidata_id=wikidata_id), patch.object(Path, 'open', return_value=io.StringIO(json.dumps(data))):
                with self.assertRaises(ValueError):
                    import_multiple_players.load_players()

    def test_single_player_upload_cancels_if_document_changes_after_preview(self):
        player = {'wikidataId': 'Q615', 'name': 'Lionel Messi', 'dateOfBirth': '1987-06-24',
                  'nationality': 'Argentina', 'position': 'Forward'}
        original = SimpleNamespace(exists=True, update_time=1, to_dict=lambda: {})
        newer = SimpleNamespace(exists=True, update_time=2, to_dict=lambda: {})
        document = Mock()
        document.get.side_effect = [original, newer]
        transaction = Mock()
        db = Mock()
        db.transaction.return_value = transaction
        def verified(data):
            data['source'] = 'Wikidata'
        with patch.object(import_players, 'load_player', return_value=copy.deepcopy(player)), \
             patch.object(import_players, 'verify_wikidata_fields', side_effect=verified), \
             patch.object(import_players, 'get_player_document', return_value=document), \
             patch.object(import_players.firestore, 'client', return_value=db), \
             patch.object(import_players.firestore, 'transactional', side_effect=lambda function: function), \
             patch('builtins.input', return_value='YES'), redirect_stdout(io.StringIO()) as output:
            self.assertEqual(import_players.main(['--apply']), 1)
        self.assertIn('changed since the preview', output.getvalue())
        document.set.assert_not_called()
        transaction.set.assert_not_called()

    def test_player_transaction_detects_creation_deletion_and_unknown_versions(self):
        for original, current in (
            (SimpleNamespace(exists=False, update_time=None), SimpleNamespace(exists=True, update_time=2)),
            (SimpleNamespace(exists=True, update_time=1), SimpleNamespace(exists=False, update_time=None)),
            (SimpleNamespace(exists=True, update_time=None), SimpleNamespace(exists=True, update_time=None)),
        ):
            document, db, transaction = Mock(), Mock(), Mock()
            document.get.return_value = current
            db.transaction.return_value = transaction
            with self.subTest(original=original, current=current), \
                 patch.object(import_players.firestore, 'client', return_value=db), \
                 patch.object(import_players.firestore, 'transactional', side_effect=lambda function: function):
                with self.assertRaises(import_players.ConflictError):
                    import_players.apply_player(document, {}, original)
            transaction.set.assert_not_called()
            document.set.assert_not_called()

    def test_player_transaction_turns_commit_conflicts_into_review_messages(self):
        aborted = Aborted('fictional transaction conflict')
        wrapped = ValueError('transaction attempts exhausted')
        wrapped.__cause__ = aborted
        for failure in (aborted, wrapped):
            db = Mock()
            with self.subTest(error=type(failure).__name__), \
                 patch.object(import_players.firestore, 'client', return_value=db), \
                 patch.object(import_players.firestore, 'transactional', return_value=Mock(side_effect=failure)):
                with self.assertRaises(import_players.ConflictError):
                    import_players.apply_player(Mock(), {}, Mock())

    def run_player_import(self, args, snapshots, answer='YES'):
        # Mock every external boundary, including the Wikidata recheck.
        player = {'wikidataId': 'Q615', 'name': 'Lionel Messi', 'dateOfBirth': '1987-06-24',
                  'nationality': 'Argentina', 'position': 'Forward', 'source': 'Wikidata'}
        document, db, transaction = Mock(), Mock(), Mock()
        document.get.side_effect = snapshots
        db.transaction.return_value = transaction
        with patch.object(import_players, 'load_player', return_value=player), \
             patch.object(import_players, 'verify_wikidata_fields'), \
             patch.object(import_players, 'get_player_document', return_value=document), \
             patch.object(import_players.firestore, 'client', return_value=db), \
             patch.object(import_players.firestore, 'transactional', side_effect=lambda function: function), \
             patch('builtins.input', return_value=answer) as prompt, redirect_stdout(io.StringIO()):
            result = import_players.main(args)
        return result, document, db, transaction, prompt

    def test_player_dry_run_never_starts_a_write_transaction(self):
        original = SimpleNamespace(exists=False, update_time=None)
        result, document, db, transaction, prompt = self.run_player_import([], [original])
        self.assertEqual(result, 0)
        db.transaction.assert_not_called()
        transaction.set.assert_not_called()
        document.set.assert_not_called()
        prompt.assert_not_called()

    def test_player_confirmation_must_be_exactly_yes(self):
        for answer in ('yes', ' YES', 'YES ', '', 'NO'):
            with self.subTest(answer=answer):
                result, document, db, transaction, prompt = self.run_player_import(
                    ['--apply'], [SimpleNamespace(exists=False, update_time=None)], answer
                )
                self.assertEqual(result, 0)
                prompt.assert_called_once()
                db.transaction.assert_not_called()
                transaction.set.assert_not_called()
                document.set.assert_not_called()

    def test_player_apply_merges_only_managed_fields_after_rechecking(self):
        original = SimpleNamespace(exists=False, update_time=None)
        saved_data = {'wikidataId': 'Q615', 'name': 'Lionel Messi', 'dateOfBirth': '1987-06-24',
                      'nationality': 'Argentina', 'position': 'Forward', 'source': 'Wikidata',
                      'unrelatedField': 'keep me'}
        saved = SimpleNamespace(exists=True, update_time=2, to_dict=lambda: saved_data)
        result, document, db, transaction, prompt = self.run_player_import(
            ['--apply'], [original, original, saved]
        )
        self.assertEqual(result, 0)
        db.transaction.assert_called_once_with(max_attempts=1)
        fields = {field: saved_data[field] for field in (*import_players.PUBLIC_FIELDS, 'source')}
        transaction.set.assert_called_once_with(document, fields, merge=True)
        self.assertEqual(document.get.call_count, 3)
        document.set.assert_not_called()

    def test_matching_player_does_not_prompt_or_write_even_in_apply_mode(self):
        saved_data = {'wikidataId': 'Q615', 'name': 'Lionel Messi', 'dateOfBirth': '1987-06-24',
                      'nationality': 'Argentina', 'position': 'Forward', 'source': 'Wikidata'}
        original = SimpleNamespace(exists=True, update_time=1, to_dict=lambda: saved_data)
        result, document, db, transaction, prompt = self.run_player_import(['--apply'], [original])
        self.assertEqual(result, 0)
        prompt.assert_not_called()
        db.transaction.assert_not_called()
        transaction.set.assert_not_called()
        document.set.assert_not_called()


if __name__ == '__main__':
    unittest.main(verbosity=2)
