"""
src/stage2_jev_ranking/jev_client.py

MOCK CLIENT. THIS IS NOT THE REAL TYPESAFE JEV API.

This project does not have a TypeSafe API key, so this file simulates
what calling the real JEV model would look like, matching the real
SDK's request shape as closely as possible, a "state" (the facts JEV is
allowed to use to answer) plus a "questions" dictionary of typed
questions (Choice, Score), and it returns a calibrated style answer with
a confidence number for each question, the same shape the real API
returns.

This mock is not pure random noise. The caller can attach a bias_hint, a
rough number from 0.0 to 1.0, worked out from simple real facts, for
example how many genres overlap between the user's taste and this
movie. The mock blends that hint with a bit of deterministic pseudo
randomness, to roughly behave the way a model that actually looked at
the facts might, without pretending to be an actual trained model.

Every number that comes out of this file is a stand in for a real JEV
call, not a measured result. Swapping this file for a real TypeSafe SDK
call later should not require changing anything else in stage 2, that
is the whole point of mirroring the real request shape here.
"""

import hashlib

# These numbers describe how the MOCK behaves. They are not product settings
# and do not belong in config/weights.py. A real JEV model would return its
# own confidence, so none of this exists in the real SDK.
NOISE_RANGE = 0.3  # how much the mock is allowed to wobble around the bias hint
MOCK_CONFIDENCE_FLOOR = 0.6   # the lowest confidence the mock ever reports
MOCK_CONFIDENCE_SPAN = 0.35   # confidence is spread over floor to floor + span


class Score:
    """Mirrors the real SDK's Score question type, expects a 0.0 to 1.0 answer."""
    def __init__(self, question_text, bias_hint=0.5):
        self.question_text = question_text
        self.question_type = "score"
        self.bias_hint = max(0.0, min(1.0, bias_hint))


class Choice:
    """Mirrors the real SDK's Choice question type, expects one of a fixed set of options."""
    def __init__(self, question_text, options, bias_hint=0.5):
        self.question_text = question_text
        self.options = options
        self.question_type = "choice"
        self.bias_hint = max(0.0, min(1.0, bias_hint))


def _deterministic_pseudo_random(seed_text):
    """
    Turns any text into a reproducible number between 0 and 1. Using a
    hash instead of random.random() means the same state and question
    always produce the same mock answer, which matters for a mock,
    results should be reproducible every time you re run the project.
    """
    digest = hashlib.sha256(seed_text.encode("utf-8")).hexdigest()
    return int(digest[:8], 16) / 0xFFFFFFFF


def ask(state, questions):
    """
    state: dict describing the content and user facts JEV is allowed to use.
    questions: dict of question_key mapped to a Score(...) or Choice(...)

    Returns: dict of question_key mapped to {"answer": ..., "confidence": float}

    This mock never looks at the internet and never calls any outside
    service, it only derives an answer from the bias hint plus a small
    amount of noise taken from the text already inside state, combined
    with the question key, so answers stay consistent for the same input.
    """
    state_fingerprint = str(sorted(state.items()))
    answers = {}

    for key, question in questions.items():
        seed_text = state_fingerprint + key
        pseudo_random_value = _deterministic_pseudo_random(seed_text)

        # Confidence gets its own hash on purpose. If it was built from the
        # same number as the answer, a confident answer and a "yes" answer
        # would be tied together, and the confidence gate in rank.py would
        # pass far more often than it should.
        confidence_value = _deterministic_pseudo_random(seed_text + "|confidence")
        confidence = round(MOCK_CONFIDENCE_FLOOR + confidence_value * MOCK_CONFIDENCE_SPAN, 3)

        if question.question_type == "score":
            wobble = (pseudo_random_value - 0.5) * NOISE_RANGE
            answer = max(0.0, min(1.0, question.bias_hint + wobble))
            answers[key] = {
                "question": question.question_text,
                "answer": round(answer, 3),
                "confidence": confidence,
            }
        elif question.question_type == "choice":
            answers[key] = {
                "question": question.question_text,
                "answer": _pick_option(question, pseudo_random_value, seed_text),
                "confidence": confidence,
            }

    return answers


def _pick_option(question, pseudo_random_value, seed_text):
    """
    The first option is treated as the positive option by convention. It is
    picked only when the pseudo random value falls below the bias hint, so a
    bias hint of 0.1 gives the first option about 10 percent of the time.
    Otherwise one of the remaining options is picked using a second, separate
    hash, so the choice stays deterministic but is not tied to the first one.
    """
    options = question.options
    if pseudo_random_value < question.bias_hint or len(options) == 1:
        return options[0]

    other_options = options[1:]
    second_value = _deterministic_pseudo_random(seed_text + "|alternative")
    return other_options[int(second_value * len(other_options)) % len(other_options)]
