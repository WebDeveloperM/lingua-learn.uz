import email
import http.client
import io
import json
import math
import os
import tempfile
import urllib.error
from unittest import mock

from django.test import SimpleTestCase, override_settings

from . import ai

ITEMS = [
    {'number': 1, 'question': 'What do you do on the weekends?', 'transcript': 'I play football.', 'seconds': 21.4,
     'allowed': 30, 'confidence': 0.876},
    {'number': 3, 'question': 'What kind of movies do you like?', 'transcript': 'Comedy, because it is fun. Á', 'seconds': 30.0,
     'allowed': 30, 'confidence': None},
]
FIELDS = {field: f'{field} text' for field in ai.FIELDS}


def reply(answers):
    return {
        'id': 'msg_1', 'type': 'message', 'role': 'assistant', 'stop_reason': 'tool_use',
        'content': [
            {'type': 'text', 'text': 'Here is the feedback.'},
            {'type': 'tool_use', 'id': 'toolu_1', 'name': 'report_feedback', 'input': {'answers': answers}},
        ],
    }


def good_reply():
    return reply([{'number': 1, **FIELDS}, {'number': 3, **FIELDS}])


def groq_reply(content, finish_reason='stop'):
    """What Groq's chat completions answer: the model's JSON comes as the text of the message."""
    if not isinstance(content, str):
        content = json.dumps(content)
    return {
        'id': 'chatcmpl-1', 'object': 'chat.completion', 'model': 'openai/gpt-oss-120b',
        'choices': [{'index': 0, 'message': {'role': 'assistant', 'content': content}, 'finish_reason': finish_reason}],
        'usage': {'prompt_tokens': 900, 'completion_tokens': 700, 'total_tokens': 1600},
    }


def good_groq_reply():
    return groq_reply({'answers': [{'number': 1, **FIELDS}, {'number': 3, **FIELDS}]})


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def read(self):
        return self.payload if isinstance(self.payload, bytes) else json.dumps(self.payload).encode('utf-8')

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def http_error(code, message='bad request', body=None, retry_after=None):
    if body is None:
        body = json.dumps({'type': 'error', 'error': {'type': 'invalid_request_error', 'message': message}}).encode()
    headers = http.client.HTTPMessage()
    if retry_after is not None:
        headers['Retry-After'] = retry_after
    return urllib.error.HTTPError('https://api.example.test/v1/messages', code, 'Reason Phrase', headers, io.BytesIO(body))


CONFIGURED = override_settings(
    ANTHROPIC_API_KEY='test-key', ANTHROPIC_BASE_URL='https://api.example.test', SPEAKING_AI_MODEL='test-model',
    SPEAKING_FEEDBACK_LANGUAGE='Uzbek', GROQ_API_KEY='',
)
GROQ = override_settings(
    ANTHROPIC_API_KEY='', GROQ_API_KEY='gsk-test-key', GROQ_BASE_URL='https://groq.example.test/openai/v1',
    GROQ_MODEL='openai/gpt-oss-120b', GROQ_TRANSCRIPTION_MODEL='whisper-test', SPEAKING_FEEDBACK_LANGUAGE='Uzbek',
)


