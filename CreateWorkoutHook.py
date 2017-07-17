import boto3
import time
import os
import logging

dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
users = dynamodb.Table('Users')
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
                "exerciseLog": {}
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


def generate_exercise_array(workout):
    if workout is not None:
        return workout.split(', ')
    return workout


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


def validate_create_workout(monday, tuesday, wednesday, thursday, friday, saturday, sunday, intent_request):
    if monday is not None:
        for exercise in monday:
            if not is_valid_exercise(exercise, intent_request):
                return build_validation_result(False, 'Monday',
                                               '{} is not recognized as one of your exercises. Would '
                                               'you like to add it?'.format(exercise))
    if tuesday is not None:
        for exercise in tuesday:
            if not is_valid_exercise(exercise, intent_request):
                return build_validation_result(False, 'Tuesday',
                                               '{} is not recognized as one of your exercises. Would '
                                               'you like to add it?'.format(exercise))
    if wednesday is not None:
        for exercise in wednesday:
            if not is_valid_exercise(exercise, intent_request):
                return build_validation_result(False, 'Wednesday',
                                               '{} is not recognized as one of your exercises. Would '
                                               'you like to add it?'.format(exercise))
    if thursday is not None:
        for exercise in thursday:
            if not is_valid_exercise(exercise, intent_request):
                return build_validation_result(False, 'Thursday',
                                               '{} is not recognized as one of your exercises. Would '
                                               'you like to add it?'.format(exercise))
    if friday is not None:
        for exercise in friday:
            if not is_valid_exercise(exercise, intent_request):
                return build_validation_result(False, 'Friday',
                                               '{} is not recognized as one of your exercises. Would '
                                               'you like to add it?'.format(exercise))
    if saturday is not None:
        for exercise in saturday:
            if not is_valid_exercise(exercise, intent_request):
                return build_validation_result(False, 'Saturday',
                                               '{} is not recognized as one of your exercises. Would '
                                               'you like to add it?'.format(exercise))
    if sunday is not None:
        for exercise in sunday:
            if not is_valid_exercise(exercise, intent_request):
                return build_validation_result(False, 'Sunday',
                                               '{} is not recognized as one of your exercises. Would '
                                               'you like to add it?'.format(exercise))
    return build_validation_result(True, None, None)


""" --- Functions that control the bot's behavior --- """


def create_workout(intent_request):
    monday = generate_exercise_array(get_slots(intent_request)["Monday"])
    tuesday = generate_exercise_array(get_slots(intent_request)["Tuesday"])
    wednesday = generate_exercise_array(get_slots(intent_request)["Wednesday"])
    thursday = generate_exercise_array(get_slots(intent_request)["Thursday"])
    friday = generate_exercise_array(get_slots(intent_request)["Friday"])
    saturday = generate_exercise_array(get_slots(intent_request)["Saturday"])
    sunday = generate_exercise_array(get_slots(intent_request)["Sunday"])
    workout_routine = [monday, tuesday, wednesday, thursday, friday, saturday, sunday]
    user = get_user(intent_request)
    source = intent_request['invocationSource']
    confirmation_status = intent_request['currentIntent']['confirmationStatus']
    session_attributes = intent_request['sessionAttributes'] if intent_request['sessionAttributes'] is not None else {}
    if source == 'DialogCodeHook':
        # Perform basic validation on the supplied input slots.
        # Use the elicitSlot dialog action to re-prompt for the first violation detected.
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
        validation_result = validate_create_workout(monday, tuesday, wednesday, thursday, friday, saturday, sunday,
                                                    intent_request)
        if not validation_result['isValid']:
            # slots[validation_result['violatedSlot']] = None
            for weekday in workout_routine:
                if weekday is not None:
                    for exercise in weekday:
                        if not is_valid_exercise(exercise, intent_request):
                            session_attributes['chainCreateWorkout'] = True
                            session_attributes['Monday'] = get_slots(intent_request)["Monday"]
                            session_attributes['Tuesday'] = get_slots(intent_request)["Tuesday"]
                            session_attributes['Wednesday'] = get_slots(intent_request)["Wednesday"]
                            session_attributes['Thursday'] = get_slots(intent_request)["Thursday"]
                            session_attributes['Friday'] = get_slots(intent_request)["Friday"]
                            session_attributes['Saturday'] = get_slots(intent_request)["Saturday"]
                            session_attributes['Sunday'] = get_slots(intent_request)["Sunday"]
                            return confirm_intent(
                                session_attributes,
                                'CreateExercise',
                                {
                                    'Exercise': exercise,
                                    'MuscleGroup': None
                                },
                                {
                                    'contentType': 'PlainText',
                                    'content': '{} is not recognized as one of your exercises. Would '
                                               'you like to add it?'.format(exercise)

                                }
                            )
            return elicit_slot(intent_request['sessionAttributes'],
                               intent_request['currentIntent']['name'],
                               slots,
                               validation_result['violatedSlot'],
                               validation_result['message'])

        return delegate(session_attributes, get_slots(intent_request))

    try_ex(lambda: session_attributes.pop('Monday'))
    try_ex(lambda: session_attributes.pop('Tuesday'))
    try_ex(lambda: session_attributes.pop('Wednesday'))
    try_ex(lambda: session_attributes.pop('Thursday'))
    try_ex(lambda: session_attributes.pop('Friday'))
    try_ex(lambda: session_attributes.pop('Saturday'))
    try_ex(lambda: session_attributes.pop('Sunday'))
    if time.strftime('%A') == 'Monday':
        todays_workout = monday
    elif time.strftime('%A') == 'Tuesday':
        todays_workout = tuesday
    elif time.strftime('%A') == 'Wednesday':
        todays_workout = wednesday
    elif time.strftime('%A') == 'Thursday':
        todays_workout = thursday
    elif time.strftime('%A') == 'Friday':
        todays_workout = friday
    elif time.strftime('%A') == 'Saturday':
        todays_workout = saturday
    else:
        todays_workout = sunday
    users.update_item(
        Key={
            'user': intent_request['userId']
        },
        UpdateExpression="set workoutSchedule = :w, dailyNutrientsAndWorkouts.#day.exercisesRemaining = :e",
        ExpressionAttributeValues={
            ':w': {
                'Monday': monday,
                'Tuesday': tuesday,
                'Wednesday': wednesday,
                'Thursday': thursday,
                'Friday': friday,
                'Saturday': saturday,
                'Sunday': sunday
            },
            ':e': todays_workout
        },
    )

    return close(intent_request['sessionAttributes'],
                 'Fulfilled',
                 {'contentType': 'PlainText',
                  'content': 'Okay, your workout schedule has been updated!'})


""" --- Intents --- """


def dispatch(intent_request):
    """
    Called when the user specifies an intent for this bot.
    """

    logger.debug(
        'dispatch userId={}, intentName={}'.format(intent_request['userId'], intent_request['currentIntent']['name']))

    intent_name = intent_request['currentIntent']['name']

    # Dispatch to your bot's intent handlers
    if intent_name == 'CreateWorkout':
        return create_workout(intent_request)

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
