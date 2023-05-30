import logging
import os
import subprocess
from dataclasses import dataclass
from http import HTTPStatus
from pathlib import Path
from typing import Sequence

import click
import yaml
from github import Github, GithubException, GitRef, Repository

from .import_fondsnet_companies import FONDSNET_COMPANY_OUTPUT_FIXTURE_PATH
from .import_fondsnet_contacts import FONDSNET_CONTACTS_OUTPUT_FIXTURE_PATH
from .import_fondsnet_dealers import FONDSNET_DEALER_OUTPUT_FIXTURE_PATH

GIT_REF_PREFIX = "refs/heads/"
BASE_BRANCH_REF = f"{GIT_REF_PREFIX}master"
FEATURE_BRANCH_NAME = "feature/automatic-fondsnet-data-import"
FEATURE_BRANCH_REF = f"{GIT_REF_PREFIX}{FEATURE_BRANCH_NAME}"

COMMIT_MESSAGE = "feat(fixtures): update FONDSNET data"

GIT_AUTHOR_NAME = "Sir Mergealot"
GIT_AUTHOR_EMAIL = "mergealot@moneymeets.com"

FONDSNET_DATA_TEAM_PATH = Path(__file__).parent.parent / ".github" / "configs" / "fondsnet-data-team.yml"

FIXTURE_FILES = (
    FONDSNET_COMPANY_OUTPUT_FIXTURE_PATH,
    FONDSNET_CONTACTS_OUTPUT_FIXTURE_PATH,
    FONDSNET_DEALER_OUTPUT_FIXTURE_PATH,
)


@dataclass(frozen=True)
class GithubTeam:
    name: str
    members: Sequence[str]


def _run_process(command: str, check: bool = True, capture_output: bool = False):
    logging.info(f"RUNNING {command}")
    return subprocess.run(command, check=check, shell=True, text=True, capture_output=capture_output)


def get_git_ref(repository: Repository, ref: str) -> GitRef:
    # https://docs.github.com/en/rest/git/refs#list-matching-references
    return repository.get_git_ref(ref.replace("refs/", ""))


def configure_git_user(name: str, email: str):
    _run_process(f"git config --local user.name '{name}'")
    _run_process(f"git config --local user.email '{email}'")


def get_github_repository() -> Repository:
    return Github(login_or_token=os.environ["GITHUB_TOKEN"]).get_repo(os.environ["GITHUB_REPOSITORY"])


def checkout_remote_feature_branch_or_create_new_local_branch(branch_exists: bool):
    logging.info(
        "Feature branch exists, checking out" if branch_exists else "Feature branch does not exist, creating it",
    )
    _run_process(f"git checkout {'' if branch_exists else '-b'} {FEATURE_BRANCH_NAME}")


def modified_files() -> bool:
    return bool(_run_process("git diff --quiet", check=False, capture_output=True).returncode)


def commit_and_push_changes(branch_exists: bool):
    logging.info(
        "Adding fixup commit to existing branch" if branch_exists else "Adding commit to newly created branch",
    )
    commit_message = f"fixup! {COMMIT_MESSAGE}" if branch_exists else COMMIT_MESSAGE
    _run_process(f"git commit -a -m '{commit_message}'")
    _run_process(f"git push {'' if branch_exists else '-u origin HEAD'}")


def check_branch_exists(repo: Repository, branch: str) -> bool:
    try:
        repo.get_branch(branch=branch)
        return True
    except GithubException as e:
        if e.status != HTTPStatus.NOT_FOUND:
            raise
        return False


def ensure_pull_request_created(repo: Repository, reviewers: Sequence[str]):
    logging.info("Checking for pull requests")
    pr = repo.get_pulls(state="open", head=f"{getattr(repo.organization, 'login', 'v-the-cmd')}:{FEATURE_BRANCH_REF}")

    if pr.totalCount == 0:
        pull_request = repo.create_pull(
            title="Update FONDSNET data",
            body="This PR was created automatically. Check the updated FONDSNET data.",
            base=BASE_BRANCH_REF,
            head=FEATURE_BRANCH_REF,
        )

        pull_request.create_review_request(reviewers=reviewers)
        logging.info(f"PR <{pull_request.number}> created, reviewers <{reviewers}>")
    else:
        pull_request, *_ = tuple(pr)
        logging.info(f"Pull request already exists, {pull_request.number}")


def get_team_from_yaml(yaml_config: str) -> GithubTeam:
    return GithubTeam(**yaml.safe_load(yaml_config))


@click.group()
def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S%z",
    )
    configure_git_user(name=GIT_AUTHOR_NAME, email=GIT_AUTHOR_EMAIL)


@main.command("set-up-branch")
def cmd_set_up_branch():
    checkout_remote_feature_branch_or_create_new_local_branch(
        branch_exists=check_branch_exists(repo=get_github_repository(), branch=FEATURE_BRANCH_REF),
    )


@main.command("check-and-push-changes")
def cmd_check_and_push_changes():
    if modified_files():
        logging.info("Found modified files, committing changes")
        repository = get_github_repository()
        commit_and_push_changes(branch_exists=check_branch_exists(repository, FEATURE_BRANCH_REF))
        logging.info("Getting FONDSNET Team information from file")
        fondsnet_team = ['v-the-cmd'] #get_team_from_yaml(yaml_config=FONDSNET_DATA_TEAM_PATH.read_text())
        ensure_pull_request_created(repo=repository, reviewers=fondsnet_team)#.members)
    else:
        logging.info("Nothing changed, skipping this step")


if __name__ == "__main__":
    main()
