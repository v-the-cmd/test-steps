import os
import unittest
from unittest.mock import call, patch

from click.testing import CliRunner

import fondsnet
from fondsnet.create_pull_request import FIXTURE_FILES, GithubTeam, get_team_from_yaml, main


class TestFixtureFiles(unittest.TestCase):
    def test_fixture_file_paths_are_not_absolute_paths(self):
        for fixture_file in FIXTURE_FILES:
            self.assertFalse(os.path.isabs(fixture_file))

    def test_fixture_file_paths_exist_in_repository(self):
        for fixture_file in FIXTURE_FILES:
            self.assertTrue(os.path.isfile(fixture_file))


class TestGetTeamFromYaml(unittest.TestCase):
    def test_get_team_from_yaml_full(self):
        self.assertEqual(
            get_team_from_yaml("name: Test Team\nmembers: ['member 1', 'member 2']"),
            GithubTeam(name="Test Team", members=["member 1", "member 2"]),
        )

    def test_get_team_from_yaml_required_fields(self):
        self.assertRaises(TypeError, get_team_from_yaml, "members:\n - test member")
        self.assertRaises(TypeError, get_team_from_yaml, "name: Test Team")


class TestCmdCheckAndPushChanges(unittest.TestCase):
    base_cli_calls = (
        call("git config --local user.name 'Sir Mergealot'"),
        call("git config --local user.email 'mergealot@moneymeets.com'"),
        call("git diff --quiet", check=False, capture_output=True),
    )

    @patch.object(fondsnet.create_pull_request, "ensure_pull_request_created")
    @patch.object(fondsnet.create_pull_request, "get_team_from_yaml")
    @patch.object(fondsnet.create_pull_request, "check_branch_exists")
    @patch.object(fondsnet.create_pull_request, "get_github_repository")
    @patch.object(fondsnet.create_pull_request, "_run_process")
    def assertCheckAndPushChanges(
        self,
        mock__run_process,
        mock_get_github_repository,
        mock_check_branch_exists,
        mock_get_team_from_yaml,
        mock_ensure_pr_created,
        changes_found,
        branch_exists,
        extra_cli_calls,
    ):
        mock__run_process.return_value.returncode = int(changes_found)
        mock_check_branch_exists.return_value = branch_exists

        result = CliRunner().invoke(main, "check-and-push-changes")

        self.assertEqual(result.exit_code, 0)

        self.assertEqual(mock__run_process.call_count, len(self.base_cli_calls) + len(extra_cli_calls))

        for i, expected_call in enumerate(self.base_cli_calls + extra_cli_calls):
            self.assertEqual(mock__run_process.call_args_list[i], expected_call)

        for mock in (
            mock_check_branch_exists,
            mock_get_github_repository,
            mock_get_team_from_yaml,
            mock_ensure_pr_created,
        ):
            self.assertEqual(mock.call_count, int(changes_found))

    def test_skip_commit_and_push_if_no_files_are_modified(self):
        self.assertCheckAndPushChanges(changes_found=False, branch_exists=False, extra_cli_calls=())

    def test_commit_and_pushes_changes_to_existing_feature_branch_if_files_modified(self):
        self.assertCheckAndPushChanges(
            changes_found=True,
            branch_exists=True,
            extra_cli_calls=(
                call("git commit -a -m 'fixup! feat(fixtures): update FONDSNET data'"),
                call("git push "),
            ),
        )

    def test_commit_and_pushes_changes_to_new_feature_branch_if_files_modified(self):
        self.assertCheckAndPushChanges(
            changes_found=True,
            branch_exists=False,
            extra_cli_calls=(
                call("git commit -a -m 'feat(fixtures): update FONDSNET data'"),
                call("git push -u origin HEAD"),
            ),
        )
