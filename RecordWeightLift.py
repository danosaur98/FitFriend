import boto3
import time
import os
import logging

dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
exercise_log = dynamodb.Table('ExerciseLog')
exercises = dynamodb.Table('Exercises')
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


def confirm_intent(session_attributes, intent_name, slots, message):
    return {
        'sessionAttributes': session_attributes,
        'dialogAction': {
            'type': 'ConfirmIntent',
            'intentName': intent_name,
            'slots': slots,
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


def try_ex(func):
    """
    Call passed in function in try block. If KeyError is encountered return None.
    This function is intended to be used to safely access dictionary.

    Note that this function would have negative impact on performance.
    """

    try:
        return func()
    except KeyError:
        return None


def parse_int(n):
    try:
        return int(n)
    except ValueError:
        return float('nan')


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


def is_valid_exercise(exercise, intent_request):
    response = exercises.get_item(
        Key={
            'UserID': 'universal',
            'ExerciseName': exercise.lower()
        }
    )
    if 'Item' in response:
        return True
    else:
        response = exercises.get_item(
            Key={
                'UserID': intent_request['userId'],
                'ExerciseName': exercise.lower()
            }
        )
        if 'Item' in response:
            return True
    return False


def validate_record_weightlift(exercise, weight, reps, sets, intent_request):
    if exercise is not None:
        if not is_valid_exercise(exercise, intent_request):
            return build_validation_result(False, 'Exercise', '{} is not recognized as one of your exercises. Would '
                                                              'you like to add it?'.format(exercise))

    return build_validation_result(True, None, None)


""" --- Functions that control the bot's behavior --- """


def record_weightlift(intent_request):
    exercise_name = get_slots(intent_request)["Exercise"]
    weight = get_slots(intent_request)["Weight"]
    reps = get_slots(intent_request)["Reps"]
    sets = get_slots(intent_request)["Sets"]
    source = intent_request['invocationSource']

    if source == 'DialogCodeHook':
        # Perform basic validation on the supplied input slots.
        # Use the elicitSlot dialog action to re-prompt for the first violation detected.
        slots = get_slots(intent_request)

        validation_result = validate_record_weightlift(exercise_name, weight, reps, sets, intent_request)
        if not validation_result['isValid']:
            slots[validation_result['violatedSlot']] = None

            return confirm_intent(
                intent_request['sessionAttributes'] if intent_request[
                                                           'sessionAttributes'] is not None else {},
                'CreateExercise',
                {
                    'Exercise': exercise_name,
                    'MuscleGroup': None
                },
                {
                    'contentType': 'PlainText',
                    'content': '{} is not recognized as one of your exercises. Would '
                               'you like to add it?'.format(exercise_name)

                }
            )

        output_session_attributes = intent_request['sessionAttributes'] if intent_request[
                                                                               'sessionAttributes'] is not None else {}

        return delegate(output_session_attributes, get_slots(intent_request))
    exercise_log.put_item(
        Item={
            "UserID": intent_request['userId'],
            "Date": time.strftime("%d/%m/%Y"),
            "ExerciseName": exercise_name,
            "Weight": weight,
            "Reps": reps,
            "Sets": sets
        }
    )
    return close(intent_request['sessionAttributes'],
                 'Fulfilled',
                 {'contentType': 'PlainText',
                  'content': 'Keep going!'})


""" --- Intents --- """


def dispatch(intent_request):
    """
    Called when the user specifies an intent for this bot.
    """

    logger.debug(
        'dispatch userId={}, intentName={}'.format(intent_request['userId'], intent_request['currentIntent']['name']))

    intent_name = intent_request['currentIntent']['name']

    # Dispatch to your bot's intent handlers
    if intent_name == 'RecordWeightlift':
        return record_weightlift(intent_request)

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
