import boto3
import time
import os
import logging

dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
table = dynamodb.Table('Exercises')
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


def is_valid_muscle_group(muscle_group):
    valid_muscle_groups = ['shoulder', 'arms', 'back', 'legs', 'chest', 'core']
    return muscle_group.lower() in valid_muscle_groups


def validate_create_exercise(name, muscle_group):
    if muscle_group is not None:
        if not is_valid_muscle_group(muscle_group):
            return build_validation_result(False, 'MuscleGroup', 'Does {} primarily work the arms, back, chest, core, '
                                                                 'shoulder, or legs?'.format(name))
    return build_validation_result(True, None, None)


""" --- Functions that control the bot's behavior --- """


def create_exercise(intent_request):
    exercise = get_slots(intent_request)["Exercise"]
    muscle_group = get_slots(intent_request)["MuscleGroup"]
    source = intent_request['invocationSource']
    confirmation_status = intent_request['currentIntent']['confirmationStatus']
    session_attributes = intent_request['sessionAttributes'] if intent_request['sessionAttributes'] is not None else {}

    if source == 'DialogCodeHook':
        # Perform basic validation on the supplied input slots.
        # Use the elicitSlot dialog action to re-prompt for the first violation detected.
        slots = get_slots(intent_request)

        if confirmation_status == 'Denied':
            return close(intent_request['sessionAttributes'],
                         'Fulfilled',
                         {'contentType': 'PlainText',
                          'content': 'It\'s all good in the hood!'})
        if confirmation_status == 'None':
            validation_result = validate_create_exercise(exercise, muscle_group)
            if not validation_result['isValid']:
                slots[validation_result['violatedSlot']] = None
                return elicit_slot(intent_request['sessionAttributes'],
                                   intent_request['currentIntent']['name'],
                                   slots,
                                   validation_result['violatedSlot'],
                                   validation_result['message'])
            return delegate(session_attributes, get_slots(intent_request))
        if confirmation_status == 'Confirmed':
            session_attributes['chainRecordWeightLift'] = True
            if not muscle_group:
                return elicit_slot(
                    session_attributes,
                    intent_request['currentIntent']['name'],
                    slots,
                    'MuscleGroup',
                    {
                        'contentType': 'PlainText',
                        'content': 'Does {} primarily work the arms, back, chest, core, '
                                   'shoulder, or legs?'.format(exercise)
                    }
                )

    table.put_item(
        Item={
            "UserID": intent_request['userId'],
            "ExerciseName": exercise,
            "MuscleGroup": muscle_group
        }
    )
    if try_ex(lambda: session_attributes['chainRecordWeightLift']):
        try_ex(lambda: session_attributes.pop('chainRecordWeightLift'))
        return confirm_intent(
            session_attributes,
            'RecordWeightlift',
            {
                'Exercise': exercise,
                'Weight': None,
                'Reps': None,
                'Sets': None
            },
            {
                'contentType': 'PlainText',
                'content': 'Got it! {} has been added to your exercises. Would you like to finish inputting your '
                           'workout?'.format(
                    exercise)
            }
        )
    else:
        return close(intent_request['sessionAttributes'],
                     'Fulfilled',
                     {'contentType': 'PlainText',
                      'content': 'Got it! {} has been added to your exercises'.format(exercise)})


""" --- Intents --- """


def dispatch(intent_request):
    """
    Called when the user specifies an intent for this bot.
    """

    logger.debug(
        'dispatch userId={}, intentName={}'.format(intent_request['userId'], intent_request['currentIntent']['name']))

    intent_name = intent_request['currentIntent']['name']

    # Dispatch to your bot's intent handlers
    if intent_name == 'CreateExercise':
        return create_exercise(intent_request)

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
