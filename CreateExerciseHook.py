import boto3
import time
import os
import logging

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
    exercise_name = get_slots(intent_request)["Exercise"]
    muscle_group = get_slots(intent_request)["MuscleGroup"]
    user = get_user(intent_request)
    source = intent_request['invocationSource']
    confirmation_status = intent_request['currentIntent']['confirmationStatus']
    session_attributes = intent_request['sessionAttributes'] if intent_request['sessionAttributes'] is not None else {}
    chain_record_weight_lift = try_ex(lambda: session_attributes['chainRecordWeightLift'])
    chain_create_workout = try_ex(lambda: session_attributes['chainCreateWorkout'])

    if source == 'DialogCodeHook':
        if not is_valid_user(user):
            return close(intent_request['sessionAttributes'],
                         'Fulfilled',
                         {
                             'contentType': 'PlainText',
                             'content': "Glad to see you're so eager! Say \'hey fitfriend\' to get started!"
                         })
        if is_new_day(user):
            exercises_remaining = get_previous_exercises_remaining(user)
            create_new_day(user, intent_request)
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
        slots = get_slots(intent_request)
        validation_result = validate_create_exercise(exercise_name, muscle_group)
        if not validation_result['isValid']:
            slots[validation_result['violatedSlot']] = None
            return elicit_slot(intent_request['sessionAttributes'],
                               intent_request['currentIntent']['name'],
                               slots,
                               validation_result['violatedSlot'],
                               validation_result['message'])
        if confirmation_status == 'Denied':
            try_ex(lambda: session_attributes.pop('chainRecordWeightLift'))
            try_ex(lambda: session_attributes.pop('chainCreateWorkout'))
            return close(intent_request['sessionAttributes'],
                         'Fulfilled',
                         {'contentType': 'PlainText',
                          'content': 'It\'s all good in the hood!'})
        if confirmation_status == 'None':
            if not muscle_group:
                if chain_record_weight_lift or chain_create_workout:
                    return confirm_intent(
                        session_attributes,
                        intent_request['currentIntent']['name'],
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
            return delegate(session_attributes, get_slots(intent_request))
        if confirmation_status == 'Confirmed':
            validation_result = validate_create_exercise(exercise_name, muscle_group)
            if not validation_result['isValid']:
                slots[validation_result['violatedSlot']] = None
                return elicit_slot(intent_request['sessionAttributes'],
                                   intent_request['currentIntent']['name'],
                                   slots,
                                   validation_result['violatedSlot'],
                                   validation_result['message'])

        return delegate(session_attributes, get_slots(intent_request))

    exercises.put_item(
        Item={
            "UserID": intent_request['userId'],
            "ExerciseName": exercise_name,
            "MuscleGroup": muscle_group
        }
    )
    if try_ex(lambda: session_attributes['chainRecordWeightLift']):
        try_ex(lambda: session_attributes.pop('chainRecordWeightLift'))
        return confirm_intent(
            session_attributes,
            'RecordWeightlift',
            {
                'Exercise': exercise_name,
                'Weight': None,
                'Reps': None,
                'Sets': None
            },
            {
                'contentType': 'PlainText',
                'content': 'Got it! {} has been added to your exercises. Would you like to finish inputting your '
                           'workout?'.format(exercise_name)
            }
        )
    elif try_ex(lambda: session_attributes['chainCreateWorkout']):
        try_ex(lambda: session_attributes.pop('chainCreateWorkout'))
        return confirm_intent(
            session_attributes,
            'CreateWorkout',
            {
                'Monday': session_attributes['Monday'],
                'Tuesday': session_attributes['Tuesday'],
                'Wednesday': session_attributes['Wednesday'],
                'Thursday': session_attributes['Thursday'],
                'Friday': session_attributes['Friday'],
                'Saturday': session_attributes['Saturday'],
                'Sunday': session_attributes['Sunday']
            },
            {
                'contentType': 'PlainText',
                'content': 'Got it! {} has been added to your exercises. Would you like to finish creating your '
                           'workout schedule?'.format(exercise_name)
            }
        )
    else:
        return close(intent_request['sessionAttributes'],
                     'Fulfilled',
                     {'contentType': 'PlainText',
                      'content': 'Got it! {} has been added to your exercises'.format(exercise_name)})


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
