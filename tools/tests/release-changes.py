#!/usr/bin/env python3
"""Release-note change list: curated CHANGELOG section plus git log."""
import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest

TOP = Path(__file__).resolve().parents[2]


def module(name):
    spec = importlib.util.spec_from_file_location(name.replace('-', '_'),
                                                  TOP / 'tools' / (name + '.py'))
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


changes = module('release-changes')


class SectionTest(unittest.TestCase):
    def test_section_stops_at_the_next_heading(self):
        text = '# log\n## 未发布\n- 改 A\n\n## 2026-11-21\n- 旧\n'
        self.assertEqual(changes.section(text, '未发布'), '- 改 A')

    def test_missing_section_is_empty(self):
        self.assertEqual(changes.section('# log\n## 其它\n- x\n', '未发布'), '')


class RenderTest(unittest.TestCase):
    def test_curated_section_and_commits_are_both_printed(self):
        changelog = '## 未发布\n\n### 电源\n- dwc3 自动挂起\n'
        output = changes.render(['abc1234 fix: x', 'def5678 docs: y'],
                                2, 'changxing60-v1', changelog, 60)
        self.assertIn('dwc3 自动挂起', output)
        self.assertIn('`abc1234 fix: x`', output)
        self.assertIn('自上一发布 `changxing60-v1` 以来共 2 个提交', output)

    def test_no_previous_tag_says_so(self):
        output = changes.render([], 0, '', '## 未发布\n- x\n', 60)
        self.assertIn('没有更早的', output)
        self.assertIn('- （无）', output)


class GitTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.repo = Path(self.tmp.name)
        self.git('init', '-q')
        self.commit('first')
        self.git('tag', 'changxing60-v1')
        self.commit('fix: second')

    def git(self, *args):
        return subprocess.run(['git', '-C', str(self.repo),
                               '-c', 'user.name=t', '-c', 'user.email=t@example.invalid', *args],
                              capture_output=True, text=True, check=True).stdout.strip()

    def commit(self, subject):
        path = self.repo / 'file'
        path.write_text((path.read_text() if path.exists() else '') + subject + '\n')
        self.git('add', 'file')
        self.git('commit', '-q', '-m', subject)

    def test_previous_tag_skips_the_current_commit(self):
        self.assertEqual(changes.previous_tag(self.repo), 'changxing60-v1')

    def test_commits_and_count_since_previous_tag(self):
        self.assertEqual(changes.commits(self.repo, 'changxing60-v1', 60),
                         [self.git('log', '-1', '--format=%h %s')])
        self.assertEqual(changes.commit_count(self.repo, 'changxing60-v1'), 1)


if __name__ == '__main__':
    unittest.main()
