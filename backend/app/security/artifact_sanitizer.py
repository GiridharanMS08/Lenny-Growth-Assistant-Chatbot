import bleach
from bleach.css_sanitizer import CSSSanitizer


ALLOWED_TAGS = set(bleach.sanitizer.ALLOWED_TAGS) | {
    "html", "head", "body", "title", "meta", "style",
    "div", "span", "p", "h1", "h2", "h3", "h4", "h5", "h6",
    "ul", "ol", "li", "strong", "em", "section", "article", "main",
    "header", "footer", "table", "thead", "tbody", "tr", "th", "td",
    "br", "hr", "a"
}

ALLOWED_ATTRS = {
    "a": ["href", "title", "target", "rel"],
    "meta": ["name", "content", "charset", "viewport"],
    "*": ["class", "id", "title"],
}

CSS_SANITIZER = CSSSanitizer(
    allowed_css_properties={
        "color", "background", "background-color", "font-family", "font-size",
        "font-weight", "line-height", "margin", "margin-top", "margin-right",
        "margin-bottom", "margin-left", "padding", "padding-top", "padding-right",
        "padding-bottom", "padding-left", "border", "border-radius", "border-color",
        "border-width", "border-style", "width", "max-width", "min-width", "height",
        "display", "gap", "grid-template-columns", "text-align", "text-decoration",
        "box-shadow", "letter-spacing", "white-space"
    }
)


def sanitize_html(html: str) -> str:
    """Sanitize generated HTML; scripts/events/unsafe URLs are stripped."""
    return bleach.clean(
        html,
        tags=ALLOWED_TAGS,
        attributes=ALLOWED_ATTRS,
        css_sanitizer=CSS_SANITIZER,
        strip=True,
    )
