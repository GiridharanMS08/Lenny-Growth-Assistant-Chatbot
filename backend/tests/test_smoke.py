from app.security.artifact_sanitizer import sanitize_html

def test_sanitize_removes_script():
    out = sanitize_html('<div>Hello</div><script>alert(1)</script>')
    assert '<script' not in out
    assert 'Hello' in out
