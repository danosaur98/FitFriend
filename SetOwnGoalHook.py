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
    if not time.strftime("%m/%d/%Y") in user['Item']['dailyNutrientsAndWorkouts']:
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

            },

        },
        ExpressionAttributeNames={
            '#day': time.strftime("%m/%d/%Y"),
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


def validate_set_own_goal(calorie_goal, protein_goal, fat_goal, carbohydrate_goal):
    return build_validation_result(True, None, None)


""" --- Functions that control the bot's behavior --- """


def set_own_goal(intent_request):
    calorie_goal = get_slots(intent_request)["CalorieGoal"]
    protein_goal = get_slots(intent_request)["ProteinGoal"]
    carbohydrate_goal = get_slots(intent_request)["CarbohydrateGoal"]
    fat_goal = get_slots(intent_request)["FatGoal"]
    user = get_user(intent_request)
    source = intent_request['invocationSource']
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

        validation_result = validate_set_own_goal(calorie_goal, protein_goal, carbohydrate_goal, fat_goal)
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
    users.update_item(
        Key={
            'user': intent_request['userId']
        },
        UpdateExpression="set calorieGoal = :cal, proteinGoal=:p, carbohydrateGoal=:car, fatGoal=:f",
        ExpressionAttributeValues={
            ':cal': calorie_goal,
            ':p': protein_goal,
            ':car': carbohydrate_goal,
            ':f': fat_goal
        }
    )
    return close(intent_request['sessionAttributes'],
                 'Fulfilled',
                 {'contentType': 'PlainText',
                  'content': 'Okay, your calorie goal has been set to {}, your protein goal has been set to {}, '
                             'your carbohydrate goal has been set to {}, and your fat goal has been set to {}'.format(
                      calorie_goal, protein_goal, fat_goal, carbohydrate_goal)})


""" --- Intents --- """


def dispatch(intent_request):
    """
    Called when the user specifies an intent for this bot.
    """

    logger.debug(
        'dispatch userId={}, intentName={}'.format(intent_request['userId'], intent_request['currentIntent']['name']))

    intent_name = intent_request['currentIntent']['name']

    # Dispatch to your bot's intent handlers
    if intent_name == 'SetOwnGoal':
        return set_own_goal(intent_request)

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
