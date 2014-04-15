#!/usr/bin/env python3
import flask
import srcomp
import yaml


app = flask.Flask(__name__)
app.debug = True
comp = srcomp.SRComp("compstate")


@app.route("/")
def index():
    return flask.render_template("index.html")


@app.route("/review")
def review():
    return flask.render_template("review.html")


@app.route("/submit", methods=["GET", "POST"])
def submit():
    def form_to_srcomp(form):
        def form_team_to_scrcomp(corner, teams):
            tla = form["team_tla_{}".format(corner)]
            if tla:
                print(form)
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
            "arena_id": form["arena"],
            "match_number": int(form["match_number"]),
            "teams": teams
        }

    if flask.request.method == "POST":
        try:
            result = form_to_srcomp(flask.request.form)
        except ValueError:
            return flask.render_template("submit.html")

        return yaml.safe_dump(result)
    else:
        return flask.render_template("submit.html")


if __name__ == "__main__":
    app.run(port=3000)
