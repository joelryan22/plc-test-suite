"""
Python syntax highlighter for QPlainTextEdit
"""

from PyQt6.QtCore import QRegularExpression, Qt
from PyQt6.QtGui import QColor, QTextCharFormat, QFont, QSyntaxHighlighter


def _fmt(color: str, bold: bool = False, italic: bool = False) -> QTextCharFormat:
    f = QTextCharFormat()
    f.setForeground(QColor(color))
    if bold:
        f.setFontWeight(QFont.Weight.Bold)
    if italic:
        f.setFontItalic(True)
    return f


class PythonHighlighter(QSyntaxHighlighter):
    """Simple Python syntax highlighter"""

    RULES = []

    def __init__(self, document):
        super().__init__(document)
        self._build_rules()

    def _build_rules(self):
        rules = []

        # Keywords
        keywords = [
            "False", "None", "True", "and", "as", "assert", "async", "await",
            "break", "class", "continue", "def", "del", "elif", "else", "except",
            "finally", "for", "from", "global", "if", "import", "in", "is",
            "lambda", "nonlocal", "not", "or", "pass", "raise", "return", "try",
            "while", "with", "yield",
        ]
        kw_fmt = _fmt("#569CD6", bold=True)
        for kw in keywords:
            rules.append((QRegularExpression(rf"\b{kw}\b"), kw_fmt))

        # Builtins
        builtins = ["print", "len", "range", "int", "float", "str", "bool",
                    "abs", "min", "max", "round", "type", "list", "dict", "set"]
        bi_fmt = _fmt("#4EC9B0")
        for bi in builtins:
            rules.append((QRegularExpression(rf"\b{bi}\b"), bi_fmt))

        # Numbers
        rules.append((QRegularExpression(r"\b[0-9]+\.?[0-9]*\b"), _fmt("#B5CEA8")))

        # Strings (single and double quoted)
        rules.append((QRegularExpression(r'"[^"\\]*(\\.[^"\\]*)*"'), _fmt("#CE9178")))
        rules.append((QRegularExpression(r"'[^'\\]*(\\.[^'\\]*)*'"), _fmt("#CE9178")))

        # Comments
        rules.append((QRegularExpression(r"#[^\n]*"), _fmt("#6A9955", italic=True)))

        # Operators
        rules.append((QRegularExpression(r"[+\-*/=<>!&|^~%]+"), _fmt("#D4D4D4")))

        self._rules = rules

    def highlightBlock(self, text: str):
        for pattern, fmt in self._rules:
            it = pattern.globalMatch(text)
            while it.hasNext():
                match = it.next()
                self.setFormat(match.capturedStart(), match.capturedLength(), fmt)