@CONFIGURED
class RequestTests(SimpleTestCase):
    def ask(self, urlopen_result):
        with mock.patch('speaking.ai.urllib.request.urlopen', side_effect=urlopen_result) as urlopen, \
                mock.patch('speaking.ai.time.sleep') as sleep:
            result = ai.request_feedback(ITEMS)
        return result, urlopen, sleep

    def test_the_request_to_the_api(self):
        result, urlopen, sleep = self.ask([FakeResponse(good_reply())])
        request = urlopen.call_args.args[0]
        self.assertEqual((request.full_url, request.get_method()), ('https://api.example.test/v1/messages', 'POST'))
        self.assertEqual(request.get_header('X-api-key'), 'test-key')
        self.assertEqual(request.get_header('Anthropic-version'), '2023-06-01')
        self.assertEqual(request.get_header('Content-type'), 'application/json')
        self.assertEqual(request.get_header('User-agent'), ai.USER_AGENT)  # not "Python-urllib", which Cloudflare refuses
        self.assertEqual(urlopen.call_args.kwargs['timeout'], ai.TIMEOUT_SECONDS)
        sleep.assert_not_called()

    def test_the_body_asks_for_one_report_in_the_set_language(self):
        _, urlopen, _ = self.ask([FakeResponse(good_reply())])
        body = json.loads(urlopen.call_args.args[0].data)
        self.assertEqual(body['model'], 'test-model')
        self.assertEqual(body['max_tokens'], ai.MAX_TOKENS)
        self.assertEqual(body['tool_choice'], {'type': 'tool', 'name': 'report_feedback'})
        tool = body['tools'][0]
        self.assertEqual(tool['name'], 'report_feedback')
        item = tool['input_schema']['properties']['answers']['items']
        self.assertEqual(item['required'], ['number', *ai.FIELDS])
        self.assertEqual(sorted(item['properties']), sorted(['number', *ai.FIELDS]))
        self.assertIn('in Uzbek', body['system'])
        self.assertNotIn('{language}', body['system'])
        self.assertIn('You cannot hear the learner', body['system'])
        self.assertTrue(body['system'].endswith(ai.TOOL_ANSWER))

    def test_the_message_has_every_answer_with_what_the_recogniser_knows(self):
        _, urlopen, _ = self.ask([FakeResponse(good_reply())])
        body = json.loads(urlopen.call_args.args[0].data)
        self.assertEqual(len(body['messages']), 1)
        message = body['messages'][0]
        self.assertEqual(message['role'], 'user')
        sent = json.loads(message['content'].split('\n\n', 1)[1])
        self.assertEqual(sent, {'answers': [
            {'number': 1, 'question': 'What do you do on the weekends?', 'transcript': 'I play football.',
             'seconds_spoken': 21, 'seconds_allowed': 30, 'recogniser_confidence': 0.88},
            {'number': 3, 'question': 'What kind of movies do you like?', 'transcript': 'Comedy, because it is fun. Á',
             'seconds_spoken': 30, 'seconds_allowed': 30, 'recogniser_confidence': None},
        ]})
        self.assertIn('Á', message['content'])  # sent as it is, not as Á

    def test_the_feedback_is_given_per_answer_number(self):
        result, _, _ = self.ask([FakeResponse(good_reply())])
        self.assertEqual(result, {1: FIELDS, 3: FIELDS})

    def test_numbers_that_were_not_asked_and_repeats_are_ignored(self):
        answers = [
            {'number': '1', **{**FIELDS, 'summary': 'first'}}, {'number': 1, **{**FIELDS, 'summary': 'second'}},
            {'number': 2, **FIELDS}, {'number': 'x', **FIELDS}, {**FIELDS}, None, {'number': 3, **FIELDS},
        ]
        result, _, _ = self.ask([FakeResponse(reply(answers))])
        self.assertEqual(sorted(result), [1, 3])
        self.assertEqual(result[1]['summary'], 'first')

    def test_missing_fields_are_empty_and_long_ones_are_cut(self):
        answers = [{'number': 1, 'summary': 'x' * 2000, 'grammar': '  fine  '}]
        result, _, _ = self.ask([FakeResponse(reply(answers))])
        self.assertEqual(len(result[1]['summary']), ai.MAX_FIELD_LENGTH)
        self.assertEqual(result[1]['grammar'], 'fine')
        self.assertEqual((result[1]['vocabulary'], result[1]['try_saying']), ('', ''))

    def test_an_answer_without_the_report_is_an_error(self):
        for payload in (
            {'content': [{'type': 'text', 'text': 'I cannot do this.'}]},
            {'content': []}, {}, [], reply([]), reply([{'number': 9, **FIELDS}]), reply({'number': 1}),
            {'content': [{'type': 'tool_use', 'name': 'other_tool', 'input': {'answers': [{'number': 1, **FIELDS}]}}]},
        ):
            with self.subTest(payload=payload), self.assertRaises(ai.FeedbackError):
                self.ask([FakeResponse(payload)])

    def test_without_a_key_nothing_is_asked(self):
        with override_settings(ANTHROPIC_API_KEY='', GROQ_API_KEY=''), \
                mock.patch('speaking.ai.urllib.request.urlopen') as urlopen, self.assertRaises(ai.FeedbackNotConfigured):
            ai.request_feedback(ITEMS)
        urlopen.assert_not_called()

    def test_claude_writes_the_feedback_even_when_there_is_a_groq_key_too(self):
        with override_settings(GROQ_API_KEY='gsk-test-key'):
            result, urlopen, _ = self.ask([FakeResponse(good_reply())])
        self.assertEqual(urlopen.call_args.args[0].full_url, 'https://api.example.test/v1/messages')
        self.assertEqual(result, {1: FIELDS, 3: FIELDS})


