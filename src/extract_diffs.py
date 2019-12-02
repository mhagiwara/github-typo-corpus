import argparse
import contextlib
import difflib
import json
import requests
import shutil
import sys

import git
from git import Repo, Commit


@contextlib.contextmanager
def clone_git(github_url: str):
    print(f'Cloning repo: {github_url} ...', file=sys.stderr)

    _, user, repo_name = github_url.rsplit('/', 2)
    repo_path = f'repos/{user}_{repo_name}'

    try:
        Repo.clone_from(github_url, repo_path)
    except git.exc.GitError:
        print(f'Failed to clone: {github_url}.', file=sys.stderr)
        yield None
        return

    repo = Repo(repo_path)

    yield repo

    shutil.rmtree(repo_path)


def iter_diffs(commit: Commit):
    if len(commit.parents) != 1:
        return

    parent_commit = commit.parents[0]

    try:
        for diff in parent_commit.diff(commit).iter_change_type('M'):
            yield diff
    except RecursionError as e:
        print(f'Encountered RecursionError when diffing.', file=sys.stderr)
        return


def get_diff_lines(diff):
    try:
        a_text = diff.a_blob.data_stream.read().decode('utf-8')
        b_text = diff.b_blob.data_stream.read().decode('utf-8')
    except ValueError:
        return []

    if len(a_text) > 50000 or len(b_text) > 50000:
        # skip if diff can be too large to compute
        return []

    try:
        diff_lines = difflib.ndiff(a_text.split('\n'), b_text.split('\n'))
    except RecursionError as e:
        print(f'Encountered RecursionError when diffing.', file=sys.stderr)
        return []
    return diff_lines


def extract_valid_pairs(diff_lines):
    pairs = []
    prev_line = ''
    for line in diff_lines:
        if line.startswith('?'):
            continue
        if line.startswith('+') and prev_line.startswith('-'):
            pairs.append((prev_line[2:], line[2:]))

        prev_line = line

    return pairs


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--filter-non-typo-commits",
                        help="filter out non-typo commits",
                        action="store_true")
    parser.add_argument("--filter-by-mod",
                        default=0,
                        type=int,
                        help="if specified an integer n, "
                             "filter out commits where hash mod n != 0")

    args = parser.parse_args()

    for line in sys.stdin:
        github_url = line.strip()
        print(f'Github repo: {github_url}', file=sys.stderr)

        # check 404
        res = requests.get(github_url)
        if res.status_code == 404:
            print(f'404 detected: {github_url}. Skipping ... ', file=sys.stderr)
            continue

        if res.status_code == 451:
            print(f'451 Unavailable for Legal Reasons: {github_url}. Skipping ...', file=sys.stderr)
            continue

        with clone_git(github_url) as repo:

            if repo is None:
                continue

            # check if empty
            try:
                repo.head.commit
            except ValueError as e:
                print(f'Empty repo: {github_url}. Skipping ... ', file=sys.stderr)
                continue

            print(f'Enumerating commits for: {github_url} ...', file=sys.stderr)

            for commit in repo.iter_commits():

                if args.filter_non_typo_commits and 'typo' not in commit.message:
                    continue

                if args.filter_by_mod > 0:
                    intsha = int(commit.hexsha, base=16)
                    if intsha % args.filter_by_mod != 0:
                        continue

                data = {'repo': github_url,
                        'commit': commit.hexsha,
                        'message': commit.message[:100]}

                pairs = []
                paths = []

                skip_commit = False
                for diff in iter_diffs(commit):
                    diff_lines = get_diff_lines(diff)
                    line_pairs = extract_valid_pairs(diff_lines)
                    paths.extend([(diff.a_path, diff.b_path)] * len(line_pairs))
                    pairs.extend(line_pairs)

                    if len(pairs) > 10:
                        skip_commit = True
                        continue

                if skip_commit:
                    continue

                if 1 <= len(pairs) <= 10:
                    data['diffs'] = pairs
                    data['paths'] = paths
                    print(json.dumps(data))


if __name__ == '__main__':
    main()
