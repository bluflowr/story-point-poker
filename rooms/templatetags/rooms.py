from django import template
from django.utils.html import format_html, format_html_join

register = template.Library()


@register.simple_tag
def ws_button(label, css="", **fields):
    """
    A one-button form that sends `fields` over the room's WebSocket, e.g.
    {% ws_button "Remove" action="remove" target=player.id %}
    """
    inputs = format_html_join("", '<input type="hidden" name="{}" value="{}">', fields.items())
    return format_html(
        '<form ws-send class="ws-button">{}<button type="submit" class="link-button {}">{}</button></form>',
        inputs,
        css,
        label,
    )


@register.filter
def minutes_seconds(seconds):
    """125 -> "2:05"."""
    return f"{seconds // 60}:{seconds % 60:02d}"
