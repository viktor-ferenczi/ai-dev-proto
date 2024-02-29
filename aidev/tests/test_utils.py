import unittest
import aidev.common.util as util


class SyncUtilsTests(unittest.TestCase):

    def test_render_html(self):
        html = util.render_html_template('test', code='```cs\nclass Class<T> {}\n```')
        self.assertTrue('<pre><code class="language-markdown">```cs\nclass Class&lt;T&gt; {}\n```</code></pre>' in html, html)
