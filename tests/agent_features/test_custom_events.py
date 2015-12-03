import pytest
import time

from newrelic.agent import background_task, record_custom_event, application
from newrelic.core.custom_event import process_event_type

from testing_support.fixtures import (reset_core_stats_engine,
        validate_custom_event_count,
        validate_custom_event_in_application_stats_engine,
        override_application_settings)

# Test process_event_type()

def test_process_event_type_name_is_string():
    name = 'string'
    assert process_event_type(name) == name

def test_process_event_type_name_is_not_string():
    name = 42
    assert process_event_type(name) is None

def test_process_event_type_name_ok_length():
    ok_name = 'CustomEventType'
    assert process_event_type(ok_name) == ok_name

def test_process_event_type_name_too_long():
    too_long = 'a' * 256
    assert process_event_type(too_long) is None

def test_process_event_type_name_valid_chars():
    valid_name = 'az09: '
    assert process_event_type(valid_name) == valid_name

def test_process_event_type_name_invalid_chars():
    invalid_name = '&'
    assert process_event_type(invalid_name) is None

_now = time.time()

_intrinsics = {
    'type': 'FooEvent',
    'timestamp': _now,
}
_user_params = {'foo': 'bar'}
_event = [_intrinsics, _user_params]

@reset_core_stats_engine()
@validate_custom_event_in_application_stats_engine(_event)
@background_task()
def test_add_custom_event_to_transaction_stats_engine():
    record_custom_event('FooEvent', _user_params)

@reset_core_stats_engine()
@validate_custom_event_in_application_stats_engine(_event)
def test_add_custom_event_to_application_stats_engine():
    app = application()
    record_custom_event('FooEvent', _user_params, application=app)

@reset_core_stats_engine()
@validate_custom_event_count(count=0)
@background_task()
def test_custom_event_inside_transaction_bad_event_type():
    record_custom_event('!@#$%^&*()', {'foo': 'bar'})

@reset_core_stats_engine()
@validate_custom_event_count(count=0)
@background_task()
def test_custom_event_outside_transaction_bad_event_type():
    app = application()
    record_custom_event('!@#$%^&*()', {'foo': 'bar'}, application=app)

_mixed_params = {'foo': 'bar', 123: 'bad key'}

@reset_core_stats_engine()
@validate_custom_event_in_application_stats_engine(_event)
@background_task()
def test_custom_event_inside_transaction_mixed_params():
    record_custom_event('FooEvent', _mixed_params)

@reset_core_stats_engine()
@validate_custom_event_in_application_stats_engine(_event)
@background_task()
def test_custom_event_outside_transaction_mixed_params():
    app = application()
    record_custom_event('FooEvent', _mixed_params, application=app)

_bad_params = {'*' * 256: 'too long', 123: 'bad key'}
_event_with_no_params = [{'type': 'FooEvent', 'timestamp': _now}, {}]

@reset_core_stats_engine()
@validate_custom_event_in_application_stats_engine(_event_with_no_params)
@background_task()
def test_custom_event_inside_transaction_bad_params():
    record_custom_event('FooEvent', _bad_params)

@reset_core_stats_engine()
@validate_custom_event_in_application_stats_engine(_event_with_no_params)
@background_task()
def test_custom_event_outside_transaction_bad_params():
    app = application()
    record_custom_event('FooEvent', _bad_params, application=app)

# Tests for Custom Events configuration settings

@override_application_settings({'collect_custom_events': False})
@reset_core_stats_engine()
@validate_custom_event_count(count=0)
@background_task()
def test_custom_event_settings_check_collector_flag():
    record_custom_event('FooEvent', _user_params)

@override_application_settings({'custom_insights_events.enabled': False})
@reset_core_stats_engine()
@validate_custom_event_count(count=0)
@background_task()
def test_custom_event_settings_check_custom_insights_enabled():
    record_custom_event('FooEvent', _user_params)
