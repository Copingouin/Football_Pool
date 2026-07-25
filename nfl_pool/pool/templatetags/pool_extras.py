from django import template

from pool.team_data import TEAM_ABBR, team_logo_url

register = template.Library()


@register.filter
def team_logo(team_name):
    """{{ game.home_team|team_logo }} — ESPN team logo URL, or '' if unrecognized."""
    return team_logo_url(team_name)


@register.filter
def favorite_logo(user):
    """{{ player|favorite_logo }} — a user's chosen favorite-team logo URL, or '' if none set."""
    profile = getattr(user, 'profile', None)
    if not profile or not profile.favorite_team:
        return ''
    return team_logo_url(profile.favorite_team)


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
