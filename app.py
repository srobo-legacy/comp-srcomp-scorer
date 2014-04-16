#!/usr/bin/env python2
import argparse
import flask
import os
import srcomp
import subprocess
import yaml


PATH = os.path.dirname(os.path.abspath(__file__))

parser = argparse.ArgumentParser(description="SR Match Score input")
parser.add_argument("-c", "--compstate", default=PATH + "/compstate",
                    help="Competition state git repository path")
args = parser.parse_args()

app = flask.Flask(__name__)
app.debug = True


@app.route("/")
def index():
    return flask.render_template("index.html")


@app.route("/review")
def review():
    return flask.render_template("review.html")


@app.route("/submit")
def submit():
    return flask.render_template("submit.html")


@app.route("/submit/<category>")
def submit_category(category):
    return flask.render_template("submit_category.html", category=category)

@app.route("/submit/<category>/<arena>", methods=["GET", "POST"])
def submit_category_arena(category, arena):
    def form_to_srcomp(form):
        def form_team_to_scrcomp(corner, teams):
            tla = form["team_tla_{}".format(corner)]
            if tla:
                teams[tla] = {
                    "zone": corner,
                    "disqualified": "robot_disqualified_{}".format(corner) in form,
                    "present": "robot_absent_{}".format(corner) not in form,
                    "robot_moved": "robot_moved_{}".format(corner) in form,
                    "upright_tokens": int(form["upright_tokens_{}".format(corner)]),
                    "zone_tokens": {
                        0: int(form["zone_tokens_0_{}".format(corner)]),
                        1: int(form["zone_tokens_1_{}".format(corner)]),
                        2: int(form["zone_tokens_2_{}".format(corner)]),
                        3: int(form["zone_tokens_3_{}".format(corner)])
                    },
                    "slot_bottoms": {
                        0: 1 if "slot_bottoms_0_{}".format(corner) in form else 0,
                        1: 1 if "slot_bottoms_1_{}".format(corner) in form else 0,
                        2: 1 if "slot_bottoms_2_{}".format(corner) in form else 0,
                        3: 1 if "slot_bottoms_3_{}".format(corner) in form else 0,
                        4: 1 if "slot_bottoms_4_{}".format(corner) in form else 0,
                        5: 1 if "slot_bottoms_5_{}".format(corner) in form else 0,
                        6: 1 if "slot_bottoms_6_{}".format(corner) in form else 0,
                        7: 1 if "slot_bottoms_7_{}".format(corner) in form else 0,
                    },
                }

        teams = {}
        form_team_to_scrcomp(0, teams)
        form_team_to_scrcomp(1, teams)
        form_team_to_scrcomp(2, teams)
        form_team_to_scrcomp(3, teams)

        return {
            "arena_id": arena,
            "match_number": int(form["match_number"]),
            "teams": teams
        }

    if flask.request.method == "POST":
        try:
            result = form_to_srcomp(flask.request.form)
        except ValueError:
            return flask.render_template("submit.html", category=category,
                                         error="Please check through your inputs.")
        else:
            subprocess.call(["git", "reset", "--hard", "HEAD"], cwd=args.compstate)
            subprocess.call(["git", "pull", "origin", "master"], cwd=args.compstate)
            path = "{0}/{1}/{2}/{3:0>3}.yaml".format(args.compstate,
                                             category,
                                             arena,
                                             int(flask.request.form["match_number"]))
            with open(path, "w") as fd:
                fd.write(yaml.safe_dump(result))
            subprocess.call(["git", "add", path], cwd=args.compstate)
            subprocess.call(["git", "commit", "-m", "update {} scores".format(category)], cwd=args.compstate)
            subprocess.call(["git", "push", "origin", "master"], cwd=args.compstate)

        return yaml.safe_dump(result)
    else:
        comp = srcomp.SRComp(args.compstate)
        match = comp.schedule.current_match(arena)
        if match:
            flask.request.form = {
                "match_number": match.num,
                "team_tla_0": match.teams[0],
                "team_tla_1": match.teams[1],
                "team_tla_2": match.teams[2],
                "team_tla_3": match.teams[3],
            }

        return flask.render_template("submit_category_arena.html", category=category, arena=arena)


if __name__ == "__main__":
    app.run(port=3000)