@GROQ
class GroqFeedbackTests(SimpleTestCase):
    """Without a Claude key the free Groq service writes the feedback (JSON in the answers schema)."""

    def ask(self, *results):
        with mock.patch('speaking.ai.urllib.request.urlopen', side_effect=list(results)) as urlopen, \
                mock.patch('speaking.ai.time.sleep') as sleep:
            try:
                return ai.request_feedback(ITEMS), urlopen, sleep
            except ai.FeedbackError as error:
                return error, urlopen, sleep

    def body(self, urlopen):
        return json.loads(urlopen.call_args.args[0].data)

    def test_the_request_to_groq(self):
        _, urlopen, sleep = self.ask(FakeResponse(good_groq_reply()))
        request = urlopen.call_args.args[0]
        self.assertEqual((request.full_url, request.get_method()),
                         ('https://groq.example.test/openai/v1/chat/completions', 'POST'))
        self.assertEqual(request.get_header('Authorization'), 'Bearer gsk-test-key')
        self.assertEqual(request.get_header('Content-type'), 'application/json')
        self.assertEqual(request.get_header('User-agent'), ai.USER_AGENT)
        self.assertIsNone(request.get_header('X-api-key'))
        self.assertEqual(urlopen.call_args.kwargs['timeout'], ai.TIMEOUT_SECONDS)
        sleep.assert_not_called()

    def test_the_body_asks_for_json_in_the_answers_schema(self):
        _, urlopen, _ = self.ask(FakeResponse(good_groq_reply()))
        body = self.body(urlopen)
        self.assertEqual(body['model'], 'openai/gpt-oss-120b')
        self.assertEqual(body['response_format'], {
            'type': 'json_schema',
            'json_schema': {'name': 'report_feedback', 'strict': True, 'schema': ai.ANSWERS_SCHEMA},
        })
        item = body['response_format']['json_schema']['schema']['properties']['answers']['items']
        self.assertEqual(item['required'], ['number', *ai.FIELDS])  # strict: every field is required
        self.assertIs(item['additionalProperties'], False)
        self.assertIs(body['response_format']['json_schema']['schema']['additionalProperties'], False)
        self.assertEqual(body['max_completion_tokens'], ai.GROQ_TOKENS_BASE + 2 * ai.GROQ_TOKENS_PER_ANSWER)
        self.assertEqual((body['reasoning_effort'], body['include_reasoning']), ('low', False))
        self.assertNotIn('tools', body)

    def test_the_messages_are_the_instructions_and_the_answers(self):
        _, urlopen, _ = self.ask(FakeResponse(good_groq_reply()))
        system, user = self.body(urlopen)['messages']
        self.assertEqual(system['role'], 'system')
        self.assertIn('in Uzbek', system['content'])
        self.assertIn('You cannot hear the learner', system['content'])
        self.assertTrue(system['content'].endswith(ai.JSON_ANSWER))
        self.assertNotIn('report_feedback tool', system['content'])
        self.assertEqual(user['role'], 'user')
        sent = json.loads(user['content'].split('\n\n', 1)[1])
        self.assertEqual([answer['number'] for answer in sent['answers']], [1, 3])
        self.assertEqual(sent['answers'][0]['recogniser_confidence'], 0.88)

    def test_models_without_the_reasoning_settings_are_not_sent_them(self):
        with override_settings(GROQ_MODEL='qwen/some-model'):
            _, urlopen, _ = self.ask(FakeResponse(good_groq_reply()))
        body = self.body(urlopen)
        self.assertEqual(body['model'], 'qwen/some-model')
        self.assertNotIn('reasoning_effort', body)
        self.assertNotIn('include_reasoning', body)

    def test_the_feedback_is_read_from_the_json(self):
        result, _, _ = self.ask(FakeResponse(good_groq_reply()))
        self.assertEqual(result, {1: FIELDS, 3: FIELDS})
        answers = [{'number': 3, **{**FIELDS, 'summary': '  long ' + 'x' * 2000}}, {'number': 7, **FIELDS}]
        result, _, _ = self.ask(FakeResponse(groq_reply({'answers': answers})))
        self.assertEqual(sorted(result), [3])
        self.assertEqual(len(result[3]['summary']), ai.MAX_FIELD_LENGTH)

    def test_an_answer_without_usable_json_is_an_error(self):
        for payload in (
            groq_reply('Sorry, I cannot help with that.'), groq_reply({'feedback': []}), groq_reply({'answers': []}),
            groq_reply('[1, 2]'), {'choices': []}, {'choices': [{'message': {}}]}, {}, [], 'text',
        ):
            with self.subTest(payload=payload):
                error, _, _ = self.ask(FakeResponse(payload))
                self.assertIsInstance(error, ai.FeedbackError)

    def test_feedback_that_was_cut_off_says_so(self):
        cut = groq_reply('{"answers": [{"number": 1, "summary": "Good', finish_reason='length')
        error, urlopen, _ = self.ask(FakeResponse(cut))
        self.assertEqual(str(error), 'The AI service stopped before the feedback was complete')
        self.assertEqual(urlopen.call_count, 1)

    def test_a_refused_request_says_why_and_the_key_stays_secret(self):
        error, urlopen, sleep = self.ask(http_error(401, 'Invalid API Key'))
        self.assertEqual(str(error), 'The AI service answered 401: Invalid API Key')
        self.assertEqual(error.status, 401)
        self.assertNotIn('gsk-test-key', str(error))
        self.assertEqual(urlopen.call_count, 1)
        sleep.assert_not_called()

    def test_a_rate_limit_is_waited_out_when_it_is_short(self):
        result, urlopen, sleep = self.ask(http_error(429, 'Rate limit reached', retry_after='3'),
                                          FakeResponse(good_groq_reply()))
        self.assertEqual(result, {1: FIELDS, 3: FIELDS})
        sleep.assert_called_once_with(3.0)
        self.assertEqual(urlopen.call_count, 2)


