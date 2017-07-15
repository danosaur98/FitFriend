import boto3
import time
import os
import logging

dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
food_log = dynamodb.Table('FoodLog')
foods = dynamodb.Table('Foods')
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


def find_violations(remaining_nutrition, user):
    violations = []
    for nutrient, amount in remaining_nutrition.items():
        if nutrient == 'calorie':
            if amount < 0:
                violations.append(nutrient)
        else:
            if amount < -int(0.1 * int(user['Item']['nutrientGoal'][nutrient])):
                violations.append(nutrient)
    return violations


def generate_violation_message(remaining_nutrition, user):
    violations = find_violations(remaining_nutrition, user)
    if len(violations) == 0:
        return ""
    elif len(violations) == 1:
        if violations[0] == 'calorie':
            return "You're going over your " + violations[0] + " limit!"
        else:
            return "You're going over 10% of your " + violations[0] + " limit!"
    elif len(violations) == 2:
        if violations[0] == 'calorie':
            return "You're going over your " + violations[0] + " limit and over 10% of your " + violations[1] + " limit!"
        else:
            return "You're going over 10% of your " + violations[0] + " and " + violations[1] + " limits!"
    elif len(violations) == 3:
        if violations[0] == 'calorie':
            return "You're going over your " + violations[0] + " limit and over 10% of your " + violations[1] + " and " + \
                   violations[2] + " limits!"
        else:
            return "You're going over 10% of your " + violations[0] + ", " + violations[1] + " and " + violations[
                2] + " limits!"
    elif len(violations) == 4:
        return "You're going over your " + violations[0] + " limit and over 10% of your " + violations[1] + ", " + \
               violations[2] + " and " + violations[3] + " limits!"


def generate_violation_string(violation):
    str = ""
    for word in violation:
        str += word + " "
    return str


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
                "dailyNutrientsAndWorkouts": {
                    time.strftime("%m/%d/%Y"): {
                        "nutritionRemaining": {
                            'calorie': user['Item']['calorieGoal'],
                            'protein': user['Item']['proteinGoal'],
                            'carbohydrate': user['Item']['carbohydrateGoal'],
                            'fat': user['Item']['fatGoal']
                        },
                        "exercisesRemaining": user['Item']['workout'][time.strftime('%A')],
                        "violations": [],
                        "isExcused": None,
                    }
                },
            }
        },
        ExpressionAttributeNames={
            '#day': time.strftime("%m/%d/%Y"),
        },
    )


def get_previous_violations(user):
    latest_day = sorted(list(user['Item']['dailyNutritionAndWorkouts'].keys()))[-1]
    return user['Item']['dailyNutritionAndWorkouts'][latest_day]['violations']


def condense_measurement_type(measurement_type):
    if measurement_type is not None:
        if measurement_type.lower() in ['grams', 'gram', 'g']:
            return 'grams'
        elif measurement_type.lower() in ['servings', 'serving']:
            return 'servings'


def calculate_nutrition(food_name, measurement, measurement_type, intent_request):
    food_information = foods.get_item(
        Key={
            'UserID': intent_request['userId'],
            'FoodName': food_name.lower()
        }
    )
    calorie, protein, carbohydrate, fat = None, None, None, None
    if measurement_type == 'servings':
        calorie = int(measurement) * int(food_information['Item']['Calorie'])
        protein = int(measurement) * int(food_information['Item']['Protein'])
        carbohydrate = int(measurement) * int(food_information['Item']['Carbohydrate'])
        fat = int(measurement) * int(food_information['Item']['Fat'])
    elif measurement_type == 'grams':
        serving = int(measurement) / int(food_information['Item']['Serving'])
        calorie = serving * int(food_information['Item']['Calorie'])
        protein = serving * int(food_information['Item']['Protein'])
        carbohydrate = serving * int(food_information['Item']['Carbohydrate'])
        fat = serving * int(food_information['Item']['Fat'])
    return {'calorie': int(calorie), 'protein': int(protein), 'carbohydrate': int(carbohydrate), 'fat': int(fat)}


def get_remaining_nutrition(food_nutrition, intent_request):
    user = users.get_item(
        Key={
            'user': intent_request['userId'],
        }
    )
    today = time.strftime("%m/%d/%Y")
    calorie = user['Item']['dailyNutrientsAndWorkouts'][today]['nutritionRemaining']['calorie'] - food_nutrition[
        'calorie']
    protein = user['Item']['dailyNutrientsAndWorkouts'][today]['nutritionRemaining']['protein'] - food_nutrition[
        'protein']
    carbohydrate = user['Item']['dailyNutrientsAndWorkouts'][today]['nutritionRemaining']['carbohydrate'] - \
                   food_nutrition['carbohydrate']
    fat = user['Item']['dailyNutrientsAndWorkouts'][today]['nutritionRemaining']['fat'] - food_nutrition['fat']
    return {'calorie': int(calorie), 'protein': int(protein), 'carbohydrate': int(carbohydrate), 'fat': int(fat)}


def is_valid_food(food_name, intent_request):
    response = foods.get_item(
        Key={
            'UserID': 'universal',
            'FoodName': food_name.lower()
        }
    )
    if 'Item' in response:
        return True
    else:
        response = foods.get_item(
            Key={
                'UserID': intent_request['userId'],
                'FoodName': food_name.lower()
            }
        )
        if 'Item' in response:
            return True
    return False


