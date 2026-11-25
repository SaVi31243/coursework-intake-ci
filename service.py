import os
import re

from flask import Blueprint, Flask, g, request

from observability import configure, emit
from release import VERSION, notify
from repository import Register


api = Blueprint("intake", __name__)
GROUP_CODE = re.compile(r"SE-[0-9]{2}")


@api.get("/health")
def health():
    return {"status": "ok", "version": VERSION}


@api.get("/submissions/<int:number>")
def find(number):
    record = g.register.lookup(number)
    if record is None:
        return {"error": "Unknown submission number"}, 404
    return record


@api.post("/submissions")
def submit():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return {"error": "Expected a JSON object"}, 400
    group = data.get("group_code")
    key = data.get("submission_key")
    if not isinstance(group, str) or GROUP_CODE.fullmatch(group) is None:
        return {"error": "Use a group code matching SE-NN"}, 400
    if not isinstance(key, str) or not key.strip() or len(key) > 64:
        return {"error": "Use a key of 1 to 64 characters"}, 400

    registration = g.register.register(group, key)
    g.number = registration.number
    if registration.group != group:
        return {"error": "Key belongs to another group"}, 409

    answer = {"id": registration.number}
    if not registration.created:
        return answer, 200

    emit(VERSION, "submission_saved", 201)
    try:
        receipt = notify(registration.number, g.confirmation_enabled)
    except ConnectionError:
        emit(VERSION, "confirmation_failed", 503)
        return {**answer, "error": "Confirmation endpoint unreachable"}, 503
    if receipt is not None:
        answer["confirmation"] = receipt
        emit(VERSION, "confirmation_sent", 201)
    return answer, 201


def create_app():
    app = Flask(__name__)
    register = Register(os.getenv("SUBMIT_DB", "intake.sqlite"))
    confirmation_enabled = os.getenv("CONFIRMATION_ENABLED", "1") == "1"
    configure(app, VERSION)

    @app.before_request
    def bind_services():
        g.register = register
        g.confirmation_enabled = confirmation_enabled

    app.register_blueprint(api)
    return app
