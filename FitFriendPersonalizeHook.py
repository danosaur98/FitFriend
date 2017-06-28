import boto3
import math
import dateutil.parser
import datetime
import time
import os
import logging

dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
table = dynamodb.Table('Users')

logger = logging.getLogger()
logger.setLevel(logging.DEBUG)

""" --- Helpers to build responses which match the structure of the necessary dialog actions --- """


def get_slots(intent_request):
    return intent_request['currentIntent']['slots']


def elicit_slot(session_attributes, intent_name, slots, slot_to_elicit, message):
    return {
        'sessionAttributes': session_attributes,
        'dialogAction': {
            'type': 'ElicitSlot',
            'intentName': intent_name,
            'slots': slots,
            'slotToElicit': slot_to_elicit,
            'message': message
        }
    }


def close(session_attributes, fulfillment_state, message):
    response = {
        'sessionAttributes': session_attributes,
        'dialogAction': {
            'type': 'Close',
            'fulfillmentState': fulfillment_state,
            'message': message
        }
    }

    return response


def delegate(session_attributes, slots):
    return {
        'sessionAttributes': session_attributes,
        'dialogAction': {
            'type': 'Delegate',
            'slots': slots
        }
    }


""" --- Helper Functions --- """


def isvalid_gender(gender):
    valid_genders = ['male', 'man', 'm', 'female', 'woman', 'f']
    return gender.lower() in valid_genders


def isvalid_measurement_system(measurementsystem):
    valid_measurementsystems = ['imperial', 'imperial system', 'metric', 'metric system']
    return measurementsystem.lower() in valid_measurementsystems


def isvalid_goal(goal):
    valid_goal = ['weight loss', 'lose weight', 'lose', 'maintain', 'maintenance', 'gain', 'gain muscle']
    return goal.lower() in valid_goal


def build_validation_result(is_valid, violated_slot, message_content):
    if message_content is None:
        return {
            "isValid": is_valid,
            "violatedSlot": violated_slot,
        }

    return {
        'isValid': is_valid,
        'violatedSlot': violated_slot,
        'message': {'contentType': 'PlainText', 'content': message_content}
    }


def validate_personalize(name, gender, age, measurementsystem, height, weight, goal, source):
    if gender is not None:
        if not isvalid_gender(gender):
            return build_validation_result(False, 'Gender', 'Sorry, can you repeat what gender you are?')
    if measurementsystem is not None:
        if not isvalid_measurement_system(measurementsystem):
            return build_validation_result(False, 'MeasurementSystem',
                                           'Sorry, can you repeat which measurement system you prefer?')
    if goal is not None:
        if not isvalid_goal(measurementsystem):
            return build_validation_result(False, 'Goal',
                                           'Sorry, can you repeat your goal is?')
    return build_validation_result(True, None, None)


""" --- Functions that control the bot's behavior --- """


def personalize(intent_request):
    name = get_slots(intent_request)["Name"]
    gender = get_slots(intent_request)["Gender"]
    age = get_slots(intent_request)["Age"]
    measurementsystem = get_slots(intent_request)["MeasurementSystem"]
    height = get_slots(intent_request)["Height"]
    weight = get_slots(intent_request)["Weight"]
    goal = get_slots(intent_request)["Goal"]
    source = intent_request['invocationSource']

    if source == 'DialogCodeHook':
        # Perform basic validation on the supplied input slots.
        # Use the elicitSlot dialog action to re-prompt for the first violation detected.
        slots = get_slots(intent_request)

        validation_result = validate_personalize(name, gender, age, measurementsystem, height, weight, goal, source)
        if not validation_result['isValid']:
            slots[validation_result['violatedSlot']] = None
            return elicit_slot(intent_request['sessionAttributes'],
                               intent_request['currentIntent']['name'],
                               slots,
                               validation_result['violatedSlot'],
                               validation_result['message'])
        output_session_attributes = intent_request['sessionAttributes'] if intent_request[
                                                                               'sessionAttributes'] is not None else {}
        return delegate(output_session_attributes, get_slots(intent_request))

    # call to a backend service.
    table.put_item(
        Item={
            "user": intent_request['userId'],
            "name": name,
            "gender": gender,
            "age": age,
            "measurementSystem": measurementsystem,
            "height": height,
            "weight": weight,
            "goal": goal
        }
    )
    return close(intent_request['sessionAttributes'],
                 'Fulfilled',
                 {'contentType': 'PlainText',
                  'content': 'Nice to meet you, {}! If you ever need help with any commands, just enter "help"'.format(
                      name)})


""" --- Intents --- """


def dispatch(intent_request):
    """
    Called when the user specifies an intent for this bot.
    """

    logger.debug(
        'dispatch userId={}, intentName={}'.format(intent_request['userId'], intent_request['currentIntent']['name']))

    intent_name = intent_request['currentIntent']['name']

    # Dispatch to your bot's intent handlers
    if intent_name == 'Personalize':
        return personalize(intent_request)

    raise Exception('Intent with name ' + intent_name + ' not supported')


""" --- Main handler --- """


def lambda_handler(event, context):
    """
    Route the incoming request based on intent.
    The JSON body of the request is provided in the event slot.
    """
    # By default, treat the user request as coming from the America/New_York time zone.
    os.environ['TZ'] = 'America/New_York'
    time.tzset()
    logger.debug('event.bot.name={}'.format(event['bot']['name']))

    return dispatch(event)