@CONFIGURED
class FailureTests(SimpleTestCase):
    def ask(self, *results):
        with mock.patch('speaking.ai.urllib.request.urlopen', side_effect=list(results)) as urlopen, \
                mock.patch('speaking.ai.time.sleep') as sleep:
            try:
                return ai.request_feedback(ITEMS), urlopen, sleep
            except ai.FeedbackError as error:
                return error, urlopen, sleep

    def test_a_refused_request_says_why_and_is_not_repeated(self):
        for code in (400, 401, 403, 404):
            error, urlopen, sleep = self.ask(http_error(code, 'invalid x-api-key'))
            self.assertIsInstance(error, ai.FeedbackError)
            self.assertEqual(str(error), f'The AI service answered {code}: invalid x-api-key')
            self.assertEqual(error.status, code)
            self.assertEqual(urlopen.call_count, 1, code)
            sleep.assert_not_called()

    def test_a_busy_service_is_asked_once_more(self):
        for code in (429, 500, 502, 503, 504, 529):
            result, urlopen, sleep = self.ask(http_error(code, 'Overloaded'), FakeResponse(good_reply()))
            self.assertEqual(result, {1: FIELDS, 3: FIELDS}, code)
            self.assertEqual(urlopen.call_count, 2)
            sleep.assert_called_once_with(ai.RETRY_DELAY_SECONDS)

    def test_a_service_that_stays_busy_is_given_up_on(self):
        error, urlopen, _ = self.ask(http_error(529, 'Overloaded'), http_error(529, 'Overloaded'))
        self.assertEqual(str(error), 'The AI service answered 529: Overloaded')
        self.assertEqual(urlopen.call_count, 2)

    def test_the_wait_the_service_asks_for_is_kept_when_it_is_short(self):
        for retry_after, wait in (('0', 0.0), ('1.5', 1.5), (str(ai.MAX_RETRY_WAIT_SECONDS), ai.MAX_RETRY_WAIT_SECONDS)):
            result, _, sleep = self.ask(http_error(429, 'Slow down', retry_after=retry_after), FakeResponse(good_reply()))
            self.assertEqual(result, {1: FIELDS, 3: FIELDS}, retry_after)
            sleep.assert_called_once_with(wait)

    def test_a_long_wait_is_not_kept_up(self):
        for retry_after in (str(ai.MAX_RETRY_WAIT_SECONDS + 1), '3600', '-1', 'nan', 'inf'):
            error, urlopen, sleep = self.ask(http_error(429, 'Rate limit reached', retry_after=retry_after))
            self.assertEqual(str(error), 'The AI service answered 429: Rate limit reached', retry_after)
            self.assertEqual(urlopen.call_count, 1, retry_after)
            sleep.assert_not_called()

    def test_a_wait_that_is_not_a_number_gets_the_short_pause(self):
        result, _, sleep = self.ask(
            http_error(503, 'Busy', retry_after='Wed, 21 Oct 2026 07:28:00 GMT'), FakeResponse(good_reply()))
        self.assertEqual(result, {1: FIELDS, 3: FIELDS})
        sleep.assert_called_once_with(ai.RETRY_DELAY_SECONDS)

    def test_network_trouble(self):
        error, urlopen, _ = self.ask(urllib.error.URLError('no route'), urllib.error.URLError('no route'))
        self.assertIsInstance(error, ai.FeedbackError)
        self.assertIn('could not be reached', str(error))
        self.assertIsNone(error.status)
        self.assertEqual(urlopen.call_count, 2)
        result, urlopen, _ = self.ask(TimeoutError('slow'), FakeResponse(good_reply()))
        self.assertEqual(result, {1: FIELDS, 3: FIELDS})

    def test_an_answer_that_is_not_json(self):
        error, urlopen, _ = self.ask(FakeResponse(b'<html>gateway</html>'))
        self.assertEqual(str(error), 'The AI service sent an answer that could not be read')
        self.assertEqual(urlopen.call_count, 1)

    def test_an_error_without_a_readable_body_uses_the_reason(self):
        error, _, _ = self.ask(http_error(401, body=b'<html>nope</html>'))
        self.assertEqual(str(error), 'The AI service answered 401: Reason Phrase')

    def test_the_key_never_appears_in_an_error(self):
        error, _, _ = self.ask(http_error(401, 'invalid x-api-key'))
        self.assertNotIn('test-key', str(error))