def is_valid_measurement_type(measurement_type):
    valid_measurement_types = ['grams', 'gram', 'g', 'servings', 'serving']
    return measurement_type.lower() in valid_measurement_types


def validate_record_meal(food_name, measurement, measurement_type, intent_request):
    if food_name is not None:
        if not is_valid_food(food_name, intent_request):
            return build_validation_result(False, 'FoodName', '{} is not recognized as one of your foods. Would '
                                                              'you like to add it?'.format(food_name))
    if measurement_type is not None:
        if not is_valid_measurement_type(measurement_type):
            return build_validation_result(False, 'MeasurementType', 'Sorry, was that in servings or grams?')
    return build_validation_result(True, None, None)


""" --- Functions that control the bot's behavior --- """


def record_meal(intent_request):
    food_name = get_slots(intent_request)["FoodName"]
    measurement = get_slots(intent_request)["Measurement"]
    measurement_type = condense_measurement_type(get_slots(intent_request)["MeasurementType"])
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
            if not len(get_previous_violations(user)) == 0:
                return confirm_intent(
                    session_attributes,
                    "GiveExcuse",
                    {
                        'Excuse': None,
                        'Violation': generate_violation_string(get_previous_violations(user))
                    },
                    {
                        'contentType': 'PlainText',
                        'content': 'Do you have a valid excuse for why you went over your limits?'
                    }
                )
        slots = get_slots(intent_request)
        validation_result = validate_record_meal(food_name, measurement, measurement_type, intent_request)
        if not validation_result['isValid']:
            slots[validation_result['violatedSlot']] = None
            if not is_valid_food(food_name, intent_request):
                return confirm_intent(
                    session_attributes,
                    'CreateFood',
                    {
                        'FoodName': food_name,
                        'Serving': None,
                        'Calorie': None,
                        'Protein': None,
                        'Carbohydrate': None,
                        'Fat': None
                    },
                    {
                        'contentType': 'PlainText',
                        'content': '{} is not recognized as one of your foods. Would '
                                   'you like to add it?'.format(food_name)

                    }
                )
            return elicit_slot(intent_request['sessionAttributes'],
                               intent_request['currentIntent']['name'],
                               slots,
                               validation_result['violatedSlot'],
                               validation_result['message'])
        if food_name and measurement and measurement_type is not None:
            food_nutrition = calculate_nutrition(food_name, measurement, measurement_type, intent_request)
            remaining_nutrition = get_remaining_nutrition(food_nutrition, intent_request)
            session_attributes['foodCalorie'] = food_nutrition['calorie']
            session_attributes['foodProtein'] = food_nutrition['protein']
            session_attributes['foodCarbohydrate'] = food_nutrition['carbohydrate']
            session_attributes['foodFat'] = food_nutrition['fat']
            session_attributes['calorieRemaining'] = remaining_nutrition['calorie']
            session_attributes['proteinRemaining'] = remaining_nutrition['protein']
            session_attributes['carbohydrateRemaining'] = remaining_nutrition['carbohydrate']
            session_attributes['fatRemaining'] = remaining_nutrition['fat']
            session_attributes['violationWarning'] = generate_violation_message(remaining_nutrition, user)
        else:
            try_ex(lambda: session_attributes.pop('foodCalorie'))
            try_ex(lambda: session_attributes.pop('foodProtein'))
            try_ex(lambda: session_attributes.pop('foodCarbohydrate'))
            try_ex(lambda: session_attributes.pop('foodFat'))
            try_ex(lambda: session_attributes.pop('calorieRemaining'))
            try_ex(lambda: session_attributes.pop('proteinRemaining'))
            try_ex(lambda: session_attributes.pop('carbohydrateRemaining'))
            try_ex(lambda: session_attributes.pop('fatRemaining'))
            try_ex(lambda: session_attributes.pop('violationWarning'))

        return delegate(session_attributes, get_slots(intent_request))
    food_nutrition = calculate_nutrition(food_name, measurement, measurement_type, intent_request)
    remaining_nutrition = get_remaining_nutrition(food_nutrition, intent_request)
    food_log.put_item(
        Item={
            "UserID": intent_request['userId'],
            "Date": time.strftime("%m/%d/%Y %T"),
            "FoodName": food_name,
            "Measurement": measurement,
            "MeasurementType": measurement_type,
            "FoodNutrition": food_nutrition,
            "NutritionRemaining": remaining_nutrition
        }
    )
    users.update_item(
        Key={
            'user': intent_request['userId']
        },
        UpdateExpression="set dailyNutrientsAndWorkouts.#day = :d",
        ExpressionAttributeValues={
            ':d': {
                "nutritionRemaining": remaining_nutrition
            }
        },
        ExpressionAttributeNames={
            '#day': time.strftime("%m/%d/%Y"),
        },
    )
    violations = find_violations(remaining_nutrition, user)
    if len(violations) != 0:
        return confirm_intent(
            session_attributes,
            "GiveExcuse",
            {
                'Excuse': None,
                'Violation': generate_violation_string(violations)
            },
            {
                'contentType': 'PlainText',
                'content': 'Do you have a valid excuse for why you went over your limits?'
            }
        )
    else:
        return close(intent_request['sessionAttributes'],
                     'Fulfilled',
                     {
                         'contentType': 'PlainText',
                         'content': "Sounds yummy! :)"
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
    if intent_name == 'RecordMeal':
        return record_meal(intent_request)

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
