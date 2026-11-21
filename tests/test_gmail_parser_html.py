
from app.services.gmail_parser import html_to_text


def test_extracts_readable_text():
    html = """
    <html>
      <head><title>Hidden title</title></head>
      <body>
        <h1>Welcome</h1>
        <p>Your application was received.</p>
        <script>ignore_this()</script>
        <style>.hidden { display: none; }</style>
      </body>
    </html>
    """

    result = html_to_text(html)

    assert "Welcome" in result
    assert "Your application was received." in result
    assert "ignore_this" not in result
    assert "display: none" not in result
    assert "Hidden title" not in result


def test_decodes_html_entities():
    html = "<p>Hello &amp; welcome to LeadFlow AI</p>"

    result = html_to_text(html)

    assert "Hello & welcome to LeadFlow AI" in result


def test_removes_invisible_characters():
    html = "<p>Lead\u200bFlow\u200b AI</p>"

    result = html_to_text(html)

    assert result == "LeadFlow AI"


def test_empty_html():
    assert html_to_text("") == ""
