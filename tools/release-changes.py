#!/usr/bin/env python3
"""Render the change section of a Changxing 60 release note.

The curated part comes from the "未发布" section of CHANGELOG.md; the raw
commit list is everything since the previous `changxing60-*` tag. Both are
printed as Markdown for `.github/workflows/changxing60-release.yml`.
"""
import argparse
from pathlib import Path
import re
import subprocess
import sys

TAG_MATCH = 'changxing60-*'


def section(text, heading):
    """Body of a level-2 heading, without the heading itself."""
    match = re.search(r'^##\s+' + re.escape(heading) + r'\s*$', text, re.M)
    if not match:
        return ''
    rest = text[match.end():]
    following = re.search(r'^##\s+', rest, re.M)
    return (rest[:following.start()] if following else rest).strip()


def git(repo, *args):
    return subprocess.run(['git', '-C', str(repo), *args],
                          capture_output=True, text=True, check=True).stdout.strip()


def previous_tag(repo):
    try:
        return git(repo, 'describe', '--tags', '--abbrev=0', '--match', TAG_MATCH, 'HEAD^')
    except subprocess.CalledProcessError:
        return ''


def commits(repo, since, limit):
    revision = '%s..HEAD' % since if since else 'HEAD'
    output = git(repo, 'log', '--no-merges', '-n%d' % limit,
                 '--format=%h %s', revision)
    return [line for line in output.splitlines() if line]


def commit_count(repo, since):
    revision = '%s..HEAD' % since if since else 'HEAD'
    return int(git(repo, 'rev-list', '--count', '--no-merges', revision))


def render(entries, count, since, changelog, limit):
    curated = section(changelog, '未发布')
    lines = ['## 本次发布改了什么', '']
    if curated:
        lines.append(curated)
    else:
        lines.append('CHANGELOG.md 没有“未发布”摘要；以下提交记录即本次变更清单。')
    lines += ['', '### 提交记录', '']
    if since:
        lines.append('自上一发布 `%s` 以来共 %d 个提交（最多列 %d 条）：' % (since, count, limit))
        lines.append('')
    else:
        lines.append('仓库内没有更早的 `%s` 标签，无法自动对比上一发布；以下为最近 %d 个提交：'
                     % (TAG_MATCH, limit))
        lines.append('')
    for entry in entries:
        lines.append('- `%s`' % entry)
    if not entries:
        lines.append('- （无）')
    lines += ['', '> 提交记录由 `tools/release-changes.py` 在构建时生成；'
              '摘要来自 `CHANGELOG.md` 的“未发布”一节。', '']
    return '\n'.join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', default='.', help='git checkout (default: .)')
    parser.add_argument('--since', default='', help='previous release tag')
    parser.add_argument('--changelog', default='CHANGELOG.md')
    parser.add_argument('--limit', type=int, default=60)
    args = parser.parse_args(argv)
    repo = Path(args.repo)
    try:
        text = (repo / args.changelog).read_text(encoding='utf-8')
    except OSError:
        text = ''
    since = args.since or previous_tag(repo)
    try:
        entries = commits(repo, since, args.limit)
        count = commit_count(repo, since)
    except subprocess.CalledProcessError as error:
        print('release-changes: git failed: %s' % (error.stderr or error), file=sys.stderr)
        return 1
    print(render(entries, count, since, text, args.limit))
    return 0


if __name__ == '__main__':
    sys.exit(main())
