import os

from . import ai
from .models import MAX_TRANSCRIPT_LENGTH, PART_RULES, SpeakingAttempt


def _transcribe(answers):
    """Turn the recordings into text on the server when that is set up (Groq's Whisper): it hears more exactly than
    the browser and works in every browser. What Whisper hears replaces what the browser heard; an answer it hears
    nothing in keeps the browser's text. Returns why the service failed, or "" when it did not."""
    if not ai.can_transcribe():
        return ''
    for answer in answers:
        if not answer.audio or not os.path.exists(answer.audio.path):
            continue
        try:
            text, confidence = ai.transcribe(answer.audio.path, answer.audio_content_type)
        except ai.RecordingRejected:
            continue  # this file cannot be turned into text: what the browser heard is all there is
        except ai.FeedbackError as error:
            return f'Answer {answer.number} could not be turned into text: {error}'
        text = text[:MAX_TRANSCRIPT_LENGTH].strip()
        if text:
            answer.transcript, answer.confidence = text, confidence
            answer.save(update_fields=['transcript', 'confidence'])
    return ''


def analyse_attempt(attempt):
    """Ask the AI for feedback on the attempt's answers and keep it (or why there is none) with the attempt.

    Never raises: the results page shows whatever state this leaves behind, and a failed request can be retried.
    """
    status = SpeakingAttempt.Feedback
    answers = list(attempt.answers.all())
    attempt.feedback_error = ''
    problem = _transcribe(answers)
    allowed = (PART_RULES[attempt.set.part]['session'] or {}).get('talk', 0)
    items = [
        {
            'number': answer.number, 'question': answer.question, 'transcript': answer.transcript.strip(),
            'seconds': answer.seconds, 'allowed': allowed, 'confidence': answer.confidence,
        }
        for answer in answers if answer.transcript.strip()
    ]
    if problem:
        attempt.feedback_status = status.FAILED
        attempt.feedback_error = problem[:300]
    elif not items:
        attempt.feedback_status = status.EMPTY
    else:
        try:
            feedback = ai.request_feedback(items)
        except ai.FeedbackNotConfigured:
            attempt.feedback_status = status.UNCONFIGURED
        except ai.FeedbackError as error:
            attempt.feedback_status = status.FAILED
            attempt.feedback_error = str(error)[:300]
        else:
            for answer in answers:
                answer.feedback = feedback.get(answer.number, {})
                answer.save(update_fields=['feedback'])
            attempt.feedback_status = status.READY
    attempt.save(update_fields=['feedback_status', 'feedback_error'])
    return attempt.feedback_status
