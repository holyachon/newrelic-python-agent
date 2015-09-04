import pytest
import webtest

from newrelic.agent import wsgi_application
from newrelic.common.encoding_utils import (deobfuscate, obfuscate,
        json_decode, json_encode)
from newrelic.core.agent import agent_instance

from testing_support.fixtures import (validate_synthetics_event,
        validate_synthetics_transaction_trace, override_application_settings)
from testing_support.external_fixtures import (
        validate_synthetics_external_trace_header)

ENCODING_KEY = '1234567890123456789012345678901234567890'
ACCOUNT_ID = '444'
SYNTHETICS_RESOURCE_ID = '09845779-16ef-4fa7-b7f2-44da8e62931c'
SYNTHETICS_JOB_ID = '8c7dd3ba-4933-4cbb-b1ed-b62f511782f4'
SYNTHETICS_MONITOR_ID = 'dc452ae9-1a93-4ab5-8a33-600521e9cd00'

_override_settings = {
    'encoding_key': ENCODING_KEY,
    'trusted_account_ids': [int(ACCOUNT_ID)],
    'synthetics.enabled': True,
}

def make_synthetics_header(version='1', account_id=ACCOUNT_ID,
        resource_id=SYNTHETICS_RESOURCE_ID, job_id=SYNTHETICS_JOB_ID,
        monitor_id=SYNTHETICS_MONITOR_ID, encoding_key=ENCODING_KEY):
    value = [version, account_id, resource_id, job_id, monitor_id]
    value = obfuscate(json_encode(value), encoding_key)
    return {'X-NewRelic-Synthetics': value}

def decode_header(header, encoding_key=ENCODING_KEY):
    result = deobfuscate(header, encoding_key)
    return json_decode(result)

@wsgi_application()
def target_wsgi_application(environ, start_response):
    status = '200 OK'

    output = '<html><head>header</head><body><p>RESPONSE</p></body></html>'
    output = output.encode('UTF-8')

    response_headers = [('Content-Type', 'text/html; charset=utf-8'),
                        ('Content-Length', str(len(output)))]
    start_response(status, response_headers)

    return [output]

target_application = webtest.TestApp(target_wsgi_application)

_test_valid_synthetics_event_required = [
        ('nr.syntheticsResourceId', SYNTHETICS_RESOURCE_ID),
        ('nr.syntheticsJobId', SYNTHETICS_JOB_ID),
        ('nr.syntheticsMonitorId', SYNTHETICS_MONITOR_ID)]
_test_valid_synthetics_event_forgone = []

@validate_synthetics_event(_test_valid_synthetics_event_required,
        _test_valid_synthetics_event_forgone, should_exist=True)
@override_application_settings(_override_settings)
def test_valid_synthetics_event():
    headers = make_synthetics_header()
    response = target_application.get('/', headers=headers)

@validate_synthetics_event([], [], should_exist=False)
@override_application_settings(_override_settings)
def test_no_synthetics_event_unsupported_version():
    headers = make_synthetics_header(version='0')
    response = target_application.get('/', headers=headers)

@validate_synthetics_event([], [], should_exist=False)
@override_application_settings(_override_settings)
def test_no_synthetics_event_untrusted_account():
    headers = make_synthetics_header(account_id='999')
    response = target_application.get('/', headers=headers)

@validate_synthetics_event([], [], should_exist=False)
@override_application_settings(_override_settings)
def test_no_synthetics_event_mismatched_encoding_key():
    encoding_key = 'zzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz'
    headers = make_synthetics_header(encoding_key=encoding_key)
    response = target_application.get('/', headers=headers)

_test_valid_synthetics_tt_required = {
        'synthetics_resource_id': SYNTHETICS_RESOURCE_ID,
        'synthetics_job_id': SYNTHETICS_JOB_ID,
        'synthetics_monitor_id': SYNTHETICS_MONITOR_ID}

