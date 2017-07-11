import boto3
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
    valid_genders = ['male', 'female']
    return gender.lower() in valid_genders


def isvalid_measurement_system(measurementsystem):
    valid_measurementsystems = ['imperial system', 'metric system']
    return measurementsystem.lower() in valid_measurementsystems


def isvalid_goal(goal):
    valid_goal = ['gain mass', 'lose weight', 'maintain weight']
    return goal.lower() in valid_goal


def get_activity_multiplier(activity):
    if activity == 'sedentary':
        return 1.2
    elif activity == 'moderate':
        return 1.375
    else:
        return 1.725


def get_goal_multiplier(goal):
    if goal == 'gain mass':
        return 1.2
    elif goal == 'lose weight':
        return 0.8
    else:
        return 1


def get_rmr(gender, measurementsystem, weight, height, age):
    # calculated based on the mifflin-st jeor formula

    if gender.lower() == "male":
        if measurementsystem == 'imperial system':
            return int(10 * (int(weight) / 2.2) + 6.25 * (int(height) * 2.54) - 5 * int(age) + 5)
        elif measurementsystem == 'metric system':
            return int(10 * int(weight) + 6.25 * int(height) - 5 * int(age) + 5)
    elif gender.lower() == 'female':
        if measurementsystem == 'imperial system':
            return int(10 * (int(weight) / 2.2) + 6.25 * (int(height) * 2.54) - 5 * int(age) - 161)
        elif measurementsystem == 'metric system':
            return int(10 * int(weight) + 6.25 * int(height) - 5 * int(age) - 161)


def calculate_calories(gender, measurementsystem, weight, height, age, goal, activity):
    # rmr is resting metabolic rate
    # maintenance is rmr * 1.2
    return int(get_rmr(gender, measurementsystem, weight, height, age) * get_activity_multiplier(
        activity) * get_goal_multiplier(goal))


def calculate_macronutrient(goal, calories):
    # 30 40 30 ratio between protein carbohydrate and fat
    if goal == 'lose weight':
        return {'protein': int(.3 * calories / 4), 'carbohydrate': int(.4 * calories / 4),
                'fat': int(.3 * calories / 9)}
    elif goal == 'gain mass':
        return {'protein': int(.3 * calories / 4), 'carbohydrate': int(.5 * calories / 4),
                'fat': int(.2 * calories / 9)}
    else:
        return {'protein': int(.3 * calories / 4), 'carbohydrate': int(.4 * calories / 4),
                'fat': int(.3 * calories / 9)}


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


def validate_personalize(name, gender, age, measurementsystem, height, weight, goal, activity, source):
    if gender is not None:
        if not isvalid_gender(gender):
            return build_validation_result(False, 'Gender', 'Sorry, can you repeat what gender you are?')
    if measurementsystem is not None:
        if not isvalid_measurement_system(measurementsystem):
            return build_validation_result(False, 'MeasurementSystem',
                                           'Sorry, can you repeat which measurement system you prefer?')
    if goal is not None:
        if not isvalid_goal(goal):
            return build_validation_result(False, 'Goal', 'Sorry, can you repeat what your goal is?')
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
    activity = get_slots(intent_request)["Activity"]
    source = intent_request['invocationSource']

    if source == 'DialogCodeHook':
        # Perform basic validation on the supplied input slots.
        # Use the elicitSlot dialog action to re-prompt for the first violation detected.
        slots = get_slots(intent_request)

        validation_result = validate_personalize(name, gender, age, measurementsystem, height, weight, goal, activity,
                                                 source)
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
    calorie_goal = calculate_calories(gender, measurementsystem, weight, height, age, goal, activity)
    macronutrients = calculate_macronutrient(goal, calorie_goal)
    protein_goal = macronutrients['protein']
    carbohydrate_goal = macronutrients['carbohydrate']
    fat_goal = macronutrients['fat']
    table.put_item(
        Item={
            "user": intent_request['userId'],
            "name": name,
            "gender": gender,
            "age": age,
            "measurementSystem": measurementsystem,
            "height": height,
            "weight": weight,
            "goal": goal,
            "activity": activity,
            "calorieGoal": calorie_goal,
            "proteinGoal": protein_goal,
            "carbohydrateGoal": carbohydrate_goal,
            "fatGoal": fat_goal,
            "dailyNutrientsRemaining": {
                time.strftime("%m/%d/%Y"): {
                    "calorieRemaining": calorie_goal,
                    "proteinRemaining": protein_goal,
                    "carbohydrateRemaining": carbohydrate_goal,
                    "fatRemaining": fat_goal
                }
            }
        }
    )
    return close(intent_request['sessionAttributes'],
                 'Fulfilled',
                 {'contentType': 'PlainText',
                  'content': 'Nice to meet you, {}! Your daily target calorie goal is {}, '
                             'your protein goal is {}g, your carbohydrate goal is {}g, and your fat goal is {}g. If '
                             'you want to set your own goals, just type \'I would like to set my own goals\'. If you '
                             'ever need help with any commands, just enter "help"'.format(name, calorie_goal,
                                                                                          protein_goal,
                                                                                          carbohydrate_goal,
                                                                                          fat_goal)})


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
