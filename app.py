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


def get_scores_path(category, arena):
    return "{}/{}/{}".format(args.compstate, category, arena)


def get_score_path(category, arena, match_number):
    scores_path = get_scores_path(category, arena)
    return "{0}/{1:0>3}.yaml".format(scores_path, match_number)


def get_current_match(arena):
    comp = srcomp.SRComp(args.compstate)
    return comp.schedule.current_match(arena)


def list_scores(category, arena):
    path = get_scores_path(category, arena)
    try:
        files = (os.path.splitext(x)[0] for x in os.listdir(path))
    except OSError:
        # directory doesn't exist
        return []
    else:
        return sorted(map(int, files))


def load_score(category, arena, match_number):
    path = get_score_path(category, arena, match_number)
    with open(path) as fd:
        return yaml.safe_load(fd)


def save_score(category, arena, match_number, score):
    path = get_score_path(category, arena, match_number)

    dirname = os.path.dirname(path)
    if not os.path.exists(dirname):
        os.makedirs(dirname)

    with open(path, "w") as fd:
        fd.write(yaml.safe_dump(score))


def form_to_score(arena, match_number, form):
    def form_team_to_scrcomp(zone, teams):
        tla = form["team_tla_{}".format(zone)]
        if tla:
            team = {
                "zone": zone,
                "disqualified": "disqualified_{}".format(zone) in form,
                "present": "absent_{}".format(zone) not in form,
                "robot_moved": "robot_moved_{}".format(zone) in form,
                "upright_tokens": int(form["upright_tokens_{}".format(zone)]),
                "zone_tokens": {},
                "slot_bottoms": {}
            }

            for i in range(4):
                v = form["zone_tokens_{}_{}".format(i, zone)]
                team["zone_tokens"][i] = int(v)

            for i in range(8):
                v = form.get("slot_bottoms_{}_{}".format(i, zone), False)
                team["slot_bottoms"][i] = 1 if v else 0

            teams[tla] = team

    teams = {}
    form_team_to_scrcomp(0, teams)
    form_team_to_scrcomp(1, teams)
    form_team_to_scrcomp(2, teams)
    form_team_to_scrcomp(3, teams)

    return {
        "arena_id": arena,
        "match_number": match_number or int(form["match_number"]),
        "teams": teams
    }


def match_to_form(match):
    return {
        "match_number": match.num,
        "team_tla_0": match.teams[0],
        "team_tla_1": match.teams[1],
        "team_tla_2": match.teams[2],
        "team_tla_3": match.teams[3],
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
            form["slot_bottoms_{}_{}".format(j, i)] = info["slot_bottoms"][j]

    return form


@app.route("/")
@app.route("/review")
@app.route("/review/league")
@app.route("/review/knockout")
@app.route("/submit")
@app.route("/submit/league")
@app.route("/submit/knockout")
def navigation():
    return flask.render_template("navigation.html")


@app.route("/review/<category>/<arena>")
def review(category, arena):
    scores = list_scores(category, arena)
    return flask.render_template("review.html", category=category, arena=arena,
                                 scores=scores)


@app.route("/submit/<category>/<arena>", defaults={"match_number": None},
           methods=["GET", "POST"])
@app.route("/submit/<category>/<arena>/<int:match_number>",
           methods=["GET", "POST"])
def submit(category, arena, match_number):
    if flask.request.method == "POST":
        try:
            score = form_to_score(category, arena, flask.request.form)
        except ValueError:
            return flask.render_template("submit.html", category=category,
                                         arena=arena, error="Invalid input.",
                                         match_number=match_number)
        else:
            try:
                subprocess.check_call(["git", "reset", "--hard", "HEAD"],
                                      cwd=args.compstate)
                subprocess.check_call(["git", "pull", "--ff-only", "origin",
                                       "master"], cwd=args.compstate)
                n = match_number or int(flask.request.form["match_number"])
                save_score(category, arena, n, score)
                path = get_score_path(category, arena, match_number)
                subprocess.check_call(["git", "add", path], cwd=args.compstate)
                commit_msg = "update {} scores for arena {}".format(category,
                                                                    arena)
                # TODO: validate competition state
                subprocess.check_call(["git", "commit", "-m", commit_msg],
                                      cwd=args.compstate)
                subprocess.check_call(["git", "push", "origin", "master"],
                                      cwd=args.compstate)
            except (OSError, subprocess.CalledProcessError) as e:
                error = "Git error ({}), try commiting manually.".format(e)
                return flask.render_template("submit.html", category=category,
                                             arena=arena, error=error,
                                             match_number=match_number)
            else:
                return flask.redirect("/submit/{}/{}/{}".format(category,
                                                                arena,
                                                                match_number))
    else:
        if match_number is not None:
            score = load_score(category, arena, match_number)
            flask.request.form = score_to_form(score)
        else:
            match = get_current_match(arena)
            if match:
                flask.request.form = match_to_form(match)

        return flask.render_template("submit.html",
                                     category=category, arena=arena,
                                     match_number=match_number)


if __name__ == "__main__":
    app.run(port=3000)
