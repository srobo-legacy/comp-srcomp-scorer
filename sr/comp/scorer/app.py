import collections
from datetime import datetime
import dateutil.tz
import itertools
import os

import flask

from sr.comp.raw_compstate import RawCompstate
from sr.comp.validation import validate


app = flask.Flask('sr.comp.scorer')
app.debug = True


def grouper(iterable, n, fillvalue=None):
    """
    Collect data into fixed-length chunks or blocks.

    >>> grouper('ABCDEFG', 3, 'x')
    ['ABC', 'DEF', 'Gxx']
    """
    args = [iter(iterable)] * n
    return itertools.zip_longest(fillvalue=fillvalue, *args)
app.jinja_env.globals.update(grouper=grouper)


def empty_if_none(string):
    return string if string is not None else ''
app.jinja_env.filters.update(empty_if_none=empty_if_none)


def parse_hex_colour(string):
    string = string.strip('#')
    return int(string[:2], 16), int(string[2:4], 16), int(string[4:], 16)
app.jinja_env.globals.update(parse_hex_colour=parse_hex_colour)


def group_list_dict(matches, keys):
    """
    Group a list of dictionaries into a dictionary of lists.

    This will convert
        [{'A': a, 'B': b}, {'A': a2, 'B': b2}]
    into
        {'A': [a, a2], 'B': [b, b2]}
    """
    target = collections.OrderedDict((key, []) for key in keys)
    for entry in matches:
        if entry is None:
            continue
        for key, value in entry.items():
            target[key].append(value)
    return target


def is_match_done(match):
    path = flask.g.compstate.get_score_path(match)
    return os.path.exists(path)
app.jinja_env.globals.update(is_match_done=is_match_done)


def form_to_score(match, form):
    detected_flags = 0

    def form_team_to_score(zone, teams):
        nonlocal detected_flags
        tla = form.get('tla_{}'.format(zone), None)
        if tla:
            flags = int(form['flags_{}'.format(zone)])
            team = {
                'zone': zone,
                'disqualified':
                    form.get('disqualified_{}'.format(zone), None) is not None,
                'present':
                    form.get('present_{}'.format(zone), None) is not None,
                'flags': flags
            }

            detected_flags += flags

            teams[tla] = team

    teams = {}
    for i in range(4):
        form_team_to_score(i, teams)

    if detected_flags + int(form.get('unclaimed_flags', 0)) != 5:
        raise ValueError("Total number of flags doesn't add up to five.")

    return {
        'arena_id': match.arena,
        'match_number': match.num,
        'teams': teams
    }


def score_to_form(score):
    form = {}

    for tla, info in score['teams'].items():
        i = info['zone']
        form['tla_{}'.format(i)] = tla
        form['disqualified_{}'.format(i)] = info.get('disqualified', False)
        form['present_{}'.format(i)] = info.get('present', True)
        form['flags_{}'.format(i)] = info.get('flags', 0)

    return form


def update_and_validate(compstate, match, score):
    compstate.save_score(match, score)

    path = compstate.get_score_path(match)
    compstate.stage(path)

    try:
        comp = compstate.load()
    except Exception as e:
        # SRComp sometimes throws generic Exceptions. We have to reset the repo
        # because if SRComp fails to instantiate, it would break everything!
        compstate.reset_hard()
        raise RuntimeError(e)
    else:
        i = validate(comp)
        if i > 0:
            raise RuntimeError('{} errors occured.'.format(i))


def commit_and_push(compstate, match):
    commit_msg = 'Update {} scores for match {} in arena {}' \
        .format(match.type.value, match.num, match.arena)

    compstate.commit_and_push(commit_msg)


def calculate_unclaimed_flags(score_sheet):
    unclaimed_flags = 5
    for tla, scores in score_sheet['teams'].items():
        unclaimed_flags -= scores['flags']
    assert unclaimed_flags > 0
    return unclaimed_flags


@app.before_request
def before_request():
    cs_path = os.path.realpath(app.config['COMPSTATE'])
    local_only = app.config['COMPSTATE_LOCAL']
    flask.g.compstate = RawCompstate(cs_path, local_only)


@app.route('/')
def index():
    comp = flask.g.compstate.load()
    all_matches = group_list_dict(comp.schedule.matches, comp.arenas.keys())
    now = datetime.now(dateutil.tz.tzlocal())
    current_matches = {match.arena: match
                       for match in comp.schedule.matches_at(now)}
    return flask.render_template('index.html', all_matches=all_matches,
                                 current_matches=current_matches,
                                 arenas=comp.arenas.values())


@app.route('/<arena>/<int:num>', methods=['GET', 'POST'])
def update(arena, num):
    compstate = flask.g.compstate
    comp = compstate.load()

    try:
        match = comp.schedule.matches[num][arena]
    except (IndexError, KeyError):
        flask.abort(404)

    template_settings = {'match': match,
                         'arenas': comp.arenas}

    if flask.request.method == 'GET':
        try:
            score = compstate.load_score(match)
        except IOError:
            pass
        else:
            flask.request.form = score_to_form(score)
            flask.request.form['unclaimed_flags'] = \
                calculate_unclaimed_flags(score)
    elif flask.request.method == 'POST':
        try:
            score = form_to_score(match, flask.request.form)
        except ValueError as e:
            return flask.render_template('update.html',
                                         error=str(e),
                                         **template_settings)

        try:
            compstate.reset_and_fast_forward()
            update_and_validate(compstate, match, score)
            commit_and_push(compstate, match)
        except RuntimeError as e:
            return flask.render_template('update.html',
                                         error=str(e),
                                         **template_settings)
        else:
            url = flask.url_for('update', arena=arena, num=num) + '?done=true'
            return flask.redirect(url)

    return flask.render_template('update.html',
                                 done=flask.request.args.get('done', False),
                                 **template_settings)
