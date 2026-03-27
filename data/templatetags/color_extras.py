from django import template


register = template.Library()


@register.filter
def color_chip_style(color):
    if not color:
        return ""
    return (
        f"background:{color.display_hex};"
        f"color:{color.display_text_color};"
        "border-radius:999px;"
        "padding:0.35rem 0.75rem;"
        "display:inline-block;"
        "font-weight:600;"
        "min-width:3.5rem;"
        "text-align:center;"
    )
