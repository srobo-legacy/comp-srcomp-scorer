import collections
from datetime import datetime
import dateutil.tz
import itertools
import os
import os.path
import subprocess

import flask
from flask import g, url_for
import yaml

from sr.comp.comp import SRComp
from sr.comp.raw_compstate import RawCompstate
from sr.comp.validation import validate

app = flask.Flask('sr.comp.scorer')
app.debug = True
app.jinja_env.globals.update(int=int, map=map)


def grouper(iterable, n, fillvalue=None):
    "Collect data into fixed-length chunks or blocks"
    # grouper('ABCDEFG', 3, 'x') --> ABC DEF Gxx
    args = [iter(iterable)] * n
    return itertools.zip_longest(fillvalue=fillvalue, *args)
app.jinja_env.globals.update(grouper=grouper)

def parse_hex_colour(string):
    string = string.strip('#')
    return int(string[:2], 16), int(string[2:4], 16), int(string[4:], 16)
app.jinja_env.globals.update(parse_hex_colour=parse_hex_colour)


def group_list_dict(matches, keys):
    """
    Group a list of dictionaries into a dictionary of lists.

    This will convert
        [{"A": a, "B": b}, {"A": a2, "B": b2}]
    into
        {"A": [a, a2], "B": [b, b2]}
    """
    target = collections.OrderedDict((key, []) for key in keys)
    for entry in matches:
        if entry is None:
            continue
        for key, value in entry.items():
            target[key].append(value)
    return target


def is_match_done(match):
    try:
        g.compstate.load_score(match)
        return True
    except IOError:
        return False
app.jinja_env.globals.update(is_match_done=is_match_done)


def form_to_score(match, form):
    detected_flags = 0

    def form_team_to_score(zone, teams):
        nonlocal detected_flags
        tla = form.get("team_tla_{}".format(zone), None)
        if tla:
            flags = int(form["flags_{}".format(zone)])
            team = {
                "zone": zone,
                "disqualified": form.get("disqualified_{}".format(zone), None) is not None,
                "present": form.get("absent_{}".format(zone), None) is None,
                "flags": flags
            }

            detected_flags += flags

            teams[tla] = team

    teams = {}
    form_team_to_score(0, teams)
    form_team_to_score(1, teams)
    form_team_to_score(2, teams)
    form_team_to_score(3, teams)

    if detected_flags > 5:
        raise ValueError("Too many flags specified.")

    return {
        "arena_id": match.arena,
        "match_number": match.num,
        "teams": teams
    }


def score_to_form(score):
    form = {}

    for tla, info in score["teams"].items():
        i = info["zone"]
        form["team_tla_{}".format(i)] = tla
        form["disqualified_{}".format(i)] = info.get("disqualified", False)
        form["absent_{}".format(i)] = not info.get("present", True)
        form["flags_{}".format(i)] = info.get("flags", True)

    return form

def update_and_validate(compstate, match, score):
    compstate.save_score(match, score)

    path = compstate.get_score_path(match)
    compstate.stage(path)

    try:
        comp = compstate.load()
    except Exception as e:  # SRComp sometimes throws generic Exceptions
        # we have to reset the repo because SRComp fails to instantiate and that
        # would break everything!
        compstate.reset_hard()
        raise RuntimeError(e)
    else:
        i = validate(comp)
        if i > 0:
            raise RuntimeError(str(i))


def commit_and_push(compstate, match):
    commit_msg = "update {} scores for match {} in arena {}".format(match.type.value,
                                                                    match.num,
                                                                    match.arena)

    compstate.commit_and_push(commit_msg)


@app.before_request
def before_request():
    cs_path = os.path.realpath(app.config["COMPSTATE"])
    local_only = app.config['COMPSTATE_LOCAL']
    g.compstate = RawCompstate(cs_path, local_only)

@app.route("/")
def index():
    comp = g.compstate.load()
    all_matches = group_list_dict(comp.schedule.matches, comp.arenas.keys())
    current_matches = {match.arena: match for match in comp.schedule.matches_at(datetime.now(dateutil.tz.tzlocal()))}
    return flask.render_template('index.html', all_matches=all_matches,
                                 current_matches=current_matches,
                                 arenas=comp.arenas.values())


@app.route("/<arena>/<int:num>", methods=["GET", "POST"])
def update(arena, num):
    compstate = g.compstate
    comp = compstate.load()

    try:
        match = comp.schedule.matches[num][arena]
    except (IndexError, KeyError):
        return flask.redirect("/")  # TODO: could show an error message here

    template_settings = {'match': match,
                         'arenas': comp.arenas,
                         'corners': comp.corners}

    if flask.request.method == "GET":
        try:
            score = compstate.load_score(match)
        except IOError:
            pass
        else:
            flask.request.form = score_to_form(score)
    elif flask.request.method == "POST":
        try:
            score = form_to_score(match, flask.request.form)
        except ValueError:
            return flask.render_template("update.html",
                                         error="Invalid input.",
                                         **template_settings)

        try:
            compstate.reset_and_fast_forward()
            update_and_validate(compstate, match, score)
            commit_and_push(compstate, match)
        except RuntimeError as e:
            return flask.render_template("update.html",
                                         error=str(e),
                                         **template_settings)
        else:
            return flask.redirect(url_for('update', arena=arena, num=num) +
                                  '?done=true')

    return flask.render_template("update.html",
                                 done=flask.request.args.get("done", False),
                                 **template_settings)
