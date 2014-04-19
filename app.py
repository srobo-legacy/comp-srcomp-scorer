#!/usr/bin/env python2
import argparse
import flask
import os
import os.path
import srcomp
import subprocess
import yaml


PATH = os.path.dirname(os.path.abspath(__file__))

parser = argparse.ArgumentParser(description="SR Competition Scorer")
parser.add_argument("-c", "--compstate", default=PATH + "/compstate",
                    help="Competition state git repository path")
args = parser.parse_args()

app = flask.Flask(__name__)
app.debug = True
app.jinja_env.globals.update(int=int)


def get_score_path(match):
    return "{0}/{1}/{2}/{3:0>3}.yaml".format(args.compstate, match.type,
                                             match.arena, match.num)


def get_competition():
    return srcomp.SRComp(args.compstate)


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
        tla = form["team_tla_{}".format(zone)]
        if tla:
            team = {
                "zone": zone,
                "disqualified": form.get("disqualified_{}".format(zone), None) is not None,
                "present": form.get("absent_{}".format(zone), None) is not None,
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

        for j in range(4):
            form["zone_tokens_{}_{}".format(j, i)] = info["zone_tokens"][j]

        for j in range(8):
            if info["slot_bottoms"][j]:
                form["slot_bottoms_{}".format(j)] = True

    return form


@app.route("/")
def index():
    comp = get_competition()
    return flask.render_template("index.html", matches=comp.schedule.matches)


@app.route("/<arena>/<int:num>", methods=["GET", "POST"])
def update(arena, num):
    comp = get_competition()

    try:
        match = comp.schedule.matches[num][arena]
    except (IndexError, KeyError):
        return flask.redirect("/")  # TODO: could show an error message here

    if flask.request.method == "GET":
        score = load_score(match)
        flask.request.form = score_to_form(score)
    elif flask.request.method == "POST":
        try:
            score = form_to_score(match, flask.request.form)
        except ValueError:
            return flask.render_template("update.html", match=match,
                                         error="Invalid input.")

        try:
            subprocess.check_call(["git", "reset", "--hard", "HEAD"],
                                    cwd=args.compstate)
            subprocess.check_call(["git", "pull", "--ff-only", "origin",
                                    "master"], cwd=args.compstate)
            save_score(match, score)
            path = get_score_path(match)
            #subprocess.check_call(["git", "add", path], cwd=args.compstate)
            # TODO: validate competition state
            #commit_msg = "update {} scores for arena {}".format(category,
            #                                                    arena)
            #subprocess.check_call(["git", "commit", "-m", commit_msg],
            #                        cwd=args.compstate)
            #subprocess.check_call(["git", "push", "origin", "master"],
            #                        cwd=args.compstate)
        except (OSError, subprocess.CalledProcessError) as e:
            error = "Git error ({}), try commiting manually.".format(e)
            return flask.render_template("update.html", match=match,
                                         error=error)
        else:
            return flask.redirect("/{}/{}".format(arena, num))

    return flask.render_template("update.html", match=match)


if __name__ == "__main__":
    app.run(port=3000)
