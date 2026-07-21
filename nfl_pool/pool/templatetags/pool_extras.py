from django import template

register = template.Library()

# Full team display name (as stored on Game.home_team/away_team, matching ESPN's
# `displayName`) -> ESPN's 3-letter team code, used to build logo CDN URLs without
# needing a DB column or a static/media pipeline.
TEAM_ABBR = {
    'Arizona Cardinals': 'ari',
    'Atlanta Falcons': 'atl',
    'Baltimore Ravens': 'bal',
    'Buffalo Bills': 'buf',
    'Carolina Panthers': 'car',
    'Chicago Bears': 'chi',
    'Cincinnati Bengals': 'cin',
    'Cleveland Browns': 'cle',
    'Dallas Cowboys': 'dal',
    'Denver Broncos': 'den',
    'Detroit Lions': 'det',
    'Green Bay Packers': 'gb',
    'Houston Texans': 'hou',
    'Indianapolis Colts': 'ind',
    'Jacksonville Jaguars': 'jax',
    'Kansas City Chiefs': 'kc',
    'Las Vegas Raiders': 'lv',
    'Los Angeles Chargers': 'lac',
    'Los Angeles Rams': 'lar',
    'Miami Dolphins': 'mia',
    'Minnesota Vikings': 'min',
    'New England Patriots': 'ne',
    'New Orleans Saints': 'no',
    'New York Giants': 'nyg',
    'New York Jets': 'nyj',
    'Philadelphia Eagles': 'phi',
    'Pittsburgh Steelers': 'pit',
    'San Francisco 49ers': 'sf',
    'Seattle Seahawks': 'sea',
    'Tampa Bay Buccaneers': 'tb',
    'Tennessee Titans': 'ten',
    'Washington Commanders': 'wsh',
}


@register.filter
def team_logo(team_name):
    """{{ game.home_team|team_logo }} — ESPN team logo URL, or '' if unrecognized."""
    abbr = TEAM_ABBR.get(team_name)
    if not abbr:
        return ''
    return f'https://a.espncdn.com/i/teamlogos/nfl/500/scoreboard/{abbr}.png'


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
