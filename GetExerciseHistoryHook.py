import boto3
import time
import os
import logging
from boto3.dynamodb.conditions import Key, Attr

dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
exercises = dynamodb.Table('Exercises')
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


def is_new_day(user):
    if not time.strftime("%Y-%m-%d") in user['Item']['dailyNutrientsAndWorkouts']:
        return True
    return False


def create_new_day(user, intent_request):
    users.update_item(
        Key={
            'user': intent_request['userId']
        },
        UpdateExpression="set dailyNutrientsAndWorkouts.#day = :d",
        ExpressionAttributeValues={
            ':d': {
                "nutritionRemaining": {
                    'calorie': user['Item']['nutrientGoal']['calorie'],
                    'protein': user['Item']['nutrientGoal']['protein'],
                    'carbohydrate': user['Item']['nutrientGoal']['carbohydrate'],
                    'fat': user['Item']['nutrientGoal']['fat'],
                },
                "exercisesRemaining": user['Item']['workoutSchedule'][time.strftime('%A')],
                "violations": [],
                "foodLog": {},
                "exerciseLog": {},
                "excuses": {}
            },

        },
        ExpressionAttributeNames={
            '#day': time.strftime("%Y-%m-%d"),
        },
    )


def get_previous_exercises_remaining(user):
    latest_day = sorted(list(user['Item']['dailyNutrientsAndWorkouts'].keys()))[-1]
    return user['Item']['dailyNutrientsAndWorkouts'][latest_day]['exercisesRemaining']


def generate_previous_exercises_remaining_string(workout):
    if len(workout) == 1:
        return "You had " + workout[0] + " left."
    workout_string = "You had "
    for item in workout[0:-1]:
        workout_string += item + ", "
    workout_string += "and " + workout[-1] + " left. "
    return workout_string


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


def get_exercise_history_string(exercise, user):
    if user['Item']['measurementSystem'] == 'imperial system':
        measurement = 'lbs'
    else:
        measurement = 'kgs'
    history = ""
    for day, components in user['Item']['dailyNutrientsAndWorkouts'].items():
        for exercise_time, exercises in (components['exerciseLog']).items():
            if exercise == exercises['ExerciseName']:
                history += "On " + str(day) + ", you did " + str(exercises['Weight']) + measurement + ' for ' + str(
                    exercises['Reps'] + ' reps and ' + str(exercises['Sets'] + ' sets. '))
    return history


def validate_how_to_exercise(exercise, intent_request):
    if exercise is not None:
        if not is_valid_exercise(exercise.lower(), intent_request):
            return build_validation_result(False, 'Exercise',
                                           '{} is not recognized as one of your exercises'.format(exercise))

    return build_validation_result(True, None, None)


""" --- Functions that control the bot's behavior --- """


def get_exercise_history(intent_request):
    exercise_name = get_slots(intent_request)["Exercise"]
    user = get_user(intent_request)
    source = intent_request['invocationSource']
    session_attributes = intent_request['sessionAttributes'] if intent_request['sessionAttributes'] is not None else {}
    if source == 'DialogCodeHook':
        if not is_valid_user(user):
            return close(intent_request['sessionAttributes'],
                         'Fulfilled',
                         {
                             'contentType': 'PlainText',
                             'content': "Glad to see you're so eager! Say \'hey fitfriend\' to get started!"
                         })
        if is_new_day(user):
            create_new_day(user, intent_request)
            exercises_remaining = get_previous_exercises_remaining(user)
            if not len(exercises_remaining) == 0 and not exercises_remaining[0] == 'rest':
                session_attributes['workoutViolationDate'] = \
                    sorted(list(user['Item']['dailyNutrientsAndWorkouts'].keys()))[-1]
                return confirm_intent(
                    session_attributes,
                    "GiveExcuse",
                    {
                        'Excuse': None,
                        'Violation': 'workout'
                    },
                    {
                        'contentType': 'PlainText',
                        'content': 'Do you have a valid excuse for why you didn\'t finish your workout yesterday? {}'.format(
                            generate_previous_exercises_remaining_string(exercises_remaining))
                    }
                )
                # Perform basic validation on the supplied input slots.
                # Use the elicitSlot dialog action to re-prompt for the first violation detected.
        slots = get_slots(intent_request)

        validation_result = validate_how_to_exercise(exercise_name, intent_request)
        if not validation_result['isValid']:
            slots[validation_result['violatedSlot']] = None
            return elicit_slot(intent_request['sessionAttributes'],
                               intent_request['currentIntent']['name'],
                               slots,
                               validation_result['violatedSlot'],
                               validation_result['message'])

        return delegate(session_attributes, get_slots(intent_request))

    return close(intent_request['sessionAttributes'],
                 'Fulfilled',
                 {
                     'contentType': 'PlainText',
                     'content': '{}'.format(get_exercise_history_string(exercise_name, user))
                 })


""" --- Intents --- """


def dispatch(intent_request):
    """
    Called when the user specifies an intent for this bot.
    """

    logger.debug(
        'dispatch userId={}, intentName={}'.format(intent_request['userId'], intent_request['currentIntent']['name']))

    intent_name = intent_request['currentIntent']['name']

    # Dispatch to your bot's intent handlers
    if intent_name == 'GetExerciseHistory':
        return get_exercise_history(intent_request)

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
