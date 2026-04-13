from django import template

register = template.Library()


@register.filter
def get_item(dictionary, key):
    """{{ my_dict|get_item:key }} — dict lookup by variable key in templates."""
    if dictionary is None:
        return None
    try:
        return dictionary.get(key)
    except AttributeError:
        try:
            return dictionary[key]
        except (KeyError, TypeError, IndexError):
            return None
