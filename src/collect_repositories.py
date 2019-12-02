import sys
import json
import requests
import gzip

VALID_LICENSES = ['apache-2.0', 'mit', 'bsd-3-clause', 'bsd-2-clause', 'cc0-1.0', 'unlicense',
                  'cc-by-4.0', 'bsl-1.0']


def is_valid_repo(repo_data):
    # check number of stargazers
    if repo_data['stargazers_count'] < 50:
        return False

    # check size (smaller than 1000 kb or larger than 1,000,000 kb)
    if repo_data['size'] < 1000 or repo_data['size'] > 1000000:
        return False

    # filter by license
    license = repo_data['license']
    if not license:
        return False

    if repo_data['license']['key'] not in VALID_LICENSES:
        return False

    return True


def collect_repo_urls(file_obj):
    valid_repos = set()
    for line in file_obj:
        event = json.loads(line)

        if event['type'] not in ['PullRequestEvent', 'PullRequestReviewCommentEvent']:
            continue

        repo_data = event['payload']['pull_request']['base']['repo']
        if is_valid_repo(repo_data):
            valid_repos.add(repo_data['html_url'])

    return valid_repos


def open_archive(archive_url):
    response = requests.get(archive_url, stream=True)
    f = gzip.GzipFile(fileobj=response.raw)

    return f


def retrieve_for_date(date_str):
    all_repos = set()
    for hour in range(24):
        archive_url = f'https://data.gharchive.org/{date_str}-{hour}.json.gz'
        print(f'Opening {archive_url}...', file=sys.stderr)
        f = open_archive(archive_url)
        repos = collect_repo_urls(f)
        all_repos.update(repos)
    return all_repos


def main():
    date_str = sys.argv[1]
    all_repos = retrieve_for_date(date_str)
    for repo in all_repos:
        print(repo)

if __name__ == '__main__':
    main()