def whisper_reply(*segments, text=None):
    """What Groq's transcription answers in verbose_json; each segment is (text, start, end, avg_logprob, no_speech)."""
    parts = [
        {'id': index, 'seek': 0, 'start': start, 'end': end, 'text': f' {said}', 'tokens': [1, 2], 'temperature': 0.0,
         'avg_logprob': logprob, 'compression_ratio': 1.1, 'no_speech_prob': no_speech}
        for index, (said, start, end, logprob, no_speech) in enumerate(segments)
    ]
    return {
        'task': 'transcribe', 'language': 'English', 'duration': 30.0,
        'text': text if text is not None else ''.join(part['text'] for part in parts), 'segments': parts,
        'x_groq': {'id': 'req_1'},
    }


@GROQ
class TranscribeTests(SimpleTestCase):
    """The recordings are turned into text by Whisper on Groq."""

    def setUp(self):
        handle = tempfile.NamedTemporaryFile(suffix='.webm', delete=False)
        handle.write(b'\x1aE\xdf\xa3 a recording')
        handle.close()
        self.path = handle.name
        self.addCleanup(os.remove, self.path)

    def transcribe(self, *results, path=None):
        with mock.patch('speaking.ai.urllib.request.urlopen', side_effect=list(results)) as urlopen, \
                mock.patch('speaking.ai.time.sleep') as sleep:
            try:
                return ai.transcribe(path or self.path, 'audio/webm'), urlopen, sleep
            except ai.FeedbackError as error:
                return error, urlopen, sleep

    def test_the_request_to_whisper(self):
        _, urlopen, sleep = self.transcribe(FakeResponse(whisper_reply(('I like films.', 0.0, 2.0, -0.2, 0.01))))
        request = urlopen.call_args.args[0]
        self.assertEqual((request.full_url, request.get_method()),
                         ('https://groq.example.test/openai/v1/audio/transcriptions', 'POST'))
        self.assertEqual(request.get_header('Authorization'), 'Bearer gsk-test-key')
        self.assertEqual(request.get_header('User-agent'), ai.USER_AGENT)
        self.assertEqual(urlopen.call_args.kwargs['timeout'], ai.TIMEOUT_SECONDS)
        sleep.assert_not_called()
        content_type = request.get_header('Content-type')
        self.assertTrue(content_type.startswith('multipart/form-data; boundary='), content_type)
        form = email.message_from_bytes(f'Content-Type: {content_type}\r\n\r\n'.encode() + request.data)
        fields = {part.get_param('name', header='content-disposition'): part for part in form.get_payload()}
        self.assertEqual(sorted(fields), ['file', 'language', 'model', 'prompt', 'response_format', 'temperature'])
        self.assertEqual({name: fields[name].get_payload() for name in fields if name != 'file'}, {
            'model': 'whisper-test', 'language': 'en', 'response_format': 'verbose_json', 'temperature': '0',
            'prompt': ai.TRANSCRIPTION_PROMPT,
        })
        recording = fields['file']
        self.assertEqual(recording.get_filename(), os.path.basename(self.path))
        self.assertEqual(recording.get_content_type(), 'audio/webm')
        self.assertEqual(recording.get_payload(decode=True), b'\x1aE\xdf\xa3 a recording')

    def test_what_was_heard_and_how_sure_whisper_was(self):
        result, _, _ = self.transcribe(FakeResponse(whisper_reply(
            ('Umm, I like comedy films.', 0.0, 3.0, -0.1, 0.02), ('They make me laugh.', 3.0, 4.0, -0.5, 0.05))))
        self.assertEqual(result, ('Umm, I like comedy films. They make me laugh.',
                                  round(math.exp((-0.1 * 3 + -0.5 * 1) / 4), 3)))

    def test_parts_that_are_not_speech_are_left_out(self):
        result, _, _ = self.transcribe(FakeResponse(whisper_reply(
            ('I live in a flat.', 0.0, 2.0, -0.3, 0.1), ('Thank you.', 2.0, 30.0, -0.2, 0.9))))
        self.assertEqual(result, ('I live in a flat.', round(math.exp(-0.3), 3)))

    def test_silence_is_no_text(self):
        for reply_ in (
            whisper_reply(('Thank you.', 0.0, 1.0, -0.4, 0.95)),
            whisper_reply(),
            whisper_reply((ai.TRANSCRIPTION_PROMPT, 0.0, 1.4, -0.3, 0.2)),  # Whisper repeating its prompt
            whisper_reply(('  ', 0.0, 1.0, -0.4, 0.1)),
        ):
            with self.subTest(reply=reply_):
                result, _, _ = self.transcribe(FakeResponse(reply_))
                self.assertEqual(result, ('', None))

    def test_without_segments_the_text_is_used(self):
        result, _, _ = self.transcribe(FakeResponse({'text': ' I like music. '}))
        self.assertEqual(result, ('I like music.', None))

    def test_segments_without_numbers_still_give_their_words(self):
        result, _, _ = self.transcribe(FakeResponse({'segments': [{'text': ' Hello there.'}, 'junk', None]}))
        self.assertEqual(result, ('Hello there.', None))

    def test_a_file_the_service_cannot_use_is_rejected_and_not_asked_again(self):
        for code in sorted(ai.REJECTED_STATUSES):
            error, urlopen, sleep = self.transcribe(http_error(code, 'could not process file'))
            self.assertIsInstance(error, ai.RecordingRejected, code)
            self.assertEqual((str(error), error.status), (f'The AI service answered {code}: could not process file', code))
            self.assertEqual(urlopen.call_count, 1)
            sleep.assert_not_called()

    def test_a_missing_file_is_rejected_without_asking(self):
        error, urlopen, _ = self.transcribe(path=os.path.join(tempfile.gettempdir(), 'no-such-recording.webm'))
        self.assertIsInstance(error, ai.RecordingRejected)
        self.assertIn('could not be read', str(error))
        urlopen.assert_not_called()

    def test_service_trouble_is_not_blamed_on_the_file(self):
        for problem in (http_error(401, 'Invalid API Key'), http_error(404, 'The model does not exist'),
                        http_error(429, 'Rate limit reached', retry_after='60')):
            error, _, _ = self.transcribe(problem)
            self.assertIsInstance(error, ai.FeedbackError)
            self.assertNotIsInstance(error, ai.RecordingRejected)
            self.assertNotIn('gsk-test-key', str(error))

    def test_a_short_rate_limit_is_waited_out(self):
        result, urlopen, sleep = self.transcribe(
            http_error(429, 'Rate limit reached', retry_after='2'),
            FakeResponse(whisper_reply(('Yes, I do.', 0.0, 1.0, -0.2, 0.0))))
        self.assertEqual(result[0], 'Yes, I do.')
        sleep.assert_called_once_with(2.0)
        self.assertEqual(urlopen.call_count, 2)

    def test_an_answer_that_is_not_json_or_not_an_object(self):
        for payload in (b'<html>gateway</html>', [], 'text'):
            error, _, _ = self.transcribe(FakeResponse(payload))
            self.assertEqual(str(error), 'The AI service sent an answer that could not be read')

    def test_without_a_groq_key_nothing_is_sent(self):
        with override_settings(GROQ_API_KEY=''), mock.patch('speaking.ai.urllib.request.urlopen') as urlopen, \
                self.assertRaises(ai.FeedbackNotConfigured):
            ai.transcribe(self.path, 'audio/webm')
        urlopen.assert_not_called()


class WhatIsSetUpTests(SimpleTestCase):
    def test_either_key_turns_the_feedback_on_but_only_groq_transcribes(self):
        for anthropic, groq, configured, transcribes in (
            ('', '', False, False), ('sk-ant-x', '', True, False), ('', 'gsk_x', True, True),
            ('sk-ant-x', 'gsk_x', True, True),
        ):
            with self.subTest(anthropic=anthropic, groq=groq), \
                    override_settings(ANTHROPIC_API_KEY=anthropic, GROQ_API_KEY=groq):
                self.assertEqual((ai.is_configured(), ai.can_transcribe()), (configured, transcribes))
