#!/usr/bin/env python2
import argparse
import itertools
import collections
import flask
import itertools
import os
import os.path
import srcomp
import srcomp.validation
import subprocess
import yaml


PATH = os.path.dirname(os.path.abspath(__file__))

app = flask.Flask(__name__)
app.debug = True
app.jinja_env.globals.update(int=int, map=map)


def grouper(iterable, n, fillvalue=None):
    "Collect data into fixed-length chunks or blocks"
    # grouper('ABCDEFG', 3, 'x') --> ABC DEF Gxx
    args = [iter(iterable)] * n
    return itertools.izip_longest(fillvalue=fillvalue, *args)
app.jinja_env.globals.update(grouper=grouper)


def group_list_dict(matches):
    """
    Group a list of dictionaries into a dictionary of lists.

    This will convert
        [{"A": a, "B": b}, {"A": a2, "B": b2}]
    into
        {"A": [a, a2], "B": [b, b2]}
    """
    target = collections.defaultdict(list)
    for k, v in itertools.chain.from_iterable(d.items() if d else [] for d in matches):
        target[k].append(v)
    return target
app.jinja_env.globals.update(group_list_dict=group_list_dict)


def is_match_done(match):
    try:
        load_score(match)
        return True
    except IOError:
        return False
app.jinja_env.globals.update(is_match_done=is_match_done)


def get_score_path(match):
    return "{0}/{1}/{2}/{3:0>3}.yaml".format(app.config['COMPSTATE'], match.type,
                                             match.arena, match.num)


def get_competition():
    return srcomp.SRComp(app.config['COMPSTATE'])


def load_score(match):
    path = get_score_path(match)
    with open(path) as fd:
        return yaml.safe_load(fd)


def save_score(match, score):
    path = get_score_path(match)

    dirname = os.path.dirname(path)
    if not os.path.exists(dirname):
        os.makedirs(dirname)

    with open(path, "w") as fd:
        fd.write(yaml.safe_dump(score))


def form_to_score(match, form):
    def form_team_to_score(zone, teams):
        tla = form.get("team_tla_{}".format(zone), None)
        if tla:
            team = {
                "zone": zone,
                "disqualified": form.get("disqualified_{}".format(zone), None) is not None,
                "present": form.get("absent_{}".format(zone), None) is None,
                "robot_moved": form.get("robot_moved_{}".format(zone), None) is not None,
                "upright_tokens": int(form["upright_tokens_{}".format(zone)]),
                "zone_tokens": {},
                "slot_bottoms": {x: 0 for x in range(8)}
            }

            for i in range(4):
                v = form["zone_tokens_{}_{}".format(i, zone)]
                team["zone_tokens"][i] = int(v)

            for i in range(8):
                selected_zone = int(form.get("slot_bottoms_{}".format(i), -1))
                if selected_zone == zone:
                    team["slot_bottoms"][i] = 1

            teams[tla] = team

    teams = {}
    form_team_to_score(0, teams)
    form_team_to_score(1, teams)
    form_team_to_score(2, teams)
    form_team_to_score(3, teams)

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
        form["robot_moved_{}".format(i)] = info.get("robot_moved", True)
        form["upright_tokens_{}".format(i)] = info.get("upright_tokens", True)

        for j in range(4):
            form["zone_tokens_{}_{}".format(j, i)] = info["zone_tokens"][j]

        for j in range(8):
            if info["slot_bottoms"][j]:
                form["slot_bottoms_{}".format(j)] = i

    return form


def reset_compstate():
    try:
        subprocess.check_call(["git", "reset", "--hard", "HEAD"],
                              cwd=app.config['COMPSTATE'])
    except (OSError, subprocess.CalledProcessError):
        raise RuntimeError("Git reset failed.")


def reset_and_pull_compstate():
    reset_compstate()

    if app.config['COMPSTATE_LOCAL']:
        return

    try:
        subprocess.check_call(["git", "pull", "--ff-only", "origin", "master"],
                              cwd=app.config['COMPSTATE'])
    except (OSError, subprocess.CalledProcessError):
        raise RuntimeError("Git pull failed, deal with the merge manually.")


def update_and_validate_compstate(match, score):
    save_score(match, score)

    path = get_score_path(match)
    subprocess.check_call(["git", "add", path], cwd=app.config['COMPSTATE'])

    try:
        comp = get_competition()
    except Exception as e:  # SRComp sometimes throws generic Exceptions
        # we have to reset the repo because SRComp fails to instantiate and that
        # would break everything!
        reset_compstate()
        raise RuntimeError(e)
    else:
        i = srcomp.validation.validate(comp)
        if i > 0:
            raise RuntimeError(str(i))


def commit_and_push_compstate(match):
    commit_msg = "update {} scores for match {} in arena {}".format(match.type,
                                                                    match.num,
                                                                    match.arena)

    try:
        subprocess.check_call(["git", "commit", "-m", commit_msg],
                            cwd=app.config['COMPSTATE'])
        if app.config['COMPSTATE_LOCAL']:
            return
        subprocess.check_call(["git", "push", "origin", "master"],
                            cwd=app.config['COMPSTATE'])
    except (OSError, subprocess.CalledProcessError):
        raise RuntimeError("Git push failed, deal with the merge manually.")


@app.route("/")
def index():
    comp = get_competition()
    current_matches = {arena: comp.schedule.current_match(arena) for arena in comp.arenas}
    return flask.render_template("index.html", matches=comp.schedule.matches,
                                 current_matches=current_matches)


@app.route("/<arena>/<int:num>", methods=["GET", "POST"])
def update(arena, num):
    comp = get_competition()

    try:
        match = comp.schedule.matches[num][arena]
    except (IndexError, KeyError):
        return flask.redirect("/")  # TODO: could show an error message here

    if flask.request.method == "GET":
        try:
            score = load_score(match)
        except IOError:
            pass
        else:
            flask.request.form = score_to_form(score)
    elif flask.request.method == "POST":
        try:
            score = form_to_score(match, flask.request.form)
        except ValueError:
            return flask.render_template("update.html", match=match,
                                         error="Invalid input.")

        try:
            reset_and_pull_compstate()
            update_and_validate_compstate(match, score)
            commit_and_push_compstate(match)
        except RuntimeError as e:
            return flask.render_template("update.html", match=match,
                                         error=str(e))
        else:
            return flask.redirect("/{}/{}?done=true".format(arena, num))

    return flask.render_template("update.html", match=match, done=flask.request.args.get("done", False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="SR Competition Scorer")
    parser.add_argument("-c", "--compstate", default=PATH + "/compstate",
                        help="Competition state git repository path")
    parser.add_argument('-l', '--local', action='store_true',
                        help="Disable fetch and push")
    args = parser.parse_args()
    app.config['COMPSTATE'] = args.compstate
    app.config['COMPSTATE_LOCAL'] = args.local
    app.run(port=3000)
