import boto3
import time
import os
import logging

dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
users = dynamodb.Table('Users')
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


def get_user(intent_request):
    response = users.get_item(
        Key={
            'user': intent_request['userId'],
        }
    )
    return response


def is_valid_user(user):
    if 'Item' in user:
        return True
    return False


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


def validate_give_excuse(excuse, violation, source_intent):
    return build_validation_result(True, None, None)


""" --- Functions that control the bot's behavior --- """


def give_excuse(intent_request):
    excuse = get_slots(intent_request)["Excuse"]
    violation = get_slots(intent_request)["Violation"]
    source = intent_request['invocationSource']
    user = get_user(intent_request)
    confirmation_status = intent_request['currentIntent']['confirmationStatus']
    session_attributes = intent_request['sessionAttributes'] if intent_request[
                                                                    'sessionAttributes'] is not None else {}
    workout_violation_date = try_ex(lambda: session_attributes['workoutViolationDate'])

    if source == 'DialogCodeHook':
        slots = get_slots(intent_request)
        if not is_valid_user(user):
            return close(intent_request['sessionAttributes'],
                         'Fulfilled',
                         {
                             'contentType': 'PlainText',
                             'content': "Glad to see you're so eager! Say \'hey fitfriend\' to get started!"
                         })
        if confirmation_status == 'Denied':
            violations = violation.split()
            if workout_violation_date:
                day = try_ex(lambda: session_attributes['workoutViolationDate'])
                try_ex(lambda: session_attributes.pop('workoutViolationDate'))
                overall_violations = user['Item']['dailyNutrientsAndWorkouts'][day]['violations']
                overall_violations.append('workout')
            else:
                day = time.strftime("%Y-%m-%d")
                overall_violations = user['Item']['dailyNutrientsAndWorkouts'][day]['violations']

            current_excuses = user['Item']['dailyNutrientsAndWorkouts'][day]['excuses']
            current_excuses[time.strftime('%T')] = {
                "Excuse": 'I am both mentally and physically weak.',
                "Violation": violations
            }
            users.update_item(
                Key={
                    'user': intent_request['userId']
                },
                UpdateExpression="set dailyNutrientsAndWorkouts.#day.excuses = :e, dailyNutrientsAndWorkouts.#day.violations = :v",
                ExpressionAttributeValues={
                    ':e': current_excuses,
                    ':v': overall_violations
                },
                ExpressionAttributeNames={
                    '#day': day
                },
            )
            return close(intent_request['sessionAttributes'],
                         'Fulfilled',
                         {'contentType': 'PlainText',
                          'content': 'Smh. I\'ve put in an acceptable reason for you. Try not to do it again!'})
        if confirmation_status == 'Confirmed':
            validation_result = validate_give_excuse(excuse, violation, intent_request)
            if not validation_result['isValid']:
                slots[validation_result['violatedSlot']] = None
                return elicit_slot(intent_request['sessionAttributes'],
                                   intent_request['currentIntent']['name'],
                                   slots,
                                   validation_result['violatedSlot'],
                                   validation_result['message'])

        return delegate(session_attributes, get_slots(intent_request))

    violations = violation.split()
    if workout_violation_date:
        day = try_ex(lambda: session_attributes['workoutViolationDate'])
        try_ex(lambda: session_attributes.pop('workoutViolationDate'))
        overall_violations = user['Item']['dailyNutrientsAndWorkouts'][day]['violations']
        overall_violations.append('workout')
    else:
        day = time.strftime("%Y-%m-%d")
        overall_violations = user['Item']['dailyNutrientsAndWorkouts'][day]['violations']

    current_excuses = user['Item']['dailyNutrientsAndWorkouts'][day]['excuses']
    current_excuses[time.strftime('%T')] = {
        "Excuse": excuse,
        "Violation": violations
    }
    users.update_item(
        Key={
            'user': intent_request['userId']
        },
        UpdateExpression="set dailyNutrientsAndWorkouts.#day.excuses = :e, dailyNutrientsAndWorkouts.#day.violations = :v",
        ExpressionAttributeValues={
            ':e': current_excuses,
            ':v': overall_violations
        },
        ExpressionAttributeNames={
            '#day': day
        },
    )
    return close(intent_request['sessionAttributes'],
                 'Fulfilled',
                 {'contentType': 'PlainText',
                  'content': 'Alright, I\'ll keep track of that. Try not to do it again!'})


""" --- Intents --- """


def dispatch(intent_request):
    """
    Called when the user specifies an intent for this bot.
    """

    logger.debug(
        'dispatch userId={}, intentName={}'.format(intent_request['userId'], intent_request['currentIntent']['name']))

    intent_name = intent_request['currentIntent']['name']

    # Dispatch to your bot's intent handlers
    if intent_name == 'GiveExcuse':
        return give_excuse(intent_request)

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