@validate_synthetics_transaction_trace(_test_valid_synthetics_tt_required)
@override_application_settings(_override_settings)
def test_valid_synthetics_in_transaction_trace():
    headers = make_synthetics_header()
    response = target_application.get('/', headers=headers)

@validate_synthetics_transaction_trace([], _test_valid_synthetics_tt_required,
        should_exist=False)
@override_application_settings(_override_settings)
def test_no_synthetics_in_transaction_trace():
    response = target_application.get('/')

_disabled_settings = {
    'encoding_key': ENCODING_KEY,
    'trusted_account_ids': [int(ACCOUNT_ID)],
    'synthetics.enabled': False,
}

@validate_synthetics_event([], [], should_exist=False)
@override_application_settings(_disabled_settings)
def test_synthetics_disabled():
    headers = make_synthetics_header()
    response = target_application.get('/', headers=headers)

_external_synthetics_header = ('X-NewRelic-Synthetics',
        make_synthetics_header()['X-NewRelic-Synthetics'])

@validate_synthetics_external_trace_header(
        required_header=_external_synthetics_header, should_exist=True)
@override_application_settings(_override_settings)
def test_valid_synthetics_external_trace_header():
    headers = make_synthetics_header()
    response = target_application.get('/', headers=headers)

@validate_synthetics_external_trace_header(should_exist=False)
@override_application_settings(_override_settings)
def test_no_synthetics_external_trace_header():
    response = target_application.get('/')

def _synthetics_limit_test(num_requests, num_events, num_transactions):

    # Force harvest to clear stats

    instance = agent_instance()
    application = list(instance.applications.values())[0]
    application.harvest()

    # Send requests

    headers = make_synthetics_header()
    for i in range(num_requests):
        response = target_application.get('/', headers=headers)

    # Check that we've saved the right number events and traces

    stats = application._stats_engine
    assert len(stats.synthetics_events) == num_events
    assert len(stats.synthetics_transactions) == num_transactions

@pytest.mark.skipif(True, reason='Test is too flaky. '
                'Need to find a way to make harvests more predictable.')
@pytest.mark.parametrize('num_requests,num_events,num_transactions', [
    (0, 0, 0),
    (20, 20, 20),
    (21, 21, 20),
    (200, 200, 20),
    (201, 200, 20)])
@override_application_settings(_override_settings)
def test_synthetics_requests_default_limits(num_requests, num_events,
        num_transactions):
    _synthetics_limit_test(num_requests, num_events, num_transactions)

_custom_settings = {
    'encoding_key': ENCODING_KEY,
    'trusted_account_ids': [int(ACCOUNT_ID)],
    'agent_limits.synthetics_events': 5,
    'agent_limits.synthetics_transactions': 3,
    'synthetics.enabled': True,
}

@pytest.mark.skipif(True, reason='Test is too flaky. '
                'Need to find a way to make harvests more predictable.')
@pytest.mark.parametrize('num_requests,num_events,num_transactions', [
    (0, 0, 0),
    (3, 3, 3),
    (4, 4, 3),
    (5, 5, 3),
    (6, 5, 3)])
@override_application_settings(_custom_settings)
def test_synthetics_requests_custom_limits(num_requests, num_events,
        num_transactions):
    _synthetics_limit_test(num_requests, num_events, num_transactions)

_zero_settings = {
    'encoding_key': ENCODING_KEY,
    'trusted_account_ids': [int(ACCOUNT_ID)],
    'agent_limits.synthetics_events': 0,
    'agent_limits.synthetics_transactions': 0,
    'synthetics.enabled': True,
}

@pytest.mark.skipif(True, reason='Test is too flaky. '
                'Need to find a way to make harvests more predictable.')
@pytest.mark.parametrize('num_requests,num_events,num_transactions', [
    (0, 0, 0),
    (1, 0, 0)])
@override_application_settings(_zero_settings)
def test_synthetics_requests_zero_limits(num_requests, num_events,
        num_transactions):
    _synthetics_limit_test(num_requests, num_events, num_transactions)
